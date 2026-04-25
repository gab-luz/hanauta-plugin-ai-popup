"""Apprise skill — send notifications to any channel via the apprise library.

Credentials are stored in skills_settings.json under the "apprise" key:
    {
        "apprise": {
            "urls": ["tgram://bottoken/chatid", "discord://webhook_id/webhook_token"],
            "enabled": true
        }
    }

Apprise URL formats: https://github.com/caronc/apprise/wiki
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "notify_send",
            "description": (
                "Send a notification message to configured channels "
                "(Telegram, Discord, Slack, email, etc.) via Apprise. "
                "Use this when the user asks to be notified, or when a tool result "
                "should be delivered to them through a messaging channel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Notification title."},
                    "body": {"type": "string", "description": "Notification body text."},
                    "channel": {
                        "type": "string",
                        "description": "Optional channel name to target (matches a label in settings). Leave empty to send to all configured channels.",
                    },
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_list_channels",
            "description": "List the notification channels currently configured in Apprise settings.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("apprise", {})
    except Exception:
        return {}


def _apprise_urls(settings: dict, channel: str = "") -> list[str]:
    raw = settings.get("urls", [])
    if isinstance(raw, str):
        raw = [u.strip() for u in raw.splitlines() if u.strip()]
    urls = [str(u).strip() for u in raw if str(u).strip()]
    if channel:
        # Filter by label prefix "label:url" if user specified a channel
        filtered = [u.split(":", 1)[1] if u.lower().startswith(f"{channel.lower()}:") else u
                    for u in urls if channel.lower() in u.lower()]
        if filtered:
            return filtered
    return urls


def dispatch(name: str, args: dict) -> str:
    settings = _load_settings()

    if name == "notify_list_channels":
        urls = _apprise_urls(settings)
        if not urls:
            return "No Apprise channels configured. Add URLs in Backend Settings → Skills → Apprise."
        lines = []
        for url in urls:
            # Mask credentials: show scheme and host only
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                lines.append(f"{parsed.scheme}://{parsed.hostname or '…'}")
            except Exception:
                lines.append(url[:40] + "…" if len(url) > 40 else url)
        return "Configured channels:\n" + "\n".join(f"  • {l}" for l in lines)

    if name == "notify_send":
        if not bool(settings.get("enabled", True)):
            return "[notify] Apprise skill is disabled in settings."
        title = str(args.get("title", "")).strip()
        body = str(args.get("body", "")).strip()
        channel = str(args.get("channel", "")).strip()
        if not body:
            return "[notify] body is required."
        urls = _apprise_urls(settings, channel)
        if not urls:
            return "[notify] No Apprise channels configured. Add URLs in Backend Settings → Skills → Apprise."

        # Try Python apprise library first
        try:
            import apprise
            ap = apprise.Apprise()
            for url in urls:
                ap.add(url)
            ok = ap.notify(title=title, body=body)
            if ok:
                return f"Notification sent to {len(urls)} channel(s)."
            return "[notify] Apprise reported a delivery failure."
        except ImportError:
            pass

        # Fallback: apprise CLI
        try:
            for url in urls:
                cmd = ["apprise", "-t", title, "-b", body, url]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
                if result.returncode != 0:
                    return f"[notify] apprise CLI error: {(result.stderr or result.stdout).strip()}"
            return f"Notification sent to {len(urls)} channel(s) via CLI."
        except FileNotFoundError:
            return (
                "[notify] apprise not installed. "
                "Run: pip install apprise  or  uv pip install apprise"
            )

    return f"[notify] unknown tool: {name}"
