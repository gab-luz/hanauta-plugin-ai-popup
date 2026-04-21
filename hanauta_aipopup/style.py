from __future__ import annotations

import json
import subprocess
from typing import Any

from PyQt6.QtGui import QColor

from .runtime import (
    NOTIFICATION_CENTER_SETTINGS_FILE,
    load_theme_palette,
    relative_luminance,
)


THEME = load_theme_palette()


def rgba(color: str, alpha: float) -> str:
    q = QColor(str(color or "#000000"))
    q.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return q.name(QColor.NameFormat.HexArgb)


def mix(color_a: str, color_b: str, amount: float) -> str:
    a = QColor(str(color_a or "#000000"))
    b = QColor(str(color_b or "#000000"))
    t = max(0.0, min(1.0, float(amount)))
    r = round(a.red() + (b.red() - a.red()) * t)
    g = round(a.green() + (b.green() - a.green()) * t)
    b_ = round(a.blue() + (b.blue() - a.blue()) * t)
    return QColor(r, g, b_).name()


def _is_global_dark_theme_enabled() -> bool:
    try:
        raw = NOTIFICATION_CENTER_SETTINGS_FILE.read_text(encoding="utf-8")
        payload: Any = json.loads(raw)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    appearance = payload.get("appearance", {})
    if not isinstance(appearance, dict):
        return False
    theme_choice = str(appearance.get("theme_choice", "")).strip().lower()
    theme_mode = str(appearance.get("theme_mode", "")).strip().lower()
    return theme_choice == "dark" or theme_mode == "dark"


def focused_workspace() -> dict[str, object] | None:
    try:
        output = subprocess.check_output(["i3-msg", "-t", "get_workspaces"], text=True)
        workspaces = json.loads(output)
    except Exception:
        return None
    if not isinstance(workspaces, list):
        return None
    for workspace in workspaces:
        if isinstance(workspace, dict) and workspace.get("focused"):
            return workspace
    return None


# Theme globals (set by apply_theme_globals()).
PANEL_BG = "#111111"
PANEL_BG_DEEP = "#111111"
PANEL_BG_FLOAT = "#111111"
CARD_BG = "#111111"
CARD_BG_SOFT = "#111111"
CARD_BG_RAISED = "#111111"
CARD_BG_ALT = "#111111"
BORDER = "#222222"
BORDER_SOFT = "#222222"
BORDER_HARD = "#222222"
BORDER_ACCENT = "#333333"
TEXT = "#ffffff"
TEXT_MID = "#cfcfcf"
TEXT_DIM = "#9a9a9a"
TEXT_SOFT = "#b0b0b0"
ACCENT = "#66ccff"
ACCENT_SOFT = "#66ccff"
ACCENT_ALT = "#ffcc66"
ACCENT_GLOW = "#66ccff"
USER_BG = "#111111"
ASSISTANT_BG = "#111111"
INPUT_BG = "#111111"
BOTTOM_BG = "#111111"
SHADOW = "#000000"
HOVER_BG = "#111111"
HERO_TOP = "#111111"
HERO_BOTTOM = "#111111"
UI_TEXT_STRONG = "#ffffff"
UI_TEXT_MUTED = "#cfcfcf"
UI_ICON_DIM = "#9a9a9a"
UI_ICON_ACTIVE = "#ffffff"
CHAT_TEXT = "#ffffff"
CHAT_SURFACE_BG = "#111111"


def apply_theme_globals() -> None:
    global THEME, PANEL_BG, PANEL_BG_DEEP, PANEL_BG_FLOAT
    global CARD_BG, CARD_BG_SOFT, CARD_BG_RAISED, CARD_BG_ALT
    global BORDER, BORDER_SOFT, BORDER_HARD, BORDER_ACCENT
    global TEXT, TEXT_MID, TEXT_DIM, TEXT_SOFT
    global ACCENT, ACCENT_SOFT, ACCENT_ALT, ACCENT_GLOW
    global USER_BG, ASSISTANT_BG, INPUT_BG, BOTTOM_BG
    global SHADOW, HOVER_BG, HERO_TOP, HERO_BOTTOM
    global UI_TEXT_STRONG, UI_TEXT_MUTED, UI_ICON_DIM, UI_ICON_ACTIVE, CHAT_TEXT, CHAT_SURFACE_BG

    THEME = load_theme_palette()
    PANEL_BG = THEME.panel_bg
    PANEL_BG_DEEP = mix(THEME.panel_bg, "#000000", 0.18)
    PANEL_BG_FLOAT = rgba(THEME.panel_bg, 0.96)

    CARD_BG = THEME.app_running_bg
    CARD_BG_SOFT = THEME.chip_bg
    CARD_BG_RAISED = mix(THEME.app_running_bg, "#ffffff", 0.04)
    CARD_BG_ALT = rgba(THEME.surface_container, 0.88)

    BORDER = THEME.panel_border
    BORDER_SOFT = THEME.chip_border
    BORDER_HARD = rgba(THEME.panel_border, 0.92)
    BORDER_ACCENT = rgba(THEME.app_focused_border, 0.95)

    TEXT = THEME.text
    TEXT_MID = THEME.text_muted
    TEXT_DIM = THEME.inactive
    TEXT_SOFT = mix(THEME.text_muted, THEME.inactive, 0.40)

    ACCENT = THEME.primary
    ACCENT_SOFT = THEME.accent_soft
    ACCENT_ALT = THEME.tertiary
    ACCENT_GLOW = rgba(THEME.primary, 0.22)

    USER_BG = mix(THEME.media_active_start, THEME.panel_bg, 0.18)
    ASSISTANT_BG = mix(THEME.app_running_bg, THEME.panel_bg, 0.05)
    INPUT_BG = rgba(THEME.surface_container, 0.98)
    BOTTOM_BG = rgba(THEME.chip_bg, 0.90)

    SHADOW = rgba(THEME.primary, 0.16)
    HOVER_BG = rgba(THEME.hover_bg, 0.92)
    HERO_TOP = mix(THEME.panel_bg, THEME.primary, 0.16)
    HERO_BOTTOM = mix(THEME.app_running_bg, THEME.panel_bg, 0.24)

    dark_surface = relative_luminance(THEME.surface_container_high) < 0.42
    if _is_global_dark_theme_enabled() or dark_surface:
        UI_TEXT_STRONG = "#F6F8FF"
        UI_TEXT_MUTED = rgba(UI_TEXT_STRONG, 0.84)
        UI_ICON_DIM = rgba(UI_TEXT_STRONG, 0.84)
        UI_ICON_ACTIVE = UI_TEXT_STRONG
        CHAT_TEXT = "#F6F8FF"
        CHAT_SURFACE_BG = mix(THEME.panel_bg, "#000000", 0.10)
    else:
        UI_TEXT_STRONG = TEXT
        UI_TEXT_MUTED = TEXT_MID
        UI_ICON_DIM = TEXT_DIM
        UI_ICON_ACTIVE = TEXT
        CHAT_TEXT = TEXT
        CHAT_SURFACE_BG = mix(THEME.surface_container, "#ffffff", 0.22)


apply_theme_globals()
