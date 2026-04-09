#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import html
import importlib
import importlib.util
import json
import logging
import os
import shlex
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import wave
import zipfile
import zlib
from base64 import b64decode
from dataclasses import dataclass, field
import faulthandler
from pathlib import Path
from urllib import request, error
from urllib.parse import parse_qs, quote, unquote, urlparse

# Qt WebEngine can crash on some Linux/GBM GPU stacks. Use conservative flags only.
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
_extra_flags = [
    "--disable-gpu",
    "--disable-features=UseSkiaRenderer,Vulkan",
]
for _flag in _extra_flags:
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags

from cryptography.fernet import Fernet, InvalidToken
from PyQt6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, QThread, Qt, QTimer, QUrl, pyqtProperty, pyqtSignal, qInstallMessageHandler
from PyQt6.QtGui import QColor, QCursor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QMenu,
    QVBoxLayout,
    QWidget,
)
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    QT_MULTIMEDIA_AVAILABLE = True
except Exception:
    QAudioOutput = object  # type: ignore[assignment]
    QMediaPlayer = object  # type: ignore[assignment]
    QT_MULTIMEDIA_AVAILABLE = False
try:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:
    QWebEnginePage = object  # type: ignore[assignment]
    QWebEngineSettings = object  # type: ignore[assignment]
    QWebEngineView = object  # type: ignore[assignment]
    WEBENGINE_AVAILABLE = False

PLUGIN_ROOT = Path(__file__).resolve().parent


def _resolve_hanauta_src() -> Path:
    env_hint = Path(str(os.environ.get("HANAUTA_SRC", "")).strip()).expanduser()
    candidates: list[Path] = []
    if str(env_hint).strip():
        candidates.append(env_hint)
    candidates.append(Path.home() / ".config" / "i3" / "hanauta" / "src")
    try:
        candidates.append(PLUGIN_ROOT.parents[2])
    except Exception:
        pass
    for parent in PLUGIN_ROOT.parents:
        candidates.append(parent / "hanauta" / "src")
        candidates.append(parent / "src")
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            resolved = candidate.expanduser()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if (resolved / "pyqt" / "shared" / "theme.py").exists():
            return resolved
    return Path.home() / ".config" / "i3" / "hanauta" / "src"


APP_DIR = _resolve_hanauta_src()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from pyqt.shared.theme import load_theme_palette, palette_mtime, relative_luminance
from pyqt.shared.button_helpers import create_close_button
try:
    from pyqt.shared.plugin_bridge import trigger_fullscreen_alert
except Exception:
    def trigger_fullscreen_alert(title: str, body: str, severity: str = "discrete") -> bool:
        del title, body, severity
        return False

THEME = load_theme_palette()
AI_ASSETS_DIR = (
    PLUGIN_ROOT / "assets"
    if (PLUGIN_ROOT / "assets" / "backend-icons").exists()
    else APP_DIR / "pyqt" / "ai-popup" / "assets"
)
BACKEND_ICONS_DIR = AI_ASSETS_DIR / "backend-icons"
AI_STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "ai-popup"
BACKEND_SETTINGS_FILE = AI_STATE_DIR / "backend_settings.json"
SECURE_DB_FILE = AI_STATE_DIR / "secure_store.sqlite3"
SECURE_KEY_FILE = AI_STATE_DIR / "secure_store.key"
IMAGE_OUTPUT_DIR = AI_STATE_DIR / "generated-images"
TTS_MODELS_DIR = AI_STATE_DIR / "tts-models"
TTS_OUTPUT_DIR = AI_STATE_DIR / "tts-audio"
CHARACTER_LIBRARY_FILE = AI_STATE_DIR / "characters.json"
CHARACTER_AVATARS_DIR = AI_STATE_DIR / "characters-avatars"
NOTIFICATION_CENTER_STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "notification-center"
NOTIFICATION_CENTER_SETTINGS_FILE = NOTIFICATION_CENTER_STATE_DIR / "settings.json"
KOKORO_ONNX_REPO = "onnx-community/Kokoro-82M-ONNX"
POCKET_ONNX_REPO = "KevinAHM/pocket-tts-onnx"
KOKORO_TTS_RELEASE_REPO = "gab-luz/hanauta"
KOKORO_TTS_RELEASE_TAG = "TTS"
KOKORO_TTS_RELEASE_ASSET = "kokorotts-quantized-bundle.zip"
KOKORO_TTS_RELEASE_URL = (
    f"https://github.com/{KOKORO_TTS_RELEASE_REPO}/releases/download/"
    f"{KOKORO_TTS_RELEASE_TAG}/{KOKORO_TTS_RELEASE_ASSET}"
)
_KOKORO_RUNTIME_READY = False
AI_POPUP_LOG_FILE = AI_STATE_DIR / "ai_popup.log"
AI_POPUP_CRASH_FILE = AI_STATE_DIR / "ai_popup.crash.log"
KOKORO_SYNTH_LOG_FILE = AI_STATE_DIR / "kokoro_synth_worker.log"


LOGGER = logging.getLogger("hanauta.ai_popup")


def _setup_diagnostics() -> None:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not LOGGER.handlers:
        LOGGER.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(AI_POPUP_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        LOGGER.addHandler(file_handler)
        LOGGER.addHandler(stream_handler)
    try:
        crash_fp = open(AI_POPUP_CRASH_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=crash_fp, all_threads=True)
        for sig in (signal.SIGSEGV, signal.SIGABRT, signal.SIGBUS, signal.SIGILL, signal.SIGFPE):
            try:
                faulthandler.register(sig, file=crash_fp, all_threads=True, chain=True)
            except Exception:
                pass
    except Exception as exc:
        LOGGER.warning("Failed to enable faulthandler crash logging: %s", exc)

    def _excepthook(exc_type, exc, tb) -> None:
        LOGGER.error("Uncaught exception", exc_info=(exc_type, exc, tb))
        try:
            traceback.print_exception(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _excepthook

    def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
        LOGGER.error(
            "Unhandled thread exception in %s",
            args.thread.name if args.thread else "unknown-thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    try:
        threading.excepthook = _threading_excepthook
    except Exception:
        pass

    def _qt_message_handler(mode, context, message) -> None:
        try:
            file_name = getattr(context, "file", "") or ""
            line = int(getattr(context, "line", 0) or 0)
            category = getattr(context, "category", "") or ""
            prefix = f"Qt[{category}] {file_name}:{line}".strip()
        except Exception:
            prefix = "Qt"
        text = f"{prefix} {message}"
        LOGGER.warning(text)

    try:
        qInstallMessageHandler(_qt_message_handler)
    except Exception as exc:
        LOGGER.warning("Failed to install Qt message handler: %s", exc)

    LOGGER.info("Diagnostics initialized. Log file: %s", AI_POPUP_LOG_FILE)


_setup_diagnostics()


def rgba(color: str, alpha: float) -> str:
    q = QColor(color)
    q.setAlphaF(max(0.0, min(1.0, alpha)))
    return q.name(QColor.NameFormat.HexArgb)


def mix(color_a: str, color_b: str, amount: float) -> str:
    a = QColor(color_a)
    b = QColor(color_b)
    t = max(0.0, min(1.0, amount))
    r = round(a.red() + (b.red() - a.red()) * t)
    g = round(a.green() + (b.green() - a.green()) * t)
    b_ = round(a.blue() + (b.blue() - a.blue()) * t)
    return QColor(r, g, b_).name()


def _is_global_dark_theme_enabled() -> bool:
    try:
        raw = NOTIFICATION_CENTER_SETTINGS_FILE.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception:
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


def load_ui_font() -> str:
    font_dir = APP_DIR.parent / "assets" / "fonts"
    if QFont("Rubik").exactMatch():
        return "Rubik"
    for name in ("Rubik-VariableFont_wght.ttf", "Rubik-Italic-VariableFont_wght.ttf", "Inter-Regular.ttf", "Inter.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(font_dir / name))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    return "Rubik"


def _is_rubik_font(ui_font: str) -> bool:
    return "rubik" in (ui_font or "").strip().lower()


def _button_qfont_weight(ui_font: str) -> QFont.Weight:
    return QFont.Weight.Medium if _is_rubik_font(ui_font) else QFont.Weight.DemiBold


def _button_css_weight(ui_font: str) -> int:
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


@dataclass
class BackendProfile:
    key: str
    label: str
    provider: str
    model: str
    host: str
    icon_name: str
    needs_api_key: bool = False
    launchable: bool = False


@dataclass
class SourceChipData:
    text: str


@dataclass
class ChatItemData:
    role: str
    title: str
    body: str
    meta: str = ""
    chips: list[SourceChipData] = field(default_factory=list)
    pending: bool = False
    audio_path: str = ""


@dataclass
class CharacterCard:
    id: str
    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_message: str = ""
    message_example: str = ""
    system_prompt: str = ""
    avatar_path: str = ""
    source_path: str = ""
    source_type: str = ""


class SurfaceFrame(QFrame):
    def __init__(self, bg: str = CARD_BG, border: str = BORDER_SOFT, radius: int = 24, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: {radius}px;
            }}
            QLabel {{
                color: {TEXT};
            }}
            """
        )


class FadeCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._offset = 0

    def get_offset(self) -> int:
        return self._offset

    def set_offset(self, value: int) -> None:
        self._offset = value
        self.setContentsMargins(0, value, 0, 0)

    yOffset = pyqtProperty(int, fget=get_offset, fset=set_offset)


class ChatInputEdit(QPlainTextEdit):
    send_requested = pyqtSignal()

    def __init__(self, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min_height = 48
        self._max_height = 122
        self.setFont(QFont(ui_font, 12))
        self.setPlaceholderText('Message the model...  Enter to send • Shift+Enter for newline')
        self.setTabChangesFocus(True)
        self.document().documentLayout().documentSizeChanged.connect(self._sync_height)
        self._sync_height()

    def _sync_height(self) -> None:
        doc_height = int(self.document().size().height())
        new_height = max(self._min_height, min(self._max_height, doc_height + 18))
        self.setFixedHeight(new_height)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
        QTimer.singleShot(0, self._sync_height)


class BackendPill(QPushButton):
    def __init__(self, profile: BackendProfile, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 40)
        self.setFont(QFont(ui_font, 11, _button_qfont_weight(ui_font)))
        self.setIcon(_backend_icon(profile.icon_name))
        self.setIconSize(QPixmap(18, 18).size())
        self.setText("")
        self.setToolTip(profile.label)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {rgba(CARD_BG_SOFT, 0.90)};
                border: 1px solid {BORDER_SOFT};
                border-radius: 20px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
            }}
            QPushButton:checked {{
                background: {ACCENT_SOFT};
                border: 1px solid {BORDER_ACCENT};
            }}
            QPushButton:disabled {{
                background: {rgba(CARD_BG_SOFT, 0.45)};
                border: 1px solid {rgba(BORDER_SOFT, 0.50)};
            }}
            """
        )


def _backend_icon_path(icon_name: str) -> Path | None:
    path = BACKEND_ICONS_DIR / f"{icon_name}.png"
    return path if path.exists() else None


def _backend_icon(icon_name: str) -> QIcon:
    path = _backend_icon_path(icon_name)
    if path is not None:
        return QIcon(str(path))
    placeholder = QPixmap(22, 22)
    placeholder.fill(Qt.GlobalColor.transparent)
    painter = QPainter(placeholder)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = placeholder.rect().adjusted(1, 1, -1, -1)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(rgba(ACCENT_SOFT, 0.92)))
    painter.drawRoundedRect(rect, 7, 7)
    painter.setPen(QColor(ACCENT))
    painter.setFont(QFont(load_ui_font(), 9, QFont.Weight.Black))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, icon_name[:2].upper())
    painter.end()
    return QIcon(placeholder)


def _path_text(value: object) -> str:
    return str(value).strip()


def _existing_path(value: object) -> Path | None:
    text = _path_text(value)
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.exists() else None


def _openai_compat_alive(host: str) -> bool:
    try:
        with request.urlopen(f"{_normalize_host_url(host)}/v1/models", timeout=1.2) as response:
            return response.status < 400
    except Exception:
        return False


def _apply_antialias_font(widget: QWidget) -> None:
    font = widget.font()
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    widget.setFont(font)
    for child in widget.findChildren(QWidget):
        child_font = child.font()
        child_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        child.setFont(child_font)


def load_backend_settings() -> dict[str, dict[str, object]]:
    try:
        return json.loads(BACKEND_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_backend_settings(settings: dict[str, dict[str, object]]) -> None:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _sanitize_character_id(name: str) -> str:
    slug = _safe_slug(name.lower())
    stamp = str(int(time.time() * 1000))
    return f"{slug}_{stamp}"


def _character_from_payload(payload: dict[str, object]) -> CharacterCard:
    return CharacterCard(
        id=str(payload.get("id", "")).strip() or _sanitize_character_id(str(payload.get("name", "character"))),
        name=str(payload.get("name", "Unnamed character")).strip() or "Unnamed character",
        description=str(payload.get("description", "")).strip(),
        personality=str(payload.get("personality", "")).strip(),
        scenario=str(payload.get("scenario", "")).strip(),
        first_message=str(payload.get("first_message", payload.get("first_mes", ""))).strip(),
        message_example=str(payload.get("message_example", payload.get("mes_example", ""))).strip(),
        system_prompt=str(payload.get("system_prompt", "")).strip(),
        avatar_path=str(payload.get("avatar_path", "")).strip(),
        source_path=str(payload.get("source_path", "")).strip(),
        source_type=str(payload.get("source_type", "")).strip(),
    )


def load_character_library() -> tuple[list[CharacterCard], str]:
    try:
        payload = json.loads(CHARACTER_LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [], ""
    cards_raw = payload.get("cards", [])
    cards: list[CharacterCard] = []
    if isinstance(cards_raw, list):
        for row in cards_raw:
            if isinstance(row, dict):
                cards.append(_character_from_payload(row))
    active_id = str(payload.get("active_id", "")).strip()
    if active_id and not any(card.id == active_id for card in cards):
        active_id = ""
    return cards, active_id


def save_character_library(cards: list[CharacterCard], active_id: str) -> None:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_id": active_id if any(card.id == active_id for card in cards) else "",
        "cards": [
            {
                "id": card.id,
                "name": card.name,
                "description": card.description,
                "personality": card.personality,
                "scenario": card.scenario,
                "first_message": card.first_message,
                "message_example": card.message_example,
                "system_prompt": card.system_prompt,
                "avatar_path": card.avatar_path,
                "source_path": card.source_path,
                "source_type": card.source_type,
            }
            for card in cards
        ],
    }
    CHARACTER_LIBRARY_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _decode_character_json_text(raw_text: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise ValueError("Empty character payload.")
    candidates = [text]
    if "%" in text:
        try:
            candidates.append(unquote(text))
        except Exception:
            pass
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    try:
        decoded = b64decode(text)
        decoded_text = decoded.decode("utf-8", errors="ignore").strip()
        if decoded_text:
            parsed = json.loads(decoded_text)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    raise ValueError("Could not decode character JSON payload.")


def _extract_tavern_png_payload(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG file.")
    offset = 8
    text_candidates: list[str] = []
    valid_keys = {b"chara", b"character", b"ccv3"}
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big", signed=False)
        chunk_type = data[offset + 4:offset + 8]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > len(data):
            break
        chunk = data[chunk_start:chunk_end]
        if chunk_type == b"tEXt":
            try:
                key, value = chunk.split(b"\x00", 1)
                if key in valid_keys:
                    text_candidates.append(value.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        elif chunk_type == b"zTXt":
            try:
                key, rest = chunk.split(b"\x00", 1)
                if key in valid_keys and rest:
                    compression = rest[0]
                    payload = rest[1:]
                    if compression == 0:
                        text_candidates.append(zlib.decompress(payload).decode("utf-8", errors="ignore"))
            except Exception:
                pass
        elif chunk_type == b"iTXt":
            try:
                parts = chunk.split(b"\x00", 5)
                if len(parts) == 6 and parts[0] in valid_keys:
                    compression_flag = parts[1][0] if parts[1] else 0
                    compression_method = parts[2][0] if parts[2] else 0
                    text_payload = parts[5]
                    if compression_flag == 1 and compression_method == 0:
                        text_payload = zlib.decompress(text_payload)
                    text_candidates.append(text_payload.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        offset = chunk_end + 4
    for candidate in text_candidates:
        try:
            return _decode_character_json_text(candidate)
        except Exception:
            continue
    raise ValueError("No TavernAI/KoboldCPP character payload found in PNG metadata.")


def _normalize_imported_character(payload: dict[str, object], source_path: Path, source_type: str) -> CharacterCard:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ValueError("Invalid character payload format.")
    name = str(data.get("name", payload.get("name", ""))).strip() or source_path.stem
    card = CharacterCard(
        id=_sanitize_character_id(name),
        name=name,
        description=str(data.get("description", payload.get("description", ""))).strip(),
        personality=str(data.get("personality", payload.get("personality", ""))).strip(),
        scenario=str(data.get("scenario", payload.get("scenario", ""))).strip(),
        first_message=str(data.get("first_mes", data.get("first_message", payload.get("first_mes", "")))).strip(),
        message_example=str(data.get("mes_example", data.get("message_example", payload.get("mes_example", "")))).strip(),
        system_prompt=str(
            data.get("system_prompt", data.get("post_history_instructions", payload.get("system_prompt", "")))
        ).strip(),
        source_path=str(source_path),
        source_type=source_type,
    )
    avatar_src: Path | None = None
    if source_path.suffix.lower() == ".png":
        avatar_src = source_path
    else:
        avatar_field = str(data.get("avatar", payload.get("avatar", ""))).strip()
        if avatar_field:
            guessed = Path(avatar_field).expanduser()
            if not guessed.is_absolute():
                guessed = source_path.parent / guessed
            if guessed.exists():
                avatar_src = guessed
    if avatar_src is not None and avatar_src.exists():
        CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        avatar_target = CHARACTER_AVATARS_DIR / f"{card.id}{avatar_src.suffix.lower() or '.png'}"
        try:
            shutil.copy2(str(avatar_src), str(avatar_target))
            card.avatar_path = str(avatar_target)
        except Exception:
            card.avatar_path = ""
    return card


def import_character_from_file(path: Path) -> CharacterCard:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Character JSON must be an object.")
        return _normalize_imported_character(payload, path, "json")
    if suffix == ".png":
        payload = _extract_tavern_png_payload(path)
        return _normalize_imported_character(payload, path, "png")
    raise ValueError("Unsupported character format. Use .json or .png")


def _character_compose_prompt(card: CharacterCard) -> str:
    sections: list[str] = []
    if card.system_prompt:
        sections.append(card.system_prompt)
    if card.description:
        sections.append(f"Description: {card.description}")
    if card.personality:
        sections.append(f"Personality: {card.personality}")
    if card.scenario:
        sections.append(f"Scenario: {card.scenario}")
    if card.first_message:
        sections.append(f"First message style: {card.first_message}")
    return "\n".join(section for section in sections if section.strip())

def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _cipher() -> Fernet:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not SECURE_KEY_FILE.exists():
        SECURE_KEY_FILE.write_bytes(Fernet.generate_key())
        _chmod_private(SECURE_KEY_FILE)
    key = SECURE_KEY_FILE.read_bytes()
    _chmod_private(SECURE_KEY_FILE)
    return Fernet(key)


def _secure_db() -> sqlite3.Connection:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(SECURE_DB_FILE)
    connection.execute("CREATE TABLE IF NOT EXISTS secrets (name TEXT PRIMARY KEY, payload BLOB NOT NULL)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, payload BLOB NOT NULL, created_at REAL NOT NULL)"
    )
    connection.commit()
    _chmod_private(SECURE_DB_FILE)
    return connection


def _encrypt_payload(payload: dict[str, object]) -> bytes:
    return _cipher().encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _decrypt_payload(blob: bytes) -> dict[str, object]:
    data = _cipher().decrypt(blob)
    value = json.loads(data.decode("utf-8"))
    return value if isinstance(value, dict) else {}


def secure_store_secret(name: str, value: str) -> None:
    connection = _secure_db()
    try:
        if value.strip():
            connection.execute(
                "INSERT INTO secrets(name, payload) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (name, _encrypt_payload({"value": value})),
            )
        else:
            connection.execute("DELETE FROM secrets WHERE name = ?", (name,))
        connection.commit()
    finally:
        connection.close()


def secure_load_secret(name: str) -> str:
    connection = _secure_db()
    try:
        row = connection.execute("SELECT payload FROM secrets WHERE name = ?", (name,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return ""
    try:
        payload = _decrypt_payload(row[0])
        return str(payload.get("value", ""))
    except (InvalidToken, json.JSONDecodeError, TypeError, ValueError):
        return ""


def secure_append_chat(item: ChatItemData) -> None:
    connection = _secure_db()
    try:
        connection.execute(
            "INSERT INTO chat_history(payload, created_at) VALUES(?, ?)",
            (
                _encrypt_payload(
                    {
                        "role": item.role,
                        "title": item.title,
                        "body": item.body,
                        "meta": item.meta,
                        "chips": [chip.text for chip in item.chips],
                        "audio_path": item.audio_path,
                    }
                ),
                time.time(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def secure_load_chat_history() -> list[ChatItemData]:
    connection = _secure_db()
    try:
        rows = connection.execute("SELECT payload FROM chat_history ORDER BY id ASC").fetchall()
    finally:
        connection.close()
    history: list[ChatItemData] = []
    for row in rows:
        try:
            payload = _decrypt_payload(row[0])
        except (InvalidToken, json.JSONDecodeError, TypeError, ValueError):
            continue
        chips_raw = payload.get("chips", [])
        chips = [SourceChipData(str(chip)) for chip in chips_raw if str(chip).strip()] if isinstance(chips_raw, list) else []
        history.append(
            ChatItemData(
                role=str(payload.get("role", "assistant")),
                title=str(payload.get("title", "")),
                body=str(payload.get("body", "")),
                meta=str(payload.get("meta", "")),
                chips=chips,
                audio_path=str(payload.get("audio_path", "")),
            )
        )
    return history


def secure_clear_chat_history() -> None:
    connection = _secure_db()
    try:
        connection.execute("DELETE FROM chat_history")
        connection.commit()
    finally:
        connection.close()


def send_desktop_notification(title: str, body: str) -> None:
    try:
        import subprocess

        LOGGER.debug("notify-send queued: title=%r body=%r", title, body)
        subprocess.Popen(
            ["notify-send", "-a", "Hanauta AI", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        LOGGER.exception("notify-send failed")


def _normalize_host_url(host: str) -> str:
    value = host.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


def _http_json(url: str, timeout: float = 10.0) -> dict[str, object] | list[object]:
    req = request.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict[str, object], timeout: float = 180.0) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"User-Agent": "Hanauta AI/1.0", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_bytes(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str] | None = None,
    timeout: float = 240.0,
) -> tuple[bytes, str]:
    body = json.dumps(payload).encode("utf-8")
    merged_headers = {
        "User-Agent": "Hanauta AI/1.0",
        "Content-Type": "application/json",
    }
    if headers:
        merged_headers.update(headers)
    req = request.Request(url, data=body, headers=merged_headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        content_type = str(response.headers.get("Content-Type", ""))
        return response.read(), content_type


def _safe_slug(value: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    compact = "_".join(part for part in raw.split("_") if part)
    return compact[:80] if compact else "audio"


def _write_wav_from_float32_mono(path: Path, samples: "np.ndarray", sample_rate: int = 24000) -> None:
    import numpy as np

    clipped = np.clip(samples.astype(np.float32), -1.0, 1.0)
    int16 = (clipped * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(int16.tobytes())


def _play_audio_file(audio_path: Path) -> None:
    commands = [
        ["pw-play", str(audio_path)],
        ["aplay", str(audio_path)],
        ["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", str(audio_path)],
    ]
    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if process.pid:
                return
        except Exception:
            continue


def _hf_resolve_url(repo_id: str, rel_path: str) -> str:
    clean_repo = repo_id.strip().strip("/")
    clean_file = rel_path.lstrip("/")
    return f"https://huggingface.co/{clean_repo}/resolve/main/{clean_file}?download=true"


def _download_file(
    url: str,
    destination: Path,
    timeout: float = 300.0,
    progress_cb: callable | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
            with request.urlopen(req, timeout=timeout) as response, destination.open("wb") as handle:
                total = int(response.headers.get("Content-Length", "0") or 0)
                written = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
                    if callable(progress_cb):
                        progress_cb(written, total)
            return
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(min(4.0, 0.8 * attempt))


def _download_hf_files(
    repo_id: str,
    files: list[str],
    destination_root: Path,
    progress_cb: callable | None = None,
) -> None:
    total_files = max(1, len(files))
    completed = 0
    for rel_path in files:
        destination = destination_root / rel_path
        if destination.exists() and destination.stat().st_size > 0:
            completed += 1
            if callable(progress_cb):
                progress_cb(completed, total_files, rel_path)
            continue
        _download_file(_hf_resolve_url(repo_id, rel_path), destination)
        completed += 1
        if callable(progress_cb):
            progress_cb(completed, total_files, rel_path)


def _download_and_extract_zip_bundle(
    bundle_url: str,
    destination_root: Path,
    progress_cb: callable | None = None,
) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hanauta-ai-tts-") as tmp:
        archive_path = Path(tmp) / "bundle.zip"

        def _bundle_progress(written: int, total: int) -> None:
            if not callable(progress_cb):
                return
            if total > 0:
                ratio = max(0.0, min(1.0, written / float(total)))
                progress_cb(int(ratio * 80), 100, "Downloading bundle")
            else:
                progress_cb(30, 100, "Downloading bundle")

        _download_file(bundle_url, archive_path, timeout=600.0, progress_cb=_bundle_progress)
        if callable(progress_cb):
            progress_cb(85, 100, "Extracting bundle")
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(destination_root)
        entries = [entry for entry in destination_root.iterdir() if entry.name not in {".DS_Store", "__MACOSX"}]
        if len(entries) == 1 and entries[0].is_dir():
            nested_root = entries[0]
            for child in list(nested_root.iterdir()):
                target = destination_root / child.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        target.unlink(missing_ok=True)
                shutil.move(str(child), str(target))
            shutil.rmtree(nested_root, ignore_errors=True)
        if callable(progress_cb):
            progress_cb(100, 100, "Bundle extracted")


def _kokoro_required_files(voice_name: str) -> list[str]:
    voice = voice_name.strip() or "af_bella"
    return [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "onnx/model_q8f16.onnx",
        f"voices/{voice}.bin",
    ]


def _pocket_required_files() -> list[str]:
    return [
        "pocket_tts_onnx.py",
        "tokenizer.model",
        "reference_sample.wav",
        "onnx/mimi_encoder.onnx",
        "onnx/text_conditioner.onnx",
        "onnx/flow_lm_main_int8.onnx",
        "onnx/flow_lm_flow_int8.onnx",
        "onnx/mimi_decoder_int8.onnx",
    ]


def _list_kokoro_voice_names(model_dir: Path) -> list[str]:
    voices_dir = model_dir / "voices"
    names: list[str] = []
    if voices_dir.exists():
        for voice_file in sorted(voices_dir.glob("*.bin")):
            names.append(voice_file.stem)
    if names:
        return names
    return [
        "af_bella",
        "af_nicole",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_michael",
        "bf_emma",
        "bf_isabella",
        "bm_george",
        "bm_lewis",
        "pf_dora",
        "pm_alex",
        "pm_santa",
    ]


def _default_tts_mode(payload: dict[str, object]) -> str:
    mode = str(payload.get("tts_mode", "")).strip().lower()
    if mode in {"local_onnx", "external_api"}:
        return mode
    host = str(payload.get("host", "")).strip()
    return "external_api" if host else "local_onnx"


def _default_tts_repo(profile: BackendProfile, payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_model_repo", "")).strip()
    if configured:
        return configured
    if profile.key == "pockettts":
        return POCKET_ONNX_REPO
    return KOKORO_ONNX_REPO


def _default_tts_bundle_url(profile: BackendProfile, payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_bundle_url", "")).strip()
    if configured:
        return configured
    if profile.key == "kokorotts":
        return KOKORO_TTS_RELEASE_URL
    return ""


def _default_tts_model_dir(profile: BackendProfile, payload: dict[str, object]) -> Path:
    configured = str(payload.get("binary_path", "")).strip()
    if configured:
        return Path(configured).expanduser()
    return TTS_MODELS_DIR / profile.key


def _ensure_tts_assets(
    profile: BackendProfile,
    payload: dict[str, object],
    *,
    download_if_missing: bool,
    progress_cb: callable | None = None,
) -> tuple[Path, str]:
    model_dir = _default_tts_model_dir(profile, payload)
    repo_id = _default_tts_repo(profile, payload)
    voice = str(payload.get("model", profile.model)).strip() or profile.model
    if profile.key == "pockettts":
        required = _pocket_required_files()
    else:
        required = _kokoro_required_files(voice)
    missing = [rel for rel in required if not (model_dir / rel).exists()]
    bundle_url = _default_tts_bundle_url(profile, payload)
    if missing and download_if_missing and bundle_url:
        _download_and_extract_zip_bundle(bundle_url, model_dir, progress_cb=progress_cb)
        missing = [rel for rel in required if not (model_dir / rel).exists()]
    if missing and not download_if_missing:
        raise RuntimeError(f"Missing model files in {model_dir}: {', '.join(missing[:3])}")
    if missing:
        _download_hf_files(repo_id, required, model_dir, progress_cb=progress_cb)
    return model_dir, voice


def _generate_kokoro_audio(
    model_dir: Path,
    voice: str,
    text: str,
    output_path: Path,
) -> None:
    _ensure_kokoro_runtime_dependencies()
    import numpy as np
    import onnxruntime as rt
    from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
    from kokoro_onnx.tokenizer import Tokenizer

    session = rt.InferenceSession(
        str(model_dir / "onnx" / "model_q8f16.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = Tokenizer(vocab={})
    phonemes = tokenizer.phonemize(text, "en-us")
    phonemes = phonemes[:MAX_PHONEME_LENGTH]
    token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
    if token_ids.size == 0:
        raise RuntimeError("No phonemes generated for input text.")
    voice_file = model_dir / "voices" / f"{voice}.bin"
    voice_data = np.fromfile(str(voice_file), dtype=np.float32)
    if voice_data.size == 0 or (voice_data.size % 256) != 0:
        raise RuntimeError(f"Voice file is not valid: {voice_file}")
    style = voice_data.reshape(-1, 1, 256)
    style_index = min(int(token_ids.size), int(style.shape[0]) - 1)
    style_vec = style[style_index]
    padded_tokens = [[0, *token_ids.tolist(), 0]]
    input_names = {entry.name for entry in session.get_inputs()}
    if "input_ids" in input_names:
        inputs = {
            "input_ids": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.array([1], dtype=np.int32),
        }
    else:
        inputs = {
            "tokens": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.ones(1, dtype=np.float32),
        }
    audio = session.run(None, inputs)[0].squeeze()
    if not isinstance(audio, np.ndarray) or audio.size == 0:
        raise RuntimeError("Kokoro ONNX returned empty audio.")
    _write_wav_from_float32_mono(output_path, audio.astype(np.float32), SAMPLE_RATE)


def _kokoro_synth_script_path() -> Path:
    return AI_STATE_DIR / "kokoro_synth_worker.py"


def _ensure_kokoro_synth_script() -> Path:
    script_path = _kokoro_synth_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import faulthandler
import os
from pathlib import Path
import traceback
import numpy as np
import onnxruntime as rt
from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
from kokoro_onnx.tokenizer import Tokenizer
import wave

STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "ai-popup"
LOG_PATH = STATE_DIR / "kokoro_synth_worker.log"


def _log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(message.rstrip() + "\\n")


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    audio = np.clip(samples.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def main() -> int:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("ORT_NUM_THREADS", "1")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    crash_fp = LOG_PATH.open("a", encoding="utf-8")
    faulthandler.enable(file=crash_fp, all_threads=True)
    _log("=== kokoro synth worker started ===")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser()
    output_path = Path(args.output).expanduser()
    _log(f"model_dir={model_dir}")
    _log(f"voice={args.voice}")
    _log(f"text_len={len(args.text or '')}")

    try:
        so = rt.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        so.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_BASIC

        _log("creating ONNX session")
        session = rt.InferenceSession(
            str(model_dir / "onnx" / "model_q8f16.onnx"),
            sess_options=so,
            providers=["CPUExecutionProvider"],
        )
        _log("session created")

        tokenizer = Tokenizer(vocab={})
        phonemes = tokenizer.phonemize(args.text, "en-us")[:MAX_PHONEME_LENGTH]
        token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
        if token_ids.size == 0:
            raise RuntimeError("No phonemes generated for input text.")
        _log(f"token_count={int(token_ids.size)}")

        voice_file = model_dir / "voices" / f"{args.voice}.bin"
        voice_data = np.fromfile(str(voice_file), dtype=np.float32)
        if voice_data.size == 0 or (voice_data.size % 256) != 0:
            raise RuntimeError(f"Voice file is not valid: {voice_file}")
        _log(f"voice_floats={int(voice_data.size)}")

        style = voice_data.reshape(-1, 1, 256)
        style_index = min(int(token_ids.size), int(style.shape[0]) - 1)
        style_vec = style[style_index]
        padded_tokens = [[0, *token_ids.tolist(), 0]]

        session_inputs = {entry.name: entry for entry in session.get_inputs()}
        input_names = set(session_inputs.keys())
        speed_input = session_inputs.get("speed")
        speed_dtype = str(getattr(speed_input, "type", "") or "").lower() if speed_input is not None else ""
        if "input_ids" in input_names:
            inputs = {
                "input_ids": padded_tokens,
                "style": np.array(style_vec, dtype=np.float32),
            }
        else:
            inputs = {
                "tokens": padded_tokens,
                "style": np.array(style_vec, dtype=np.float32),
            }
        if "speed" in input_names:
            if "int" in speed_dtype:
                inputs["speed"] = np.array([1], dtype=np.int32)
            else:
                inputs["speed"] = np.ones(1, dtype=np.float32)

        _log("running session")
        audio = session.run(None, inputs)[0].squeeze()
        if not isinstance(audio, np.ndarray) or audio.size == 0:
            raise RuntimeError("Kokoro ONNX returned empty audio.")
        write_wav(output_path, audio.astype(np.float32), SAMPLE_RATE)
        _log(f"wrote output={output_path}")
        return 0
    except Exception as exc:
        _log(f"exception={exc}")
        _log(traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _generate_kokoro_audio_subprocess(
    model_dir: Path,
    voice: str,
    text: str,
    output_path: Path,
) -> None:
    script_path = _ensure_kokoro_synth_script()
    command = [
        sys.executable,
        str(script_path),
        "--model-dir",
        str(model_dir),
        "--voice",
        voice,
        "--text",
        text,
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or "no output"
        if completed.returncode == -11:
            detail = (
                f"{detail}. Native segmentation fault in Kokoro worker. "
                f"See {KOKORO_SYNTH_LOG_FILE} for last checkpoint."
            )
        raise RuntimeError(
            f"Kokoro synth subprocess failed (exit {completed.returncode}). Detail: {detail}"
        )
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("Kokoro synth subprocess did not produce audio output.")


def _ensure_kokoro_runtime_dependencies() -> None:
    global _KOKORO_RUNTIME_READY
    if _KOKORO_RUNTIME_READY:
        return
    requirements: list[tuple[str, str]] = [
        ("onnxruntime", "onnxruntime>=1.19.0"),
        ("kokoro_onnx", "kokoro-onnx>=0.4.9"),
    ]
    missing_specs: list[str] = []
    for module_name, package_spec in requirements:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing_specs.append(package_spec)
    if missing_specs:
        attempts: list[list[str]] = []
        uv_bin = shutil.which("uv")
        if uv_bin:
            attempts.append([uv_bin, "pip", "install", "--python", sys.executable, *missing_specs])
        attempts.append([sys.executable, "-m", "pip", "install", *missing_specs])
        attempts.append([sys.executable, "-m", "pip", "install", "--user", *missing_specs])
        errors: list[str] = []
        installed = False
        for command in attempts:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                installed = True
                break
            detail = (completed.stderr or completed.stdout or "").strip()
            errors.append(f"{' '.join(command)} => {detail or 'unknown error'}")
            if command[:3] == [sys.executable, "-m", "pip"]:
                ensure = subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if ensure.returncode == 0:
                    retry = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if retry.returncode == 0:
                        installed = True
                        break
                    retry_detail = (retry.stderr or retry.stdout or "").strip()
                    errors.append(f"{' '.join(command)} (after ensurepip) => {retry_detail or 'unknown error'}")
        if not installed:
            details = " | ".join(errors[-3:]) if errors else "no installer command available"
            raise RuntimeError(
                "Missing optional Kokoro runtime dependencies and automatic install failed. "
                f"Attempts: {details}"
            )
        for module_name, _ in requirements:
            importlib.import_module(module_name)
    _KOKORO_RUNTIME_READY = True


def _generate_pocket_audio(
    model_dir: Path,
    text: str,
    output_path: Path,
    voice_reference: str,
) -> None:
    import numpy as np

    script_path = model_dir / "pocket_tts_onnx.py"
    if not script_path.exists():
        raise RuntimeError("PocketTTS ONNX script not found in model directory.")
    spec = importlib.util.spec_from_file_location("hanauta_pocket_tts_onnx", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load PocketTTS ONNX module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = module.PocketTTSOnnx(
        models_dir=str(model_dir / "onnx"),
        tokenizer_path=str(model_dir / "tokenizer.model"),
        precision="int8",
        device="auto",
    )
    reference = Path(voice_reference).expanduser() if voice_reference.strip() else (model_dir / "reference_sample.wav")
    if not reference.exists():
        raise RuntimeError(f"PocketTTS voice reference not found: {reference}")
    audio = engine.generate(text, voice=str(reference))
    if not isinstance(audio, np.ndarray) or audio.size == 0:
        raise RuntimeError("PocketTTS ONNX returned empty audio.")
    _write_wav_from_float32_mono(output_path, audio.astype(np.float32), 24000)


def synthesize_tts(
    profile: BackendProfile,
    payload: dict[str, object],
    text: str,
) -> tuple[Path, str]:
    mode = _default_tts_mode(payload)
    voice = str(payload.get("model", profile.model)).strip() or profile.model
    stamp = int(time.time() * 1000)
    out_name = f"{profile.key}_{stamp}_{_safe_slug(voice)}.wav"
    output_path = TTS_OUTPUT_DIR / out_name
    if mode == "external_api":
        host = str(payload.get("host", "")).strip()
        if not host:
            raise RuntimeError("External API mode requires a host URL.")
        api_key = secure_load_secret(f"{profile.key}:api_key").strip()
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = f"{_normalize_host_url(host)}/v1/audio/speech"
        body, content_type = _http_post_bytes(
            url,
            {"model": str(payload.get("tts_remote_model", payload.get("model", profile.model))).strip() or "tts-1", "input": text, "voice": voice},
            headers=headers,
            timeout=240.0,
        )
        if "application/json" in content_type.lower():
            parsed = json.loads(body.decode("utf-8"))
            audio_blob = parsed.get("audio")
            if isinstance(audio_blob, str) and audio_blob.strip():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b64decode(audio_blob))
            else:
                raise RuntimeError("External API returned JSON without audio payload.")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(body)
        return output_path, "external-api"

    model_dir, resolved_voice = _ensure_tts_assets(
        profile, payload, download_if_missing=bool(payload.get("tts_download_if_missing", True))
    )
    if profile.key == "pockettts":
        _generate_pocket_audio(
            model_dir,
            text,
            output_path,
            str(payload.get("tts_voice_reference", "")).strip(),
        )
    else:
        if profile.key == "kokorotts":
            _generate_kokoro_audio_subprocess(model_dir, resolved_voice, text, output_path)
        else:
            _generate_kokoro_audio(model_dir, resolved_voice, text, output_path)
    return output_path, "local-onnx"


def validate_backend(profile: BackendProfile, payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    model = str(payload.get("model", "")).strip()
    api_key = secure_load_secret(f"{profile.key}:api_key")
    binary_path = _existing_path(payload.get("binary_path"))
    gguf_path = _existing_path(payload.get("gguf_path"))
    if not model:
        return False, "Model is required."
    if profile.needs_api_key and not api_key:
        return False, "API key is required."
    if not profile.needs_api_key and not host and not profile.launchable:
        return False, "Host is required."

    if profile.key == "koboldcpp":
        if binary_path is None:
            return False, "KoboldCpp binary path is required."
        if gguf_path is None:
            return False, "Select a GGUF model for KoboldCpp."
        if host and _openai_compat_alive(host):
            return True, "KoboldCpp is reachable."
        return True, "Launch config saved. Click the KoboldCpp icon to start it."

    if profile.provider == "tts_local":
        mode = _default_tts_mode(payload)
        if mode == "external_api":
            if not host:
                return False, "External API mode requires a host."
            return True, "External TTS endpoint saved."
        model_dir = _default_tts_model_dir(profile, payload)
        if profile.key == "pockettts":
            required = _pocket_required_files()
        else:
            voice = str(payload.get("model", profile.model)).strip() or profile.model
            required = _kokoro_required_files(voice)
        missing = [rel for rel in required if not (model_dir / rel).exists()]
        if not missing:
            return True, "Local ONNX model directory looks valid."
        if bool(payload.get("tts_download_if_missing", True)):
            return True, "Local ONNX mode is ready to download missing model files."
        preview = ", ".join(missing[:2])
        suffix = "..." if len(missing) > 2 else ""
        return False, f"Missing local ONNX files: {preview}{suffix}"

    if profile.provider == "sdwebui":
        url = _normalize_host_url(host)
        try:
            response = _http_json(f"{url}/sdapi/v1/samplers", timeout=3.0)
            if not isinstance(response, list):
                return False, "SD WebUI did not return samplers."
        except Exception:
            return False, "SD WebUI host did not respond."
        return True, "SD WebUI connection looks valid."

    if profile.provider == "openai_compat":
        url = _normalize_host_url(host)
        try:
            with request.urlopen(f"{url}/v1/models", timeout=2.5) as response:
                if response.status >= 400:
                    return False, f"HTTP {response.status}"
        except Exception:
            return False, "Host did not respond."
    elif profile.key == "ollama":
        url = _normalize_host_url(host)
        try:
            with request.urlopen(f"{url}/api/tags", timeout=2.5) as response:
                if response.status >= 400:
                    return False, f"HTTP {response.status}"
        except Exception:
            return False, "Host did not respond."

    return True, "Connection settings look valid."


def _start_kokoro_server(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_kokoro_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    if source == "auto":
        payload["tts_server_command"] = shlex.join(command)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Unable to start Kokoro server: {exc}"
    payload["tts_server_pid"] = int(process.pid or 0)
    return True, f"Kokoro server started with: {' '.join(command)}"


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _host_reachable(host: str, timeout: float = 1.2) -> bool:
    text = host.strip()
    if not text:
        return False
    parsed = urlparse(text if "://" in text else f"http://{text}")
    hostname = parsed.hostname or ""
    port = int(parsed.port or 80)
    if not hostname:
        return False
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def _parse_host_port(host: str) -> tuple[str, int]:
    raw = host.strip()
    if not raw:
        return "127.0.0.1", 8880
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    hostname = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 8880)
    return hostname, port


def _kokoro_local_server_script_path() -> Path:
    return AI_STATE_DIR / "kokoro_local_server.py"


def _ensure_kokoro_local_server_script() -> Path:
    script_path = _kokoro_local_server_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnxruntime as rt
from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
from kokoro_onnx.tokenizer import Tokenizer


def _synth(model_dir: Path, text: str, voice: str) -> bytes:
    session = rt.InferenceSession(
        str(model_dir / "onnx" / "model_q8f16.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = Tokenizer(vocab={})
    phonemes = tokenizer.phonemize(text, "en-us")[:MAX_PHONEME_LENGTH]
    token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
    if token_ids.size == 0:
        raise RuntimeError("No phonemes generated.")
    voice_file = model_dir / "voices" / f"{voice}.bin"
    if not voice_file.exists():
        raise RuntimeError(f"Voice not found: {voice_file}")
    voice_data = np.fromfile(str(voice_file), dtype=np.float32)
    if voice_data.size == 0 or (voice_data.size % 256) != 0:
        raise RuntimeError(f"Invalid voice file: {voice_file}")
    style = voice_data.reshape(-1, 1, 256)
    style_idx = min(int(token_ids.size), int(style.shape[0]) - 1)
    style_vec = style[style_idx]
    padded_tokens = [[0, *token_ids.tolist(), 0]]
    input_names = {entry.name for entry in session.get_inputs()}
    if "input_ids" in input_names:
        inputs = {
            "input_ids": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.array([1], dtype=np.int32),
        }
    else:
        inputs = {
            "tokens": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.ones(1, dtype=np.float32),
        }
    audio = session.run(None, inputs)[0].squeeze()
    audio = np.clip(audio.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(SAMPLE_RATE))
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


def _handler(model_dir: Path, default_voice: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"ok": True})
                return
            if self.path == "/v1/models":
                self._json(200, {"data": [{"id": "kokoro-local"}]})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/audio/speech":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self._json(400, {"error": "invalid json"})
                return
            text = str(payload.get("input", "")).strip()
            voice = str(payload.get("voice", default_voice)).strip() or default_voice
            if not text:
                self._json(400, {"error": "input is required"})
                return
            try:
                wav = _synth(model_dir, text, voice)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8880)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--voice", default="af_bella")
    args = parser.parse_args()
    model_dir = Path(args.model_dir).expanduser()
    server = ThreadingHTTPServer((args.host, args.port), _handler(model_dir, args.voice))
    server.serve_forever()


if __name__ == "__main__":
    main()
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _default_kokoro_server_command(payload: dict[str, object]) -> list[str] | None:
    try:
        _ensure_kokoro_runtime_dependencies()
    except Exception:
        return None
    model_dir = _default_tts_model_dir(
        BackendProfile("kokorotts", "KokoroTTS", "tts_local", "af_bella", "127.0.0.1:8880", "kokorotts"),
        payload,
    )
    if not model_dir.exists():
        return None
    host, port = _parse_host_port(str(payload.get("host", "127.0.0.1:8880")))
    voice = str(payload.get("model", "af_bella")).strip() or "af_bella"
    server_script = _ensure_kokoro_local_server_script()
    return [
        sys.executable,
        str(server_script),
        "--host",
        host,
        "--port",
        str(port),
        "--model-dir",
        str(model_dir),
        "--voice",
        voice,
    ]


def _resolve_kokoro_server_command(payload: dict[str, object]) -> tuple[list[str], str]:
    command_text = str(payload.get("tts_server_command", "")).strip()
    if command_text:
        try:
            return shlex.split(command_text), "custom"
        except Exception as exc:
            raise RuntimeError(f"Invalid server command: {exc}")
    candidate = _existing_path(payload.get("binary_path"))
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return [str(candidate)], "binary"
    auto = _default_kokoro_server_command(payload)
    if auto:
        return auto, "auto"
    raise RuntimeError(
        "No valid Kokoro server command was found. Download models first, or set 'TTS server command'."
    )


def _kokoro_server_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host:
        if _openai_compat_alive(host) or _host_reachable(host):
            return True, f"Server active at {host}"
    pid = int(payload.get("tts_server_pid", 0) or 0)
    if _is_pid_alive(pid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def _stop_kokoro_server(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("tts_server_pid", 0) or 0)
    if not _is_pid_alive(pid):
        payload["tts_server_pid"] = 0
        return False, "No tracked Kokoro server process is running."
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"Unable to stop Kokoro server: {exc}"
    payload["tts_server_pid"] = 0
    return True, f"Stopped Kokoro server process {pid}."


def _kokoro_systemd_user_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "hanauta-kokorotts.service"


def _systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_kokoro_systemd_service(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_kokoro_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    command_text = shlex.join(command)
    if source == "auto":
        payload["tts_server_command"] = command_text
    service_path = _kokoro_systemd_user_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_text = f"""[Unit]
Description=Hanauta KokoroTTS Server
After=default.target

[Service]
Type=simple
ExecStart={command_text}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""
    service_path.write_text(service_text, encoding="utf-8")
    result = _systemctl_user("daemon-reload")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"systemd reload failed: {detail or 'unknown error'}"
    return True, f"Service file written at {service_path}"


def _set_kokoro_autostart(payload: dict[str, object], enabled: bool) -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return False, "systemctl is not available on this system."
    if enabled:
        ok, msg = _write_kokoro_systemd_service(payload)
        if not ok:
            return False, msg
        result = _systemctl_user("enable", "--now", "hanauta-kokorotts.service")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, f"Failed to enable autostart: {detail or 'unknown error'}"
        return True, "Kokoro autostart enabled."
    result = _systemctl_user("disable", "--now", "hanauta-kokorotts.service")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lowered = detail.lower()
        if "not loaded" not in lowered and "does not exist" not in lowered:
            return False, f"Failed to disable autostart: {detail or 'unknown error'}"
    return True, "Kokoro autostart disabled."


class TtsDownloadFinishedFullscreen(QWidget):
    def __init__(self, title: str, body: str, start_payload: dict[str, object] | None = None) -> None:
        super().__init__()
        self.start_payload = dict(start_payload or {})
        self.setWindowTitle("Hanauta Reminder")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(40, 40, 40, 40)
        shell.setSpacing(0)
        card = SurfaceFrame(bg=rgba(CARD_BG, 0.97), border=BORDER_ACCENT, radius=30)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(14)
        overline = QLabel("FULLSCREEN REMINDER")
        overline.setStyleSheet(f"color: {TEXT_DIM}; font-weight: 700; letter-spacing: 1px;")
        card_layout.addWidget(overline)
        headline = QLabel(title.strip() or "Download complete")
        headline.setWordWrap(True)
        headline.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: 700;")
        card_layout.addWidget(headline)
        detail = QLabel(body.strip())
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {TEXT_MID}; font-size: 14px;")
        card_layout.addWidget(detail)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(10)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.close)
        actions.addWidget(dismiss)
        if self.start_payload:
            start_btn = QPushButton("Start Kokoro Server")
            start_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {ACCENT};
                    color: {THEME.active_text};
                    border: 1px solid {ACCENT};
                    border-radius: 18px;
                    padding: 8px 14px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background: {mix(ACCENT, '#ffffff', 0.08)};
                }}
                """
            )
            start_btn.clicked.connect(self._start_server)
            actions.addWidget(start_btn)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        shell.addStretch(1)
        shell.addWidget(card)
        shell.addStretch(1)

    def _start_server(self) -> None:
        ok, message = _start_kokoro_server(self.start_payload)
        send_desktop_notification("Kokoro server", message)
        if ok:
            self.close()


class TtsModelDownloadWorker(QThread):
    progress = pyqtSignal(str, int, str)
    finished_ok = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(self, profile: BackendProfile, payload: dict[str, object]) -> None:
        super().__init__()
        self.profile = profile
        self.payload = dict(payload)

    def run(self) -> None:
        try:
            model_dir, _voice = _ensure_tts_assets(
                self.profile,
                self.payload,
                download_if_missing=True,
                progress_cb=lambda done, total, label: self._emit_progress(done, total, f"Fetching {label}"),
            )
        except Exception as exc:
            self.failed.emit(self.profile.key, str(exc))
            return
        self.progress.emit(self.profile.key, 100, "Model ready")
        self.finished_ok.emit(self.profile.key, str(model_dir))

    def _emit_progress(self, done: int, total: int, label: str) -> None:
        ratio = 0 if total <= 0 else int(max(0.0, min(1.0, done / float(total))) * 100)
        self.progress.emit(self.profile.key, ratio, label)


class TtsDownloadManager(QObject):
    progress_changed = pyqtSignal(str, int, str)
    download_finished = pyqtSignal(str, str)
    download_failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__(None)
        self._workers: dict[str, TtsModelDownloadWorker] = {}
        self._status: dict[str, dict[str, object]] = {}
        self._kokoro_payload: dict[str, object] = {}
        self._fullscreen_alerts: list[TtsDownloadFinishedFullscreen] = []

    def status(self, profile_key: str) -> dict[str, object]:
        return dict(self._status.get(profile_key, {}))

    def is_running(self, profile_key: str) -> bool:
        worker = self._workers.get(profile_key)
        return worker is not None and worker.isRunning()

    def start(self, profile: BackendProfile, payload: dict[str, object]) -> bool:
        if self.is_running(profile.key):
            return False
        worker = TtsModelDownloadWorker(profile, payload)
        self._workers[profile.key] = worker
        self._status[profile.key] = {"running": True, "progress": 0, "message": "Starting download"}
        if profile.key == "kokorotts":
            self._kokoro_payload = dict(payload)
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda key=profile.key: self._workers.pop(key, None))
        worker.start()
        return True

    def _on_progress(self, profile_key: str, value: int, message: str) -> None:
        self._status[profile_key] = {"running": True, "progress": value, "message": message}
        self.progress_changed.emit(profile_key, value, message)

    def _on_finished(self, profile_key: str, model_dir: str) -> None:
        self._status[profile_key] = {"running": False, "progress": 100, "message": "Download complete", "model_dir": model_dir}
        self.download_finished.emit(profile_key, model_dir)
        if profile_key == "kokorotts":
            title = "Kokoro ONNX model download completed"
            body = f"Model files were installed at:\n{model_dir}\n\nYou can start a local Kokoro server now."
            alert = TtsDownloadFinishedFullscreen(title, body, start_payload=self._kokoro_payload)
            self._fullscreen_alerts.append(alert)
            alert.destroyed.connect(lambda _=None, a=alert: self._fullscreen_alerts.remove(a) if a in self._fullscreen_alerts else None)
            trigger_fullscreen_alert(title, body, "discrete")
            alert.showFullScreen()

    def _on_failed(self, profile_key: str, message: str) -> None:
        self._status[profile_key] = {"running": False, "progress": 0, "message": message}
        self.download_failed.emit(profile_key, message)


_TTS_DOWNLOAD_MANAGER: TtsDownloadManager | None = None


def get_tts_download_manager() -> TtsDownloadManager:
    global _TTS_DOWNLOAD_MANAGER
    if _TTS_DOWNLOAD_MANAGER is None:
        _TTS_DOWNLOAD_MANAGER = TtsDownloadManager()
    return _TTS_DOWNLOAD_MANAGER


class BackendSettingsDialog(QDialog):
    def __init__(
        self,
        profiles: list[BackendProfile],
        settings: dict[str, dict[str, object]],
        ui_font: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profiles = profiles
        self.profile_map = {profile.key: profile for profile in profiles}
        self.settings = json.loads(json.dumps(settings))
        self.ui_font = ui_font

        self.setWindowTitle("AI Backend Settings")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(620, 760)
        self.setModal(True)
        self.setStyleSheet(
            f"""
            QDialog {{
                background: transparent;
                color: {TEXT};
            }}
            QLabel {{
                color: {TEXT};
            }}
            QLineEdit, QComboBox {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 18px;
                padding: 10px 12px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QComboBox QAbstractItemView {{
                background: {CARD_BG};
                color: {TEXT};
                selection-background-color: {ACCENT_SOFT};
                border: 1px solid {BORDER_SOFT};
            }}
            QCheckBox {{
                color: {TEXT};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid {BORDER_SOFT};
                background: {CARD_BG};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border: 1px solid {ACCENT};
            }}
            QPushButton {{
                min-height: 36px;
                background: {CARD_BG_SOFT};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 18px;
                padding: 0 14px;
                font-weight: {_button_css_weight(ui_font)};
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        shell = SurfaceFrame(bg=rgba(CARD_BG, 0.92), border=BORDER_SOFT, radius=28)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(18, 18, 18, 18)
        shell_layout.setSpacing(12)
        root.addWidget(shell)

        title = QLabel("Backend settings")
        title.setFont(QFont(ui_font, 14, QFont.Weight.DemiBold))
        shell_layout.addWidget(title)

        subtitle = QLabel("Teste e habilite os providers antes de expor os ícones na sidebar.")
        subtitle.setFont(QFont(ui_font, 10))
        subtitle.setStyleSheet(f"color: {TEXT_DIM};")
        shell_layout.addWidget(subtitle)

        self.backend_combo = QComboBox()
        for profile in profiles:
            self.backend_combo.addItem(profile.label, profile.key)
        self.backend_combo.currentIndexChanged.connect(self._load_selected_backend)
        shell_layout.addWidget(self.backend_combo)

        self.enabled_check = QCheckBox("Mostrar backend na barra após teste bem-sucedido")
        shell_layout.addWidget(self.enabled_check)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Host")
        shell_layout.addWidget(self.host_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Model")
        shell_layout.addWidget(self.model_input)
        self.kokoro_voice_combo = QComboBox()
        self.kokoro_voice_combo.setToolTip("Kokoro voice")
        shell_layout.addWidget(self.kokoro_voice_combo)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("API key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        shell_layout.addWidget(self.api_key_input)

        self.tts_mode_combo = QComboBox()
        self.tts_mode_combo.addItem("Local ONNX", "local_onnx")
        self.tts_mode_combo.addItem("External API", "external_api")
        shell_layout.addWidget(self.tts_mode_combo)

        self.binary_path_input = QLineEdit()
        self.binary_path_input.setPlaceholderText("Local binary path")
        shell_layout.addWidget(self.binary_path_input)

        self.tts_repo_input = QLineEdit()
        self.tts_repo_input.setPlaceholderText("Model repo (owner/repo)")
        shell_layout.addWidget(self.tts_repo_input)

        self.tts_bundle_url_input = QLineEdit()
        self.tts_bundle_url_input.setPlaceholderText("Optional ZIP bundle URL (fallback for CDN errors)")
        shell_layout.addWidget(self.tts_bundle_url_input)

        self.tts_server_command_input = QLineEdit()
        self.tts_server_command_input.setPlaceholderText("Optional Kokoro server command (e.g. python -m kokoro_server ...)")
        shell_layout.addWidget(self.tts_server_command_input)
        self.tts_server_status_label = QLabel("Server status: unknown")
        self.tts_server_status_label.setStyleSheet(f"color: {TEXT_DIM};")
        shell_layout.addWidget(self.tts_server_status_label)
        server_actions = QHBoxLayout()
        server_actions.setContentsMargins(0, 0, 0, 0)
        server_actions.setSpacing(8)
        self.kokoro_start_button = QPushButton("Start")
        self.kokoro_start_button.clicked.connect(self._start_kokoro_server_clicked)
        server_actions.addWidget(self.kokoro_start_button)
        self.kokoro_restart_button = QPushButton("Restart")
        self.kokoro_restart_button.clicked.connect(self._restart_kokoro_server_clicked)
        server_actions.addWidget(self.kokoro_restart_button)
        self.kokoro_stop_button = QPushButton("Stop")
        self.kokoro_stop_button.clicked.connect(self._stop_kokoro_server_clicked)
        server_actions.addWidget(self.kokoro_stop_button)
        server_actions.addStretch(1)
        shell_layout.addLayout(server_actions)
        self.kokoro_autostart_check = QCheckBox("Auto-start Kokoro server when Linux session boots")
        shell_layout.addWidget(self.kokoro_autostart_check)

        self.tts_voice_ref_input = QLineEdit()
        self.tts_voice_ref_input.setPlaceholderText("PocketTTS voice reference WAV (optional)")
        shell_layout.addWidget(self.tts_voice_ref_input)

        self.tts_auto_download_check = QCheckBox("Auto-download ONNX model files when missing")
        shell_layout.addWidget(self.tts_auto_download_check)
        self.tts_test_label = QLabel("Text to be spoken")
        self.tts_test_label.setStyleSheet(f"color: {TEXT_MID};")
        shell_layout.addWidget(self.tts_test_label)
        self.tts_test_input = QLineEdit()
        self.tts_test_input.setPlaceholderText("Enter the exact text Kokoro should speak")
        shell_layout.addWidget(self.tts_test_input)
        self.tts_test_button = QPushButton("Speak test text")
        self.tts_test_button.clicked.connect(self._test_tts_synthesis)
        shell_layout.addWidget(self.tts_test_button)

        self.gguf_path_input = QLineEdit()
        self.gguf_path_input.setPlaceholderText("GGUF model path")
        shell_layout.addWidget(self.gguf_path_input)

        self.text_model_path_input = QLineEdit()
        self.text_model_path_input.setPlaceholderText("Optional text model path for JoyCaption-style setups")
        shell_layout.addWidget(self.text_model_path_input)

        self.mmproj_path_input = QLineEdit()
        self.mmproj_path_input.setPlaceholderText("Optional mmproj path")
        shell_layout.addWidget(self.mmproj_path_input)

        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("GPU", "gpu")
        self.device_combo.setToolTip("Execution device")
        shell_layout.addWidget(self.device_combo)

        self.negative_prompt_input = QLineEdit()
        self.negative_prompt_input.setPlaceholderText("Default negative prompt")
        shell_layout.addWidget(self.negative_prompt_input)

        self.sampler_input = QLineEdit()
        self.sampler_input.setPlaceholderText("Sampler")
        shell_layout.addWidget(self.sampler_input)

        self.steps_input = QLineEdit()
        self.steps_input.setPlaceholderText("Steps")
        shell_layout.addWidget(self.steps_input)

        self.cfg_scale_input = QLineEdit()
        self.cfg_scale_input.setPlaceholderText("CFG scale")
        shell_layout.addWidget(self.cfg_scale_input)

        self.width_input = QLineEdit()
        self.width_input.setPlaceholderText("Width")
        shell_layout.addWidget(self.width_input)

        self.height_input = QLineEdit()
        self.height_input.setPlaceholderText("Height")
        shell_layout.addWidget(self.height_input)

        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("SD output folder for monitor notifications")
        shell_layout.addWidget(self.output_dir_input)

        self.monitor_check = QCheckBox("Notify when new SD images appear in the output folder")
        shell_layout.addWidget(self.monitor_check)

        self.status_label = QLabel("Configure um backend e clique em Test.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")
        shell_layout.addWidget(self.status_label)
        self.validation_badge = QLabel("○ Not validated")
        self.validation_badge.setStyleSheet(f"color: {TEXT_DIM}; font-weight: 600;")
        shell_layout.addWidget(self.validation_badge)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.hide()
        shell_layout.addWidget(self.download_progress)

        self.download_progress_label = QLabel("")
        self.download_progress_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.download_progress_label.hide()
        shell_layout.addWidget(self.download_progress_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._test_current_backend)
        actions.addWidget(self.test_button)

        self.download_tts_button = QPushButton("Download TTS model")
        self.download_tts_button.clicked.connect(self._download_tts_assets)
        actions.addWidget(self.download_tts_button)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._save_current_backend)
        self.save_button.setStyleSheet(
            f"""
            QPushButton {{
                min-height: 36px;
                background: {ACCENT};
                color: {THEME.active_text};
                border: 1px solid {ACCENT};
                border-radius: 18px;
                padding: 0 14px;
                font-weight: {_button_css_weight(ui_font)};
            }}
            QPushButton:hover {{
                background: {mix(ACCENT, '#ffffff', 0.08)};
                border: 1px solid {ACCENT};
            }}
            """
        )
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        shell_layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        shell_layout.addWidget(buttons)

        _apply_antialias_font(self)
        self._download_manager = get_tts_download_manager()
        self._tts_preview_worker: TtsSynthesisWorker | None = None
        self._download_manager.progress_changed.connect(self._on_tts_download_progress)
        self._download_manager.download_finished.connect(self._on_tts_download_finished)
        self._download_manager.download_failed.connect(self._on_tts_download_failed)
        self._load_selected_backend()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(QPen(QColor(rgba(BORDER_HARD, 0.92)), 1))
        painter.setBrush(QColor(rgba(PANEL_BG, 0.96)))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 30, 30)

    def _selected_profile(self) -> BackendProfile:
        key = str(self.backend_combo.currentData())
        return self.profile_map[key]

    def _current_payload(self) -> dict[str, object]:
        profile = self._selected_profile()
        existing = dict(self.settings.get(profile.key, {}))
        model_value = (
            str(self.kokoro_voice_combo.currentData() or self.kokoro_voice_combo.currentText()).strip()
            if profile.key == "kokorotts"
            else self.model_input.text().strip()
        )
        existing.update(
            {
                "enabled": bool(self.enabled_check.isChecked()),
                "host": self.host_input.text().strip(),
                "model": model_value,
                "binary_path": self.binary_path_input.text().strip(),
                "tts_mode": str(self.tts_mode_combo.currentData()),
                "tts_model_repo": self.tts_repo_input.text().strip(),
                "tts_bundle_url": self.tts_bundle_url_input.text().strip(),
                "tts_server_command": self.tts_server_command_input.text().strip(),
                "tts_voice_reference": self.tts_voice_ref_input.text().strip(),
                "tts_download_if_missing": bool(self.tts_auto_download_check.isChecked()),
                "tts_autostart": bool(self.kokoro_autostart_check.isChecked()),
                "gguf_path": self.gguf_path_input.text().strip(),
                "text_model_path": self.text_model_path_input.text().strip(),
                "mmproj_path": self.mmproj_path_input.text().strip(),
                "device": str(self.device_combo.currentData()),
                "negative_prompt": self.negative_prompt_input.text().strip(),
                "sampler_name": self.sampler_input.text().strip(),
                "steps": self.steps_input.text().strip(),
                "cfg_scale": self.cfg_scale_input.text().strip(),
                "width": self.width_input.text().strip(),
                "height": self.height_input.text().strip(),
                "output_dir": self.output_dir_input.text().strip(),
                "monitor_enabled": bool(self.monitor_check.isChecked()),
            }
        )
        return existing

    def _load_selected_backend(self) -> None:
        profile = self._selected_profile()
        payload = dict(self.settings.get(profile.key, {}))
        self.enabled_check.setChecked(bool(payload.get("enabled", True)))
        self.host_input.setText(str(payload.get("host", profile.host)))
        self.model_input.setText(str(payload.get("model", profile.model)))
        self.api_key_input.setText(secure_load_secret(f"{profile.key}:api_key"))
        self.binary_path_input.setText(str(payload.get("binary_path", "")))
        self.tts_mode_combo.setCurrentIndex(1 if _default_tts_mode(payload) == "external_api" else 0)
        self.tts_repo_input.setText(_default_tts_repo(profile, payload))
        self.tts_bundle_url_input.setText(_default_tts_bundle_url(profile, payload))
        self.tts_server_command_input.setText(str(payload.get("tts_server_command", "")))
        self.tts_voice_ref_input.setText(str(payload.get("tts_voice_reference", "")))
        self.tts_auto_download_check.setChecked(bool(payload.get("tts_download_if_missing", True)))
        self.kokoro_autostart_check.setChecked(bool(payload.get("tts_autostart", False)))
        self.gguf_path_input.setText(str(payload.get("gguf_path", "")))
        self.text_model_path_input.setText(str(payload.get("text_model_path", "")))
        self.mmproj_path_input.setText(str(payload.get("mmproj_path", "")))
        device = str(payload.get("device", "cpu")).lower()
        self.device_combo.setCurrentIndex(1 if device == "gpu" else 0)
        self.negative_prompt_input.setText(str(payload.get("negative_prompt", "")))
        self.sampler_input.setText(str(payload.get("sampler_name", "Euler a")))
        self.steps_input.setText(str(payload.get("steps", "28")))
        self.cfg_scale_input.setText(str(payload.get("cfg_scale", "7.0")))
        self.width_input.setText(str(payload.get("width", "1024")))
        self.height_input.setText(str(payload.get("height", "1024")))
        self.output_dir_input.setText(str(payload.get("output_dir", "")))
        self.monitor_check.setChecked(bool(payload.get("monitor_enabled", False)))
        self.api_key_input.setVisible(profile.needs_api_key or profile.provider == "tts_local")
        show_host = (not profile.needs_api_key) or profile.provider in {"sdwebui", "tts_local"}
        self.host_input.setVisible(show_host)
        is_sd = profile.provider == "sdwebui"
        is_kobold = profile.key == "koboldcpp"
        is_tts = profile.provider == "tts_local"
        device_enabled = is_kobold or is_tts
        self.binary_path_input.setVisible(is_kobold or is_tts)
        self.tts_mode_combo.setVisible(is_tts)
        self.tts_repo_input.setVisible(is_tts)
        self.tts_bundle_url_input.setVisible(is_tts)
        self.tts_server_command_input.setVisible(is_tts and profile.key == "kokorotts")
        self.tts_server_status_label.setVisible(is_tts and profile.key == "kokorotts")
        self.kokoro_start_button.setVisible(is_tts and profile.key == "kokorotts")
        self.kokoro_restart_button.setVisible(is_tts and profile.key == "kokorotts")
        self.kokoro_stop_button.setVisible(is_tts and profile.key == "kokorotts")
        self.kokoro_autostart_check.setVisible(is_tts and profile.key == "kokorotts")
        self.tts_voice_ref_input.setVisible(is_tts and profile.key == "pockettts")
        self.tts_auto_download_check.setVisible(is_tts)
        self.download_tts_button.setVisible(is_tts)
        self.tts_test_label.setVisible(is_tts and profile.key == "kokorotts")
        self.tts_test_input.setVisible(is_tts and profile.key == "kokorotts")
        self.tts_test_button.setVisible(is_tts and profile.key == "kokorotts")
        self.gguf_path_input.setVisible(is_kobold)
        self.text_model_path_input.setVisible(is_kobold)
        self.mmproj_path_input.setVisible(is_kobold)
        self.device_combo.setVisible(device_enabled)
        self.negative_prompt_input.setVisible(is_sd)
        self.sampler_input.setVisible(is_sd)
        self.steps_input.setVisible(is_sd)
        self.cfg_scale_input.setVisible(is_sd)
        self.width_input.setVisible(is_sd)
        self.height_input.setVisible(is_sd)
        self.output_dir_input.setVisible(is_sd)
        self.monitor_check.setVisible(is_sd)
        if is_sd:
            self.model_input.setPlaceholderText("Checkpoint / model")
        elif is_tts:
            if profile.key == "pockettts":
                self.binary_path_input.setPlaceholderText("Local model folder (optional)")
                self.model_input.setPlaceholderText("Voice label (metadata)")
            else:
                self.binary_path_input.setPlaceholderText("Local ONNX model folder (optional)")
                self.model_input.setPlaceholderText("Kokoro voice")
        else:
            self.model_input.setPlaceholderText("Model")
        self.model_input.setVisible(not (is_tts and profile.key == "kokorotts"))
        self.kokoro_voice_combo.setVisible(is_tts and profile.key == "kokorotts")
        if is_tts and profile.key == "kokorotts":
            self._reload_kokoro_voice_list(payload)
            self._refresh_kokoro_server_status(payload)
        self._refresh_download_progress(profile.key if is_tts else "")
        tested = bool(payload.get("tested", False))
        last_status = str(payload.get("last_status", "Configure um backend e clique em Test."))
        self.status_label.setText(last_status if last_status else "Configure um backend e clique em Test.")
        self.status_label.setStyleSheet(f"color: {ACCENT if tested else TEXT_MID};")
        self.validation_badge.setText("✓ Validated" if tested else "○ Not validated")
        self.validation_badge.setStyleSheet(
            f"color: {ACCENT if tested else TEXT_DIM}; font-weight: 700;"
        )

    def _test_current_backend(self) -> None:
        profile = self._selected_profile()
        payload = self._current_payload()
        ok, message = validate_backend(profile, payload)
        payload["tested"] = ok
        payload["last_status"] = message
        self.settings[profile.key] = payload
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self.validation_badge.setText("✓ Validated" if ok else "○ Not validated")
        self.validation_badge.setStyleSheet(
            f"color: {ACCENT if ok else ACCENT_ALT}; font-weight: 700;"
        )

    def _save_current_backend(self) -> None:
        profile = self._selected_profile()
        payload = self._current_payload()
        existing = self.settings.get(profile.key, {})
        secure_store_secret(f"{profile.key}:api_key", self.api_key_input.text().strip())
        payload["tested"] = bool(existing.get("tested", False))
        payload["last_status"] = existing.get("last_status", "Saved.")
        self.settings[profile.key] = payload
        save_backend_settings(self.settings)
        if profile.key == "kokorotts":
            ok, message = _set_kokoro_autostart(payload, bool(payload.get("tts_autostart", False)))
            if not ok:
                self.status_label.setText(message)
                self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
                return
            self.settings[profile.key] = payload
            save_backend_settings(self.settings)
        self.status_label.setText("Saved.")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")

    def _download_tts_assets(self) -> None:
        profile = self._selected_profile()
        if profile.provider != "tts_local":
            self.status_label.setText("This backend does not use TTS model downloads.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        payload = self._current_payload()
        started = self._download_manager.start(profile, payload)
        if not started:
            self.status_label.setText("A model download is already running for this backend.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            self._refresh_download_progress(profile.key)
            return
        self.status_label.setText("Background model download started. You can close this dialog safely.")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")
        self._refresh_download_progress(profile.key)

    def _refresh_download_progress(self, profile_key: str) -> None:
        if not profile_key:
            self.download_progress.hide()
            self.download_progress_label.hide()
            return
        status = self._download_manager.status(profile_key)
        running = bool(status.get("running", False))
        value = int(status.get("progress", 0) or 0)
        message = str(status.get("message", "")).strip()
        if not running and not message:
            self.download_progress.hide()
            self.download_progress_label.hide()
            return
        self.download_progress.show()
        self.download_progress_label.show()
        self.download_progress.setValue(max(0, min(100, value)))
        self.download_progress_label.setText(message or ("Download complete" if value >= 100 else "Downloading model..."))

    def _on_tts_download_progress(self, profile_key: str, value: int, message: str) -> None:
        selected = self._selected_profile()
        if selected.provider == "tts_local" and selected.key == profile_key:
            self._refresh_download_progress(profile_key)
            self.status_label.setText(message or f"Downloading... {value}%")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")

    def _on_tts_download_finished(self, profile_key: str, model_dir: str) -> None:
        payload = dict(self.settings.get(profile_key, {}))
        payload["binary_path"] = model_dir
        profile = self.profile_map.get(profile_key)
        ok = False
        message = f"Downloaded model files into {model_dir}."
        if profile is not None:
            ok, message = validate_backend(profile, payload)
        payload["tested"] = bool(ok)
        payload["last_status"] = message
        self.settings[profile_key] = payload
        save_backend_settings(self.settings)
        selected = self._selected_profile()
        if selected.key == profile_key:
            self.binary_path_input.setText(model_dir)
            if selected.key == "kokorotts":
                self._reload_kokoro_voice_list(payload)
            self._refresh_download_progress(profile_key)
            self.status_label.setText(message)
            self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
            self.validation_badge.setText("✓ Validated" if ok else "○ Not validated")
            self.validation_badge.setStyleSheet(
                f"color: {ACCENT if ok else ACCENT_ALT}; font-weight: 700;"
            )
        send_desktop_notification("TTS model ready", f"{profile_key} model files installed at {model_dir}.")

    def _on_tts_download_failed(self, profile_key: str, message: str) -> None:
        selected = self._selected_profile()
        if selected.key == profile_key:
            self._refresh_download_progress(profile_key)
            self.status_label.setText(f"Model download failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

    def _reload_kokoro_voice_list(self, payload: dict[str, object]) -> None:
        profile = self._selected_profile()
        if profile.key != "kokorotts":
            return
        selected_voice = str(payload.get("model", profile.model)).strip() or profile.model
        model_dir = _default_tts_model_dir(profile, payload)
        voices = _list_kokoro_voice_names(model_dir)
        self.kokoro_voice_combo.blockSignals(True)
        self.kokoro_voice_combo.clear()
        for voice in voices:
            self.kokoro_voice_combo.addItem(voice, voice)
        index = max(0, self.kokoro_voice_combo.findData(selected_voice))
        self.kokoro_voice_combo.setCurrentIndex(index)
        self.kokoro_voice_combo.blockSignals(False)

    def _refresh_kokoro_server_status(self, payload: dict[str, object] | None = None) -> None:
        effective = dict(payload or self._current_payload())
        active, detail = _kokoro_server_status(effective)
        prefix = "● Active" if active else "○ Inactive"
        self.tts_server_status_label.setText(f"Server status: {prefix} — {detail}")
        self.tts_server_status_label.setStyleSheet(
            f"color: {ACCENT if active else TEXT_DIM}; font-weight: 600;"
        )

    def _start_kokoro_server_clicked(self) -> None:
        payload = self._current_payload()
        ok, message = _start_kokoro_server(payload)
        self.settings["kokorotts"] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_kokoro_server_status(payload)

    def _stop_kokoro_server_clicked(self) -> None:
        payload = self._current_payload()
        ok, message = _stop_kokoro_server(payload)
        self.settings["kokorotts"] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_kokoro_server_status(payload)

    def _restart_kokoro_server_clicked(self) -> None:
        payload = self._current_payload()
        _stop_kokoro_server(payload)
        ok, message = _start_kokoro_server(payload)
        self.settings["kokorotts"] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message if ok else f"Restart failed: {message}")
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_kokoro_server_status(payload)

    def _test_tts_synthesis(self) -> None:
        profile = self._selected_profile()
        if profile.key != "kokorotts":
            return
        text = self.tts_test_input.text().strip()
        if not text:
            self.status_label.setText("Enter some text to test Kokoro TTS.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        if self._tts_preview_worker is not None and self._tts_preview_worker.isRunning():
            self.status_label.setText("A TTS preview is already running.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        payload = self._current_payload()
        worker = TtsSynthesisWorker(profile, payload, text)
        self._tts_preview_worker = worker
        self.status_label.setText("Generating Kokoro preview...")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")

        def _done(audio_path: str, _label: str, _source: str) -> None:
            self.status_label.setText(f"Preview generated: {audio_path}")
            self.status_label.setStyleSheet(f"color: {ACCENT};")

        def _failed(message: str) -> None:
            self.status_label.setText(f"TTS preview failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

        worker.finished_ok.connect(_done)
        worker.failed.connect(_failed)
        worker.finished.connect(lambda: setattr(self, "_tts_preview_worker", None))
        worker.start()


class HeaderBadge(QFrame):
    def __init__(self, text: str, ui_font: str, accent: bool = False) -> None:
        super().__init__()
        bg = ACCENT_SOFT if accent else rgba(CARD_BG_SOFT, 0.92)
        fg = ACCENT if accent else TEXT_MID
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)
        label = QLabel(text)
        label.setFont(QFont(ui_font, 10, QFont.Weight.DemiBold))
        layout.addWidget(label)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {bg};
                border: 1px solid {BORDER_SOFT};
                border-radius: 999px;
            }}
            QLabel {{
                color: {fg};
            }}
            """
        )


class AntiAliasButton(QPushButton):
    def __init__(self, text: str, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._ui_font = ui_font
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setMinimumWidth(88)
        self.setFont(QFont(ui_font, 11, QFont.Weight.Medium))
        self.setFlat(True)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = rect.height() / 2.0

        fill = QColor(ACCENT)
        if self.isDown():
            fill = QColor(mix(ACCENT, "#000000", 0.12))
        elif self.underMouse():
            fill = QColor(mix(ACCENT, "#ffffff", 0.08))

        border = QColor(rgba(BORDER_ACCENT, 0.58))
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(QColor(THEME.active_text))
        painter.setFont(QFont(self._ui_font, 11, QFont.Weight.Medium))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


class ActionIcon(QToolButton):
    def __init__(self, text: str, tooltip: str, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(30, 30)
        self.setFont(QFont(ui_font, 11, _button_qfont_weight(ui_font)))
        self.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                color: {UI_ICON_DIM};
                border: none;
                border-radius: 15px;
            }}
            QToolButton:hover {{
                background: {HOVER_BG};
                color: {UI_ICON_ACTIVE};
            }}
            """
        )


class AvatarBadge(QLabel):
    def __init__(self, text: str, bg: str, fg: str, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(30, 30)
        self.setFont(QFont(ui_font, 10, QFont.Weight.DemiBold))
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid {rgba(fg, 0.18)};
                border-radius: 15px;
            }}
            """
        )


def _audio_chip_href(audio_path: str) -> str:
    return f"hanauta-audio://play?path={quote(audio_path, safe='')}"


def _audio_chip_path(href: str) -> Path | None:
    try:
        parsed = urlparse(href)
    except Exception:
        return None
    if parsed.scheme != "hanauta-audio":
        return None
    params = parse_qs(parsed.query or "")
    raw = (params.get("path") or [""])[0]
    decoded = unquote(raw).strip()
    if not decoded:
        return None
    return Path(decoded).expanduser()


def _audio_duration_label(audio_path: str) -> str:
    try:
        path = Path(audio_path).expanduser()
        with wave.open(str(path), "rb") as handle:
            frames = int(handle.getnframes() or 0)
            rate = int(handle.getframerate() or 0)
        if rate <= 0:
            return "0:00"
        seconds = max(0, int(round(frames / float(rate))))
        minutes = seconds // 60
        rem = seconds % 60
        return f"{minutes}:{rem:02d}"
    except Exception:
        return "0:00"


def _looks_like_audio_filename(text: str) -> bool:
    value = text.strip().lower()
    return value.endswith((".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac"))


def _audio_wave_svg_html(is_playing: bool) -> str:
    active = "#b7a1ff"
    idle = "#6f678d"
    dot = "#d1c1ff" if is_playing else "#9f94cc"
    fills = [active if idx < (11 if is_playing else 7) else idle for idx in range(27)]
    return (
        '<svg class="audio-wave-svg" viewBox="0 0 185 40" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<rect y="17" width="3" height="6" rx="1.5" fill="{fills[0]}"/>'
        f'<rect x="7" y="15.5" width="3" height="9" rx="1.5" fill="{fills[1]}"/>'
        f'<rect x="21" y="6.5" width="3" height="27" rx="1.5" fill="{fills[2]}"/>'
        f'<rect x="14" y="6.5" width="3" height="27" rx="1.5" fill="{fills[3]}"/>'
        f'<rect x="28" y="3" width="3" height="34" rx="1.5" fill="{fills[4]}"/>'
        f'<rect x="35" y="3" width="3" height="34" rx="1.5" fill="{fills[5]}"/>'
        f'<rect x="42" y="5.5" width="3" height="29" rx="1.5" fill="{fills[6]}"/>'
        f'<rect x="49" y="10" width="3" height="20" rx="1.5" fill="{fills[7]}"/>'
        f'<rect x="56" y="13.5" width="3" height="13" rx="1.5" fill="{fills[8]}"/>'
        f'<rect x="63" y="16" width="3" height="8" rx="1.5" fill="{fills[9]}"/>'
        f'<rect x="70" y="12.5" width="3" height="15" rx="1.5" fill="{fills[10]}"/>'
        f'<rect x="77" y="3" width="3" height="34" rx="1.5" fill="{fills[11]}"/>'
        f'<rect x="84" y="3" width="3" height="34" rx="1.5" fill="{fills[12]}"/>'
        f'<rect x="91" y="0.5" width="3" height="39" rx="1.5" fill="{fills[13]}"/>'
        f'<rect x="98" y="0.5" width="3" height="39" rx="1.5" fill="{fills[14]}"/>'
        f'<rect x="105" y="2" width="3" height="36" rx="1.5" fill="{fills[15]}"/>'
        f'<rect x="112" y="6.5" width="3" height="27" rx="1.5" fill="{fills[16]}"/>'
        f'<rect x="119" y="9" width="3" height="22" rx="1.5" fill="{fills[17]}"/>'
        f'<rect x="126" y="11.5" width="3" height="17" rx="1.5" fill="{fills[18]}"/>'
        f'<rect x="133" y="2" width="3" height="36" rx="1.5" fill="{fills[19]}"/>'
        f'<rect x="140" y="2" width="3" height="36" rx="1.5" fill="{fills[20]}"/>'
        f'<rect x="147" y="7" width="3" height="26" rx="1.5" fill="{fills[21]}"/>'
        f'<rect x="154" y="9" width="3" height="22" rx="1.5" fill="{fills[22]}"/>'
        f'<rect x="161" y="9" width="3" height="22" rx="1.5" fill="{fills[23]}"/>'
        f'<rect x="168" y="13.5" width="3" height="13" rx="1.5" fill="{fills[24]}"/>'
        f'<rect x="175" y="16" width="3" height="8" rx="1.5" fill="{fills[25]}"/>'
        f'<rect x="182" y="17.5" width="3" height="5" rx="1.5" fill="{fills[26]}"/>'
        f'<rect x="66" y="16" width="8" height="8" rx="4" fill="{dot}"/>'
        "</svg>"
    )


def render_chat_html(
    history: list[ChatItemData],
    *,
    active_audio_path: str = "",
    audio_playing: bool = False,
) -> str:
    blocks: list[str] = []
    for item in history:
        is_user = item.role == "user"
        bubble_bg = USER_BG if is_user else ASSISTANT_BG
        bubble_border = BORDER_ACCENT if is_user else rgba(BORDER_SOFT, 0.95)
        title_color = ACCENT_ALT if is_user else ACCENT
        pending_class = " pending" if item.pending else ""
        chips = "".join(
            f'<span class="chip">{html.escape(chip.text)}</span>'
            for chip in item.chips
            if not _looks_like_audio_filename(chip.text)
        )
        audio_card_html = ""
        if item.audio_path.strip():
            current = str(Path(item.audio_path).expanduser())
            is_active = bool(active_audio_path and current == active_audio_path)
            chip_label = "Pause audio" if (is_active and audio_playing) else "Play audio"
            play_icon = "⏸" if (is_active and audio_playing) else "▶"
            tooltip = html.escape(Path(current).name)
            duration = _audio_duration_label(current)
            state_class = "is-playing" if (is_active and audio_playing) else "is-paused"
            waveform = _audio_wave_svg_html(is_active and audio_playing)
            audio_card_html = (
                '<div class="audio-card-shell">'
                f'<a class="audio-card {state_class}" title="{tooltip}" aria-label="{html.escape(chip_label)}" href="{_audio_chip_href(current)}">'
                f'<span class="audio-play">{play_icon}</span>'
                f'<span class="audio-wave">{waveform}</span>'
                f'<span class="audio-duration">{duration}</span>'
                "</a>"
                "</div>"
            )
        chips_html = f'<div class="chips">{chips}</div>' if chips else ""
        blocks.append(
            f"""
            <article class="message {'user' if is_user else 'assistant'}{pending_class}">
              <div class="avatar">{'Y' if is_user else 'AI'}</div>
              <div class="bubble" style="background:{bubble_bg}; border:1px solid {bubble_border};">
                <div class="header">
                  <span class="dot" style="color:{title_color};">●</span>
                  <span class="title" style="color:{title_color};">{html.escape(item.title)}</span>
                  <span class="meta">{html.escape(item.meta)}</span>
                </div>
                <div class="body">{item.body}</div>
                {audio_card_html}
                {chips_html}
              </div>
            </article>
            """
        )

    if not blocks:
        blocks.append(
            f"""
            <section class="empty-state">
              <div class="empty-title">No conversation yet</div>
              <div class="empty-copy">Pick a backend and start typing. Use <code>/image your prompt</code> with an SD backend to generate images.</div>
            </section>
            """
        )

    return f"""
    <html>
      <head>
        <style>
        html, body {{
            margin: 0;
            padding: 0;
            background: {CHAT_SURFACE_BG};
            color: {TEXT};
            font-family: system-ui, sans-serif;
        }}
          body {{
            padding: 8px 6px 14px 6px;
          }}
          ::-webkit-scrollbar {{
            width: 12px;
          }}
          ::-webkit-scrollbar-track {{
            background: {rgba(CARD_BG_SOFT, 0.44)};
            border-radius: 6px;
          }}
          ::-webkit-scrollbar-thumb {{
            background: linear-gradient({rgba(ACCENT, 0.78)}, {rgba(THEME.app_running_border, 0.98)});
            border: 1px solid {rgba(BORDER_ACCENT, 0.72)};
            border-radius: 6px;
          }}
          .message {{
            display: flex;
            gap: 10px;
            margin: 0 0 12px 0;
            align-items: flex-start;
          }}
          .message.user {{
            flex-direction: row-reverse;
          }}
          .avatar {{
            width: 30px;
            min-width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 15px;
            font-size: 11px;
            font-weight: 700;
            background: {rgba(CARD_BG_SOFT, 0.96)};
            color: {ACCENT};
            border: 1px solid {rgba(ACCENT, 0.18)};
          }}
          .message.user .avatar {{
            background: {ACCENT_SOFT};
            color: {ACCENT_ALT};
            border-color: {rgba(ACCENT_ALT, 0.18)};
          }}
          .bubble {{
            flex: 1;
            max-width: calc(100% - 48px);
            border-radius: 24px;
            padding: 14px 16px 16px 16px;
            box-sizing: border-box;
          }}
          .message.pending .bubble {{
            box-shadow: 0 0 0 1px {rgba(ACCENT, 0.08)} inset;
          }}
          .header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
          }}
          .title {{
            font-weight: 700;
            font-size: 13px;
          }}
          .meta {{
            color: {TEXT_DIM};
            font-size: 11px;
          }}
          .body {{
            color: {CHAT_TEXT};
            font-size: 13px;
            line-height: 1.55;
          }}
          .body p {{
            margin: 0 0 8px 0;
          }}
          .body code {{
            background: {rgba(CARD_BG_SOFT, 0.94)};
            padding: 2px 6px;
            border-radius: 10px;
          }}
          .body pre {{
            background: {rgba(CARD_BG_SOFT, 0.96)};
            border: 1px solid {rgba(BORDER_SOFT, 0.95)};
            padding: 10px 12px;
            border-radius: 16px;
            white-space: pre-wrap;
          }}
          .body img {{
            margin-top: 10px;
            max-width: 100%;
            border-radius: 18px;
            border: 1px solid {rgba(BORDER_SOFT, 0.95)};
          }}
          .loading-row {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            color: {TEXT};
          }}
          .loading-ring {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid {rgba(ACCENT, 0.22)};
            border-top-color: {ACCENT};
            animation: spin 0.9s linear infinite;
            box-sizing: border-box;
          }}
          @keyframes spin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
          }}
          .chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
          }}
          .chip {{
            padding: 7px 12px;
            border-radius: 999px;
            background: {rgba(CARD_BG_SOFT, 0.92)};
            border: 1px solid {BORDER_SOFT};
            color: {CHAT_TEXT};
            font-size: 11px;
          }}
          .audio-card-shell {{
            margin-top: 10px;
          }}
          .audio-card {{
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 10px;
            min-width: 286px;
            max-width: 336px;
            padding: 10px 12px;
            border-radius: 14px;
            background: linear-gradient(180deg, #201d2b 0%, #181624 100%);
            border: 1px solid #3f3a57;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(139, 123, 228, 0.28);
            color: #c7b8ff;
          }}
          .audio-card:hover {{
            background: linear-gradient(180deg, #27223a 0%, #1e1a2f 100%);
            border-color: #5a5190;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), 0 0 0 1px rgba(170, 152, 248, 0.45);
          }}
          .audio-play {{
            width: 34px;
            min-width: 34px;
            height: 34px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            line-height: 1;
            color: #2f2354;
            background: #bca8ff;
            border: 1px solid #a58af5;
          }}
          .audio-card.is-playing .audio-play {{
            background: #d0c0ff;
            border-color: #b9a4ff;
          }}
          .audio-wave {{
            display: inline-flex;
            align-items: center;
            flex: 1;
          }}
          .audio-wave-svg {{
            display: block;
            width: 150px;
            height: 32px;
          }}
          .audio-duration {{
            min-width: 36px;
            text-align: right;
            font-size: 12px;
            font-weight: 700;
            color: #bda9ff;
          }}
          .empty-state {{
            padding: 28px 18px;
            border-radius: 24px;
            border: 1px dashed {rgba(BORDER_SOFT, 0.9)};
            background: {rgba(CARD_BG_SOFT, 0.18)};
          }}
          .empty-title {{
            font-size: 15px;
            font-weight: 700;
            margin-bottom: 8px;
            color: {UI_TEXT_STRONG};
          }}
          .empty-copy {{
            font-size: 13px;
            line-height: 1.55;
            color: {TEXT_DIM};
          }}
          a {{
            color: {ACCENT};
            text-decoration: none;
          }}
        </style>
      </head>
      <body>{''.join(blocks)}</body>
    </html>
    """


class _AudioWebPage(QWebEnginePage):
    link_clicked = pyqtSignal(QUrl)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            self.link_clicked.emit(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class ChatWebView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {CHAT_SURFACE_BG}; border: none;")
        self._history: list[ChatItemData] = []
        self._active_audio_path: str = ""
        self._audio_playing: bool = False
        self._pending_play_path: str = ""
        # Default to QTextBrowser HTML rendering for stability on Linux GPU/GBM stacks.
        # Set HANAUTA_AI_POPUP_WEBENGINE=1 to force QWebEngineView.
        self._using_webengine = WEBENGINE_AVAILABLE and os.environ.get("HANAUTA_AI_POPUP_WEBENGINE", "0").strip() == "1"
        self._web_restore_mode: str = ""
        self._web_restore_ratio: float = 1.0
        self._view: QWebEngineView | QTextBrowser
        self._audio_output: QAudioOutput | None = None
        self._media_player: QMediaPlayer | None = None

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        if self._using_webengine:
            view = QWebEngineView(self)
            page = _AudioWebPage(view)
            page.link_clicked.connect(self._on_anchor_clicked)
            page.setBackgroundColor(QColor(CHAT_SURFACE_BG))
            view.setPage(page)
            view.loadFinished.connect(self._on_web_load_finished)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._view = view
        else:
            view = QTextBrowser(self)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.setOpenExternalLinks(False)
            view.setOpenLinks(False)
            view.setReadOnly(True)
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.anchorClicked.connect(self._on_anchor_clicked)
            view.highlighted.connect(self._on_anchor_hovered)
            view.customContextMenuRequested.connect(self._on_text_context_menu)
            self._view = view
        shell.addWidget(self._view, 1)

        if QT_MULTIMEDIA_AVAILABLE:
            try:
                self._audio_output = QAudioOutput(self)
                self._media_player = QMediaPlayer(self)
                self._media_player.setAudioOutput(self._audio_output)
                self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)
                self._media_player.errorOccurred.connect(self._on_media_error)
            except Exception:
                self._audio_output = None
                self._media_player = None
        self._view.setStyleSheet(
            f"""
            QTextBrowser, QWebEngineView {{
                background: {CHAT_SURFACE_BG};
                border: none;
                color: {TEXT};
            }}
            QScrollBar:vertical {{
                background: {rgba(CARD_BG_SOFT, 0.30)};
                width: 12px;
                margin: 6px 2px 6px 2px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {rgba(ACCENT, 0.82)};
                min-height: 28px;
                border-radius: 6px;
                border: 1px solid {rgba(BORDER_ACCENT, 0.92)};
            }}
            QScrollBar::handle:vertical:hover {{
                background: {rgba(ACCENT, 0.95)};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            """
        )

    def set_history(self, history: list[ChatItemData]) -> None:
        LOGGER.debug("ChatWebView.set_history called with %d items", len(history))
        self._history = list(history)
        self._rerender(preserve_scroll=False)
        self._scroll_bottom()

    def _scroll_bottom(self) -> None:
        try:
            if self._using_webengine:
                assert isinstance(self._view, QWebEngineView)
                self._view.page().runJavaScript("window.scrollTo(0, document.body.scrollHeight);")
            else:
                assert isinstance(self._view, QTextBrowser)
                bar = self._view.verticalScrollBar()
                bar.setValue(bar.maximum())
        except Exception:
            pass

    def _on_web_load_finished(self, ok: bool) -> None:
        if not ok or not self._using_webengine:
            return
        assert isinstance(self._view, QWebEngineView)
        if self._web_restore_mode == "bottom":
            self._view.page().runJavaScript("window.scrollTo(0, document.body.scrollHeight);")
            return
        if self._web_restore_mode == "ratio":
            ratio = max(0.0, min(1.0, float(self._web_restore_ratio)))
            self._view.page().runJavaScript(
                f"(function(){{const d=document.documentElement||document.body;"
                f"const max=Math.max(1,d.scrollHeight-window.innerHeight);window.scrollTo(0,Math.round(max*{ratio}));}})();"
            )

    def _rerender(self, preserve_scroll: bool = True) -> None:
        html_doc = render_chat_html(
            self._history,
            active_audio_path=self._active_audio_path,
            audio_playing=self._audio_playing,
        )
        if self._using_webengine:
            assert isinstance(self._view, QWebEngineView)
            if not preserve_scroll:
                self._web_restore_mode = "bottom"
                self._web_restore_ratio = 1.0
                self._view.setHtml(html_doc)
                return

            def _apply(result) -> None:
                y = 0.0
                max_scroll = 1.0
                if isinstance(result, (list, tuple)) and len(result) >= 2:
                    try:
                        y = float(result[0] or 0.0)
                        max_scroll = max(1.0, float(result[1] or 1.0))
                    except Exception:
                        y = 0.0
                        max_scroll = 1.0
                at_bottom = bool(y >= (max_scroll - 3.0))
                self._web_restore_mode = "bottom" if at_bottom else "ratio"
                self._web_restore_ratio = 1.0 if at_bottom else (y / max_scroll)
                self._view.setHtml(html_doc)

            self._view.page().runJavaScript(
                "(function(){const d=document.documentElement||document.body;"
                "const max=Math.max(1,d.scrollHeight-window.innerHeight);return [window.scrollY,max];})();",
                _apply,
            )
            return

        assert isinstance(self._view, QTextBrowser)
        bar = self._view.verticalScrollBar()
        old_value = int(bar.value())
        at_bottom = bool(old_value >= (bar.maximum() - 3))
        self._view.setHtml(html_doc)
        if not preserve_scroll:
            return
        def _restore() -> None:
            current_bar = self._view.verticalScrollBar()
            if at_bottom:
                current_bar.setValue(current_bar.maximum())
                return
            current_bar.setValue(min(old_value, current_bar.maximum()))
        QTimer.singleShot(0, _restore)
        QTimer.singleShot(24, _restore)
        QTimer.singleShot(72, _restore)

    def _set_audio_state(self, path: Path, playing: bool) -> None:
        self._active_audio_path = str(path.expanduser().resolve())
        self._audio_playing = bool(playing)
        self._rerender(preserve_scroll=True)

    def _on_playback_state_changed(self, state) -> None:
        if self._media_player is None:
            return
        playing = bool(state == QMediaPlayer.PlaybackState.PlayingState)
        if playing:
            self._pending_play_path = ""
        if playing == self._audio_playing:
            return
        self._audio_playing = playing
        self._rerender()

    def _on_media_error(self, *_args) -> None:
        if not self._pending_play_path:
            return
        pending = Path(self._pending_play_path)
        self._pending_play_path = ""
        LOGGER.warning("Qt multimedia playback failed; falling back to external player: %s", pending)
        _play_audio_file(pending)
        self._set_audio_state(pending, True)

    def _ensure_playback_started(self, path_text: str) -> None:
        if not self._pending_play_path or self._pending_play_path != path_text:
            return
        self._pending_play_path = ""
        if self._media_player is None:
            return
        state = self._media_player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            return
        pending = Path(path_text)
        LOGGER.warning(
            "Qt multimedia did not reach PlayingState (state=%s); external fallback for %s",
            state,
            pending,
        )
        _play_audio_file(pending)
        self._set_audio_state(pending, True)

    def _toggle_audio_path(self, path: Path) -> None:
        absolute = path.expanduser().resolve()
        if not absolute.exists():
            send_desktop_notification("Audio not found", str(absolute))
            return
        if self._media_player is None:
            _play_audio_file(absolute)
            self._set_audio_state(absolute, True)
            return
        current = self._active_audio_path
        is_current = bool(current and current == str(absolute))
        state = self._media_player.playbackState()
        if is_current and state == QMediaPlayer.PlaybackState.PlayingState:
            self._pending_play_path = ""
            self._media_player.pause()
            self._set_audio_state(absolute, False)
            return
        if is_current and state == QMediaPlayer.PlaybackState.PausedState:
            self._pending_play_path = str(absolute)
            self._media_player.play()
            self._set_audio_state(absolute, True)
            QTimer.singleShot(350, lambda p=str(absolute): self._ensure_playback_started(p))
            return
        self._pending_play_path = str(absolute)
        self._media_player.setSource(QUrl.fromLocalFile(str(absolute)))
        self._media_player.play()
        self._set_audio_state(absolute, True)
        QTimer.singleShot(350, lambda p=str(absolute): self._ensure_playback_started(p))

    def autoplay_audio(self, path: Path) -> None:
        self._toggle_audio_path(path)

    def _save_audio_as(self, source: Path) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save audio file",
            str(source.name),
            "WAV audio (*.wav);;All files (*)",
        )
        if not target:
            return
        try:
            shutil.copy2(str(source), str(Path(target).expanduser()))
        except Exception as exc:
            send_desktop_notification("Audio save failed", str(exc))

    def _on_anchor_clicked(self, url: QUrl) -> None:
        href = url.toString()
        audio_path = _audio_chip_path(href)
        if audio_path is not None:
            self._toggle_audio_path(audio_path)
            return
        QDesktopServices.openUrl(url)

    def _on_anchor_hovered(self, href: str) -> None:
        if self._using_webengine:
            return
        audio_path = _audio_chip_path(href) if href else None
        self._view.setToolTip(audio_path.name if audio_path is not None else "")

    def _on_text_context_menu(self, pos: QPoint) -> None:
        if self._using_webengine:
            return
        assert isinstance(self._view, QTextBrowser)
        anchor = self._view.anchorAt(pos)
        audio_path = _audio_chip_path(anchor) if anchor else None
        if audio_path is None:
            return
        menu = QMenu(self._view)
        play_pause_label = (
            "Pause"
            if self._active_audio_path == str(audio_path.expanduser().resolve()) and self._audio_playing
            else "Play"
        )
        play_action = menu.addAction(play_pause_label)
        save_action = menu.addAction("Download audio...")
        chosen = menu.exec(self._view.mapToGlobal(pos))
        if chosen == play_action:
            self._toggle_audio_path(audio_path)
        elif chosen == save_action:
            self._save_audio_as(audio_path)


class SdImageWorker(QThread):
    finished_ok = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    def __init__(self, profile: BackendProfile, settings: dict[str, object], prompt: str) -> None:
        super().__init__()
        self.profile = profile
        self.settings = settings
        self.prompt = prompt

    def run(self) -> None:
        try:
            path = self._generate()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(path), self.prompt, self.profile.label)

    def _generate(self) -> Path:
        url = _normalize_host_url(str(self.settings.get("host", self.profile.host)))
        IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        request_payload: dict[str, object] = {
            "prompt": self.prompt,
            "negative_prompt": str(self.settings.get("negative_prompt", "")),
            "sampler_name": str(self.settings.get("sampler_name", "Euler a")),
            "steps": int(float(str(self.settings.get("steps", "28")) or 28)),
            "cfg_scale": float(str(self.settings.get("cfg_scale", "7.0")) or 7.0),
            "width": int(float(str(self.settings.get("width", "1024")) or 1024)),
            "height": int(float(str(self.settings.get("height", "1024")) or 1024)),
        }
        checkpoint = str(self.settings.get("model", self.profile.model)).strip()
        if checkpoint:
            request_payload["override_settings"] = {"sd_model_checkpoint": checkpoint}
        response = _http_post_json(f"{url}/sdapi/v1/txt2img", request_payload, timeout=300.0)
        images = response.get("images", [])
        if not isinstance(images, list) or not images:
            raise RuntimeError("SD WebUI returned no images.")
        raw = str(images[0]).split(",", 1)[-1]
        file_path = IMAGE_OUTPUT_DIR / f"hanauta-ai-{int(time.time())}.png"
        file_path.write_bytes(b64decode(raw))
        return file_path


class TtsSynthesisWorker(QThread):
    finished_ok = pyqtSignal(str, str, str)
    failed = pyqtSignal(str)

    def __init__(self, profile: BackendProfile, settings: dict[str, object], text: str) -> None:
        super().__init__()
        self.profile = profile
        self.settings = settings
        self.text = text

    def run(self) -> None:
        try:
            audio_path, source = synthesize_tts(self.profile, self.settings, self.text)
        except Exception as exc:
            details = str(exc).strip() or exc.__class__.__name__
            self.failed.emit(details)
            return
        self.finished_ok.emit(str(audio_path), self.profile.label, source)


class MessageCard(FadeCard):
    def __init__(self, item: ChatItemData, ui_font: str) -> None:
        super().__init__()
        self.item = item
        self.browser: QTextBrowser | None = None
        self.bubble: QFrame | None = None

        self.setStyleSheet("background: transparent; border: none;")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        is_user = item.role == "user"
        bubble_bg = USER_BG if is_user else ASSISTANT_BG
        bubble_border = BORDER_ACCENT if is_user else rgba(BORDER_SOFT, 0.95)
        title_color = ACCENT_ALT if is_user else ACCENT

        avatar = AvatarBadge(
            "Y" if is_user else "AI",
            bg=ACCENT_SOFT if is_user else rgba(CARD_BG_SOFT, 0.96),
            fg=ACCENT_ALT if is_user else ACCENT,
            ui_font=ui_font,
        )

        bubble = QFrame()
        bubble.setObjectName("messageBubble")
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        bubble.setStyleSheet(
            f"""
            QFrame#messageBubble {{
                background: {bubble_bg};
                border: 1px solid {bubble_border};
                border-radius: 24px;
            }}
            QLabel {{
                color: {TEXT};
            }}
            QTextBrowser {{
                background: transparent;
                border: none;
                color: {TEXT};
                font-size: 12px;
            }}
            """
        )
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(16, 14, 16, 16)
        bubble_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {title_color}; font-size: 8px;")
        header.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

        title = QLabel(item.title)
        title.setFont(QFont(ui_font, 11, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {title_color};")
        header.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)

        if item.meta:
            meta = QLabel(item.meta)
            meta.setFont(QFont(ui_font, 9))
            meta.setStyleSheet(f"color: {TEXT_DIM};")
            header.addWidget(meta, 0, Qt.AlignmentFlag.AlignVCenter)

        header.addStretch(1)
        copy_button = ActionIcon("⧉", "Copy response", ui_font)
        copy_button.clicked.connect(self._copy_body)
        header.addWidget(copy_button)
        header.addWidget(ActionIcon("⋯", "More", ui_font))
        bubble_layout.addLayout(header)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setFrameShape(QFrame.Shape.NoFrame)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        browser.document().setDocumentMargin(0)
        browser.setStyleSheet(
            f"""
            QTextBrowser {{
                color: {CHAT_TEXT};
                background: transparent;
                border: none;
                font-size: 12px;
                line-height: 1.50;
            }}
            """
        )
        browser.document().setDefaultStyleSheet(
            f"""
            body {{
                color: {CHAT_TEXT};
                font-size: 12px;
                line-height: 1.50;
                margin: 0;
            }}
            p {{
                margin-top: 0;
                margin-bottom: 8px;
            }}
            b {{
                color: {CHAT_TEXT};
                font-weight: 700;
            }}
            code {{
                background: {rgba(CARD_BG_SOFT, 0.94)};
                padding: 2px 6px;
                border-radius: 10px;
                color: {CHAT_TEXT};
            }}
            pre {{
                background: {rgba(CARD_BG_SOFT, 0.96)};
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                padding: 10px 12px;
                border-radius: 16px;
                color: {CHAT_TEXT};
                white-space: pre-wrap;
            }}
            a {{
                color: {ACCENT};
                text-decoration: none;
            }}
            ul {{
                margin: 6px 0 8px 18px;
            }}
            """
        )
        browser.setHtml(item.body)
        browser.document().contentsChanged.connect(lambda b=browser: self._fit_browser_height(b))
        bubble_layout.addWidget(browser)

        if item.chips:
            chips_wrap = QWidget()
            chips_layout = QHBoxLayout(chips_wrap)
            chips_layout.setContentsMargins(0, 0, 0, 0)
            chips_layout.setSpacing(8)
            for chip in item.chips:
                chips_layout.addWidget(self._chip(chip.text, ui_font))
            chips_layout.addStretch(1)
            bubble_layout.addWidget(chips_wrap)

        self.browser = browser
        self.bubble = bubble
        self._fit_browser_height(browser)

        if is_user:
            root.addStretch(1)
            root.addWidget(bubble, 0)
            root.addWidget(avatar, 0, Qt.AlignmentFlag.AlignBottom)
        else:
            root.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            root.addWidget(bubble, 0)
            root.addStretch(1)

    def _copy_body(self) -> None:
        QApplication.clipboard().setText(self.browser.toPlainText() if self.browser else "")

    def _chip(self, text: str, ui_font: str) -> QPushButton:
        chip = QPushButton(text)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setFont(QFont(ui_font, 10))
        chip.setStyleSheet(
            f"""
            QPushButton {{
                background: {rgba(CARD_BG_SOFT, 0.92)};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 999px;
                padding: 7px 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
            }}
            """
        )
        return chip

    def _fit_browser_height(self, browser: QTextBrowser) -> None:
        viewport_width = max(0, browser.viewport().width())
        if viewport_width > 0:
            browser.document().setTextWidth(viewport_width)
        height = int(browser.document().documentLayout().documentSize().height() + 8)
        browser.setFixedHeight(max(28, height))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.bubble is not None:
            self.bubble.setMaximumWidth(max(280, int(self.width() * 0.80)))
        if self.browser is not None:
            self._fit_browser_height(self.browser)


class ComposerBar(QFrame):
    send_requested = pyqtSignal(str)
    character_requested = pyqtSignal()

    def __init__(self, ui_font: str) -> None:
        super().__init__()
        self._ui_font = ui_font
        self.provider_label = QLabel("")
        self.setObjectName("composerBar")
        self.setStyleSheet(
            f"""
            QFrame#composerBar {{
                background: {BOTTOM_BG};
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                border-radius: 24px;
            }}
            QLabel {{
                color: {TEXT_DIM};
            }}
            QPlainTextEdit {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.98)};
                border-radius: 20px;
                font-size: 12px;
                padding: 10px 12px;
                selection-background-color: {ACCENT_SOFT};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.entry = ChatInputEdit(ui_font)
        self.entry.send_requested.connect(self._emit_send)
        layout.addWidget(self.entry)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(10)

        self.provider_label.setFont(QFont(ui_font, 10, QFont.Weight.DemiBold))
        self.provider_label.setStyleSheet(f"color: {TEXT_MID};")
        footer.addWidget(self.provider_label)

        footer.addStretch(1)

        character_button = AntiAliasButton("Characters", ui_font)
        character_button.clicked.connect(self.character_requested.emit)
        footer.addWidget(character_button)

        clear_hint = QLabel("/clear")
        clear_hint.setFont(QFont(ui_font, 10, QFont.Weight.DemiBold))
        clear_hint.setStyleSheet(
            f"color: {TEXT_DIM}; background: {rgba(CARD_BG_SOFT, 0.22)}; border: none; padding: 6px 10px;"
        )
        footer.addWidget(clear_hint)

        send_button = AntiAliasButton("Send", ui_font)
        send_button.clicked.connect(self._emit_send)
        footer.addWidget(send_button)
        layout.addLayout(footer)

    def set_profile(self, profile: BackendProfile) -> None:
        self.provider_label.setText(f"{profile.label}  •  {profile.model}")

    def _emit_send(self) -> None:
        text = self.entry.toPlainText().strip()
        if text:
            self.send_requested.emit(text)
            self.entry.clear()
            self.entry._sync_height()


class CharacterLibraryDialog(QDialog):
    def __init__(self, cards: list[CharacterCard], active_id: str, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Character Library")
        self.cards = [CharacterCard(**card.__dict__) for card in cards]
        self.active_id = active_id
        self.selected_id = active_id
        self.setMinimumWidth(560)
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {PANEL_BG_FLOAT};
                color: {TEXT};
            }}
            QComboBox, QPlainTextEdit {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QLabel {{
                color: {TEXT_MID};
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Characters")
        title.setFont(QFont(ui_font, 13, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        layout.addWidget(title)

        self.combo = QComboBox()
        self.combo.setFont(QFont(ui_font, 11))
        self.combo.currentIndexChanged.connect(self._refresh_preview)
        layout.addWidget(self.combo)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(220)
        layout.addWidget(self.preview)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        import_button = QPushButton("Import JSON/PNG")
        import_button.clicked.connect(self._import_cards)
        row.addWidget(import_button)

        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected)
        row.addWidget(remove_button)

        row.addStretch(1)
        layout.addLayout(row)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        disable_button = QPushButton("Disable character")
        disable_button.clicked.connect(self._disable_character)
        actions.addWidget(disable_button)

        use_button = QPushButton("Use selected")
        use_button.clicked.connect(self._accept_selected)
        actions.addWidget(use_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        layout.addLayout(actions)

        self._reload_combo()

    def _reload_combo(self) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("None", "")
        active_index = 0
        for card in self.cards:
            self.combo.addItem(card.name, card.id)
            if self.selected_id and card.id == self.selected_id:
                active_index = self.combo.count() - 1
        self.combo.setCurrentIndex(active_index)
        self.combo.blockSignals(False)
        self._refresh_preview()

    def _current_card(self) -> CharacterCard | None:
        current_id = str(self.combo.currentData() or "").strip()
        for card in self.cards:
            if card.id == current_id:
                return card
        return None

    def _refresh_preview(self) -> None:
        card = self._current_card()
        if card is None:
            self.preview.setPlainText("No character selected.")
            return
        lines = [
            f"Name: {card.name}",
            f"Source: {card.source_type or 'imported'}",
            f"File: {card.source_path or '-'}",
        ]
        if card.description:
            lines.append(f"\nDescription:\n{card.description}")
        if card.personality:
            lines.append(f"\nPersonality:\n{card.personality}")
        if card.scenario:
            lines.append(f"\nScenario:\n{card.scenario}")
        if card.first_message:
            lines.append(f"\nFirst message:\n{card.first_message}")
        if card.system_prompt:
            lines.append(f"\nSystem prompt:\n{card.system_prompt}")
        self.preview.setPlainText("\n".join(lines))

    def _import_cards(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import character cards",
            str(Path.home()),
            "Character Cards (*.json *.png);;JSON (*.json);;PNG (*.png)",
        )
        if not paths:
            return
        imported_names: list[str] = []
        for raw in paths:
            source = Path(raw).expanduser()
            try:
                card = import_character_from_file(source)
            except Exception as exc:
                send_desktop_notification("Character import failed", f"{source.name}: {exc}")
                continue
            existing_idx = next((idx for idx, row in enumerate(self.cards) if row.name == card.name), None)
            if existing_idx is None:
                self.cards.append(card)
            else:
                self.cards[existing_idx] = card
            self.selected_id = card.id
            imported_names.append(card.name)
        self._reload_combo()
        if imported_names:
            send_desktop_notification("Character import", f"Imported: {', '.join(imported_names[:4])}")

    def _remove_selected(self) -> None:
        card = self._current_card()
        if card is None:
            return
        self.cards = [row for row in self.cards if row.id != card.id]
        if self.selected_id == card.id:
            self.selected_id = ""
        self._reload_combo()

    def _disable_character(self) -> None:
        self.selected_id = ""
        self.accept()

    def _accept_selected(self) -> None:
        self.selected_id = str(self.combo.currentData() or "").strip()
        self.accept()


class SidebarPanel(QFrame):
    def __init__(self, ui_font: str) -> None:
        super().__init__()
        self.ui_font = ui_font
        self.icon_font = load_material_icon_font()
        self.profiles = [
            BackendProfile("gemini", "Gemini", "gemini", "gemini-2.0-flash", "Google", "gemini", True),
            BackendProfile("koboldcpp", "KoboldCpp", "openai_compat", "koboldcpp", "127.0.0.1:5001", "koboldcpp", False, True),
            BackendProfile("lmstudio", "LM Studio", "openai_compat", "local-model", "127.0.0.1:1234", "lmstudio"),
            BackendProfile("ollama", "Ollama", "ollama", "llama3.2", "127.0.0.1:11434", "ollama"),
            BackendProfile("openai", "OpenAI", "openai", "gpt-4.1-mini", "api.openai.com", "openai", True),
            BackendProfile("mistral", "Mistral", "openai", "mistral-small", "api.mistral.ai", "mistral", True),
            BackendProfile("sdwebui", "SD WebUI", "sdwebui", "sdxl", "127.0.0.1:7860", "sdwebui"),
            BackendProfile("sdreforge", "SD ReForge", "sdwebui", "sdxl", "127.0.0.1:7861", "sdreforge"),
            BackendProfile("kokorotts", "KokoroTTS", "tts_local", "kokoro", "127.0.0.1:8880", "kokorotts", False, True),
            BackendProfile("pockettts", "PocketTTS", "tts_local", "pocket", "127.0.0.1:8890", "pockettts", False, True),
        ]
        self.profile_by_key = {profile.key: profile for profile in self.profiles}
        self.backend_settings = load_backend_settings()
        self.current_profile: BackendProfile | None = None
        self._card_animations: list[QPropertyAnimation] = []
        self.chat_history = secure_load_chat_history()
        self.character_cards, self.active_character_id = load_character_library()
        self._sd_seen_outputs: dict[str, tuple[str, float]] = {}
        self._image_worker: SdImageWorker | None = None
        self._tts_worker: TtsSynthesisWorker | None = None
        self._local_backend_processes: dict[str, subprocess.Popen[str]] = {}
        self._pending_item: ChatItemData | None = None
        self._text_response_timer = QTimer(self)
        self._text_response_timer.setSingleShot(True)
        self._text_response_timer.timeout.connect(self._finish_mock_text_response)

        self.setObjectName("sidebarPanel")
        self.setFixedWidth(452)
        self.setStyleSheet(
            f"""
            QFrame#sidebarPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {PANEL_BG_FLOAT},
                    stop:0.55 {rgba(HERO_BOTTOM, 0.97)},
                    stop:1 {rgba(PANEL_BG_DEEP, 0.99)});
                border: 1px solid {BORDER_HARD};
                border-radius: 34px;
            }}
            QToolTip {{
                background: {rgba(CARD_BG, 0.98)};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_ACCENT, 0.92)};
                border-radius: 10px;
                padding: 7px 10px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 18)
        glow = QColor(SHADOW)
        shadow.setColor(glow)
        self.setGraphicsEffect(shadow)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._build_hero())
        root.addWidget(self._build_backend_strip())

        convo_shell = SurfaceFrame(bg=rgba(CARD_BG, 0.72), border=rgba(BORDER_SOFT, 0.85), radius=28)
        convo_layout = QVBoxLayout(convo_shell)
        convo_layout.setContentsMargins(10, 10, 10, 10)
        convo_layout.setSpacing(8)

        convo_label = QLabel("Conversation")
        convo_label.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        convo_label.setStyleSheet(f"color: {UI_TEXT_STRONG}; padding-left: 4px;")
        convo_layout.addWidget(convo_label)

        self.chat_view = ChatWebView()
        convo_layout.addWidget(self.chat_view, 1)

        root.addWidget(convo_shell, 1)

        self.composer = ComposerBar(ui_font)
        self.composer.send_requested.connect(self.add_user_message)
        self.composer.character_requested.connect(self._open_character_library)
        root.addWidget(self.composer)

        self._render_chat_history()
        self._refresh_available_backends()
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self._poll_sd_output_monitors)
        self.monitor_timer.start(8000)

    def _popup_open(self) -> bool:
        win = self.window()
        return bool(win is not None and win.isVisible() and not win.isMinimized())

    def _notify_if_popup_closed(self, title: str, body: str) -> None:
        if not self._popup_open():
            send_desktop_notification(title, body)

    def _build_hero(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("heroCard")
        frame.setStyleSheet(
            f"""
            QFrame#heroCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {rgba(HERO_TOP, 0.98)},
                    stop:1 {rgba(HERO_BOTTOM, 0.94)});
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                border-radius: 26px;
            }}
            QLabel {{
                color: {UI_TEXT_STRONG};
            }}
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        orb = QLabel("◉")
        orb.setFont(QFont(self.ui_font, 13, QFont.Weight.Bold))
        orb.setStyleSheet(f"color: {ACCENT};")
        top.addWidget(orb, 0, Qt.AlignmentFlag.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(0)

        title = QLabel("Hanauta AI")
        title.setFont(QFont(self.ui_font, 16, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        title_wrap.addWidget(title)
        top.addLayout(title_wrap, 1)

        settings_button = ActionIcon("⚙", "Backend settings", self.ui_font)
        settings_button.clicked.connect(self._open_backend_settings)
        top.addWidget(settings_button)

        close_button = create_close_button("\ue5cd", self.icon_font)
        close_button.setToolTip("Close")
        close_button.setProperty("iconButton", True)
        close_button.setFixedSize(34, 34)
        close_button.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {UI_ICON_DIM};
                border: none;
                border-radius: 17px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                color: {UI_ICON_ACTIVE};
            }}
            """
        )
        close_button.clicked.connect(self.window().close)
        top.addWidget(close_button)
        layout.addLayout(top)

        status_shell = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.64), border=rgba(BORDER_SOFT, 0.90), radius=18)
        status_layout = QVBoxLayout(status_shell)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(0)

        self.header_status = QLabel("Configure backends with the gear icon.")
        self.header_status.setFont(QFont(self.ui_font, 10, QFont.Weight.DemiBold))
        self.header_status.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        status_layout.addWidget(self.header_status)
        layout.addWidget(status_shell)

        return frame

    def _build_backend_strip(self) -> QFrame:
        self.backend_buttons: dict[str, BackendPill] = {}

        frame = SurfaceFrame(bg=rgba(CARD_BG, 0.82), border=rgba(BORDER_SOFT, 0.88), radius=26)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        label = QLabel("Backends")
        label.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        label.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        label.setMinimumWidth(92)
        row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)

        icon_row = QHBoxLayout()
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_row.setSpacing(8)
        for profile in self.profiles:
            button = BackendPill(profile, self.ui_font)
            button.clicked.connect(lambda checked=False, p=profile, b=button: self._select_backend(p, b))
            self.backend_buttons[profile.key] = button
            icon_row.addWidget(button)
        icon_row.addStretch(1)

        row.addLayout(icon_row, 1)
        layout.addLayout(row)
        return frame

    def _refresh_backend_hint(self) -> None:
        if self.current_profile is None:
            self.header_status.setText("No active backend.")
            return
        payload = self.backend_settings.get(self.current_profile.key, {})
        host = str(payload.get("host", self.current_profile.host))
        model = str(payload.get("model", self.current_profile.model))
        if self.current_profile.provider == "tts_local":
            mode = _default_tts_mode(payload)
            model_dir = _default_tts_model_dir(self.current_profile, payload)
            if mode == "external_api":
                self.header_status.setText(f"{self.current_profile.label}  •  external API  •  {host}")
            else:
                self.header_status.setText(f"{self.current_profile.label}  •  local ONNX  •  {model_dir}")
            return
        self.header_status.setText(f"{self.current_profile.label}  •  {model}  •  {host}")

    def _active_character(self) -> CharacterCard | None:
        if not self.active_character_id:
            return None
        for card in self.character_cards:
            if card.id == self.active_character_id:
                return card
        return None

    def _refresh_character_status(self) -> None:
        return

    def _open_character_library(self) -> None:
        dialog = CharacterLibraryDialog(self.character_cards, self.active_character_id, self.ui_font, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.character_cards = dialog.cards
        self.active_character_id = dialog.selected_id
        save_character_library(self.character_cards, self.active_character_id)
        active = self._active_character()
        if active is None:
            send_desktop_notification("Character disabled", "No character card is active.")
        else:
            send_desktop_notification("Character selected", active.name)

    def _select_backend(self, profile: BackendProfile, active_button: BackendPill) -> None:
        settings = self.backend_settings.get(profile.key, {})
        if not settings.get("tested") or not settings.get("enabled", True):
            if profile.key != "koboldcpp" or not self._maybe_launch_koboldcpp(profile):
                return
            settings = self.backend_settings.get(profile.key, {})
        elif profile.key == "koboldcpp":
            self._maybe_launch_koboldcpp(profile)
        self.current_profile = profile
        for button in self.backend_buttons.values():
            if button is not active_button:
                button.setChecked(False)
        active_button.setChecked(True)
        self._refresh_backend_hint()
        self.composer.set_profile(profile)

    def _refresh_available_backends(self) -> None:
        available: list[BackendProfile] = []
        for profile in self.profiles:
            payload = self.backend_settings.get(profile.key, {})
            button = self.backend_buttons.get(profile.key)
            ready = bool(payload.get("enabled", True) and payload.get("tested", False))
            if button is not None:
                button.setEnabled(ready)
                button.setChecked(False)
                button.setToolTip(f"{profile.label} — {'ready' if ready else 'not tested'}")
            if ready:
                available.append(profile)

        self.current_profile = available[0] if available else None
        if self.current_profile is not None:
            active = self.backend_buttons.get(self.current_profile.key)
            if active is not None:
                active.setChecked(True)
            self.composer.set_profile(self.current_profile)
            self.composer.entry.setEnabled(True)
            self.composer.entry.setPlaceholderText('Message the model...  Enter to send • Shift+Enter for newline')
        else:
            self.composer.provider_label.setText("No tested backend configured")
            self.composer.entry.setEnabled(False)
            self.composer.entry.setPlaceholderText("Open backend settings to configure a provider")
        self._refresh_backend_hint()

    def _open_backend_settings(self) -> None:
        dialog = BackendSettingsDialog(self.profiles, self.backend_settings, self.ui_font, self)
        dialog.exec()
        self.backend_settings = load_backend_settings()
        self._refresh_available_backends()

    def _render_chat_history(self) -> None:
        history = list(self.chat_history)
        if self._pending_item is not None:
            history.append(self._pending_item)
        LOGGER.debug(
            "render_chat_history: stored=%d pending=%s total=%d",
            len(self.chat_history),
            self._pending_item is not None,
            len(history),
        )
        self.chat_view.set_history(history)

    def _maybe_launch_koboldcpp(self, profile: BackendProfile) -> bool:
        payload = dict(self.backend_settings.get(profile.key, {}))
        host = str(payload.get("host", profile.host)).strip()
        if host and _openai_compat_alive(host):
            return True
        process = self._local_backend_processes.get(profile.key)
        if process is not None and process.poll() is None:
            return True
        binary_path = _existing_path(payload.get("binary_path"))
        gguf_path = _existing_path(payload.get("gguf_path"))
        if binary_path is None or gguf_path is None:
            return False
        answer = QMessageBox.question(
            self,
            "Start KoboldCpp",
            "KoboldCpp is not responding. Start it now with the configured GGUF model?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        ok, message = self._launch_koboldcpp_process(profile, payload)
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Hanauta AI",
                meta="runtime launch" if ok else "runtime launch failed",
                body=f"<p>{html.escape(message)}</p>",
            )
        )
        return ok

    def _launch_koboldcpp_process(self, profile: BackendProfile, payload: dict[str, object]) -> tuple[bool, str]:
        binary_path = _existing_path(payload.get("binary_path"))
        gguf_path = _existing_path(payload.get("gguf_path"))
        if binary_path is None or gguf_path is None:
            return False, "Configure both the KoboldCpp binary path and GGUF model first."
        command = [str(binary_path), "--model", str(gguf_path)]
        mmproj_path = _existing_path(payload.get("mmproj_path"))
        if mmproj_path is not None:
            command.extend(["--mmproj", str(mmproj_path)])
        host = str(payload.get("host", profile.host)).strip()
        if host:
            parsed = urlparse(_normalize_host_url(host))
            if parsed.port:
                command.extend(["--port", str(parsed.port)])
        if str(payload.get("device", "cpu")).lower() == "gpu":
            command.append("--usecublas")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            return False, f"Unable to start KoboldCpp: {exc}"
        self._local_backend_processes[profile.key] = process
        send_desktop_notification("KoboldCpp starting", f"{profile.label} is starting with {gguf_path.name}.")
        return True, f"Starting KoboldCpp with {gguf_path.name}."

    def _clear_cards(self) -> None:
        self.chat_history = []
        self._pending_item = None
        self._text_response_timer.stop()
        secure_clear_chat_history()
        self._render_chat_history()

    def add_card(self, data: ChatItemData, animate: bool = True) -> None:
        del animate
        LOGGER.debug(
            "add_card: role=%s title=%r meta=%r body_len=%d",
            data.role,
            data.title,
            data.meta,
            len(data.body or ""),
        )
        self.chat_history.append(data)
        secure_append_chat(data)
        self._render_chat_history()

    def _set_pending_state(self, profile_label: str, message: str, meta: str) -> None:
        LOGGER.debug("set_pending_state: profile=%r meta=%r message=%r", profile_label, meta, message)
        self._pending_item = ChatItemData(
            role="assistant",
            title=profile_label,
            meta=meta,
            body=(
                f'<div class="loading-row"><span class="loading-ring"></span>'
                f"<span>{html.escape(message)}</span></div>"
            ),
            pending=True,
        )
        self.composer.entry.setEnabled(False)
        self._render_chat_history()

    def _clear_pending_state(self) -> None:
        LOGGER.debug("clear_pending_state")
        self._pending_item = None
        self.composer.entry.setEnabled(self.current_profile is not None)
        self._render_chat_history()

    def _build_image_response(self, image_path: Path, prompt: str) -> str:
        image_url = image_path.resolve().as_uri()
        return (
            f"<p><b>Image generated.</b> Prompt: {html.escape(prompt)}</p>"
            f'<p><img src="{image_url}" alt="Generated image"/></p>'
            f"<p><a href=\"{image_url}\">Open image</a></p>"
        )

    def _poll_sd_output_monitors(self) -> None:
        for profile in self.profiles:
            if profile.provider != "sdwebui":
                continue
            payload = self.backend_settings.get(profile.key, {})
            if not bool(payload.get("monitor_enabled", False)):
                continue
            output_dir = Path(str(payload.get("output_dir", "")).strip()).expanduser()
            if not output_dir.exists() or not output_dir.is_dir():
                continue
            candidates = [
                path for path in output_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            if not candidates:
                continue
            latest = max(candidates, key=lambda item: item.stat().st_mtime)
            latest_state = (str(latest), latest.stat().st_mtime)
            previous = self._sd_seen_outputs.get(profile.key)
            self._sd_seen_outputs[profile.key] = latest_state
            if previous is None:
                continue
            if latest_state != previous:
                send_desktop_notification("SD image detected", f"New image found for {profile.label}: {latest.name}")

    def _start_image_generation(self, profile: BackendProfile, prompt: str) -> None:
        if self._image_worker is not None and self._image_worker.isRunning():
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    meta="image generation busy",
                    body="<p>An image is already being generated. Please wait for it to finish.</p>",
                )
            )
            return
        self._set_pending_state(profile.label, "Response is being generated", "image generation")
        self._image_worker = SdImageWorker(profile, dict(self.backend_settings.get(profile.key, {})), prompt)
        self._image_worker.finished_ok.connect(self._handle_image_generated)
        self._image_worker.failed.connect(self._handle_image_failed)
        self._image_worker.finished.connect(self._finish_image_worker)
        self._image_worker.start()

    def _handle_image_generated(self, image_path_text: str, prompt: str, profile_label: str) -> None:
        image_path = Path(image_path_text)
        self._clear_pending_state()
        self.add_card(
            ChatItemData(
                role="assistant",
                title=profile_label,
                meta="image generated",
                body=self._build_image_response(image_path, prompt),
                chips=[SourceChipData("sd image"), SourceChipData(image_path.name)],
            )
        )
        self._notify_if_popup_closed("Image generated", f"{profile_label} finished a new image.")

    def _handle_image_failed(self, message: str) -> None:
        self._clear_pending_state()
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Hanauta AI",
                meta="image generation failed",
                body=f"<p>Unable to generate image: {html.escape(message)}</p>",
            )
        )

    def _finish_image_worker(self) -> None:
        self._image_worker = None

    def _start_tts_generation(self, profile: BackendProfile, text: str) -> None:
        clean = text.strip()
        if not clean:
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    meta="tts",
                    body="<p>Please provide text for speech synthesis.</p>",
                )
            )
            return
        if self._tts_worker is not None and self._tts_worker.isRunning():
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    meta="tts busy",
                    body="<p>A TTS request is already running. Wait for it to finish.</p>",
                )
            )
            return
        self._set_pending_state(profile.label, "Synthesizing speech", "tts")
        payload = dict(self.backend_settings.get(profile.key, {}))
        self._tts_worker = TtsSynthesisWorker(profile, payload, clean)
        self._tts_worker.finished_ok.connect(self._handle_tts_generated)
        self._tts_worker.failed.connect(self._handle_tts_failed)
        self._tts_worker.finished.connect(self._finish_tts_worker)
        self._tts_worker.start()

    def _handle_tts_generated(self, audio_path_text: str, profile_label: str, source: str) -> None:
        self._clear_pending_state()
        audio_path = Path(audio_path_text)
        resolved_audio = audio_path.expanduser().resolve()
        audio_url = resolved_audio.as_uri()
        self.add_card(
            ChatItemData(
                role="assistant",
                title=profile_label,
                meta="tts",
                body=(
                    "<p><b>Speech generated.</b> Playback was started automatically.</p>"
                    f"<p><a href=\"{audio_url}\">Open audio file</a></p>"
                ),
                chips=[SourceChipData("tts"), SourceChipData(source)],
                audio_path=str(resolved_audio),
            )
        )
        try:
            self.chat_view.autoplay_audio(resolved_audio)
        except Exception:
            LOGGER.exception("autoplay failed for %s", resolved_audio)
        self._notify_if_popup_closed("Speech generated", f"{profile_label} finished speaking.")

    def _handle_tts_failed(self, message: str) -> None:
        self._clear_pending_state()
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Hanauta AI",
                meta="tts failed",
                body=f"<p>Unable to synthesize speech: {html.escape(message)}</p>",
            )
        )

    def _finish_tts_worker(self) -> None:
        self._tts_worker = None

    def _finish_mock_text_response(self) -> None:
        LOGGER.debug("finish_mock_text_response: timer fired")
        self._clear_pending_state()
        if self.current_profile is None:
            LOGGER.debug("finish_mock_text_response: no current_profile")
            return
        summary = (
            "Mock response ready. "
            f"Backend: {self.current_profile.label} ({self.current_profile.model})."
        )
        active_character = self._active_character()
        character_line = ""
        chips = [SourceChipData(self.current_profile.provider), SourceChipData(self.current_profile.model)]
        if active_character is not None:
            prompt_preview = _character_compose_prompt(active_character)
            preview_html = html.escape(prompt_preview[:240] + ("..." if len(prompt_preview) > 240 else ""))
            character_line = (
                f"<p>Active character: <b>{html.escape(active_character.name)}</b>.</p>"
                f"<p>Character prompt preview: <code>{preview_html}</code></p>"
            )
            chips.append(SourceChipData(f"character:{active_character.name}"))
        self.add_card(
            ChatItemData(
                role="assistant",
                title=self.current_profile.label,
                meta=self.current_profile.model,
                body=(
                    "<p><b>Mock response:</b> text backends are still using the current placeholder response layer.</p>"
                    f"<p>Active backend: <b>{html.escape(self.current_profile.label)}</b> at <b>{html.escape(self.current_profile.host)}</b>.</p>"
                    f"{character_line}"
                    "<p>The chat history and secure backend secrets are now stored outside the project in Hanauta state.</p>"
                ),
                chips=chips,
            )
        )
        LOGGER.debug("finish_mock_text_response: answer card appended")
        self._notify_if_popup_closed("New AI answer", summary)

    def add_user_message(self, text: str) -> None:
        command = text.strip()
        LOGGER.info(
            "add_user_message: raw_len=%d command=%r profile=%s",
            len(text or ""),
            command[:180],
            self.current_profile.key if self.current_profile else "none",
        )
        if command == "/clear":
            LOGGER.debug("command /clear")
            self._clear_cards()
            return
        if command == "/tts":
            LOGGER.debug("command /tts")
            self._open_backend_settings()
            return
        if self.current_profile is None:
            LOGGER.warning("message ignored because no current_profile")
            return

        safe = html.escape(text).replace("\n", "<br>")
        active_character = self._active_character()
        user_chips: list[SourceChipData] = []
        if active_character is not None:
            user_chips.append(SourceChipData(f"character:{active_character.name}"))
        self.add_card(ChatItemData(role="user", title="You", body=f"<p>{safe}</p>", meta="prompt", chips=user_chips))

        if command == "/say" or command == "/speak":
            LOGGER.debug("command /say|/speak without payload")
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    body="<p>Usage: <code>/say your text</code></p>",
                    meta="tts command",
                )
            )
            return

        if command.startswith("/speak ") or command.startswith("/say "):
            LOGGER.debug("command /say|/speak with payload")
            prefix = "/say " if command.startswith("/say ") else "/speak "
            speak_prompt = command[len(prefix):].strip()
            if self.current_profile.provider != "tts_local":
                self.add_card(
                    ChatItemData(
                        role="assistant",
                        title="Hanauta AI",
                        body="<p>Select KokoroTTS or PocketTTS before using <code>/say</code>.</p>",
                        meta="tts command",
                    )
                )
                return
            self._start_tts_generation(self.current_profile, speak_prompt)
            return

        if command.startswith("/image "):
            LOGGER.debug("command /image")
            prompt = command[len("/image "):].strip()
            if self.current_profile.provider != "sdwebui":
                self.add_card(
                    ChatItemData(
                        role="assistant",
                        title="Hanauta AI",
                        body="<p>Select an SD WebUI or SD ReForge backend before using <code>/image</code>.</p>",
                        meta="image command",
                    )
                )
                return
            if not prompt:
                self.add_card(
                    ChatItemData(role="assistant", title="Hanauta AI", body="<p>Usage: <code>/image your prompt</code></p>", meta="image command")
                )
                return
            self._start_image_generation(self.current_profile, prompt)
            return

        if self.current_profile.provider == "tts_local":
            LOGGER.debug("plain text with tts_local backend; showing guidance card")
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    body=(
                        "<p>This backend is TTS-only.</p>"
                        "<p>Use <code>/say your text</code> to synthesize speech, or switch to a text backend for chat replies.</p>"
                    ),
                    meta="tts command",
                )
            )
            return

        LOGGER.debug("starting mock text response timer (1350ms)")
        self._set_pending_state(self.current_profile.label, "Response is being generated", "text generation")
        self._text_response_timer.start(1350)


class DemoWindow(QMainWindow):
    def __init__(self, ui_font: str) -> None:
        super().__init__()
        self.ui_font = ui_font
        self._theme_mtime = palette_mtime()
        self._slide_animation: QPropertyAnimation | None = None
        self._fade_animation: QPropertyAnimation | None = None
        self._drag_offset: QPoint | None = None
        self._screen_fix_applied = False

        self.setWindowTitle("Hanauta AI")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        root = QWidget()
        root.setStyleSheet("background: transparent;")
        self.setCentralWidget(root)
        self.root = root

        self.layout = QVBoxLayout(root)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self._build_panel()

        self.resize(452, 930)
        self._place_window()
        self.setWindowOpacity(1.0)

        self.theme_timer = QTimer(self)
        self.theme_timer.timeout.connect(self._reload_theme_if_needed)
        self.theme_timer.start(3000)

    def _build_panel(self) -> None:
        if hasattr(self, "panel") and self.panel is not None:
            self.layout.removeWidget(self.panel)
            self.panel.deleteLater()
        self.panel = SidebarPanel(self.ui_font)
        self.layout.addWidget(self.panel)

    def _reload_theme_if_needed(self) -> None:
        current_mtime = palette_mtime()
        if current_mtime == self._theme_mtime:
            return
        self._theme_mtime = current_mtime
        apply_theme_globals()
        self._build_panel()

    def _place_window(self) -> None:
        workspace = focused_workspace()
        if isinstance(workspace, dict):
            rect = workspace.get("rect")
            if isinstance(rect, dict):
                try:
                    self.move(int(rect.get("x", 0)) + 16, int(rect.get("y", 0)) + 40)
                    return
                except Exception:
                    pass
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(16, 44)
            return
        geo = screen.availableGeometry()
        self.move(geo.x() + 16, geo.y() + 40)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._screen_fix_applied:
            return
        self._screen_fix_applied = True
        QTimer.singleShot(0, self._force_primary_screen)

    def _force_primary_screen(self) -> None:
        workspace = focused_workspace()
        screen = None
        if isinstance(workspace, dict):
            rect = workspace.get("rect")
            if isinstance(rect, dict):
                try:
                    screen = QGuiApplication.screenAt(
                        QPoint(int(rect.get("x", 0)) + 48, int(rect.get("y", 0)) + 48)
                    )
                except Exception:
                    screen = None
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            handle = self.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
        self._place_window()

    def _animate_in(self) -> None:
        self._slide_animation = None
        self._fade_animation = None
        self.setWindowOpacity(1.0)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 110:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ui_font = load_ui_font()
    app.setFont(QFont(ui_font, 10))
    def _handle_sigint(_sig, _frame) -> None:
        LOGGER.info("SIGINT received (Ctrl+C). Quitting Hanauta AI popup.")
        app.quit()
    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception as exc:
        LOGGER.warning("Unable to install SIGINT handler: %s", exc)
    window = DemoWindow(ui_font)
    window.show()
    sys.exit(app.exec())
