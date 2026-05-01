"""
Hanauta AI Skills — tool-calling registry.

Each skill module exposes:
    SKILL_DEFINITIONS: list[dict]   — OpenAI-style tool definitions
    dispatch(name, arguments) -> str — execute a tool, return plain-text result

Usage:
    from skills import registry
    tools   = registry.tool_definitions()   # pass to LLM
    result  = registry.call("docker_ps", {}) # execute after LLM picks a tool
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("hanauta.skills")

# Maps logical module name -> filename (relative to this package directory)
_SKILL_FILES: list[tuple[str, str]] = [
    ("skills.apprise",          "apprise.py"),
    ("skills.calendar",         "calendar.py"),
    ("skills.docker",           "docker.py"),
    ("skills.emotion_engine",   "py-emotion-engine.py"),
    ("skills.hanauta_desktop",  "hanauta-desktop.py"),
("skills.hanauta_mail",     "hanauta-mail.py"),
    ("skills.homeassistant",    "homeassistant.py"),
    ("skills.image",          "image.py"),
    ("skills.jellyfin",      "jellyfin.py"),
("skills.kdeconnect",       "kdeconnect.py"),
    ("skills.lutris",          "lutris.py"),
    ("skills.pc_sensors",     "pc-sensors.py"),
    ("skills.reminders",        "reminders.py"),
    ("skills.spotify",       "spotify.py"),
]

_registry: dict[str, tuple[dict, Any]] = {}  # name -> (definition, module)


def _load() -> None:
    if _registry:
        return
    skills_dir = Path(__file__).parent
    # Load per-skill enabled flags from settings
    settings: dict = {}
    try:
        settings_path = skills_dir.parent / "hanauta_aipopup" / ".." / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
        # Use the canonical path via runtime if available
        state_path = Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
        if state_path.exists():
            import json as _json
            settings = _json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    if not bool(settings.get("skills_enabled", True)):
        return  # all skills disabled globally

    _SKILL_ENABLED_KEYS = {
        "apprise.py":            "apprise",
        "calendar.py":           "calendar",
        "docker.py":             "docker",
        "hanauta-desktop.py":    "hanauta_desktop",
"hanauta-mail.py":       "mail",
        "homeassistant.py":      "homeassistant",
        "image.py":            "sdwebui",
        "jellyfin.py":         "jellyfin",
"kdeconnect.py":         "kdeconnect",
        "lutris.py":           "lutris",
        "pc-sensors.py":       "pc_sensors",
        "reminders.py":         "reminders",
        "spotify.py":          "spotify",
        "py-emotion-engine.py":  "emotion_engine",
    }

    for mod_name, filename in _SKILL_FILES:
        path = skills_dir / filename
        if not path.exists():
            LOGGER.warning("Skill file not found: %s", path)
            continue
        skill_key = _SKILL_ENABLED_KEYS.get(filename, "")
        if skill_key and not bool(settings.get(skill_key, {}).get("enabled", True)):
            LOGGER.debug("Skill %s disabled in settings", filename)
            continue
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            for defn in getattr(mod, "SKILL_DEFINITIONS", []):
                fn_name = defn.get("function", {}).get("name") or defn.get("name", "")
                if fn_name:
                    _registry[fn_name] = (defn, mod)
        except Exception as exc:
            LOGGER.warning("Failed to load skill %s: %s", filename, exc)


def tool_definitions() -> list[dict]:
    """Return all skill definitions in OpenAI tools format."""
    _load()
    return [defn for defn, _mod in _registry.values()]


def call(name: str, arguments: dict) -> str:
    """Dispatch a tool call by name. Returns a plain-text result string."""
    _load()
    entry = _registry.get(name)
    if entry is None:
        return f"[skill error] Unknown tool: {name!r}"
    _defn, mod = entry
    # NSFL safety guard — runs before every tool call
    try:
        import sys as _sys
        _safety_mod = _sys.modules.get("skills.safety")
        if _safety_mod is None:
            from pathlib import Path as _Path
            import importlib.util as _ilu
            _safety_path = _Path(__file__).parent / "safety.py"
            _spec = _ilu.spec_from_file_location("skills.safety", _safety_path)
            _safety_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_safety_mod)  # type: ignore[union-attr]
            _sys.modules["skills.safety"] = _safety_mod
        _safety_mod.safety_check(name, arguments)
    except Exception as _se:
        if type(_se).__name__ == "SafetyBlocked":
            return f"[safety] {_se}"
        # safety module itself failed — log and continue
        LOGGER.debug("Safety module error (non-blocking): %s", _se)
    try:
        return str(mod.dispatch(name, arguments))
    except Exception as exc:
        LOGGER.exception("Skill %s raised an exception", name)
        return f"[skill error] {name}: {exc}"


def available_names() -> list[str]:
    _load()
    return list(_registry.keys())
