"""Reminders skill — manage timed reminders via hanauta-plugin-reminders.

This skill interfaces with the reminder queue daemon to schedule and list reminders.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

_REMINDER_QUEUE_PATH = Path("/home/gabi/dev/hanauta-plugin-reminders")
_QUEUE_FILE = Path.home() / ".local" / "state" / "hanauta" / "service" / "reminders_queue.json"
_DAEMON_PID_FILE = Path.home() / ".local" / "state" / "hanauta" / "service" / "reminder-daemon.pid"

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "reminders_add",
            "description": (
                "Add a new reminder that will fire after a specified delay or at a specific time. "
                "The reminder will trigger a fullscreen alert when due."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Reminder title."},
                    "body": {"type": "string", "description": "Reminder body text."},
                    "delay_seconds": {"type": "integer", "description": "Delay in seconds from now (e.g., 300 for 5 min, 3600 for 1 hour). Mutually exclusive with delay_minutes."},
                    "delay_minutes": {"type": "integer", "description": "Delay in minutes from now (e.g., 5 for 5 min, 60 for 1 hour). Mutually exclusive with delay_seconds."},
                    "severity": {"type": "string", "description": "Alert severity: 'discrete' (default), 'info', 'warning', 'critical'."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_list",
            "description": "List all pending reminders in the queue.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_cancel",
            "description": "Cancel a reminder by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "The reminder ID to cancel."}
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_clear",
            "description": "Clear all pending reminders.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_status",
            "description": "Check if the reminder daemon is running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_start_daemon",
            "description": "Start the reminder background daemon if not already running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("reminders", {})
    except Exception:
        return {}


def _load_queue() -> list[dict]:
    try:
        if _QUEUE_FILE.exists():
            payload = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
    except Exception:
        pass
    return []


def _save_queue(entries: list[dict]) -> None:
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUEUE_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _daemon_is_running() -> bool:
    try:
        if _DAEMON_PID_FILE.exists():
            pid = int(_DAEMON_PID_FILE.read_text(encoding="utf-8").strip())
            import os
            os.kill(pid, 0)
            return True
    except Exception:
        pass
    return False


def _start_daemon() -> bool:
    if _daemon_is_running():
        return True
    try:
        daemon_script = _REMINDER_QUEUE_PATH / "reminder_daemon.py"
        if daemon_script.exists():
            subprocess.Popen(
                [sys.executable, str(daemon_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
    except Exception:
        pass
    return False


def _fmt_reminder(entry: dict, idx: int = 0) -> str:
    rid = entry.get("id", "")[:8]
    title = entry.get("title", "?")
    body = entry.get("body", "")
    due = entry.get("due_at", "")
    severity = entry.get("severity", "discrete")
    try:
        due_dt = datetime.fromisoformat(due)
        now = datetime.now()
        if due_dt > now:
            remaining = due_dt - now
            mins = int(remaining.total_seconds() // 60)
            if mins >= 60:
                hours = mins // 60
                mins = mins % 60
                due_str = f"in {hours}h {mins}m"
            else:
                due_str = f"in {mins}m"
        else:
            due_str = "now"
    except Exception:
        due_str = due[:16] if due else "?"
    body_short = body[:40] + "..." if len(body) > 40 else body
    return f"[{idx}] {title} — {body_short} (due: {due_str}, {severity}) [{rid}]"


def dispatch(name: str, args: dict) -> str:
    cfg = _load_settings()
    if not bool(cfg.get("enabled", True)):
        return "[reminders] Skill is disabled in settings."

    try:
        if name == "reminders_add":
            title = str(args.get("title", "Reminder"))
            body = str(args.get("body", "Time is up."))
            delay_seconds = int(args.get("delay_seconds") or 0)
            delay_minutes = int(args.get("delay_minutes") or 0)
            if delay_minutes and not delay_seconds:
                delay_seconds = delay_minutes * 60
            if not delay_seconds:
                delay_seconds = 300
            severity = str(args.get("severity", "discrete"))

            from uuid import uuid4
            entry = {
                "id": str(uuid4()),
                "title": title,
                "body": body,
                "severity": severity,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "due_at": (datetime.now() + timedelta(seconds=delay_seconds)).isoformat(timespec="seconds"),
            }
            queue = _load_queue()
            queue.append(entry)
            queue.sort(key=lambda item: str(item.get("due_at", "")))
            _save_queue(queue)

            _start_daemon()
            mins = delay_seconds // 60
            return f"Reminder added: '{title}' due in {mins} minute(s)."

        if name == "reminders_list":
            queue = _load_queue()
            if not queue:
                return "No pending reminders."
            lines = ["Pending reminders:"]
            for i, entry in enumerate(queue):
                lines.append(_fmt_reminder(entry, i))
            return "\n".join(lines)

        if name == "reminders_cancel":
            rid = str(args.get("reminder_id", "")).strip()
            if not rid:
                return "No reminder_id provided."
            queue = _load_queue()
            original_len = len(queue)
            queue = [e for e in queue if not e.get("id", "").startswith(rid)]
            if len(queue) == original_len:
                return f"Reminder {rid} not found."
            _save_queue(queue)
            return f"Cancelled reminder {rid}."

        if name == "reminders_clear":
            queue = _load_queue()
            if not queue:
                return "No reminders to clear."
            _save_queue([])
            return f"Cleared {len(queue)} reminder(s)."

        if name == "reminders_status":
            running = _daemon_is_running()
            queue = _load_queue()
            count = len(queue)
            if running:
                return f"Reminder daemon is running. {count} pending reminder(s)."
            return f"Reminder daemon is NOT running. {count} pending reminder(s)."

        if name == "reminders_start_daemon":
            if _daemon_is_running():
                return "Reminder daemon is already running."
            started = _start_daemon()
            if started:
                return "Reminder daemon started."
            return "Failed to start reminder daemon."

    except Exception as exc:
        return f"[reminders] {exc}"

    return f"[reminders] unknown tool: {name}"