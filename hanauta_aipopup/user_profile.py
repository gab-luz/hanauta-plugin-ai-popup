from __future__ import annotations

import json
from pathlib import Path


_SETTINGS_FILE = (
    Path.home()
    / ".local"
    / "state"
    / "hanauta"
    / "notification-center"
    / "settings.json"
)


def _safe_read_settings() -> dict:
    try:
        payload = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


try:
    from pyqt.shared.profile import (  # type: ignore
        load_profile_state as load_profile_state,
        preferred_user_name as preferred_user_name,
        spoken_name as spoken_name,
        format_new_email_interrupt_phrase as format_new_email_interrupt_phrase,
    )
except Exception:  # pragma: no cover

    def load_profile_state(settings: dict | None = None) -> dict:
        payload = settings if isinstance(settings, dict) else _safe_read_settings()
        raw = payload.get("profile", {}) if isinstance(payload, dict) else {}
        profile = dict(raw) if isinstance(raw, dict) else {}
        profile["first_name"] = str(profile.get("first_name", "")).strip()
        profile["nickname"] = str(profile.get("nickname", "")).strip()
        profile["pronunciations"] = (
            profile.get("pronunciations", [])
            if isinstance(profile.get("pronunciations", []), list)
            else []
        )
        return profile

    def preferred_user_name(profile: dict | None) -> str:
        if not isinstance(profile, dict):
            return ""
        nickname = str(profile.get("nickname", "")).strip()
        if nickname:
            return nickname
        return str(profile.get("first_name", "")).strip()

    def spoken_name(profile: dict | None, *, language_code: str = "") -> str:
        del language_code
        return preferred_user_name(profile)

    def format_new_email_interrupt_phrase(
        profile: dict | None,
        *,
        language_code: str = "en",
        fallback_template: str = "{user}, sorry to interrupt you — you got a new email.",
    ) -> str:
        del language_code
        user = preferred_user_name(profile)
        try:
            return fallback_template.format(user=user)
        except Exception:
            return f"{user}, sorry to interrupt you — you got a new email."

