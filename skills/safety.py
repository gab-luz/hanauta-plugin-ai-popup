"""
Hanauta AI — Safety Guard.

Mandatory — cannot be disabled. Runs before every skill dispatch.

Protection levels:
  BLOCKED      — refused outright, no override ever.
  CONFIRM_2x   — fullscreen alert shown TWICE with Allow/Reject buttons.
                 Auto-rejects after 30s if user does nothing.
                 For physical hazards (garage, locks, stoves…).
  CONFIRM_1x   — fullscreen alert shown ONCE with content preview.
                 Auto-rejects after 20s if user does nothing.
                 For communication actions (SMS, email, notifications).
  SESSION_ONCE — confirm once per session, then allowed freely.
  TIMED_30     — confirm once, then allowed for 30 minutes.

Icons: emoji only — render universally without font dependency.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_FULLSCREEN_ALERT_SCRIPT = (
    Path.home() / ".config" / "i3" / "hanauta" / "src" / "pyqt" / "shared" / "fullscreen_alert.py"
)

# Auto-reject timeouts (seconds)
_TIMEOUT_2X = 30   # physical hazard — 30s to respond
_TIMEOUT_1X = 20   # communication — 20s to respond

# ── Allowance store ───────────────────────────────────────────────────────────
_ALLOWED: dict[str, float] = {}


def _allowance_key(tool_name: str, args: dict) -> str:
    target = (
        str(args.get("number", ""))
        or str(args.get("to", ""))
        or str(args.get("entity_id", ""))
        or str(args.get("title", ""))[:40]
        or str(args.get("body", ""))[:40]
    )
    return f"{tool_name}:{target}"


def _is_allowed(key: str) -> bool:
    expiry = _ALLOWED.get(key)
    if expiry is None:
        return False
    if expiry == float("inf"):
        return True
    if time.time() < expiry:
        return True
    del _ALLOWED[key]
    return False


def _grant_session(key: str) -> None:
    _ALLOWED[key] = float("inf")


def _grant_timed(key: str, minutes: int = 30) -> None:
    _ALLOWED[key] = time.time() + minutes * 60


# ── Fullscreen alert ──────────────────────────────────────────────────────────

def _show_alert(title: str, body: str, severity: str = "disturbing",
                timeout: float = 30.0) -> bool:
    """
    Show the Hanauta fullscreen alert.
    Returns True if the process exited cleanly within timeout (user dismissed it).
    Returns False if timed out or failed — treated as rejection.
    """
    script = _FULLSCREEN_ALERT_SCRIPT
    if not script.exists():
        try:
            subprocess.run(
                ["notify-send", "-u", "critical", "-t", str(int(timeout * 1000)),
                 "-a", "Hanauta Safety", title, body],
                check=False, timeout=5,
            )
        except Exception:
            pass
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--title", title, "--body", body, "--severity", severity],
            check=False,
            timeout=timeout,
        )
        # Exit 0 = user dismissed (clicked Done) = allowed
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        # User did nothing — auto-reject
        return False
    except Exception:
        return False


def _confirm_2x(emoji: str, title: str, body: str) -> bool:
    """
    Show fullscreen alert TWICE with auto-reject on timeout.
    First: "Allow this action?" — must be dismissed within 30s.
    Second: "Are you absolutely sure?" — must be dismissed within 30s.
    Both must be confirmed; timeout on either = rejection.
    """
    full_title = f"{emoji}  {title}" if emoji else title

    first_body = (
        f"{body}\n\n"
        f"⏱ You have {_TIMEOUT_2X} seconds to respond.\n"
        f"[Step 1 of 2 — Click Done to allow, or close to reject]"
    )
    ok1 = _show_alert(full_title, first_body, "disturbing", timeout=_TIMEOUT_2X)
    if not ok1:
        return False

    time.sleep(0.4)

    second_body = (
        f"{body}\n\n"
        f"⚠️ This is your final confirmation.\n"
        f"⏱ You have {_TIMEOUT_2X} seconds to respond.\n"
        f"[Step 2 of 2 — Click Done to confirm, or close to cancel]"
    )
    ok2 = _show_alert(full_title, second_body, "disturbing", timeout=_TIMEOUT_2X)
    return ok2


def _confirm_1x(emoji: str, title: str, body: str) -> bool:
    """
    Show fullscreen alert ONCE with content preview.
    Auto-rejects after 20s if user does nothing.
    """
    full_title = f"{emoji}  {title}" if emoji else title
    full_body = (
        f"{body}\n\n"
        f"⏱ Auto-rejected in {_TIMEOUT_1X}s if no response.\n"
        f"[Click Done to allow, or close to reject]"
    )
    return _show_alert(full_title, full_body, "disturbing", timeout=_TIMEOUT_1X)


# ── KDE Connect device helper ─────────────────────────────────────────────────

def _kdeconnect_device_line(args: dict) -> str:
    """Return '📱 Device: <name>' line for KDE Connect confirmations."""
    device_hint = str(args.get("device", "")).strip()
    device_name = device_hint or "paired device"
    # Try to resolve the actual device name from kdeconnect-cli
    try:
        result = subprocess.run(
            ["kdeconnect-cli", "--list-available"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        if lines:
            # Pick the first matching line or the first device
            for line in lines:
                if device_hint and device_hint.lower() in line.lower():
                    device_name = line.split("-")[0].strip()
                    break
            else:
                device_name = lines[0].split("-")[0].strip()
    except Exception:
        pass
    return f"📱 Device: {device_name}"


# ── Rule catalogue ────────────────────────────────────────────────────────────

class SafetyBlocked(Exception):
    """Raised when an action is blocked by the safety guard."""


# ── BLOCKED: no override ever ─────────────────────────────────────────────────
_BLOCKED: list[tuple] = [
    # Medical equipment
    (
        lambda n, a: any(kw in str(a.get("body") or a.get("message") or "").lower()
                         + str(a.get("entity_id") or "").lower()
            for kw in ("ventilator", "defibrillator", "pacemaker",
                       "oxygen concentrator", "infusion pump", "medical device")),
        "This action involves life-critical medical equipment and cannot be executed by AI.",
    ),
    # Emergency services
    (
        lambda n, a: any(kw in str(a).lower()
            for kw in ("911", "112", "999", "190", "193",
                       "emergency services", "ambulance", "fire brigade", "police dispatch")),
        "Emergency service commands cannot be triggered by AI.",
    ),
    # Self-harm / harm to others in message content
    (
        lambda n, a: n in ("kdeconnect_send_sms", "mail_send", "notify_send") and any(
            kw in str(a.get("body") or a.get("message") or "").lower()
            for kw in ("kill myself", "end my life", "suicide", "self harm",
                       "hurt myself", "kill you", "hurt you", "i will harm",
                       "bomb", "weapon", "explosive")),
        "Message content flagged for potential self-harm or harm to others. Action blocked.",
    ),
    # Destructive shell commands
    (
        lambda n, a: n == "desktop_run_command" and any(
            kw in str(a.get("command", "")).lower()
            for kw in ("rm -rf /", "rm -rf ~", "mkfs", "dd if=/dev/zero",
                       ":(){ :|:& };:", "chmod -R 000 /", "shred /dev")),
        "This command could destroy system data and is blocked.",
    ),
    # Credentials in outgoing messages
    (
        lambda n, a: n in ("kdeconnect_send_sms", "mail_send", "notify_send") and any(
            kw in str(a.get("body") or a.get("message") or "").lower()
                   + str(a.get("subject") or "").lower()
            for kw in ("password", "passwd", "api_key", "api key", "secret",
                       "private key", "ssh key", "credit card", "cvv", "ssn")),
        "Message appears to contain sensitive credentials. Sending blocked for your security.",
    ),
]

# ── CONFIRM_2x: double fullscreen, timed allowance ────────────────────────────
_CONFIRM_2X: list[tuple] = [
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("garage", "gate", "portao", "portão", "barrier",
                       "bollard", "shutter", "rolling_door")),
        "🚗", "Garage / Gate Action",
        ("The AI wants to open or close a garage door or gate.\n\n"
         "HIGH RISK — a person, child, or animal could be crushed.\n\n"
         "Make sure the area is completely clear before confirming."),
        "timed_30",
    ),
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("stove", "oven", "hob", "burner", "heating_element",
                       "fogão", "forno", "cooktop")),
        "🔥", "Stove / Oven Action",
        ("The AI wants to control a stove or oven.\n\n"
         "Activating a heating element unattended is a fire hazard.\n\n"
         "Only confirm if you are present and watching."),
        "timed_30",
    ),
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("valve", "water_main", "flood", "sprinkler", "irrigation")),
        "💧", "Water Valve Action",
        ("The AI wants to open or close a water valve.\n\n"
         "An unexpected change can cause flooding or water damage.\n\n"
         "Confirm only if you are certain."),
        "timed_30",
    ),
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("breaker", "circuit", "main_power", "cut_power", "power_off_all")),
        "⚡", "Power / Circuit Breaker Action",
        ("The AI wants to cut power to a circuit or the main breaker.\n\n"
         "This could shut down critical equipment or cause data loss.\n\n"
         "Confirm only if you are certain."),
        "timed_30",
    ),
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("alarm", "siren", "panic_button", "burglar")),
        "🚨", "Alarm / Siren Action",
        ("The AI wants to trigger an alarm or siren.\n\n"
         "A false alarm can cause panic and waste emergency resources.\n\n"
         "Confirm only if this is intentional."),
        "timed_30",
    ),
]

# ── CONFIRM_1x: single fullscreen with content preview ────────────────────────
_CONFIRM_1X: list[tuple] = [
    (
        lambda n, a: n == "kdeconnect_send_sms",
        "📱", "Send SMS",
        lambda a: (
            f"{_kdeconnect_device_line(a)}\n"
            f"To: {a.get('number', '?')}\n"
            f"Message: {str(a.get('message', ''))[:200]}"
            + ("…" if len(str(a.get('message', ''))) > 200 else "")
        ),
        "timed_30",
    ),
    (
        lambda n, a: n == "kdeconnect_ring",
        "📱", "Ring Device",
        lambda a: (
            f"{_kdeconnect_device_line(a)}\n"
            f"The AI wants to ring your phone to help find it."
        ),
        "session",
    ),
    (
        lambda n, a: n == "kdeconnect_share_file",
        "📱", "Share File to Device",
        lambda a: (
            f"{_kdeconnect_device_line(a)}\n"
            f"File: {a.get('path', '?')}"
        ),
        "session",
    ),
    (
        lambda n, a: n == "kdeconnect_share_url",
        "📱", "Share URL to Device",
        lambda a: (
            f"{_kdeconnect_device_line(a)}\n"
            f"URL: {a.get('url', '?')}"
        ),
        "session",
    ),
    (
        lambda n, a: n == "mail_send",
        "📧", "Send Email",
        lambda a: (
            f"To: {a.get('to', '?')}\n"
            f"Subject: {a.get('subject', '?')}\n"
            f"Body: {str(a.get('body', ''))[:200]}"
            + ("…" if len(str(a.get('body', ''))) > 200 else "")
        ),
        "timed_30",
    ),
    (
        lambda n, a: n == "notify_send",
        "🔔", "Send Notification",
        lambda a: (
            f"Title: {a.get('title', '?')}\n"
            f"Body: {str(a.get('body', ''))[:200]}"
            + ("…" if len(str(a.get('body', ''))) > 200 else "")
        ),
        "timed_30",
    ),
    (
        lambda n, a: any(kw in (str(n) + str(a)).lower()
            for kw in ("lock", "unlock", "deadbolt", "front_door", "back_door", "door_lock")),
        "🔒", "Door Lock Action",
        lambda a: (
            "The AI wants to lock or unlock a door.\n\n"
            "Unlocking could expose your home to intruders.\n"
            "Locking could trap someone inside.\n\n"
            "Confirm only if you are certain this is safe."
        ),
        "timed_30",
    ),
    (
        lambda n, a: n == "ha_trigger_automation",
        "⚡", "Trigger Automation",
        lambda a: (
            f"Automation: {a.get('entity_id', '?')}\n\n"
            "Make sure this automation is safe to run right now."
        ),
        "session",
    ),
    (
        lambda n, a: n == "ha_call_service" and str(a.get("domain", "")) not in (
            "light", "media_player", "input_boolean", "scene"),
        "🏠", "Home Assistant Service",
        lambda a: (
            f"Service: {a.get('domain', '?')}.{a.get('service', '?')}\n"
            f"Entity: {a.get('entity_id', 'all')}\n\n"
            "Confirm only if this is safe to execute."
        ),
        "session",
    ),
    (
        lambda n, a: n == "desktop_run_command",
        "💻", "Run Shell Command",
        lambda a: (
            f"Command: {a.get('command', '?')}\n\n"
            "Review carefully before allowing."
        ),
        "session",
    ),
    (
        lambda n, a: n in ("docker_stop", "docker_restart"),
        "🐳", "Docker Container Action",
        lambda a: (
            f"Container: {a.get('container', '?')}\n\n"
            "This may interrupt running services."
        ),
        "session",
    ),
]


# ── Public API ────────────────────────────────────────────────────────────────

def safety_check(tool_name: str, args: dict) -> None:
    """
    Run before every skill dispatch. Raises SafetyBlocked if refused.
    Auto-rejects if the user does not respond within the timeout.
    """
    # 1. Hard blocks
    for match_fn, reason in _BLOCKED:
        try:
            if match_fn(tool_name, args):
                raise SafetyBlocked(reason)
        except SafetyBlocked:
            raise
        except Exception:
            pass

    key = _allowance_key(tool_name, args)

    # 2. Double-confirm rules
    for entry in _CONFIRM_2X:
        match_fn, emoji, title, body, grant_mode = entry
        try:
            if not match_fn(tool_name, args):
                continue
        except Exception:
            continue
        if _is_allowed(key):
            return
        confirmed = _confirm_2x(emoji, title, body)
        if not confirmed:
            raise SafetyBlocked(
                f"Action '{tool_name}' was not confirmed (auto-rejected after {_TIMEOUT_2X}s)."
            )
        _grant_timed(key, 30) if grant_mode == "timed_30" else _grant_session(key)
        return

    # 3. Single-confirm rules
    for entry in _CONFIRM_1X:
        match_fn, emoji, title, body_fn, grant_mode = entry
        try:
            if not match_fn(tool_name, args):
                continue
        except Exception:
            continue
        if _is_allowed(key):
            return
        body = body_fn(args) if callable(body_fn) else str(body_fn)
        confirmed = _confirm_1x(emoji, title, body)
        if not confirmed:
            raise SafetyBlocked(
                f"Action '{tool_name}' was not confirmed (auto-rejected after {_TIMEOUT_1X}s)."
            )
        _grant_timed(key, 30) if grant_mode == "timed_30" else _grant_session(key)
        return


def is_dangerous(tool_name: str, args: dict) -> tuple[bool, str]:
    """Non-raising pre-flight check. Returns (is_dangerous, reason)."""
    for match_fn, reason in _BLOCKED:
        try:
            if match_fn(tool_name, args):
                return True, reason
        except Exception:
            pass
    for entry in _CONFIRM_2X:
        match_fn, _e, title, _b, _g = entry
        try:
            if match_fn(tool_name, args):
                return True, f"Requires double confirmation: {title}"
        except Exception:
            pass
    for entry in _CONFIRM_1X:
        match_fn, _e, title, _b, _g = entry
        try:
            if match_fn(tool_name, args):
                return True, f"Requires confirmation: {title}"
        except Exception:
            pass
    return False, ""


def revoke_allowance(tool_name: str, args: dict) -> None:
    _ALLOWED.pop(_allowance_key(tool_name, args), None)


def clear_all_allowances() -> None:
    _ALLOWED.clear()
