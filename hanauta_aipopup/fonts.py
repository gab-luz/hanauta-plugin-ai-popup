from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase

from .runtime import APP_DIR


def load_ui_font() -> str:
    font_dir = APP_DIR.parent / "assets" / "fonts"
    if QFont("Rubik").exactMatch():
        return "Rubik"
    for name in (
        "Rubik-VariableFont_wght.ttf",
        "Rubik-Italic-VariableFont_wght.ttf",
        "Inter-Regular.ttf",
        "Inter.ttf",
    ):
        font_id = QFontDatabase.addApplicationFont(str(font_dir / name))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    return "Rubik"


def _is_rubik_font(ui_font: str) -> bool:
    return "rubik" in (ui_font or "").strip().lower()


def button_css_weight(ui_font: str) -> int:
    return 500 if _is_rubik_font(ui_font) else 600


def load_material_icon_font() -> str:
    font_dir = APP_DIR.parent / "assets" / "fonts"
    for name in (
        "MaterialIcons-Regular.ttf",
        "MaterialIconsOutlined-Regular.otf",
        "MaterialSymbolsOutlined.ttf",
        "MaterialSymbolsRounded.ttf",
    ):
        font_id = QFontDatabase.addApplicationFont(str(font_dir / name))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    return "Material Icons"

