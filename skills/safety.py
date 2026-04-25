"""
Hanauta AI — NSFL Safety Guard.

Prevents the AI from autonomously executing actions that could harm
people, animals, or property — regardless of character personality.

Two protection levels:
  BLOCKED  — action is refused outright, no override possible.
  CONFIRM  — requires the user to confirm TWICE via fullscreen alert
              before the action is allowed to proceed.

Import and call `safety_check(tool_name, args)` at the top of every
skill's dispatch() that controls physical hardware or infrastructure.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# ── Risk catalogue ────────────────────────────────────────────────────────────
# Each entry: (match_fn, level, icon, title, body)
# match_fn receives (tool_name: str, args: dict) -> bool

_FULLSCREEN_ALERT_SCRIPT = (
    Path.home() / ".config" / "i3" / "hanauta" / "src" / "pyqt" / "shared" / "fullscreen_alert.py"
)

# Actions that are ALWAYS blocked — no confirmation possible
_BLOCKED: list[tuple] = [
    # Never let the AI cut power to medical equipment keywords
    (
        lambda n, a: any(
            kw in str(a).lower()
            for kw in ("ventilator", "defibrillator", "pacemaker", "oxygen", "medical")
        ),
        "This action involves medical equipment and cannot be executed by AI.",
    ),
    # Never let the AI send emergency services commands
    (
        lambda n, a: any(
            kw in str(a).lower()
            for kw in ("911", "112", "999", "emergency services", "ambulance")
        ),
        "Emergency service commands cannot be triggered by AI.",
    ),
]

# Actions that require DOUBLE fullscreen confirmation
_CONFIRM_RULES: list[tuple] = [
    # Garage / gate / barrier — crushing hazard
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("garage", "gate", "portao", "portão", "barrier", "bollard", "shutter", "rolling_door")
        ),
        "\ue531",  # Material icon: garage
        "⚠️ Garage / Gate Action",
        (
            "The AI wants to open or close a garage door or gate.\n\n"
            "This is a HIGH-RISK action — a person, child, or animal could be "
            "crushed if they are in the path of the door.\n\n"
            "Make sure the area is completely clear before confirming."
        ),
    ),
    # Locks / door locks — security risk
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("lock", "unlock", "deadbolt", "front_door", "back_door", "door_lock")
        ),
        "\ue897",  # lock
        "⚠️ Door Lock Action",
        (
            "The AI wants to lock or unlock a door.\n\n"
            "Unlocking a door could expose your home to intruders. "
            "Locking a door could trap someone inside.\n\n"
            "Confirm only if you are certain this is safe."
        ),
    ),
    # Stove / oven / heating elements — fire hazard
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("stove", "oven", "hob", "burner", "heating_element", "fogão", "forno")
        ),
        "\ue6f3",  # outdoor_grill
        "⚠️ Stove / Oven Action",
        (
            "The AI wants to control a stove or oven.\n\n"
            "Activating a heating element unattended is a fire hazard.\n\n"
            "Only confirm if you are present and watching."
        ),
    ),
    # Alarm / siren — distress / false alarm
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("alarm", "siren", "panic", "burglar")
        ),
        "\ue7f7",  # notifications_active
        "⚠️ Alarm / Siren Action",
        (
            "The AI wants to trigger an alarm or siren.\n\n"
            "A false alarm can cause panic and waste emergency resources.\n\n"
            "Confirm only if this is intentional."
        ),
    ),
    # Water / flood valves
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("valve", "water_main", "flood", "sprinkler", "irrigation")
        ),
        "\ue798",  # water
        "⚠️ Water Valve Action",
        (
            "The AI wants to open or close a water valve.\n\n"
            "An unexpected valve change can cause flooding or water damage.\n\n"
            "Confirm only if you are certain."
        ),
    ),
    # Power / circuit breaker
    (
        lambda n, a: any(
            kw in (str(n) + str(a)).lower()
            for kw in ("breaker", "circuit", "main_power", "cut_power", "power_off_all")
        ),
        "\ue63e",  # power
        "⚠️ Power / Circuit Breaker Action",
        (
            "The AI wants to cut power to a circuit or the main breaker.\n\n"
            "This could shut down critical equipment or cause data loss.\n\n"
            "Confirm only if you are certain."
        ),
    ),
]


# ── Fullscreen confirmation ───────────────────────────────────────────────────

def _show_fullscreen_alert(title: str, body: str, severity: str = "disturbing") -> bool:
    """
    Show the Hanauta fullscreen alert. Returns True if the script ran.
    Uses the standard fullscreen_alert.py from the Hanauta shared module.
    """
    script = _FULLSCREEN_ALERT_SCRIPT
    if not script.exists():
        # Fallback: try trigger_fullscreen_alert from runtime
        try:
            sys.path.insert(0, str(Path.home() / ".config" / "i3"))
            from hanauta.src.pyqt.shared.fullscreen_alert import main as _fa_main  # type: ignore
            _fa_main(["--title", title, "--body", body, "--severity", severity])
            return True
        except Exception:
            pass
        return False
    try:
        subprocess.run(
            [sys.executable, str(script), "--title", title, "--body", body, "--severity", severity],
            check=False,
            timeout=120,
        )
        return True
    except Exception:
        return False


def _double_confirm(icon: str, title: str, body: str) -> bool:
    """
    Show the fullscreen alert TWICE. The user must dismiss both.
    Returns True only if both alerts were shown (user saw both warnings).
    """
    full_title = f"{icon}  {title}" if icon else title
    # First alert
    ok1 = _show_fullscreen_alert(full_title, body + "\n\n[Confirmation 1 of 2]", severity="disturbing")
    if not ok1:
        return False
    time.sleep(0.3)
    # Second alert — slightly different wording to force re-reading
    ok2 = _show_fullscreen_alert(
        full_title,
        body + "\n\n[Confirmation 2 of 2 — Are you absolutely sure?]",
        severity="disturbing",
    )
    return ok2


# ── Public API ────────────────────────────────────────────────────────────────

class SafetyBlocked(Exception):
    """Raised when an action is blocked by the NSFL safety guard."""


def safety_check(tool_name: str, args: dict) -> None:
    """
    Call at the top of any skill dispatch() that controls physical hardware.

    Raises SafetyBlocked if the action is refused.
    Shows double fullscreen confirmation for high-risk actions and raises
    SafetyBlocked if the confirmation flow could not be completed.

    Usage:
        from skills.safety import safety_check, SafetyBlocked
        def dispatch(name, args):
            try:
                safety_check(name, args)
            except SafetyBlocked as e:
                return f"[safety] {e}"
            ...
    """
    # Check hard blocks first
    for match_fn, reason in _BLOCKED:
        try:
            if match_fn(tool_name, args):
                raise SafetyBlocked(reason)
        except SafetyBlocked:
            raise
        except Exception:
            pass

    # Check confirmation-required actions
    for entry in _CONFIRM_RULES:
        match_fn, icon, title, body = entry
        try:
            if not match_fn(tool_name, args):
                continue
        except Exception:
            continue

        confirmed = _double_confirm(icon, title, body)
        if not confirmed:
            raise SafetyBlocked(
                f"Action '{tool_name}' requires physical confirmation. "
                "Please confirm via the fullscreen alert on your screen."
            )
        # Both alerts dismissed — allow the action
        return


def is_dangerous(tool_name: str, args: dict) -> tuple[bool, str]:
    """
    Non-raising version. Returns (is_dangerous, reason).
    Useful for pre-flight checks without executing the confirmation flow.
    """
    for match_fn, reason in _BLOCKED:
        try:
            if match_fn(tool_name, args):
                return True, reason
        except Exception:
            pass
    for entry in _CONFIRM_RULES:
        match_fn, _icon, title, _body = entry
        try:
            if match_fn(tool_name, args):
                return True, f"Requires double confirmation: {title}"
        except Exception:
            pass
    return False, ""
