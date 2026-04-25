"""KDE Connect skill — interact with paired Android/iOS devices via kdeconnect-cli."""
from __future__ import annotations

import subprocess

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_list_devices",
            "description": "List all paired KDE Connect devices and their reachability.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_battery",
            "description": "Get the battery level of a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID (leave empty for first reachable device)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_ping",
            "description": "Send a ping notification to a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "message": {"type": "string", "description": "Optional ping message."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_ring",
            "description": "Ring a paired phone to help find it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_send_sms",
            "description": "Send an SMS via a paired Android phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "number": {"type": "string", "description": "Phone number to send SMS to."},
                    "message": {"type": "string", "description": "SMS text."},
                },
                "required": ["number", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_share_file",
            "description": "Share a local file to a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "path": {"type": "string", "description": "Absolute path to the file to share."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_share_url",
            "description": "Open a URL on a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "url": {"type": "string", "description": "URL to open on the device."},
                },
                "required": ["url"],
            },
        },
    },
]


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(err or out or f"exit {result.returncode}")
    return out or "(done)"


def _resolve_device(hint: str) -> str:
    """Return a device ID matching the hint, or the first reachable device."""
    raw = subprocess.run(
        ["kdeconnect-cli", "--list-available", "--id-only"],
        capture_output=True, text=True, timeout=5, check=False,
    ).stdout.strip()
    ids = [line.strip() for line in raw.splitlines() if line.strip()]
    if not ids:
        # Fall back to all devices
        raw = subprocess.run(
            ["kdeconnect-cli", "--list-devices", "--id-only"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
        ids = [line.strip() for line in raw.splitlines() if line.strip()]
    if not ids:
        raise RuntimeError("No KDE Connect devices found.")
    if not hint:
        return ids[0]
    hint_lower = hint.strip().lower()
    for dev_id in ids:
        if hint_lower in dev_id.lower():
            return dev_id
    # Try matching by name
    for dev_id in ids:
        name_raw = subprocess.run(
            ["kdeconnect-cli", "--device", dev_id, "--name"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
        if hint_lower in name_raw.lower():
            return dev_id
    return ids[0]


def dispatch(name: str, args: dict) -> str:
    try:
        if name == "kdeconnect_list_devices":
            return _run(["kdeconnect-cli", "--list-devices"])

        device_hint = str(args.get("device") or "").strip()

        if name == "kdeconnect_battery":
            dev = _resolve_device(device_hint)
            return _run(["kdeconnect-cli", "--device", dev, "--battery"])

        if name == "kdeconnect_ping":
            dev = _resolve_device(device_hint)
            msg = str(args.get("message") or "Ping from Hanauta AI").strip()
            return _run(["kdeconnect-cli", "--device", dev, "--ping-msg", msg])

        if name == "kdeconnect_ring":
            dev = _resolve_device(device_hint)
            return _run(["kdeconnect-cli", "--device", dev, "--ring"])

        if name == "kdeconnect_send_sms":
            dev = _resolve_device(device_hint)
            number = str(args["number"]).strip()
            message = str(args["message"]).strip()
            return _run(["kdeconnect-cli", "--device", dev, "--send-sms", message, "--destination", number])

        if name == "kdeconnect_share_file":
            from pathlib import Path
            dev = _resolve_device(device_hint)
            path = Path(str(args["path"]).strip()).expanduser()
            if not path.exists():
                return f"File not found: {path}"
            return _run(["kdeconnect-cli", "--device", dev, "--share", str(path)])

        if name == "kdeconnect_share_url":
            dev = _resolve_device(device_hint)
            url = str(args["url"]).strip()
            return _run(["kdeconnect-cli", "--device", dev, "--share", url])

    except FileNotFoundError:
        return "[kdeconnect] kdeconnect-cli not found. Install kdeconnect."
    except Exception as exc:
        return f"[kdeconnect] {exc}"

    return f"[kdeconnect] unknown tool: {name}"
