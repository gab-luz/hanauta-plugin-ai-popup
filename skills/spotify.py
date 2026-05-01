"""Spotify skill — control Spotify playback via playerctl or spicetify.

Requires either:
- playerctl (MPRIS) - works with Spotify when running
- spicetify CLI - installed if using Spicetify

Settings in skills_settings.json under "spotify":
    {
        "spotify": {
            "enabled": true,
            "use_spicetify": true
        }
    }
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "spotify_now_playing",
            "description": "Show what's currently playing on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_play",
            "description": "Start playback on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_pause",
            "description": "Pause playback on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_play_pause",
            "description": "Toggle play/pause on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_next",
            "description": "Skip to the next track on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_previous",
            "description": "Skip to the previous track on Spotify.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_volume",
            "description": "Get or set Spotify volume (0.0-1.0).",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "number", "description": "Volume level 0.0-1.0, or empty to just get current volume."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_seek",
            "description": "Seek to a position in the current track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position": {"type": "number", "description": "Position in seconds."},
                },
                "required": ["position"],
            },
        },
    },
]


def _load_settings() -> dict:
    try:
        import json
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("spotify", {})
    except Exception:
        return {}


def _run_playerctl(args: list[str], timeout: int = 10) -> str:
    cmd = ["playerctl", "-p", "spotify"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _run_spicetify(args: list[str], timeout: int = 10) -> str:
    cmd = ["spicetify"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _get_status() -> tuple[str, str, str, str]:
    status = _run_playerctl(["status"])
    if not status:
        return "stopped", "", "", ""
    meta = _run_playerctl(["metadata", "--format", "{{title}}|{{artist}}|{{album}}"])
    parts = meta.split("|")
    title = parts[0] if len(parts) > 0 else "?"
    artist = parts[1] if len(parts) > 1 else "?"
    album = parts[2] if len(parts) > 2 else "?"
    return status.strip(), title, artist, album


def dispatch(name: str, args: dict) -> str:
    cfg = _load_settings()
    if not bool(cfg.get("enabled", True)):
        return "[spotify] Skill is disabled in settings."

    try:
        if name == "spotify_now_playing":
            status, title, artist, album = _get_status()
            if status == "stopped":
                return "Nothing playing on Spotify."
            if status == "Paused":
                return f"Paused: {title} — {artist} ({album})"
            return f"▶ {title} — {artist} ({album})"

        if name == "spotify_play":
            result = _run_playerctl(["play"])
            if not result:
                return "Failed to play. Is Spotify running?"
            return "Playing."

        if name == "spotify_pause":
            result = _run_playerctl(["pause"])
            if not result:
                return "Failed to pause."
            return "Paused."

        if name == "spotify_play_pause":
            result = _run_playerctl(["play-pause"])
            if not result:
                return "Failed. Is Spotify running?"
            status = _run_playerctl(["status"])
            if status == "Playing":
                return "Now playing."
            return "Paused."

        if name == "spotify_next":
            result = _run_playerctl(["next"])
            if not result:
                return "Failed. Is Spotify running?"
            status, title, artist, album = _get_status()
            return f"Skipped to: {title} — {artist}"

        if name == "spotify_previous":
            result = _run_playerctl(["previous"])
            if not result:
                return "Failed. Is Spotify running?"
            status, title, artist, album = _get_status()
            return f"Previous: {title} — {artist}"

        if name == "spotify_volume":
            level = args.get("level")
            if level is None:
                vol = _run_playerctl(["volume"])
                return f"Volume: {vol}"
            vol = float(level)
            vol = max(0.0, min(1.0, vol))
            _run_playerctl([f"volume", str(vol)])
            return f"Volume set to {vol:.0%}"

        if name == "spotify_seek":
            pos = int(args.get("position", 0))
            result = _run_playerctl(["position", str(pos)])
            if not result:
                return "Failed to seek."
            return f"Seeked to {pos}s."

    except Exception as e:
        return f"[spotify] {e}"

    return f"[spotify] unknown tool: {name}"