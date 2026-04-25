"""Hanauta Desktop skill — control the i3 desktop via i3-msg and hanauta helpers."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "desktop_list_workspaces",
            "description": "List all i3 workspaces with their names and focus state.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_switch_workspace",
            "description": "Switch to an i3 workspace by number or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace": {"type": "string", "description": "Workspace number or name, e.g. '2' or 'music'."}
                },
                "required": ["workspace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_list_windows",
            "description": "List all open windows (title, workspace, app class).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_focus_window",
            "description": "Focus a window by its title substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Substring of the window title to match."}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_set_wallpaper",
            "description": "Set the desktop wallpaper to a given image file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the image file."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_send_notification",
            "description": "Send a desktop notification with a title and body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_run_command",
            "description": "Run a shell command on the desktop (non-interactive, output captured). Use for safe read-only commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "desktop_lock_screen",
            "description": "Lock the screen immediately.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _i3msg(payload: str) -> str:
    result = subprocess.run(
        ["i3-msg", payload], capture_output=True, text=True, timeout=5, check=False
    )
    return (result.stdout or result.stderr or "").strip()


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(err or out or f"exit {result.returncode}")
    return out or "(done)"


def dispatch(name: str, args: dict) -> str:
    if name == "desktop_list_workspaces":
        raw = subprocess.run(
            ["i3-msg", "-t", "get_workspaces"], capture_output=True, text=True, timeout=5
        ).stdout
        try:
            workspaces = json.loads(raw)
            lines = [
                f"{'*' if ws.get('focused') else ' '} {ws.get('num', '?')}: {ws.get('name', '?')} "
                f"({'visible' if ws.get('visible') else 'hidden'})"
                for ws in workspaces
            ]
            return "\n".join(lines) or "No workspaces found."
        except Exception:
            return raw.strip() or "Could not parse workspaces."

    if name == "desktop_switch_workspace":
        ws = str(args["workspace"]).strip()
        return _i3msg(f"workspace {ws}")

    if name == "desktop_list_windows":
        raw = subprocess.run(
            ["i3-msg", "-t", "get_tree"], capture_output=True, text=True, timeout=5
        ).stdout
        try:
            tree = json.loads(raw)
        except Exception:
            return "Could not parse window tree."

        windows: list[str] = []

        def _walk(node: dict, ws_name: str = "") -> None:
            if node.get("type") == "workspace":
                ws_name = node.get("name", ws_name)
            if node.get("window") and node.get("name"):
                app = (node.get("window_properties") or {}).get("class", "")
                windows.append(f"[{ws_name}] {node['name']}" + (f" ({app})" if app else ""))
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                _walk(child, ws_name)

        _walk(tree)
        return "\n".join(windows) or "No windows found."

    if name == "desktop_focus_window":
        title = str(args["title"]).strip().replace('"', '\\"')
        return _i3msg(f'[title="{title}"] focus')

    if name == "desktop_set_wallpaper":
        path = Path(str(args["path"]).strip()).expanduser()
        if not path.exists():
            return f"File not found: {path}"
        for cmd in [
            ["feh", "--bg-fill", str(path)],
            ["nitrogen", "--set-zoom-fill", str(path)],
        ]:
            try:
                return _run(cmd)
            except (FileNotFoundError, RuntimeError):
                continue
        return "No wallpaper setter found (install feh or nitrogen)."

    if name == "desktop_send_notification":
        subprocess.Popen(
            ["notify-send", "-a", "Hanauta AI", str(args.get("title", "")), str(args.get("body", ""))],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return "Notification sent."

    if name == "desktop_run_command":
        cmd_str = str(args["command"]).strip()
        result = subprocess.run(
            cmd_str, shell=True, capture_output=True, text=True, timeout=15, check=False
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        return out or err or f"(exit {result.returncode})"

    if name == "desktop_lock_screen":
        for locker in ["loginctl lock-session", "i3lock", "xdg-screensaver lock"]:
            try:
                subprocess.Popen(locker.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "Screen locked."
            except FileNotFoundError:
                continue
        return "No screen locker found."

    return f"[desktop] unknown tool: {name}"
