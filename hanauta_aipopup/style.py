from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from PyQt6.QtGui import QColor

from .runtime import (
    NOTIFICATION_CENTER_SETTINGS_FILE,
    load_theme_palette,
    relative_luminance,
)


THEME = load_theme_palette()


def _parse_qcolor(color: str) -> QColor:
    value = str(color or "").strip()
    if not value:
        return QColor("#000000")

    # Support CSS-like rgb()/rgba() strings (ThemePalette uses these).
    match = re.fullmatch(
        r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*(?:,\s*([0-9.]+)\s*)?\)",
        value,
        flags=re.IGNORECASE,
    )
    if match:
        red = float(match.group(1))
        green = float(match.group(2))
        blue = float(match.group(3))
        alpha_raw = match.group(4)

        def _clamp_byte(channel: float) -> int:
            return int(max(0.0, min(255.0, channel)))

        qcolor = QColor(_clamp_byte(red), _clamp_byte(green), _clamp_byte(blue))
        if alpha_raw is not None:
            alpha = float(alpha_raw)
            if alpha > 1.0:
                alpha = alpha / 255.0
            qcolor.setAlphaF(max(0.0, min(1.0, alpha)))
        return qcolor

    qcolor = QColor(value)
    if not qcolor.isValid() and not value.startswith("#") and len(value) == 6:
        qcolor = QColor(f"#{value}")
    if not qcolor.isValid():
        qcolor = QColor("#000000")
    return qcolor


def rgba(color: str, alpha: float) -> str:
    q = _parse_qcolor(color or "#000000")
    q.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return q.name(QColor.NameFormat.HexArgb)


def mix(color_a: str, color_b: str, amount: float) -> str:
    a = _parse_qcolor(color_a or "#000000")
    b = _parse_qcolor(color_b or "#000000")
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
    if not (_is_global_dark_theme_enabled() or dark_surface):
        # Light mode: keep floated panels and inputs closer to the palette background so dialogs
        # don't look "dimmed" compared to the web popup UI.
        PANEL_BG_FLOAT = rgba(THEME.background, 0.995)
        INPUT_BG = rgba(mix(THEME.background, "#ffffff", 0.55), 0.995)
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


def is_dark_theme() -> bool:
    theme = THEME
    try:
        dark_surface = relative_luminance(theme.surface_container_high) < 0.42
    except Exception:
        dark_surface = True
    return _is_global_dark_theme_enabled() or dark_surface


def _rgba_css(color: str, alpha: float) -> str:
    q = _parse_qcolor(color or "#000000")
    clamped = max(0.0, min(1.0, float(alpha)))
    return f"rgba({q.red()}, {q.green()}, {q.blue()}, {clamped:.2f})"


def popup_web_theme_css() -> str:
    theme = THEME
    dark = is_dark_theme()

    page_top = mix(theme.background, theme.primary, 0.10 if dark else 0.06)
    page_bottom = mix(theme.background, theme.surface_container, 0.14 if dark else 0.10)
    topbar_top = mix(theme.surface_container_high, theme.primary, 0.10 if dark else 0.06)
    topbar_bottom = mix(theme.surface_container, theme.background, 0.12 if dark else 0.06)
    hover_bg = _rgba_css(theme.primary, 0.10 if dark else 0.08)

    border = _rgba_css(theme.outline, 0.18 if dark else 0.26)
    border_soft = _rgba_css(theme.outline, 0.12 if dark else 0.18)
    card_bg = _rgba_css(theme.surface_container_high, 0.64 if dark else 0.72)
    chip_bg = _rgba_css(theme.surface_container, 0.72 if dark else 0.82)

    shadow = "rgba(0,0,0,0.22)" if dark else "rgba(0,0,0,0.12)"
    shadow_strong = "rgba(0,0,0,0.42)" if dark else "rgba(0,0,0,0.18)"

    accent_soft = _rgba_css(theme.primary, 0.18 if dark else 0.16)
    accent_soft_hover = _rgba_css(theme.primary, 0.24 if dark else 0.22)
    you_bg = _rgba_css(theme.secondary, 0.14 if dark else 0.12)
    you_border = _rgba_css(theme.secondary, 0.30 if dark else 0.28)

    text = UI_TEXT_STRONG
    text_mid = UI_TEXT_MUTED
    text_dim = UI_ICON_DIM

    return (
        f"""
/* Theme overrides (generated from Hanauta palette). */
:root {{
  color-scheme: {"dark" if dark else "light"};
  --bg: {page_bottom};
  --text: {text};
  --text-mid: {text_mid};
  --text-dim: {text_dim};
  --accent: {theme.primary};
  --accent-2: {theme.secondary};
  --border: {border};
  --border-2: {border_soft};
  --shadow: {shadow};
  --shadow-2: {shadow_strong};
}}

body {{
  color: var(--text);
  background:
    radial-gradient(circle at 50% 8%, {_rgba_css(theme.primary, 0.10 if dark else 0.08)}, transparent 26%),
    radial-gradient(circle at 18% 30%, {_rgba_css(theme.secondary, 0.08 if dark else 0.06)}, transparent 24%),
    linear-gradient(180deg, {page_top}, {page_bottom});
}}

.topbar {{
  border: 0;
  border-bottom: 1px solid var(--border);
  background:
    radial-gradient(circle at 20% 20%, {_rgba_css(theme.secondary, 0.10 if dark else 0.08)}, transparent 28%),
    radial-gradient(circle at 80% 10%, {_rgba_css(theme.primary, 0.10 if dark else 0.08)}, transparent 28%),
    linear-gradient(180deg, {topbar_top} 0%, {topbar_bottom} 100%);
  box-shadow: none;
}}

.topbar::after {{
  background:
    radial-gradient(circle at 40% 20%, {_rgba_css(theme.on_surface, 0.08 if dark else 0.06)}, transparent 44%),
    radial-gradient(circle at 70% 50%, {_rgba_css(theme.primary, 0.10 if dark else 0.08)}, transparent 52%);
  opacity: {0.60 if dark else 0.42};
}}

.brand .logo {{
  color: var(--accent);
  background: {chip_bg};
  border: 1px solid var(--border-2);
  box-shadow: inset 0 1px 0 {_rgba_css(theme.on_surface, 0.10 if dark else 0.06)};
}}

.brand .status {{
  color: var(--text-dim);
}}

.icon-btn {{
  color: var(--text);
}}

.icon-btn:hover {{
  background: {hover_bg};
}}

.info-dot {{
  color: var(--text);
  background: {chip_bg};
  border: 1px solid var(--border);
}}

.info-tip {{
  color: var(--text);
  background: {_rgba_css(theme.surface_container, 0.94 if dark else 0.96)};
  border: 1px solid var(--border);
  box-shadow: 0 18px 40px var(--shadow-2);
}}

.tip-title {{
  color: var(--text);
}}

.tip-line {{
  color: var(--text-mid);
}}

.body {{
  border: 0;
  background: {_rgba_css(theme.surface_container, 0.44 if dark else 0.62)};
}}

.backend-pill {{
  background: {chip_bg};
  border: 1px solid var(--border);
  color: var(--text);
}}

.backend-pill.active {{
  background: {accent_soft};
  border-color: {_rgba_css(theme.primary, 0.42 if dark else 0.38)};
  color: var(--text);
}}

.avatar {{
  background: {chip_bg};
  border: 1px solid var(--border);
  color: var(--text);
}}

.bubble {{
  border: 1px solid var(--border);
  background: {card_bg};
  box-shadow: 0 8px 18px var(--shadow);
}}

.bubble.you {{
  background: {you_bg};
  border-color: {you_border};
}}

.meta {{
  color: var(--text-mid);
}}

.meta .name {{
  color: var(--text);
}}

.meta .time {{
  color: var(--text-dim);
}}

.body-text {{
  color: var(--text);
}}

.composer {{
  background: {chip_bg};
  border-top: 1px solid var(--border-2);
}}

.attachment-chip {{
  background: {card_bg};
  border: 1px solid var(--border);
  color: var(--text);
}}

.attachment-remove {{
  color: var(--text-dim);
}}

.composer textarea {{
  background: {card_bg};
  color: var(--text);
}}

.send-btn {{
  background: {accent_soft};
  color: {theme.active_text};
}}

.send-btn:hover {{
  background: {accent_soft_hover};
}}

.send-btn.secondary {{
  background: transparent;
  color: var(--text);
}}

.send-btn.secondary:hover {{
  background: {hover_bg};
}}

.voice-shell {{
  border: 1px solid var(--border);
  background:
    radial-gradient(circle at 50% 8%, {_rgba_css(theme.primary, 0.10 if dark else 0.08)}, transparent 22%),
    linear-gradient(180deg, {topbar_top} 0%, {topbar_bottom} 100%);
}}

.voice-nav-btn {{
  border: 1px solid var(--border);
  background: linear-gradient(180deg, {_rgba_css(theme.on_surface, 0.08 if dark else 0.06)}, {_rgba_css(theme.on_surface, 0.04 if dark else 0.03)});
}}

.voice-card {{
  border: 1px solid var(--border);
  background: {chip_bg};
}}

.voice-card .label {{
  color: var(--text-dim);
}}

.voice-card .value {{
  color: var(--text);
}}
""".strip()
        + "\n"
    )
