from __future__ import annotations

import json
import locale as pylocale
import os
import re
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LOCALE_DIR = PLUGIN_ROOT / "locale"
DEFAULT_LOCALE = "en-US"
HANAUTA_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "notification-center" / "settings.json"
)

_LOCALE_ALIASES = {
    "pt": "pt-BR",
    "ptbr": "pt-BR",
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "enus": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
    "en": "en-US",
    "es": "es-419",
    "es419": "es-419",
    "es-419": "es-419",
    "es_419": "es-419",
    "ru": "ru-RU",
    "ru-ru": "ru-RU",
    "ru_ru": "ru-RU",
}

_CACHE: dict[str, dict[str, str]] = {}


def _normalize_locale_code(value: str) -> str:
    raw = re.sub(r"\s+", "", str(value or "").strip())
    if not raw:
        return DEFAULT_LOCALE
    lower = raw.lower().replace("_", "-")
    if lower in _LOCALE_ALIASES:
        return _LOCALE_ALIASES[lower]
    parts = [p for p in lower.split("-") if p]
    if not parts:
        return DEFAULT_LOCALE
    if len(parts) == 1:
        return _LOCALE_ALIASES.get(parts[0], parts[0])
    return f"{parts[0]}-{parts[1].upper()}"


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _flatten(prefix: str, node: dict[str, Any], out: dict[str, str]) -> None:
    for key, value in node.items():
        next_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            _flatten(next_key, value, out)
        elif isinstance(value, str):
            out[next_key] = value


def _load_locale_map(locale_code: str) -> dict[str, str]:
    normalized = _normalize_locale_code(locale_code)
    if normalized in _CACHE:
        return _CACHE[normalized]
    path = LOCALE_DIR / f"{normalized}.json"
    data = _safe_json(path)
    strings: dict[str, str] = {}
    if data:
        if isinstance(data.get("strings"), dict):
            _flatten("", data.get("strings", {}), strings)
        else:
            _flatten("", data, strings)
    _CACHE[normalized] = strings
    return strings


def available_locales() -> list[str]:
    locales: list[str] = []
    if not LOCALE_DIR.exists():
        return locales
    for path in sorted(LOCALE_DIR.glob("*.json")):
        locales.append(path.stem)
    return locales


def detect_locale() -> str:
    # Hanauta "System locale" setting should be honored first so UI follows user selection
    # even before shell/session env vars are refreshed.
    try:
        payload = _safe_json(HANAUTA_SETTINGS_FILE)
        region = payload.get("region", {}) if isinstance(payload, dict) else {}
        if isinstance(region, dict):
            saved = str(region.get("locale_code", "")).strip()
            if saved:
                return _normalize_locale_code(saved.split(".")[0].split(":")[0])
    except Exception:
        pass
    for key in ("HANAUTA_AI_POPUP_LOCALE", "LC_ALL", "LANG", "LANGUAGE"):
        value = str(os.environ.get(key, "")).strip()
        if value:
            return _normalize_locale_code(value.split(".")[0].split(":")[0])
    try:
        sys_locale = pylocale.getdefaultlocale()[0] or ""
    except Exception:
        sys_locale = ""
    return _normalize_locale_code(sys_locale)


def tr(key: str, default: str | None = None, *, locale_code: str | None = None, **fmt: object) -> str:
    requested = _normalize_locale_code(locale_code or detect_locale())
    primary = _load_locale_map(requested)
    fallback = _load_locale_map(DEFAULT_LOCALE) if requested != DEFAULT_LOCALE else primary
    text = primary.get(key) or fallback.get(key) or (default if default is not None else key)
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text
