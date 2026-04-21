#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import hashlib
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
import re
import zipfile
import zlib
from base64 import b64decode, b64encode
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
from PyQt6.QtCore import QEasingCurve, QObject, QPoint, QPropertyAnimation, QLocale, QThread, Qt, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot, qInstallMessageHandler
from PyQt6.QtGui import QColor, QCursor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
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
    QStackedLayout,
    QSizePolicy,
    QStyle,
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
QWebEnginePage = object  # type: ignore[assignment]
QWebEngineSettings = object  # type: ignore[assignment]
QWebEngineView = object  # type: ignore[assignment]
QWebChannel = object  # type: ignore[assignment]
WEBENGINE_AVAILABLE = False
try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:
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
VOICE_RECORDINGS_DIR = AI_STATE_DIR / "voice-recordings"
CHARACTER_LIBRARY_FILE = AI_STATE_DIR / "characters.json"
CHARACTER_AVATARS_DIR = AI_STATE_DIR / "characters-avatars"
VOICE_PRIVACY_CODEBOOK_FILE = AI_STATE_DIR / "voice-privacy-codebook.txt"
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
POCKETTTS_SERVER_SRC_DIR = PLUGIN_ROOT / "onnx" / "cpp" / "pockettts_server"
POCKETTTS_SERVER_INSTALL_DIR = AI_STATE_DIR / "pockettts-server"
POCKETTTS_SERVER_BINARY_NAME = "pockettts_server"
POCKETTTS_SERVER_INFER_SCRIPT_NAME = "pockettts_infer.py"
POCKETTTS_REFERENCE_DIR = AI_STATE_DIR / "pockettts-references"
POCKETTTS_VOICES_REPO = "kyutai/tts-voices"
POCKETTTS_PRESET_VOICES: list[tuple[str, str]] = [
    ("alba", "alba-mackenna/casual.wav"),
    ("marius", "voice-donations/Selfie.wav"),
    ("javert", "voice-donations/Butter.wav"),
    ("jean", "ears/p010/freeform_speech_01.wav"),
    ("fantine", "vctk/p244_023.wav"),
    ("cosette", "expresso/ex04-ex02_confused_001_channel1_499s.wav"),
    ("eponine", "vctk/p262_023.wav"),
    ("azelma", "vctk/p303_023.wav"),
]
POCKETTTS_LANGUAGES: list[tuple[str, str]] = [
    ("Auto", "auto"),
    ("English", "english"),
    ("Français", "french"),
    ("Deutsch", "german"),
    ("Português", "portuguese"),
    ("Italiano", "italian"),
    ("Español", "spanish"),
]
POCKETTTS_LANGUAGE_CODES = {code for _label, code in POCKETTTS_LANGUAGES}
AI_POPUP_LOG_FILE = AI_STATE_DIR / "ai_popup.log"
AI_POPUP_CRASH_FILE = AI_STATE_DIR / "ai_popup.crash.log"
KOKORO_SYNTH_LOG_FILE = AI_STATE_DIR / "kokoro_synth_worker.log"
_WAVEFORM_CACHE: dict[str, list[int]] = {}


LOGGER = logging.getLogger("hanauta.ai_popup")


def _ansi(text: str, code: str) -> str:
    stream = getattr(sys, "stderr", None)
    if stream is not None and hasattr(stream, "isatty") and stream.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def _voice_log(kind: str, backend: str, model: str, message: str) -> None:
    palette = {
        "stt": ("38;5;117", "38;5;153"),
        "llm": ("38;5;213", "38;5;219"),
    }
    backend_color, model_color = palette.get(kind, ("38;5;250", "38;5;255"))
    title = "Voice STT transcript" if kind == "stt" else "Voice LLM reply"
    pretty = (
        f"{_ansi(title, '1;97')} "
        f"({_ansi('backend', '38;5;245')}: {_ansi(backend, backend_color)}, "
        f"{_ansi('model', '38;5;245')}: {_ansi(model, model_color)}): "
        f"{message}"
    )
    LOGGER.info(pretty)


VOICE_EMOTIONS = {
    "neutral",
    "happy",
    "sad",
    "angry",
    "excited",
    "shy",
    "playful",
    "calm",
    "flirty",
    "serious",
    "embarrassed",
    "teasing",
    "affectionate",
}


def _emotion_prompt_suffix(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "Before each assistant reply, add exactly one leading emotion tag like "
        "[neutral], [happy], [sad], [angry], [excited], [shy], [playful], [calm], "
        "[flirty], [serious], [embarrassed], [teasing], or [affectionate]. "
        "Use one tag only, then continue with the reply text."
    )


def _extract_emotion_and_clean_text(text: str) -> tuple[str, str]:
    clean = text.strip()
    match = re.match(r"^\s*\[([a-zA-Z_ -]{2,24})\]\s*", clean)
    if not match:
        return "neutral", clean
    emotion = match.group(1).strip().lower().replace(" ", "_")
    emotion = emotion if emotion in VOICE_EMOTIONS else "neutral"
    return emotion, clean[match.end():].strip()


def _replace_sensitive_words(text: str, words: list[str]) -> tuple[str, dict[str, str]]:
    masked = str(text)
    mapping: dict[str, str] = {}
    if not words:
        return masked, mapping
    for index, word in enumerate(words, start=1):
        clean = word.strip()
        if not clean:
            continue
        token = f"__HX_{index:03d}__"
        mapping[token] = clean
        masked = re.sub(re.escape(clean), token, masked, flags=re.IGNORECASE)
    return masked, mapping


def _restore_sensitive_words(text: str, mapping: dict[str, str]) -> str:
    restored = str(text)
    for token, value in mapping.items():
        restored = restored.replace(token, value)
    return restored


def _privacy_word_list(config: dict[str, object]) -> list[str]:
    raw = str(config.get("privacy_words", "")).replace(",", "\n")
    words = [line.strip() for line in raw.splitlines() if line.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for word in words:
        lowered = word.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(word)
    return deduped


def _write_privacy_codebook(config: dict[str, object]) -> str:
    if not bool(config.get("privacy_word_coding_enabled", False)):
        if VOICE_PRIVACY_CODEBOOK_FILE.exists():
            VOICE_PRIVACY_CODEBOOK_FILE.unlink(missing_ok=True)
        return ""
    words = _privacy_word_list(config)
    if not words:
        return ""
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Hanauta AI voice privacy codebook", ""]
    for index, word in enumerate(words, start=1):
        lines.append(f"__HX_{index:03d}__ = {word}")
    VOICE_PRIVACY_CODEBOOK_FILE.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    _chmod_private(VOICE_PRIVACY_CODEBOOK_FILE)
    return str(VOICE_PRIVACY_CODEBOOK_FILE)


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
    audio_waveform: list[int] = field(default_factory=list)


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


class ClickableLineEdit(QLineEdit):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
                        "audio_waveform": [int(v) for v in item.audio_waveform],
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
        waveform_raw = payload.get("audio_waveform", [])
        waveform = (
            [max(0, min(100, int(v))) for v in waveform_raw if isinstance(v, (int, float, str))]
            if isinstance(waveform_raw, list)
            else []
        )
        history.append(
            ChatItemData(
                role=str(payload.get("role", "assistant")),
                title=str(payload.get("title", "")),
                body=str(payload.get("body", "")),
                meta=str(payload.get("meta", "")),
                chips=chips,
                audio_path=str(payload.get("audio_path", "")),
                audio_waveform=waveform,
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


def send_desktop_notification(title: str, body: str, icon_path: str = "") -> None:
    try:
        import subprocess

        command = ["notify-send", "-a", "Hanauta AI"]
        icon_candidate = Path(str(icon_path).strip()).expanduser() if str(icon_path).strip() else None
        if icon_candidate is not None and icon_candidate.exists():
            command.extend(["-i", str(icon_candidate)])
        command.extend([title, body])
        LOGGER.debug("notify-send queued: title=%r body=%r icon=%r", title, body, icon_path)
        subprocess.Popen(
            command,
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


def _http_json(
    url: str,
    timeout: float = 10.0,
    headers: dict[str, str] | None = None,
) -> dict[str, object] | list[object]:
    merged_headers = {"User-Agent": "Hanauta AI/1.0"}
    if headers:
        merged_headers.update(headers)
    req = request.Request(url, headers=merged_headers)
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(
    url: str,
    payload: dict[str, object],
    timeout: float = 180.0,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    merged_headers = {
        "User-Agent": "Hanauta AI/1.0",
        "Content-Type": "application/json",
    }
    if headers:
        merged_headers.update(headers)
    req = request.Request(
        url,
        data=body,
        headers=merged_headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _sd_auth_headers(profile_key: str, payload: dict[str, object]) -> dict[str, str]:
    username = str(payload.get("sd_auth_user", "")).strip()
    password = secure_load_secret(f"{profile_key}:sd_auth_pass").strip()
    if not username or not password:
        return {}
    token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _sdapi_not_found_message(host: str) -> str:
    normalized = _normalize_host_url(host)
    return (
        "SD API endpoint returned 404. "
        "Start WebUI/Forge with --api and use the base host only "
        f"(example: {normalized})."
    )


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


def _http_post_multipart(
    url: str,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    headers: dict[str, str] | None = None,
    timeout: float = 240.0,
) -> dict[str, object]:
    boundary = f"----HanautaAIPopup{int(time.time() * 1000)}{os.getpid()}"
    body_parts: list[bytes] = []
    for name, value in fields.items():
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        body_parts.append(str(value).encode("utf-8"))
        body_parts.append(b"\r\n")
    for name, (filename, data, content_type) in files.items():
        safe_name = filename.replace('"', "")
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{safe_name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        body_parts.append(data)
        body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(body_parts)
    merged_headers = {
        "User-Agent": "Hanauta AI/1.0",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if headers:
        merged_headers.update(headers)
    req = request.Request(url, data=body, headers=merged_headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _voice_mode_defaults() -> dict[str, object]:
    return {
        "enabled": False,
        "record_seconds": "5",
        "silence_threshold": "0.012",
        "stt_backend": "whisper",
        "stt_model": "small",
        "stt_device": "cpu",
        "stt_external_api": False,
        "stt_host": "api.openai.com",
        "stt_remote_model": "whisper-1",
        "stt_vosk_model_path": "",
        "llm_backend": "profile",
        "llm_profile": "koboldcpp",
        "llm_device": "cpu",
        "llm_external_api": False,
        "llm_host": "api.openai.com",
        "llm_model": "gpt-4.1-mini",
        "tts_profile": "kokorotts",
        "tts_device": "cpu",
        "tts_external_api": False,
        "barge_in_enabled": True,
        "barge_in_threshold": "0.035",
        "emotion_tags_enabled": True,
        "privacy_word_coding_enabled": False,
        "privacy_words": "",
        "compaction_model_host": "",
        "compaction_model_name": "",
        "enable_character": True,
        "hide_character_photo": False,
        "hide_answer_text": False,
        "generic_notification_text": "Notification received",
    }


def _voice_mode_settings(settings: dict[str, dict[str, object]]) -> dict[str, object]:
    payload = dict(_voice_mode_defaults())
    raw = settings.get("_voice_mode", {})
    if isinstance(raw, dict):
        payload.update(raw)
    return payload


def _with_voice_device(payload: dict[str, object], device: str) -> dict[str, object]:
    updated = dict(payload)
    clean = device.strip().lower()
    if clean in {"cpu", "gpu"}:
        updated["device"] = clean
    return updated


def _api_url_from_host(host: str) -> str:
    clean = host.strip().rstrip("/")
    if not clean:
        return ""
    if clean.startswith(("http://", "https://")):
        return clean
    if clean in {"api.openai.com", "www.api.openai.com"} or clean.endswith(".openai.com"):
        return f"https://{clean}"
    return f"http://{clean}"


def _voice_recording_rms(audio_path: Path) -> float:
    try:
        import audioop

        with wave.open(str(audio_path), "rb") as handle:
            width = int(handle.getsampwidth() or 2)
            frames = handle.readframes(int(handle.getnframes() or 0))
        if not frames:
            return 0.0
        peak = float((1 << (8 * width - 1)) - 1)
        return float(audioop.rms(frames, width)) / peak if peak > 0 else 0.0
    except Exception:
        return 0.0


def _wav_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frames = int(handle.getnframes() or 0)
            rate = int(handle.getframerate() or 0)
        return (frames / float(rate)) if rate > 0 else 0.0
    except Exception:
        return 0.0


def _record_microphone_wav(seconds: float) -> Path:
    VOICE_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    duration = max(0.25, min(30.0, float(seconds or 5.0)))
    output = VOICE_RECORDINGS_DIR / f"voice_{int(time.time() * 1000)}.wav"
    commands: list[list[str]] = []
    if shutil.which("ffmpeg"):
        commands.append([
            "ffmpeg",
            "-y",
            "-f",
            "pulse",
            "-i",
            "default",
            "-t",
            f"{duration:.2f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output),
        ])
    if shutil.which("arecord"):
        commands.append([
            "arecord",
            "-q",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            "16000",
            "-d",
            str(max(1, int(round(duration)))),
            str(output),
        ])
    if shutil.which("pw-record"):
        commands.append([
            "pw-record",
            "--channels",
            "1",
            "--rate",
            "16000",
            str(output),
        ])
    if not commands:
        raise RuntimeError("Install ffmpeg, arecord, or pw-record to capture microphone audio.")
    last_error = ""
    for command in commands:
        try:
            timeout = duration + 4.0
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0 and output.exists() and output.stat().st_size > 44:
                return output
            last_error = (result.stderr or result.stdout or "").strip()
        except subprocess.TimeoutExpired:
            if output.exists() and output.stat().st_size > 44:
                return output
            last_error = "microphone recorder timed out"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "Microphone recording failed.")


def _transcribe_with_external_api(audio_path: Path, config: dict[str, object]) -> str:
    host = str(config.get("stt_host", "")).strip()
    if not host:
        raise RuntimeError("External STT requires a host.")
    api_key = secure_load_secret("voice_mode:stt_api_key").strip()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = _http_post_multipart(
        f"{_api_url_from_host(host)}/v1/audio/transcriptions",
        fields={
            "model": str(config.get("stt_remote_model", "whisper-1")).strip() or "whisper-1",
            "response_format": "json",
        },
        files={"file": (audio_path.name, audio_path.read_bytes(), "audio/wav")},
        headers=headers,
        timeout=240.0,
    )
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("STT endpoint returned no text.")
    return text


def _voice_venv_dir(engine: str, model_name: str, device: str) -> Path:
    engine_slug = _safe_slug(engine.strip().lower() or "voice")
    model_slug = _safe_slug(model_name.strip().lower() or "model")
    device_slug = _safe_slug(device.strip().lower() or "cpu")
    return AI_STATE_DIR / "voice-venvs" / engine_slug / model_slug / device_slug


def _voice_venv_python(engine: str, model_name: str, device: str) -> Path:
    return _voice_venv_dir(engine, model_name, device) / "bin" / "python3"


def _ensure_voice_venv(
    engine: str,
    model_name: str,
    device: str,
    requirements: list[str],
    import_name: str,
) -> Path:
    venv_dir = _voice_venv_dir(engine, model_name, device)
    python_bin = _voice_venv_python(engine, model_name, device)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_bin.exists():
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0 or not python_bin.exists():
            detail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
            raise RuntimeError("Failed to create voice model virtualenv:\n" + "\n".join(detail).strip())
    import_check = subprocess.run(
        [str(python_bin), "-c", f"import {import_name}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if import_check.returncode == 0:
        return python_bin
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", *requirements],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-14:]
        raise RuntimeError(
            "Voice STT runtime install failed in the isolated venv:\n"
            + "\n".join(detail).strip()
        )
    return python_bin


def _voice_whisper_script_path() -> Path:
    return AI_STATE_DIR / "voice-runtime" / "faster_whisper_transcribe.py"


def _ensure_voice_whisper_script() -> Path:
    script_path = _voice_whisper_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download


MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
}


def _resolve_model_path(model_name: str, model_cache: Path) -> Path:
    if model_name.startswith("/") or model_name.startswith("."):
        candidate = Path(model_name).expanduser()
        if candidate.exists():
            return candidate
    repo_id = MODEL_REPOS.get(model_name, model_name)
    target = model_cache / repo_id.replace("/", "--")
    if target.exists():
        return target
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "35")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "20")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target),
            local_dir_use_symlinks=False,
            max_workers=4,
            etag_timeout=20,
        )
    except KeyboardInterrupt:
        raise RuntimeError(
            "Whisper model download was interrupted. "
            "Please wait for the first model download to finish, or switch STT to External API."
        )
    except Exception as exc:
        raise RuntimeError(
            f"Unable to download the Whisper model '{model_name}' into {target}: {exc}"
        ) from exc
    return target


def _try_transcribe(model_name: str, audio_path: Path, device: str, compute_type: str, model_cache: Path) -> str:
    resolved_model = _resolve_model_path(model_name, model_cache)
    model = WhisperModel(
        str(resolved_model),
        device=device,
        compute_type=compute_type,
    )
    segments, _info = model.transcribe(str(audio_path), vad_filter=True, beam_size=1)
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--model-cache", required=True)
    args = parser.parse_args()
    audio_path = Path(args.audio).expanduser()
    model_cache = Path(args.model_cache).expanduser()
    model_cache.mkdir(parents=True, exist_ok=True)
    attempts = []
    if args.device == "gpu":
        attempts.extend([
            ("cuda", "float16"),
            ("cuda", "int8_float16"),
        ])
    attempts.extend([
        ("cpu", "int8"),
        ("cpu", "int8_float32"),
    ])
    errors = []
    for device, compute_type in attempts:
        try:
            text = _try_transcribe(args.model, audio_path, device, compute_type, model_cache)
            print(json.dumps({"text": text, "device": device, "compute_type": compute_type}))
            return 0
        except Exception as exc:
            errors.append(f"{device}/{compute_type}: {exc}")
    print(json.dumps({"error": "\\n".join(errors[-4:])}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _voice_vosk_script_path() -> Path:
    return AI_STATE_DIR / "voice-runtime" / "vosk_transcribe.py"


def _ensure_voice_vosk_script() -> Path:
    script_path = _voice_vosk_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

import vosk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--audio", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path).expanduser()
    audio_path = Path(args.audio).expanduser()
    chunks = []
    with wave.open(str(audio_path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getframerate() not in {8000, 16000, 24000, 48000}:
            raise RuntimeError("VOSK needs mono WAV audio.")
        recognizer = vosk.KaldiRecognizer(vosk.Model(str(model_path)), handle.getframerate())
        while True:
            data = handle.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                parsed = json.loads(recognizer.Result())
                text = str(parsed.get("text", "")).strip()
                if text:
                    chunks.append(text)
        parsed = json.loads(recognizer.FinalResult())
        final = str(parsed.get("text", "")).strip()
        if final:
            chunks.append(final)
    print(json.dumps({"text": " ".join(chunks).strip()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _transcribe_with_whisper(audio_path: Path, config: dict[str, object]) -> str:
    model_name = str(config.get("stt_model", "small")).strip().lower() or "small"
    if model_name not in {"tiny", "small", "medium", "large"}:
        model_name = "small"
    device = "gpu" if str(config.get("stt_device", "cpu")).lower() == "gpu" else "cpu"
    python_bin = _ensure_voice_venv("whisper", model_name, device, ["faster-whisper", "huggingface-hub"], "faster_whisper")
    script_path = _ensure_voice_whisper_script()
    model_cache = _voice_venv_dir("whisper", model_name, device) / "model-cache"
    result = subprocess.run(
        [
            str(python_bin),
            str(script_path),
            "--model",
            model_name,
            "--audio",
            str(audio_path.expanduser()),
            "--device",
            device,
            "--model-cache",
            str(model_cache),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(
            "Whisper STT failed in its isolated faster-whisper venv:\n"
            + "\n".join(detail).strip()
        )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("Whisper STT returned invalid output.") from exc
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("Whisper STT returned no text.")
    LOGGER.debug(
        "voice whisper transcribed with model=%s requested_device=%s actual_device=%s compute=%s",
        model_name,
        device,
        payload.get("device", ""),
        payload.get("compute_type", ""),
    )
    return text



def _transcribe_with_vosk(audio_path: Path, config: dict[str, object]) -> str:
    model_path = Path(str(config.get("stt_vosk_model_path", "")).strip()).expanduser()
    if not str(model_path).strip() or not model_path.exists():
        raise RuntimeError("Set a local VOSK English model folder in Voice Mode settings.")
    model_key = hashlib.sha1(str(model_path.resolve()).encode("utf-8", "ignore")).hexdigest()[:12]
    python_bin = _ensure_voice_venv("vosk", model_key, "cpu", ["vosk"], "vosk")
    script_path = _ensure_voice_vosk_script()
    result = subprocess.run(
        [
            str(python_bin),
            str(script_path),
            "--model-path",
            str(model_path),
            "--audio",
            str(audio_path.expanduser()),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(
            "VOSK STT failed in its isolated venv:\n"
            + "\n".join(detail).strip()
        )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("VOSK STT returned invalid output.") from exc
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("VOSK STT returned no text.")
    return text


def transcribe_voice_audio(audio_path: Path, config: dict[str, object]) -> str:
    if bool(config.get("stt_external_api", False)):
        return _transcribe_with_external_api(audio_path, config)
    backend = str(config.get("stt_backend", "whisper")).strip().lower()
    if backend == "vosk":
        return _transcribe_with_vosk(audio_path, config)
    return _transcribe_with_whisper(audio_path, config)


def _chat_messages_for_prompt(prompt: str, character: CharacterCard | None, *, emotion_tags: bool = False) -> list[dict[str, str]]:
    system = "You are Hanauta AI. Keep spoken replies concise, natural, and easy to listen to."
    if character is not None:
        character_prompt = _character_compose_prompt(character).strip()
        if character_prompt:
            system = f"{system}\n\nActive character:\n{character_prompt}"
    emotion_suffix = _emotion_prompt_suffix(emotion_tags)
    if emotion_suffix:
        system = f"{system}\n\n{emotion_suffix}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


def _generate_openai_style_reply(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model.strip() or "gpt-4.1-mini",
        "messages": messages,
        "temperature": 0.8,
    }
    response = _http_post_json(
        f"{_api_url_from_host(host)}/v1/chat/completions",
        payload,
        timeout=240.0,
        headers=headers,
    )
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                text = str(message.get("content", "")).strip()
                if text:
                    return text
            text = str(first.get("text", "")).strip()
            if text:
                return text
    raise RuntimeError("LLM endpoint returned no assistant text.")


def generate_voice_chat_reply(
    config: dict[str, object],
    profiles: dict[str, BackendProfile],
    backend_settings: dict[str, dict[str, object]],
    prompt: str,
    character: CharacterCard | None,
) -> tuple[str, str, str, str]:
    privacy_mapping: dict[str, str] = {}
    masked_prompt = prompt
    if bool(config.get("privacy_word_coding_enabled", False)):
        masked_prompt, privacy_mapping = _replace_sensitive_words(prompt, _privacy_word_list(config))
    messages = _chat_messages_for_prompt(
        masked_prompt,
        character,
        emotion_tags=bool(config.get("emotion_tags_enabled", False)),
    )
    if bool(config.get("llm_external_api", False)):
        host = str(config.get("llm_host", "")).strip()
        model = str(config.get("llm_model", "")).strip() or "gpt-4.1-mini"
        text = _generate_openai_style_reply(
            host,
            model,
            messages,
            secure_load_secret("voice_mode:llm_api_key").strip(),
        )
        restored = _restore_sensitive_words(text, privacy_mapping)
        emotion, cleaned = _extract_emotion_and_clean_text(restored)
        return cleaned, "OpenAI-compatible", model, emotion

    profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
    profile = profiles.get(profile_key)
    if profile is None:
        raise RuntimeError("Select a valid text backend for voice mode.")
    payload = dict(backend_settings.get(profile.key, {}))
    if profile.key == "ollama":
        host = str(payload.get("host", profile.host)).strip()
        model = str(payload.get("model", profile.model)).strip() or profile.model
        response = _http_post_json(
            f"{_api_url_from_host(host)}/api/chat",
            {"model": model, "messages": messages, "stream": False},
            timeout=240.0,
        )
        message = response.get("message", {})
        if isinstance(message, dict):
            text = str(message.get("content", "")).strip()
            if text:
                restored = _restore_sensitive_words(text, privacy_mapping)
                emotion, cleaned = _extract_emotion_and_clean_text(restored)
                return cleaned, profile.label, model, emotion
        raise RuntimeError("Ollama returned no assistant text.")
    if profile.provider in {"openai", "openai_compat"}:
        host = str(payload.get("host", profile.host)).strip()
        model = str(payload.get("model", profile.model)).strip() or profile.model
        api_key = secure_load_secret(f"{profile.key}:api_key").strip()
        text = _generate_openai_style_reply(host, model, messages, api_key)
        if profile.key == "koboldcpp":
            gguf_path = _existing_path(payload.get("gguf_path"))
            if gguf_path is not None:
                model = gguf_path.name
        restored = _restore_sensitive_words(text, privacy_mapping)
        emotion, cleaned = _extract_emotion_and_clean_text(restored)
        return cleaned, profile.label, model, emotion
    raise RuntimeError("Voice mode supports KoboldCpp/OpenAI-compatible, OpenAI-style, and Ollama text backends.")


def _resolve_hanauta_service_binary() -> Path | None:
    candidates = [
        APP_DIR.parent / "bin" / "hanauta-service",
        Path.home() / ".config" / "i3" / "hanauta" / "bin" / "hanauta-service",
    ]
    for candidate in candidates:
        path = candidate.expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


def _waveform_from_hanauta_service(audio_path: Path, bars: int = 32) -> list[int]:
    key = str(audio_path.expanduser().resolve())
    cached = _WAVEFORM_CACHE.get(key)
    if cached:
        return list(cached)
    binary = _resolve_hanauta_service_binary()
    if binary is None:
        return []
    try:
        result = subprocess.run(
            [str(binary), "--waveform", key, str(max(8, min(128, int(bars))))],
            capture_output=True,
            text=True,
            timeout=6,
            check=True,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
        raw = payload.get("bars", []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            return []
        cleaned = [max(0, min(100, int(v))) for v in raw if isinstance(v, (int, float, str))]
        if cleaned:
            _WAVEFORM_CACHE[key] = list(cleaned)
        return cleaned
    except Exception:
        return []


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


def _ensure_wav_reference(reference_path: Path) -> Path:
    source = reference_path.expanduser()
    if not source.exists():
        raise RuntimeError(f"Reference audio file not found: {source}")
    if source.suffix.lower() == ".wav":
        return source
    if shutil.which("ffmpeg") is None and shutil.which("sox") is None:
        raise RuntimeError("Install ffmpeg (recommended) or sox to convert reference audio to WAV.")

    POCKETTTS_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{str(source.resolve())}|{int(source.stat().st_mtime)}|{int(source.stat().st_size)}".encode("utf-8", "ignore")
    digest = hashlib.sha1(key).hexdigest()[:10]
    out = POCKETTTS_REFERENCE_DIR / f"{source.stem}_{digest}.wav"
    if out.exists():
        return out

    if shutil.which("ffmpeg") is not None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(out),
        ]
    else:
        cmd = [
            "sox",
            str(source),
            "-c",
            "1",
            "-r",
            "24000",
            str(out),
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0 or not out.exists():
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(f"Audio conversion failed:\n" + "\n".join(detail).strip())
    return out


def _tts_venv_dir(profile_key: str) -> Path:
    return AI_STATE_DIR / "tts-venvs" / profile_key


def _tts_venv_python(profile_key: str) -> Path:
    venv = _tts_venv_dir(profile_key)
    return venv / "bin" / "python3"


def _tts_engine_requirements(profile_key: str) -> list[str]:
    if profile_key == "kokorotts":
        return ["onnxruntime", "kokoro-onnx", "numpy"]
    if profile_key == "pockettts":
        return ["onnxruntime", "numpy", "sentencepiece", "soundfile", "scipy"]
    return []


def _system_language_code() -> str:
    try:
        code = str(QLocale.system().name() or "").split("_", 1)[0].strip().lower()
    except Exception:
        code = ""
    return code


def _default_pocket_language(payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_language", "")).strip().lower()
    legacy = {
        "en": "english",
        "fr": "french",
        "de": "german",
        "pt": "portuguese",
        "it": "italian",
        "es": "spanish",
    }
    if configured in legacy:
        configured = legacy[configured]
    if configured in POCKETTTS_LANGUAGE_CODES:
        return configured
    system_code = _system_language_code()
    sys_map = {
        "en": "english",
        "fr": "french",
        "de": "german",
        "pt": "portuguese",
        "it": "italian",
        "es": "spanish",
    }
    mapped = sys_map.get(system_code, "")
    if mapped in POCKETTTS_LANGUAGE_CODES:
        return mapped
    if "english" in POCKETTTS_LANGUAGE_CODES:
        return "english"
    return "auto"


def _ensure_tts_runtime_venv(
    profile_key: str,
    *,
    progress_cb: callable | None = None,
) -> Path:
    requirements = _tts_engine_requirements(profile_key)
    if not requirements:
        raise RuntimeError(f"No runtime requirements declared for {profile_key}.")
    venv_dir = _tts_venv_dir(profile_key)
    python_bin = _tts_venv_python(profile_key)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_bin.exists():
        if callable(progress_cb):
            progress_cb(5, 100, "Creating virtualenv")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0 or not python_bin.exists():
            detail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
            raise RuntimeError("Failed to create virtualenv:\n" + "\n".join(detail).strip())
    if callable(progress_cb):
        progress_cb(20, 100, "Upgrading pip")
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    if callable(progress_cb):
        progress_cb(35, 100, "Installing runtime dependencies")
    result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", *requirements],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError("Runtime dependency install failed:\n" + "\n".join(detail).strip())
    if callable(progress_cb):
        progress_cb(100, 100, "Runtime ready")
    return python_bin


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


def _list_pocket_voice_references(model_dir: Path) -> list[tuple[str, str]]:
    voices: list[tuple[str, str]] = []
    voices_dir = model_dir / "voices"
    if voices_dir.exists():
        for wav in sorted(voices_dir.rglob("*.wav")):
            try:
                rel = wav.relative_to(voices_dir).as_posix()
            except Exception:
                rel = wav.name
            label = wav.stem if rel == wav.name else f"{wav.stem} ({rel})"
            voices.append((label, str(wav)))
    reference = model_dir / "reference_sample.wav"
    if reference.exists():
        voices.insert(0, ("Default (reference_sample.wav)", str(reference)))
    if not voices:
        for wav in sorted(model_dir.glob("*.wav")):
            voices.append((wav.name, str(wav)))
    if not voices:
        return [("Select a WAV…", "")]
    return voices


def _pocket_preset_voice_path(model_dir: Path, preset_name: str) -> Path:
    safe_name = _safe_slug(preset_name.strip().lower() or "voice")
    return model_dir / "voices" / "kyutai" / f"{safe_name}.wav"


def _ensure_pocket_preset_voice(
    model_dir: Path,
    preset_name: str,
    *,
    progress_cb: callable | None = None,
) -> Path:
    rel = next((path for name, path in POCKETTTS_PRESET_VOICES if name == preset_name), "")
    if not rel:
        raise RuntimeError(f"Unknown PocketTTS preset voice: {preset_name}")
    target = _pocket_preset_voice_path(model_dir, preset_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return target
    if callable(progress_cb):
        progress_cb(0, 1, f"Downloading {preset_name}")
    _download_hf_files(POCKETTTS_VOICES_REPO, [rel], target.parent, progress_cb=progress_cb)
    downloaded_candidates = [
        target.parent / rel,
        target.parent / Path(rel).name,
    ]
    downloaded: Path | None = None
    for candidate in downloaded_candidates:
        if candidate.exists():
            downloaded = candidate
            break
    if downloaded is None:
        for found in sorted(target.parent.rglob(Path(rel).name)):
            if found.is_file() and found.stat().st_size > 0:
                downloaded = found
                break
    if downloaded is not None and downloaded.exists():
        try:
            shutil.move(str(downloaded), str(target))
        except Exception:
            try:
                shutil.copy2(str(downloaded), str(target))
            except Exception:
                pass
    if not target.exists():
        # Fallback: keep original filename in-place (debuggability)
        if downloaded is not None and downloaded.exists():
            return downloaded
        raise RuntimeError(f"Failed to download preset voice: {preset_name}")
    return target


def _ensure_all_pocket_preset_voices(
    model_dir: Path,
    *,
    progress_cb: callable | None = None,
) -> None:
    total = max(1, len(POCKETTTS_PRESET_VOICES))
    done = 0
    for preset_name, _rel in POCKETTTS_PRESET_VOICES:
        if callable(progress_cb):
            progress_cb(done, total, f"{preset_name}")
        _ensure_pocket_preset_voice(model_dir, preset_name)
        done += 1
        if callable(progress_cb):
            progress_cb(done, total, f"{preset_name}")


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
    python_bin = _tts_venv_python("kokorotts")
    python_exec = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_exec,
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
        if "No module named 'onnxruntime'" in detail or "No module named onnxruntime" in detail:
            raise RuntimeError(
                "Missing Kokoro runtime deps (onnxruntime). "
                "In Backend Settings, click 'Download TTS model' (it also installs runtime deps)."
            )
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
    language: str,
    voice_mode: str = "reference",
) -> None:
    script_path = _ensure_pocket_synth_script()
    python_bin = _tts_venv_python("pockettts")
    python_exec = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_exec,
        str(script_path),
        "--model-dir",
        str(model_dir),
        "--text",
        text,
        "--output",
        str(output_path),
        "--language",
        str(language or "auto"),
    ]
    if str(voice_mode).strip().lower() != "none":
        reference = (
            Path(voice_reference).expanduser()
            if voice_reference.strip()
            else (model_dir / "reference_sample.wav")
        )
        reference = _ensure_wav_reference(reference)
        command.extend(["--voice-reference", str(reference)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or "no output"
        if "No module named 'onnxruntime'" in detail or "No module named onnxruntime" in detail:
            raise RuntimeError(
                "Missing PocketTTS runtime deps (onnxruntime). "
                "In Backend Settings, click 'Install PocketTTS' (it also installs runtime deps)."
            )
        raise RuntimeError(f"PocketTTS synth failed (exit {completed.returncode}). Detail: {detail}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("PocketTTS synth did not produce audio output.")


def _pocket_synth_script_path() -> Path:
    return AI_STATE_DIR / "pocket_synth_worker.py"


def _ensure_pocket_synth_script() -> Path:
    script_path = _pocket_synth_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import wave

import numpy as np


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 24000) -> None:
    audio = np.clip(samples.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice-reference", default="")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser()
    output_path = Path(args.output).expanduser()
    reference = Path(args.voice_reference).expanduser() if str(args.voice_reference or "").strip() else None

    script_path = model_dir / "pocket_tts_onnx.py"
    if not script_path.exists():
        raise RuntimeError(f"PocketTTS ONNX script not found: {script_path}")
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
    lang = str(args.language or "").strip() or "auto"
    if reference is None:
        try:
            audio = engine.generate(args.text, language=lang)
        except TypeError:
            audio = engine.generate(args.text)
    else:
        try:
            audio = engine.generate(args.text, voice=str(reference), language=lang)
        except TypeError:
            audio = engine.generate(args.text, voice=str(reference))
    if not isinstance(audio, np.ndarray) or audio.size == 0:
        raise RuntimeError("PocketTTS returned empty audio.")
    _write_wav(output_path, audio.astype(np.float32), 24000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


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
        body_payload: dict[str, object] = {
            "model": str(payload.get("tts_remote_model", payload.get("model", profile.model))).strip() or "tts-1",
            "input": text,
            "voice": voice,
        }
        if profile.key == "pockettts":
            lang = _default_pocket_language(payload)
            if lang and lang != "auto":
                body_payload["language"] = lang
        body, content_type = _http_post_bytes(
            url,
            body_payload,
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
        voice_mode = str(payload.get("tts_voice_mode", "reference")).strip().lower()
        preset = str(payload.get("tts_voice_preset", "")).strip().lower()
        voice_reference = str(payload.get("tts_voice_reference", "")).strip()
        if voice_mode != "none" and preset:
            try:
                voice_reference = str(_ensure_pocket_preset_voice(model_dir, preset))
            except Exception as exc:
                raise RuntimeError(f"Failed to fetch PocketTTS preset voice '{preset}': {exc}")
        _generate_pocket_audio(
            model_dir,
            text,
            output_path,
            voice_reference,
            _default_pocket_language(payload),
            voice_mode=voice_mode,
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
            response = _http_json(
                f"{url}/sdapi/v1/samplers",
                timeout=3.0,
                headers=_sd_auth_headers(profile.key, payload),
            )
            if not isinstance(response, list):
                return False, "SD WebUI did not return samplers."
        except error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) == 404:
                return False, _sdapi_not_found_message(host)
            return False, f"SD WebUI request failed: HTTP {getattr(exc, 'code', 'error')}"
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


def _pocket_server_binary_path() -> Path:
    return POCKETTTS_SERVER_INSTALL_DIR / POCKETTTS_SERVER_BINARY_NAME


def _install_pockettts_server(progress_cb: callable | None = None) -> Path:
    if shutil.which("g++") is None:
        raise RuntimeError("g++ is required to build the PocketTTS server.")
    if not POCKETTTS_SERVER_SRC_DIR.exists():
        raise RuntimeError(f"PocketTTS server sources not found: {POCKETTTS_SERVER_SRC_DIR}")
    build_script = POCKETTTS_SERVER_SRC_DIR / "build.sh"
    if not build_script.exists():
        raise RuntimeError(f"Missing build script: {build_script}")
    if callable(progress_cb):
        progress_cb(5, 100, "Building PocketTTS server")
    result = subprocess.run(
        ["bash", str(build_script)],
        cwd=str(POCKETTTS_SERVER_SRC_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        detail = "\n".join(tail).strip()
        raise RuntimeError(f"PocketTTS server build failed.\n{detail or 'unknown error'}")
    built_binary = POCKETTTS_SERVER_SRC_DIR / "build" / POCKETTTS_SERVER_BINARY_NAME
    if not built_binary.exists():
        raise RuntimeError(f"Built PocketTTS server binary not found: {built_binary}")
    POCKETTTS_SERVER_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = _pocket_server_binary_path()
    shutil.copy2(built_binary, target)
    try:
        os.chmod(target, 0o755)
    except Exception:
        pass
    infer_src = POCKETTTS_SERVER_SRC_DIR / POCKETTTS_SERVER_INFER_SCRIPT_NAME
    if not infer_src.exists():
        raise RuntimeError(f"Missing PocketTTS infer helper script: {infer_src}")
    shutil.copy2(infer_src, POCKETTTS_SERVER_INSTALL_DIR / POCKETTTS_SERVER_INFER_SCRIPT_NAME)
    if callable(progress_cb):
        progress_cb(100, 100, "PocketTTS server installed")
    return target


def _parse_host_port_default(host: str, default_port: int) -> tuple[str, int]:
    raw = host.strip()
    if not raw:
        return "127.0.0.1", int(default_port)
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    hostname = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or default_port)
    return hostname, port


def _default_pocket_server_command(payload: dict[str, object]) -> list[str] | None:
    binary = _pocket_server_binary_path()
    if not (binary.exists() and os.access(binary, os.X_OK)):
        return None
    model_dir = _default_tts_model_dir(
        BackendProfile("pockettts", "PocketTTS", "tts_local", "pocket", "127.0.0.1:8890", "pockettts"),
        payload,
    )
    if not model_dir.exists():
        return None
    host, port = _parse_host_port_default(str(payload.get("host", "127.0.0.1:8890")), 8890)
    default_language = str(payload.get("tts_language", "")).strip() or "auto"
    return [
        str(binary),
        "--host",
        host,
        "--port",
        str(port),
        "--model-dir",
        str(model_dir),
        "--default-language",
        default_language,
    ]


def _resolve_pocket_server_command(payload: dict[str, object]) -> tuple[list[str], str]:
    command_text = str(payload.get("tts_server_command", "")).strip()
    if command_text:
        try:
            return shlex.split(command_text), "custom"
        except Exception as exc:
            raise RuntimeError(f"Invalid server command: {exc}")
    auto = _default_pocket_server_command(payload)
    if auto:
        return auto, "auto"
    raise RuntimeError(
        "No valid PocketTTS server command was found. Click Install PocketTTS first, or set 'TTS server command'."
    )


def _pocket_server_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host:
        if _openai_compat_alive(host) or _host_reachable(host):
            return True, f"Server active at {host}"
    pid = int(payload.get("tts_server_pid", 0) or 0)
    if _is_pid_alive(pid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def _start_pocket_server(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_pocket_server_command(payload)
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
        return False, f"Unable to start PocketTTS server: {exc}"
    payload["tts_server_pid"] = int(process.pid or 0)
    return True, f"PocketTTS server started with: {' '.join(command)}"


def _stop_pocket_server(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("tts_server_pid", 0) or 0)
    if not _is_pid_alive(pid):
        payload["tts_server_pid"] = 0
        return False, "No tracked PocketTTS server process is running."
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"Unable to stop PocketTTS server: {exc}"
    payload["tts_server_pid"] = 0
    return True, f"Stopped PocketTTS server process {pid}."


def _pocket_systemd_user_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "hanauta-pockettts.service"


def _write_pocket_systemd_service(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_pocket_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    command_text = shlex.join(command)
    if source == "auto":
        payload["tts_server_command"] = command_text
    service_path = _pocket_systemd_user_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_text = f"""[Unit]
Description=Hanauta PocketTTS Server
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


def _set_pocket_autostart(payload: dict[str, object], enabled: bool) -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return False, "systemctl is not available on this system."
    if enabled:
        ok, msg = _write_pocket_systemd_service(payload)
        if not ok:
            return False, msg
        result = _systemctl_user("enable", "--now", "hanauta-pockettts.service")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, f"Failed to enable autostart: {detail or 'unknown error'}"
        return True, "PocketTTS autostart enabled."
    result = _systemctl_user("disable", "--now", "hanauta-pockettts.service")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lowered = detail.lower()
        if "not loaded" not in lowered and "does not exist" not in lowered:
            return False, f"Failed to disable autostart: {detail or 'unknown error'}"
    return True, "PocketTTS autostart disabled."


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

    def __init__(self, profile: BackendProfile, payload: dict[str, object], install_server: bool = False) -> None:
        super().__init__()
        self.profile = profile
        self.payload = dict(payload)
        self.install_server = bool(install_server)

    def run(self) -> None:
        try:
            model_dir, _voice = _ensure_tts_assets(
                self.profile,
                self.payload,
                download_if_missing=True,
                progress_cb=lambda done, total, label: self._emit_progress(done, total, f"Fetching {label}"),
            )
            if self.profile.provider == "tts_local":
                _ensure_tts_runtime_venv(
                    self.profile.key,
                    progress_cb=lambda done, total, label: self._emit_progress(done, total, f"Runtime: {label}"),
                )
        except Exception as exc:
            self.failed.emit(self.profile.key, str(exc))
            return
        if self.install_server and self.profile.key == "pockettts":
            try:
                _install_pockettts_server(progress_cb=lambda done, total, label: self._emit_progress(done, total, label))
                _ensure_all_pocket_preset_voices(
                    model_dir,
                    progress_cb=lambda done, total, label: self._emit_progress(done, total, f"Voices: {label}"),
                )
            except Exception as exc:
                self.failed.emit(self.profile.key, str(exc))
                return
        self.progress.emit(self.profile.key, 100, "Model ready")
        self.finished_ok.emit(self.profile.key, str(model_dir))

    def _emit_progress(self, done: int, total: int, label: str) -> None:
        ratio = 0 if total <= 0 else int(max(0.0, min(1.0, done / float(total))) * 100)
        self.progress.emit(self.profile.key, ratio, label)


class TtsRuntimeInstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, profile_key: str) -> None:
        super().__init__()
        self.profile_key = profile_key

    def run(self) -> None:
        try:
            _ensure_tts_runtime_venv(
                self.profile_key,
                progress_cb=lambda value, _total, label: self.progress.emit(int(value), str(label)),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(self.profile_key)


class PocketPresetVoiceWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_dir: Path, preset: str) -> None:
        super().__init__()
        self.model_dir = model_dir
        self.preset = preset

    def run(self) -> None:
        try:
            voice_path = _ensure_pocket_preset_voice(
                self.model_dir,
                self.preset,
                progress_cb=lambda done, total, label: self._emit(done, total, label),
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(str(voice_path))

    def _emit(self, done: int, total: int, label: str) -> None:
        value = 0 if total <= 0 else int(max(0.0, min(1.0, done / float(total))) * 100)
        self.progress.emit(value, str(label).strip() or "Downloading voice…")


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

    def start(self, profile: BackendProfile, payload: dict[str, object], *, install_server: bool = False) -> bool:
        if self.is_running(profile.key):
            return False
        worker = TtsModelDownloadWorker(profile, payload, install_server=install_server)
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
        self.resize(620, 680)
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
        self.sd_auth_user_input = QLineEdit()
        self.sd_auth_user_input.setPlaceholderText("SD WebUI username (optional)")
        shell_layout.addWidget(self.sd_auth_user_input)
        self.sd_auth_pass_input = QLineEdit()
        self.sd_auth_pass_input.setPlaceholderText("SD WebUI password (optional)")
        self.sd_auth_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        shell_layout.addWidget(self.sd_auth_pass_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Model")
        shell_layout.addWidget(self.model_input)
        self.sd_model_combo = QComboBox()
        self.sd_model_combo.setEditable(True)
        if self.sd_model_combo.lineEdit() is not None:
            self.sd_model_combo.lineEdit().setPlaceholderText("Checkpoint / model")
        self.sd_model_combo.setToolTip("SD checkpoint")
        shell_layout.addWidget(self.sd_model_combo)
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
        self.tts_mode_combo.currentIndexChanged.connect(self._on_tts_mode_changed)
        shell_layout.addWidget(self.tts_mode_combo)

        self.pocket_mode_row = QWidget()
        pocket_mode_layout = QHBoxLayout(self.pocket_mode_row)
        pocket_mode_layout.setContentsMargins(0, 0, 0, 0)
        pocket_mode_layout.setSpacing(10)
        pocket_mode_layout.addWidget(QLabel("PocketTTS mode"))
        self.pocket_mode_combo = QComboBox()
        self.pocket_mode_combo.addItem("Local PocketTTS", "local_onnx")
        self.pocket_mode_combo.addItem("External API", "external_api")
        self.pocket_mode_combo.currentIndexChanged.connect(self._on_pocket_mode_changed)
        pocket_mode_layout.addWidget(self.pocket_mode_combo, 1)
        pocket_mode_layout.addStretch(1)
        shell_layout.addWidget(self.pocket_mode_row)

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
        self.tts_server_command_input.setPlaceholderText("Optional local TTS server command (OpenAI-compatible)")
        shell_layout.addWidget(self.tts_server_command_input)
        self.tts_server_row = QWidget()
        tts_server_layout = QHBoxLayout(self.tts_server_row)
        tts_server_layout.setContentsMargins(0, 0, 0, 0)
        tts_server_layout.setSpacing(8)
        self.tts_server_status_label = QLabel("Server status: unknown")
        self.tts_server_status_label.setStyleSheet(f"color: {TEXT_DIM};")
        tts_server_layout.addWidget(self.tts_server_status_label, 1)
        self.kokoro_start_button = QPushButton("Start")
        self.kokoro_start_button.clicked.connect(self._start_tts_server_clicked)
        tts_server_layout.addWidget(self.kokoro_start_button)
        self.kokoro_restart_button = QPushButton("Restart")
        self.kokoro_restart_button.clicked.connect(self._restart_tts_server_clicked)
        tts_server_layout.addWidget(self.kokoro_restart_button)
        self.kokoro_stop_button = QPushButton("Stop")
        self.kokoro_stop_button.clicked.connect(self._stop_tts_server_clicked)
        tts_server_layout.addWidget(self.kokoro_stop_button)
        shell_layout.addWidget(self.tts_server_row)
        self.kokoro_autostart_check = QCheckBox("Auto-start local TTS server when Linux session boots")
        shell_layout.addWidget(self.kokoro_autostart_check)

        self.pocket_language_combo = QComboBox()
        self.pocket_language_combo.setToolTip("PocketTTS language")
        for label, code in POCKETTTS_LANGUAGES:
            self.pocket_language_combo.addItem(label, code)
        self.pocket_preset_combo = QComboBox()
        self.pocket_preset_combo.setToolTip("PocketTTS preset voices (downloaded from Kyutai voice repository)")
        self.pocket_preset_combo.addItem("Voice cloning (custom reference)", "")
        for name, _rel in POCKETTTS_PRESET_VOICES:
            self.pocket_preset_combo.addItem(name, name)
        self.pocket_preset_combo.currentIndexChanged.connect(self._on_pocket_preset_changed)

        self.pocket_lang_preset_row = QWidget()
        pocket_lang_layout = QHBoxLayout(self.pocket_lang_preset_row)
        pocket_lang_layout.setContentsMargins(0, 0, 0, 0)
        pocket_lang_layout.setSpacing(8)
        self.pocket_language_label = QLabel("Language")
        pocket_lang_layout.addWidget(self.pocket_language_label)
        pocket_lang_layout.addWidget(self.pocket_language_combo, 1)
        self.pocket_preset_label = QLabel("Voice")
        pocket_lang_layout.addWidget(self.pocket_preset_label)
        pocket_lang_layout.addWidget(self.pocket_preset_combo, 2)
        shell_layout.addWidget(self.pocket_lang_preset_row)

        self.pocket_voice_combo = QComboBox()
        self.pocket_voice_combo.setToolTip("PocketTTS voice reference presets found in the model folder")
        self.pocket_voice_combo.currentIndexChanged.connect(self._on_pocket_voice_selected)
        self.tts_voice_ref_input = ClickableLineEdit()
        self.tts_voice_ref_input.setPlaceholderText("Reference audio (click to browse)")
        self.tts_voice_ref_input.setToolTip("Click to select an audio file (WAV/MP3/OGG/etc), or paste a path")
        self.tts_voice_ref_input.clicked.connect(self._browse_pocket_voice_reference)

        self.pocket_voice_ref_row = QWidget()
        pocket_ref_layout = QHBoxLayout(self.pocket_voice_ref_row)
        pocket_ref_layout.setContentsMargins(0, 0, 0, 0)
        pocket_ref_layout.setSpacing(8)
        pocket_ref_layout.addWidget(QLabel("Reference"))
        pocket_ref_layout.addWidget(self.pocket_voice_combo, 2)
        pocket_ref_layout.addWidget(self.tts_voice_ref_input, 3)
        shell_layout.addWidget(self.pocket_voice_ref_row)

        self.tts_auto_download_check = QCheckBox("Auto-download ONNX model files when missing")
        shell_layout.addWidget(self.tts_auto_download_check)
        self.tts_test_label = QLabel("Text to be spoken")
        self.tts_test_label.setStyleSheet(f"color: {TEXT_MID};")
        shell_layout.addWidget(self.tts_test_label)
        self.tts_test_row = QWidget()
        tts_test_layout = QHBoxLayout(self.tts_test_row)
        tts_test_layout.setContentsMargins(0, 0, 0, 0)
        tts_test_layout.setSpacing(8)
        self.tts_test_input = QLineEdit()
        self.tts_test_input.setPlaceholderText("Enter the exact text to speak")
        tts_test_layout.addWidget(self.tts_test_input, 1)
        self.tts_test_button = QToolButton()
        self.tts_test_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.tts_test_button.setToolTip("Speak test text")
        self.tts_test_button.clicked.connect(self._test_tts_synthesis)
        self.tts_test_button.setFixedSize(44, 40)
        tts_test_layout.addWidget(self.tts_test_button)
        shell_layout.addWidget(self.tts_test_row)

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

        self.sampler_combo = QComboBox()
        self.sampler_combo.setEditable(True)
        if self.sampler_combo.lineEdit() is not None:
            self.sampler_combo.lineEdit().setPlaceholderText("Sampler")
        shell_layout.addWidget(self.sampler_combo)

        self.cfg_steps_row = QWidget()
        self.cfg_steps_layout = QHBoxLayout(self.cfg_steps_row)
        self.cfg_steps_layout.setContentsMargins(0, 0, 0, 0)
        self.cfg_steps_layout.setSpacing(8)
        self.cfg_label = QLabel("CFG")
        self.cfg_steps_layout.addWidget(self.cfg_label)
        self.cfg_scale_input = QLineEdit()
        self.cfg_scale_input.setPlaceholderText("7.0")
        self.cfg_scale_input.setMaximumWidth(110)
        self.cfg_steps_layout.addWidget(self.cfg_scale_input)
        self.steps_label = QLabel("Steps")
        self.cfg_steps_layout.addWidget(self.steps_label)
        self.steps_input = QLineEdit()
        self.steps_input.setPlaceholderText("28")
        self.steps_input.setMaximumWidth(110)
        self.cfg_steps_layout.addWidget(self.steps_input)
        self.cfg_steps_layout.addStretch(1)
        shell_layout.addWidget(self.cfg_steps_row)

        self.resolution_row = QWidget()
        self.resolution_layout = QHBoxLayout(self.resolution_row)
        self.resolution_layout.setContentsMargins(0, 0, 0, 0)
        self.resolution_layout.setSpacing(8)
        self.width_label = QLabel("Width")
        self.resolution_layout.addWidget(self.width_label)
        self.width_input = QLineEdit()
        self.width_input.setPlaceholderText("1024")
        self.width_input.setMaximumWidth(120)
        self.resolution_layout.addWidget(self.width_input)
        self.height_label = QLabel("Height")
        self.resolution_layout.addWidget(self.height_label)
        self.height_input = QLineEdit()
        self.height_input.setPlaceholderText("1024")
        self.height_input.setMaximumWidth(120)
        self.resolution_layout.addWidget(self.height_input)
        self.resolution_layout.addStretch(1)
        shell_layout.addWidget(self.resolution_row)

        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("SD output folder for monitor notifications")
        shell_layout.addWidget(self.output_dir_input)

        self.monitor_check = QCheckBox("Notify when new SD images appear in the output folder")
        shell_layout.addWidget(self.monitor_check)
        self.sd_options_refresh_button = QPushButton("Refresh SD samplers/checkpoints")
        self.sd_options_refresh_button.clicked.connect(self._refresh_sd_options_clicked)
        shell_layout.addWidget(self.sd_options_refresh_button)

        self.status_label = QLabel("Configure um backend e clique em Test.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")
        self.status_row = QWidget()
        status_row_layout = QHBoxLayout(self.status_row)
        status_row_layout.setContentsMargins(0, 0, 0, 0)
        status_row_layout.setSpacing(8)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_row_layout.addWidget(self.status_label, 1)
        self.copy_status_button = QToolButton()
        self.copy_status_button.setText("Copy errors")
        self.copy_status_button.setToolTip("Copy the current status/error text to the clipboard")
        self.copy_status_button.clicked.connect(self._copy_backend_errors)
        status_row_layout.addWidget(self.copy_status_button)
        shell_layout.addWidget(self.status_row)
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

        self.install_pocket_button = QPushButton("Install PocketTTS (server + models + runtime + voices)")
        self.install_pocket_button.clicked.connect(self._install_pockettts)
        actions.addWidget(self.install_pocket_button)

        actions.addStretch(1)

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
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        shell_layout.addLayout(actions)

        _apply_antialias_font(self)
        self._download_manager = get_tts_download_manager()
        self._tts_preview_worker: TtsSynthesisWorker | None = None
        self._preview_audio_output: QAudioOutput | None = None
        self._preview_media_player: QMediaPlayer | None = None
        self._runtime_worker: TtsRuntimeInstallWorker | None = None
        self._pocket_voice_worker: PocketPresetVoiceWorker | None = None
        self._download_manager.progress_changed.connect(self._on_tts_download_progress)
        self._download_manager.download_finished.connect(self._on_tts_download_finished)
        self._download_manager.download_failed.connect(self._on_tts_download_failed)
        self._load_selected_backend()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if getattr(self, "_did_center", False):
            return
        setattr(self, "_did_center", True)
        parent = self.parentWidget()
        center = None
        if parent is not None and parent.isVisible():
            try:
                center = parent.frameGeometry().center()
            except Exception:
                center = None
        if center is None:
            screen = None
            try:
                if parent is not None and parent.windowHandle() is not None:
                    screen = parent.windowHandle().screen()
            except Exception:
                screen = None
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is not None:
                center = screen.availableGeometry().center()
        if center is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(center)
        self.move(frame.topLeft())

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
            else str(self.sd_model_combo.currentData() or self.sd_model_combo.currentText()).strip()
            if profile.provider == "sdwebui"
            else self.model_input.text().strip()
        )
        pocket_voice_data = str(self.pocket_voice_combo.currentData() or "").strip()
        pocket_preset = str(self.pocket_preset_combo.currentData() or "").strip().lower()
        if pocket_preset:
            voice_mode = "preset"
        elif pocket_voice_data == "__none__":
            voice_mode = "none"
        else:
            voice_mode = "reference"
        existing.update(
            {
                "enabled": bool(self.enabled_check.isChecked()),
                "host": self.host_input.text().strip(),
                "sd_auth_user": self.sd_auth_user_input.text().strip(),
                "model": model_value,
                "binary_path": self.binary_path_input.text().strip(),
                "tts_mode": str(self.tts_mode_combo.currentData()),
                "tts_model_repo": self.tts_repo_input.text().strip(),
                "tts_bundle_url": self.tts_bundle_url_input.text().strip(),
                "tts_server_command": self.tts_server_command_input.text().strip(),
                "tts_voice_reference": self.tts_voice_ref_input.text().strip() if voice_mode == "reference" else "",
                "tts_language": str(self.pocket_language_combo.currentData() or "").strip(),
                "tts_voice_preset": pocket_preset if voice_mode == "preset" else "",
                "tts_voice_mode": voice_mode,
                "tts_download_if_missing": bool(self.tts_auto_download_check.isChecked()),
                "tts_autostart": bool(self.kokoro_autostart_check.isChecked()),
                "gguf_path": self.gguf_path_input.text().strip(),
                "text_model_path": self.text_model_path_input.text().strip(),
                "mmproj_path": self.mmproj_path_input.text().strip(),
                "device": str(self.device_combo.currentData()),
                "negative_prompt": self.negative_prompt_input.text().strip(),
                "sampler_name": str(
                    self.sampler_combo.currentData() or self.sampler_combo.currentText()
                ).strip(),
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
        self.sd_auth_user_input.setText(str(payload.get("sd_auth_user", "")).strip())
        self.sd_auth_pass_input.setText(secure_load_secret(f"{profile.key}:sd_auth_pass"))
        self.model_input.setText(str(payload.get("model", profile.model)))
        self._set_combo_selected(
            self.sd_model_combo, str(payload.get("model", profile.model)).strip() or profile.model
        )
        self.api_key_input.setText(secure_load_secret(f"{profile.key}:api_key"))
        self.binary_path_input.setText(str(payload.get("binary_path", "")))
        self.tts_mode_combo.setCurrentIndex(1 if _default_tts_mode(payload) == "external_api" else 0)
        pocket_mode = _default_tts_mode(payload)
        self._set_combo_selected(self.pocket_mode_combo, pocket_mode)
        self.tts_repo_input.setText(_default_tts_repo(profile, payload))
        self.tts_bundle_url_input.setText(_default_tts_bundle_url(profile, payload))
        self.tts_server_command_input.setText(str(payload.get("tts_server_command", "")))
        self._set_combo_selected(self.pocket_language_combo, _default_pocket_language(payload))
        preset = str(payload.get("tts_voice_preset", "")).strip().lower()
        self._set_combo_selected(self.pocket_preset_combo, preset)
        voice_mode = str(payload.get("tts_voice_mode", "reference")).strip().lower()
        effective_voice_mode = "preset" if profile.key == "pockettts" and preset else voice_mode
        self.tts_voice_ref_input.setText(
            ""
            if profile.key == "pockettts" and effective_voice_mode in {"none", "preset"}
            else str(payload.get("tts_voice_reference", ""))
        )
        if profile.key == "pockettts" and voice_mode == "none":
            self._set_combo_selected(self.pocket_preset_combo, "")
        self.tts_auto_download_check.setChecked(bool(payload.get("tts_download_if_missing", True)))
        self.kokoro_autostart_check.setChecked(bool(payload.get("tts_autostart", False)))
        self.gguf_path_input.setText(str(payload.get("gguf_path", "")))
        self.text_model_path_input.setText(str(payload.get("text_model_path", "")))
        self.mmproj_path_input.setText(str(payload.get("mmproj_path", "")))
        device = str(payload.get("device", "cpu")).lower()
        self.device_combo.setCurrentIndex(1 if device == "gpu" else 0)
        self.negative_prompt_input.setText(str(payload.get("negative_prompt", "")))
        self._set_combo_selected(
            self.sampler_combo, str(payload.get("sampler_name", "Euler a")).strip() or "Euler a"
        )
        self.steps_input.setText(str(payload.get("steps", "28")))
        self.cfg_scale_input.setText(str(payload.get("cfg_scale", "7.0")))
        self.width_input.setText(str(payload.get("width", "1024")))
        self.height_input.setText(str(payload.get("height", "1024")))
        self.output_dir_input.setText(str(payload.get("output_dir", "")))
        self.monitor_check.setChecked(bool(payload.get("monitor_enabled", False)))
        mode = _default_tts_mode(payload)
        show_host = (not profile.needs_api_key) or profile.provider in {"sdwebui", "tts_local"}
        if profile.provider == "tts_local":
            if profile.key == "pockettts":
                show_host = mode == "external_api"
            elif profile.key == "kokorotts":
                show_host = True
        self.host_input.setVisible(show_host)
        self.api_key_input.setVisible(profile.needs_api_key or (profile.provider == "tts_local" and mode == "external_api"))
        is_sd = profile.provider == "sdwebui"
        is_kobold = profile.key == "koboldcpp"
        is_tts = profile.provider == "tts_local"
        device_enabled = is_kobold or is_tts
        self.sd_auth_user_input.setVisible(is_sd)
        self.sd_auth_pass_input.setVisible(is_sd)
        self.binary_path_input.setVisible(is_kobold or (is_tts and mode == "local_onnx"))
        self.tts_mode_combo.setVisible(is_tts and profile.key != "pockettts")
        self.pocket_mode_row.setVisible(is_tts and profile.key == "pockettts")
        self.tts_repo_input.setVisible(is_tts and mode == "local_onnx")
        self.tts_bundle_url_input.setVisible(is_tts and mode == "local_onnx")
        show_tts_server_controls = is_tts and profile.key in {"kokorotts", "pockettts"} and mode == "local_onnx"
        self.tts_server_command_input.setVisible(show_tts_server_controls)
        self.tts_server_row.setVisible(show_tts_server_controls)
        self.kokoro_autostart_check.setVisible(show_tts_server_controls)
        self.pocket_lang_preset_row.setVisible(is_tts and profile.key == "pockettts")
        self.pocket_voice_ref_row.setVisible(is_tts and profile.key == "pockettts" and mode == "local_onnx")
        self.tts_voice_ref_input.setVisible(is_tts and profile.key == "pockettts" and mode == "local_onnx")
        self.tts_auto_download_check.setVisible(is_tts and mode == "local_onnx")
        self.download_tts_button.setVisible(is_tts and mode == "local_onnx")
        self.install_pocket_button.setVisible(is_tts and profile.key == "pockettts" and mode == "local_onnx")
        supports_tts_preview = is_tts and profile.key in {"kokorotts", "pockettts"}
        self.tts_test_label.setVisible(supports_tts_preview)
        self.tts_test_row.setVisible(supports_tts_preview)
        self.gguf_path_input.setVisible(is_kobold)
        self.text_model_path_input.setVisible(is_kobold)
        self.mmproj_path_input.setVisible(is_kobold)
        self.device_combo.setVisible(device_enabled)
        self.negative_prompt_input.setVisible(is_sd)
        self.sampler_combo.setVisible(is_sd)
        self.cfg_steps_row.setVisible(is_sd)
        self.resolution_row.setVisible(is_sd)
        self.output_dir_input.setVisible(is_sd)
        self.monitor_check.setVisible(is_sd)
        self.sd_options_refresh_button.setVisible(is_sd)
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
        self.model_input.setVisible(not (is_tts and profile.key == "kokorotts") and not is_sd)
        self.sd_model_combo.setVisible(is_sd)
        self.kokoro_voice_combo.setVisible(is_tts and profile.key == "kokorotts")
        if is_sd:
            self._reload_sd_backend_options(payload, user_initiated=False)
        if is_tts and profile.key == "kokorotts":
            self._reload_kokoro_voice_list(payload)
        if is_tts and profile.key == "pockettts" and mode == "local_onnx":
            self._reload_pocket_voice_list(payload)
        if show_tts_server_controls:
            self._refresh_tts_server_status(payload)
        self._refresh_download_progress(profile.key if is_tts else "")
        if is_tts:
            self._apply_tts_mode_visibility()
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
        if profile.provider == "tts_local" and profile.key == "pockettts":
            self._test_tts_synthesis()
            return
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
        secure_store_secret(f"{profile.key}:sd_auth_pass", self.sd_auth_pass_input.text().strip())
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
        if profile.key == "pockettts":
            ok, message = _set_pocket_autostart(payload, bool(payload.get("tts_autostart", False)))
            if not ok:
                self.status_label.setText(message)
                self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
                return
            self.settings[profile.key] = payload
            save_backend_settings(self.settings)
        self.status_label.setText("Saved.")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")

    def _install_pockettts(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        payload = self._current_payload()
        started = self._download_manager.start(profile, payload, install_server=True)
        if not started:
            self.status_label.setText("PocketTTS install is already running.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            self._refresh_download_progress(profile.key)
            return
        self.status_label.setText("PocketTTS install started in background (server + model files + runtime + voices).")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")
        self._refresh_download_progress(profile.key)

    def _install_tts_runtime_clicked(self) -> None:
        profile = self._selected_profile()
        if profile.provider != "tts_local":
            return
        if self._runtime_worker is not None and self._runtime_worker.isRunning():
            self.status_label.setText("A runtime install is already running.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        worker = TtsRuntimeInstallWorker(profile.key)
        self._runtime_worker = worker
        self.download_progress.show()
        self.download_progress_label.show()
        self.download_progress.setValue(0)
        self.download_progress_label.setText("Preparing runtime install…")
        self.status_label.setText(f"Installing runtime deps for {profile.label}…")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")

        def _progress(value: int, message: str) -> None:
            self.download_progress.setValue(max(0, min(100, int(value))))
            self.download_progress_label.setText(str(message).strip())

        def _done(_key: str) -> None:
            self.download_progress.setValue(100)
            self.download_progress_label.setText("Runtime ready")
            self.status_label.setText("Runtime dependencies installed.")
            self.status_label.setStyleSheet(f"color: {ACCENT};")

        def _failed(message: str) -> None:
            self.status_label.setText(f"Runtime install failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

        worker.progress.connect(_progress)
        worker.finished_ok.connect(_done)
        worker.failed.connect(_failed)
        worker.finished.connect(lambda: setattr(self, "_runtime_worker", None))
        worker.start()

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

    def _copy_backend_errors(self) -> None:
        status_text = self.status_label.text().strip()
        progress_text = self.download_progress_label.text().strip()
        chunks = []
        if status_text:
            chunks.append(status_text)
        if progress_text and progress_text not in chunks:
            chunks.append(progress_text)
        payload = "\n\n".join(chunks).strip()
        if not payload:
            send_desktop_notification("Clipboard", "No status text to copy yet.")
            return
        QGuiApplication.clipboard().setText(payload)
        send_desktop_notification("Clipboard", "Copied backend errors/status text.")

    def _on_tts_mode_changed(self) -> None:
        profile = self._selected_profile()
        if profile.provider != "tts_local":
            return
        if profile.key == "pockettts":
            mode = str(self.tts_mode_combo.currentData() or "").strip()
            self.pocket_mode_combo.blockSignals(True)
            try:
                self._set_combo_selected(self.pocket_mode_combo, mode)
            finally:
                self.pocket_mode_combo.blockSignals(False)
        self._apply_tts_mode_visibility()

    def _on_pocket_mode_changed(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        desired = str(self.pocket_mode_combo.currentData() or "local_onnx").strip()
        self.tts_mode_combo.blockSignals(True)
        try:
            index = 1 if desired == "external_api" else 0
            self.tts_mode_combo.setCurrentIndex(index)
        finally:
            self.tts_mode_combo.blockSignals(False)
        self._apply_tts_mode_visibility()

    def _apply_tts_mode_visibility(self) -> None:
        profile = self._selected_profile()
        payload = self._current_payload()
        if profile.provider != "tts_local":
            return
        mode = _default_tts_mode(payload)
        if profile.key == "pockettts":
            show_external_fields = mode == "external_api"
            self.host_input.setVisible(show_external_fields)
            self.api_key_input.setVisible(show_external_fields)
        elif profile.key == "kokorotts":
            self.host_input.setVisible(True)
            self.api_key_input.setVisible(mode == "external_api")
        else:
            self.host_input.setVisible(mode == "external_api")
            self.api_key_input.setVisible(mode == "external_api" or profile.needs_api_key)

        local_visible = mode == "local_onnx"
        self.binary_path_input.setVisible(local_visible)
        self.tts_repo_input.setVisible(local_visible)
        self.tts_bundle_url_input.setVisible(local_visible)
        self.tts_auto_download_check.setVisible(local_visible)
        self.download_tts_button.setVisible(local_visible)

        show_server_controls = local_visible and profile.key in {"kokorotts", "pockettts"}
        self.tts_server_command_input.setVisible(show_server_controls)
        self.tts_server_row.setVisible(show_server_controls)
        self.kokoro_autostart_check.setVisible(show_server_controls)

        show_pocket_voice = local_visible and profile.key == "pockettts"
        pocket_preset = str(self.pocket_preset_combo.currentData() or "").strip().lower()
        pocket_voice_data = str(self.pocket_voice_combo.currentData() or "").strip()
        show_pocket_reference = show_pocket_voice and not pocket_preset
        show_pocket_reference_file = show_pocket_reference and pocket_voice_data not in {"", "__none__"}
        self.pocket_lang_preset_row.setVisible(profile.key == "pockettts")
        self.pocket_preset_label.setVisible(show_pocket_voice)
        self.pocket_preset_combo.setVisible(show_pocket_voice)
        self.pocket_voice_ref_row.setVisible(show_pocket_reference)
        self.tts_voice_ref_input.setVisible(show_pocket_reference_file)
        self.install_pocket_button.setVisible(show_pocket_voice)
        if show_pocket_voice:
            self._reload_pocket_voice_list(payload)

    def _browse_pocket_voice_reference(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        current = self.tts_voice_ref_input.text().strip()
        start_dir = str(Path(current).expanduser().parent) if current else str(Path.home())
        path = self._select_reference_audio_file("Select PocketTTS reference audio", start_dir)
        if not path:
            return
        try:
            wav_path = _ensure_wav_reference(Path(path))
        except Exception as exc:
            self.status_label.setText(f"Reference audio conversion failed: {exc}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
            return
        self.tts_voice_ref_input.setText(str(wav_path))
        self._sync_pocket_voice_combo(str(wav_path))
        self._apply_tts_mode_visibility()

    def _select_reference_audio_file(self, title: str, start_dir: str) -> str:
        dialog = QFileDialog(self)
        dialog.setWindowTitle(title)
        dialog.setDirectory(start_dir)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilters(
            [
                "Audio files (*.wav *.mp3 *.ogg *.flac *.m4a *.aac *.opus)",
                "WAV files (*.wav)",
                "All files (*)",
            ]
        )
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet(
            f"""
            QFileDialog, QWidget {{
                background: {CARD_BG};
                color: {TEXT};
            }}
            QLineEdit, QComboBox {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QListView, QTreeView {{
                background: {rgba(PANEL_BG, 0.96)};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
            }}
            QListView::item:selected, QTreeView::item:selected {{
                background: {ACCENT_SOFT};
                color: {TEXT};
            }}
            QPushButton {{
                min-height: 34px;
                background: {CARD_BG_SOFT};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 16px;
                padding: 0 12px;
                font-weight: {_button_css_weight(self.ui_font)};
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
            }}
            """
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        files = dialog.selectedFiles()
        return files[0] if files else ""

    def _on_pocket_voice_selected(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        data = str(self.pocket_voice_combo.currentData() or "").strip()
        if not data:
            return
        if data == "__none__":
            self.tts_voice_ref_input.setText("")
            self.pocket_preset_combo.blockSignals(True)
            try:
                self.pocket_preset_combo.setCurrentIndex(0)
            finally:
                self.pocket_preset_combo.blockSignals(False)
            self._apply_tts_mode_visibility()
            return
        if data == "__browse__":
            self._browse_pocket_voice_reference()
            return
        self.tts_voice_ref_input.setText(data)
        self._apply_tts_mode_visibility()

    def _sync_pocket_voice_combo(self, voice_ref: str) -> None:
        target = str(Path(voice_ref).expanduser())
        for idx in range(self.pocket_voice_combo.count()):
            data = str(self.pocket_voice_combo.itemData(idx) or "")
            if data and str(Path(data).expanduser()) == target:
                self.pocket_voice_combo.setCurrentIndex(idx)
                return
        custom_idx = self.pocket_voice_combo.findData("__browse__")
        if custom_idx >= 0:
            self.pocket_voice_combo.setCurrentIndex(custom_idx)

    def _on_pocket_preset_changed(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        preset = str(self.pocket_preset_combo.currentData() or "").strip().lower()
        self._apply_tts_mode_visibility()
        if not preset:
            return
        if self._pocket_voice_worker is not None and self._pocket_voice_worker.isRunning():
            self.status_label.setText("A PocketTTS voice download is already running.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        payload = self._current_payload()
        model_dir = _default_tts_model_dir(profile, payload)
        self.download_progress.show()
        self.download_progress_label.show()
        self.download_progress.setValue(0)
        self.download_progress_label.setText("Starting voice download…")
        self.status_label.setText(f"Downloading PocketTTS voice: {preset}…")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")
        worker = PocketPresetVoiceWorker(model_dir, preset)
        self._pocket_voice_worker = worker

        def _progress(value: int, message: str) -> None:
            self.download_progress.setValue(max(0, min(100, int(value))))
            self.download_progress_label.setText(str(message).strip())

        def _done(path_text: str) -> None:
            self.download_progress.setValue(100)
            self.download_progress_label.setText("Voice ready")
            self.status_label.setText("PocketTTS voice downloaded.")
            self.status_label.setStyleSheet(f"color: {ACCENT};")
            del path_text
            self.tts_voice_ref_input.setText("")
            self._apply_tts_mode_visibility()

        def _failed(message: str) -> None:
            self.status_label.setText(f"Preset voice download failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

        worker.progress.connect(_progress)
        worker.finished_ok.connect(_done)
        worker.failed.connect(_failed)
        worker.finished.connect(lambda: setattr(self, "_pocket_voice_worker", None))
        worker.start()

    def _reload_pocket_voice_list(self, payload: dict[str, object]) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        model_dir = _default_tts_model_dir(profile, payload)
        selected_ref = str(payload.get("tts_voice_reference", "")).strip()
        voice_mode = str(payload.get("tts_voice_mode", "reference")).strip().lower()
        voices = _list_pocket_voice_references(model_dir)
        self.pocket_voice_combo.blockSignals(True)
        try:
            self.pocket_voice_combo.clear()
            self.pocket_voice_combo.addItem("No voice cloning", "__none__")
            for label, path in voices:
                self.pocket_voice_combo.addItem(label, path)
            self.pocket_voice_combo.addItem("Custom…", "__browse__")
            if voice_mode == "none":
                idx = self.pocket_voice_combo.findData("__none__")
                if idx >= 0:
                    self.pocket_voice_combo.setCurrentIndex(idx)
            elif selected_ref:
                idx = self.pocket_voice_combo.findData(selected_ref)
                if idx >= 0:
                    self.pocket_voice_combo.setCurrentIndex(idx)
        finally:
            self.pocket_voice_combo.blockSignals(False)

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

    def _refresh_tts_server_status(self, payload: dict[str, object] | None = None) -> None:
        effective = dict(payload or self._current_payload())
        selected = self._selected_profile()
        if selected.key == "pockettts":
            active, detail = _pocket_server_status(effective)
        else:
            active, detail = _kokoro_server_status(effective)
        prefix = "● Active" if active else "○ Inactive"
        self.tts_server_status_label.setText(f"Server status: {prefix} — {detail}")
        self.tts_server_status_label.setStyleSheet(
            f"color: {ACCENT if active else TEXT_DIM}; font-weight: 600;"
        )

    def _start_tts_server_clicked(self) -> None:
        payload = self._current_payload()
        selected = self._selected_profile()
        if selected.key == "pockettts":
            ok, message = _start_pocket_server(payload)
        else:
            ok, message = _start_kokoro_server(payload)
        self.settings[selected.key] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_tts_server_status(payload)

    def _stop_tts_server_clicked(self) -> None:
        payload = self._current_payload()
        selected = self._selected_profile()
        if selected.key == "pockettts":
            ok, message = _stop_pocket_server(payload)
        else:
            ok, message = _stop_kokoro_server(payload)
        self.settings[selected.key] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_tts_server_status(payload)

    def _restart_tts_server_clicked(self) -> None:
        payload = self._current_payload()
        selected = self._selected_profile()
        if selected.key == "pockettts":
            _stop_pocket_server(payload)
            ok, message = _start_pocket_server(payload)
        else:
            _stop_kokoro_server(payload)
            ok, message = _start_kokoro_server(payload)
        self.settings[selected.key] = payload
        save_backend_settings(self.settings)
        self.status_label.setText(message if ok else f"Restart failed: {message}")
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self._refresh_tts_server_status(payload)

    def _play_tts_preview(self, audio_path: Path) -> None:
        absolute = audio_path.expanduser().resolve()
        if not absolute.exists():
            send_desktop_notification("Audio not found", str(absolute))
            return
        if not QT_MULTIMEDIA_AVAILABLE:
            _play_audio_file(absolute)
            return
        try:
            if self._preview_audio_output is None or self._preview_media_player is None:
                self._preview_audio_output = QAudioOutput(self)
                self._preview_media_player = QMediaPlayer(self)
                self._preview_media_player.setAudioOutput(self._preview_audio_output)
            self._preview_media_player.stop()
            self._preview_media_player.setSource(QUrl.fromLocalFile(str(absolute)))
            self._preview_media_player.play()
        except Exception:
            _play_audio_file(absolute)

    def _test_tts_synthesis(self) -> None:
        profile = self._selected_profile()
        if profile.key not in {"kokorotts", "pockettts"}:
            return
        text = self.tts_test_input.text().strip()
        if not text:
            self.status_label.setText("Digite um texto para testar o TTS.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        if self._tts_preview_worker is not None and self._tts_preview_worker.isRunning():
            self.status_label.setText("A TTS preview is already running.")
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")
            return
        payload = self._current_payload()
        worker = TtsSynthesisWorker(profile, payload, text)
        self._tts_preview_worker = worker
        label = "PocketTTS" if profile.key == "pockettts" else "Kokoro"
        self.status_label.setText(f"Gerando preview de {label}…")
        self.status_label.setStyleSheet(f"color: {TEXT_MID};")

        def _done(audio_path: str, _label: str, _source: str) -> None:
            self.status_label.setText("Preview gerado. Reproduzindo áudio…")
            self.status_label.setStyleSheet(f"color: {ACCENT};")
            self._play_tts_preview(Path(audio_path))

        def _failed(message: str) -> None:
            self.status_label.setText(f"TTS preview failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

        worker.finished_ok.connect(_done)
        worker.failed.connect(_failed)
        worker.finished.connect(lambda: setattr(self, "_tts_preview_worker", None))
        worker.start()

    def _set_combo_selected(self, combo: QComboBox, value: str) -> None:
        selected = value.strip()
        combo.blockSignals(True)
        if selected:
            idx = combo.findData(selected)
            if idx < 0:
                idx = combo.findText(selected, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(selected)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _set_combo_options(self, combo: QComboBox, values: list[str], selected: str) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = str(value).strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            normalized.append(clean)
        combo.blockSignals(True)
        combo.clear()
        for item in normalized:
            combo.addItem(item, item)
        combo.blockSignals(False)
        self._set_combo_selected(combo, selected)

    def _sd_sampler_options(self, host: str) -> list[str]:
        url = _normalize_host_url(host)
        raw = _http_json(
            f"{url}/sdapi/v1/samplers",
            timeout=3.0,
            headers=self._sd_auth_headers_for_payload(),
        )
        if not isinstance(raw, list):
            raise RuntimeError("Sampler endpoint returned an invalid payload.")
        names: list[str] = []
        for entry in raw:
            if isinstance(entry, dict):
                name = str(entry.get("name", "")).strip()
            else:
                name = str(entry).strip()
            if name:
                names.append(name)
        if not names:
            raise RuntimeError("No samplers were returned by SD WebUI.")
        return names

    def _sd_checkpoint_options(self, host: str) -> list[str]:
        url = _normalize_host_url(host)
        raw = _http_json(
            f"{url}/sdapi/v1/sd-models",
            timeout=3.0,
            headers=self._sd_auth_headers_for_payload(),
        )
        if not isinstance(raw, list):
            raise RuntimeError("Checkpoint endpoint returned an invalid payload.")
        names: list[str] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            model_name = str(entry.get("model_name", "")).strip()
            if title:
                names.append(title)
            elif model_name:
                names.append(model_name)
        if not names:
            raise RuntimeError("No checkpoints were returned by SD WebUI.")
        return names

    def _reload_sd_backend_options(
        self, payload: dict[str, object], *, user_initiated: bool
    ) -> None:
        profile = self._selected_profile()
        if profile.provider != "sdwebui":
            return
        host = str(payload.get("host", self.host_input.text().strip() or profile.host)).strip()
        if not host:
            if user_initiated:
                self.status_label.setText("Set SD host first, then refresh options.")
                self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
            return
        current_sampler = (
            str(payload.get("sampler_name", "")).strip()
            or str(self.sampler_combo.currentData() or self.sampler_combo.currentText()).strip()
            or "Euler a"
        )
        current_model = (
            str(payload.get("model", "")).strip()
            or str(self.sd_model_combo.currentData() or self.sd_model_combo.currentText()).strip()
            or profile.model
        )
        try:
            samplers = self._sd_sampler_options(host)
            checkpoints = self._sd_checkpoint_options(host)
        except error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) == 404:
                if user_initiated:
                    self.status_label.setText(_sdapi_not_found_message(host))
                    self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
                return
            if user_initiated:
                self.status_label.setText(
                    f"Unable to refresh SD options: HTTP {getattr(exc, 'code', 'error')}"
                )
                self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
            return
        except Exception as exc:
            if user_initiated:
                self.status_label.setText(f"Unable to refresh SD options: {exc}")
                self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
            return
        self._set_combo_options(self.sampler_combo, samplers, current_sampler)
        self._set_combo_options(self.sd_model_combo, checkpoints, current_model)
        if user_initiated:
            self.status_label.setText(
                f"Loaded {len(samplers)} sampler(s) and {len(checkpoints)} checkpoint(s) from SD API."
            )
            self.status_label.setStyleSheet(f"color: {TEXT_MID};")

    def _refresh_sd_options_clicked(self) -> None:
        self._reload_sd_backend_options(self._current_payload(), user_initiated=True)

    def _sd_auth_headers_for_payload(self) -> dict[str, str]:
        profile = self._selected_profile()
        if profile.provider != "sdwebui":
            return {}
        username = self.sd_auth_user_input.text().strip()
        password = self.sd_auth_pass_input.text().strip()
        if not password:
            password = secure_load_secret(f"{profile.key}:sd_auth_pass").strip()
        if not username or not password:
            return {}
        token = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}


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


def _audio_wave_inline_html(samples: list[int], is_playing: bool) -> str:
    if not samples:
        samples = [18, 26, 42, 58, 73, 54, 37, 24, 33, 49, 67, 54, 39, 28, 34, 51, 45, 30, 22]
    picked = samples[:24]
    active_cut = max(4, min(len(picked), 8 if not is_playing else 13))
    bars: list[str] = []
    for idx, amplitude in enumerate(picked):
        height = 8 + int((max(0, min(100, amplitude)) / 100.0) * 24)
        color = "#d8ccff" if idx < active_cut else "#8b84a8"
        bars.append(
            f'<span style="display:inline-block;width:3px;height:{height}px;margin-right:3px;'
            f'background:{color};border-radius:2px;vertical-align:bottom;"></span>'
        )
    return "".join(bars)


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
            tooltip = html.escape(Path(current).name)
            samples = item.audio_waveform or _waveform_from_hanauta_service(Path(current), bars=24)
            waveform = _audio_wave_inline_html(samples, is_active and audio_playing)
            card_border = "#7e72d6" if (is_active and audio_playing) else "#655da8"
            icon_color = "#f4eeff"
            icon_text = "⏸" if (is_active and audio_playing) else "▶"
            audio_href = _audio_chip_href(current)
            audio_card_html = (
                '<div class="audio-card-shell">'
                f'<div title="{tooltip}" aria-label="{html.escape(chip_label)}" '
                'style="display:inline-block;outline:none;'
                f'background:linear-gradient(180deg,#262039 0%,#1e1a2e 100%);'
                f'border:2px solid {card_border};border-radius:15px;'
                'padding:8px 10px;line-height:0;">'
                '<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;"><tr>'
                '<td style="width:42px;vertical-align:middle;text-align:center;padding-right:8px;">'
                f'<a href="{audio_href}" title="{tooltip}" aria-label="{html.escape(chip_label)}" '
                'style="display:inline-block;text-decoration:none;outline:none;border:none;">'
                f'<span style="display:inline-block;width:31px;height:31px;line-height:31px;'
                f'font-size:18px;font-weight:700;color:{icon_color};font-family:DejaVu Sans, sans-serif;'
                'background:transparent;border:none;">'
                f'{icon_text}</span>'
                "</a>"
                "</td>"
                '<td style="vertical-align:middle;min-width:154px;max-width:230px;line-height:0;">'
                f'{waveform}'
                "</td>"
                "</tr></table>"
                "</div>"
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


def render_voice_mode_html(
    *,
    status: str,
    transcript: str,
    response: str,
    character_name: str = "",
    character_image_url: str = "",
    listening: bool = False,
    speaking: bool = False,
) -> str:
    accent_ring = "#cab7ff" if listening else "#a88cff" if speaking else "#8b76d1"
    accent_fill = "rgba(202,183,255,0.22)" if listening else "rgba(168,140,255,0.22)" if speaking else "rgba(139,118,209,0.14)"
    state_label = "Listening" if listening else "Speaking" if speaking else status.strip() or "Voice mode"
    transcript_html = html.escape(transcript.strip() or "Say something whenever you're ready.")
    response_clean = response.strip()
    caption_html = html.escape(
        response_clean if speaking and response_clean else "Captions appear here while the character is speaking."
    )
    character_html = html.escape(character_name.strip() or "Hanauta AI")
    avatar_html = (
        f'<img src="{html.escape(character_image_url)}" alt="{character_html}" class="orb-photo-img" />'
        if character_image_url.strip()
        else '<div class="orb-photo-fallback">AI</div>'
    )
    return f"""
    <html>
      <head>
        <style>
        html, body {{
            margin: 0;
            padding: 0;
            background:
              radial-gradient(circle at 50% 16%, rgba(196,181,253,0.12), transparent 18%),
              radial-gradient(circle at 24% 26%, rgba(125,211,252,0.10), transparent 24%),
              radial-gradient(circle at 76% 30%, rgba(192,132,252,0.10), transparent 24%),
              linear-gradient(180deg, #120f20 0%, #0b0912 100%);
            color: {TEXT};
            font-family: Inter, system-ui, sans-serif;
        }}
        body {{
            min-height: 100vh;
            padding: 22px 18px 24px 18px;
            box-sizing: border-box;
            overflow: hidden;
        }}
        .shell {{
            min-height: calc(100vh - 52px);
            border-radius: 28px;
            border: 1px solid rgba(210, 196, 255, 0.12);
            background:
              radial-gradient(circle at 50% 8%, rgba(186, 160, 255, 0.09), transparent 22%),
              linear-gradient(180deg, rgba(22,18,35,0.96) 0%, rgba(12,10,20,0.98) 100%);
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,0.05),
              0 22px 60px rgba(0,0,0,0.36);
            padding: 18px 18px 18px 18px;
            box-sizing: border-box;
            position: relative;
            overflow: hidden;
        }}
        .eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(200,190,255,0.12);
            color: #ddd6fe;
            font-size: 11px;
            letter-spacing: 0;
        }}
        .hero {{
            text-align: center;
            padding: 8px 0 4px 0;
        }}
        .character {{
            margin-top: 16px;
            font-size: 15px;
            font-weight: 700;
            color: #f5f3ff;
        }}
        .status {{
            margin-top: 8px;
            font-size: 30px;
            line-height: 1.15;
            font-weight: 700;
            color: #ffffff;
        }}
        .sub {{
            margin-top: 8px;
            font-size: 13px;
            line-height: 1.5;
            color: #b7adc9;
        }}
        .orb-scene {{
            position: relative;
            margin: 22px auto 14px auto;
            width: 100%;
            min-height: 420px;
        }}
        .soft-grid {{
            position: absolute;
            inset: -50px;
            background-image:
              linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
              linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px);
            background-size: 40px 40px;
            mask-image: radial-gradient(circle at center, black 32%, transparent 84%);
            opacity: 0.5;
        }}
        .orb-wrap {{
            margin: 0 auto;
            width: 330px;
            height: 330px;
            position: relative;
            transform-style: preserve-3d;
        }}
        .orb-glow, .orb-aura, .orb-core, .orb-liquid, .orb-glass,
        .orb-ring, .orb-ring-2, .orb-ring-3, .orb-photo-border, .orb-photo {{
            position: absolute;
            inset: 0;
            border-radius: 50%;
            transform-style: preserve-3d;
        }}
        .orb-glow {{
            inset: -16%;
            background:
              radial-gradient(circle at 50% 50%, rgba(196,181,253,0.30), rgba(129,140,248,0.16) 34%, transparent 68%);
            filter: blur(30px);
            animation: glowPulse 3.1s ease-in-out infinite;
        }}
        .orb-aura {{
            inset: -7%;
            background:
              radial-gradient(circle at 50% 50%, rgba(255,255,255,0.08), transparent 58%),
              conic-gradient(from 180deg, rgba(125,211,252,0.14), rgba(192,132,252,0.12), rgba(196,181,253,0.18), rgba(125,211,252,0.14));
            opacity: 0.95;
            filter: blur(2px);
            animation: auraDrift 5.5s ease-in-out infinite;
        }}
        .orb-core {{
            background:
              radial-gradient(circle at 32% 24%, rgba(255,255,255,0.94) 0 6%, rgba(255,255,255,0.18) 10%, transparent 18%),
              radial-gradient(circle at 68% 70%, rgba(191, 219, 254, 0.12), transparent 20%),
              radial-gradient(circle at 28% 72%, rgba(125, 211, 252, 0.22), transparent 30%),
              radial-gradient(circle at 72% 34%, rgba(192, 132, 252, 0.24), transparent 28%),
              linear-gradient(145deg, rgba(17,24,39,0.12), rgba(9,14,30,0.46)),
              conic-gradient(from 220deg at 50% 50%, #9de4ff, #a471ff, #7fb4ff, #7de2e8, #9de4ff);
            box-shadow:
              inset -26px -36px 70px rgba(0, 0, 0, 0.44),
              inset 10px 16px 46px rgba(255, 255, 255, 0.08),
              0 0 0 1px rgba(255,255,255,0.06);
            overflow: hidden;
            animation: coreMorph 3.1s ease-in-out infinite;
        }}
        .orb-liquid {{
            inset: 5%;
            background:
              radial-gradient(circle at 30% 30%, rgba(255,255,255,0.16), transparent 20%),
              radial-gradient(circle at 64% 44%, rgba(255,255,255,0.10), transparent 22%),
              conic-gradient(from 120deg, rgba(125,211,252,0.16), rgba(167,139,250,0.10), rgba(196,181,253,0.16), rgba(125,211,252,0.16));
            mix-blend-mode: screen;
            opacity: 0.95;
            filter: blur(12px);
            animation: liquidMove 4.6s ease-in-out infinite;
        }}
        .orb-glass {{
            inset: 6%;
            background:
              linear-gradient(145deg, rgba(255,255,255,0.22), rgba(255,255,255,0.02) 34%, rgba(255,255,255,0.08) 58%, rgba(255,255,255,0.04) 100%),
              radial-gradient(circle at 32% 20%, rgba(255,255,255,0.70), rgba(255,255,255,0.12) 16%, transparent 28%);
            mix-blend-mode: screen;
            pointer-events: none;
        }}
        .orb-ring, .orb-ring-2, .orb-ring-3 {{
            border: 1px solid rgba(255,255,255,0.14);
        }}
        .orb-ring {{
            inset: -4%;
            opacity: 0.58;
            animation: ringSpin 11s linear infinite;
        }}
        .orb-ring-2 {{
            inset: 4%;
            opacity: 0.42;
            animation: ringSpinReverse 14s linear infinite;
        }}
        .orb-ring-3 {{
            inset: 16%;
            opacity: 0.28;
            animation: ringPulse 2.4s ease-in-out infinite;
        }}
        .orb-photo-border {{
            inset: 28%;
            background: linear-gradient(145deg, rgba(255,255,255,0.28), rgba(255,255,255,0.08));
            padding: 1px;
            box-shadow: 0 16px 40px rgba(0,0,0,0.30);
        }}
        .orb-photo {{
            inset: 1px;
            overflow: hidden;
            background:
              radial-gradient(circle at 35% 24%, rgba(255,255,255,0.10), transparent 16%),
              linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03)),
              rgba(14, 12, 24, 0.92);
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(10px);
        }}
        .orb-photo-img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}
        .orb-photo-fallback {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #f5f3ff;
            font-size: 30px;
            font-weight: 700;
            background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
        }}
        .orb-photo::after {{
            content: "";
            position: absolute;
            inset: 0;
            background:
              radial-gradient(circle at 30% 20%, rgba(255,255,255,0.16), transparent 20%),
              linear-gradient(180deg, rgba(255,255,255,0.05), transparent 40%, rgba(255,255,255,0.02));
            pointer-events: none;
        }}
        .particle {{
            position: absolute;
            border-radius: 50%;
            background: rgba(255,255,255,0.78);
            box-shadow: 0 0 20px rgba(186,230,253,0.50);
        }}
        .p1 {{ left: 10%; top: 18%; width: 12px; height: 12px; animation: particleA 4.4s ease-in-out infinite; }}
        .p2 {{ left: 22%; top: 30%; width: 8px; height: 8px; animation: particleB 5.0s ease-in-out infinite; }}
        .p3 {{ left: 78%; top: 26%; width: 10px; height: 10px; animation: particleC 4.0s ease-in-out infinite; }}
        .p4 {{ left: 84%; top: 56%; width: 7px; height: 7px; animation: particleA 4.8s ease-in-out infinite; }}
        .p5 {{ left: 18%; top: 72%; width: 9px; height: 9px; animation: particleC 5.2s ease-in-out infinite; }}
        .p6 {{ left: 68%; top: 78%; width: 11px; height: 11px; animation: particleB 4.7s ease-in-out infinite; }}
        .caption-wrap {{
            min-height: 88px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: -8px;
        }}
        .caption {{
            max-width: 690px;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.10);
            background:
              linear-gradient(135deg, rgba(255,255,255,0.16), rgba(255,255,255,0.03)),
              rgba(255,255,255,0.04);
            box-shadow:
              inset 0 1px 0 rgba(255,255,255,0.14),
              0 18px 40px rgba(0,0,0,0.24);
            backdrop-filter: blur(18px);
            color: rgba(255,255,255,0.90);
            font-size: 15px;
            line-height: 1.55;
            padding: 14px 22px;
            text-align: center;
        }}
        .caption.idle {{
            color: rgba(255,255,255,0.48);
        }}
        .footer-card {{
            max-width: 620px;
            margin: 10px auto 0 auto;
            border-radius: 20px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            padding: 14px 16px 16px 16px;
        }}
        .footer-label {{
            color: #c4b5fd;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .footer-value {{
            color: #f8f7ff;
            font-size: 14px;
            line-height: 1.6;
        }}
        .listening .orb-wrap {{
            animation: sceneFloat 3.0s ease-in-out infinite;
        }}
        .speaking .orb-wrap {{
            animation: scenePulse 2.6s ease-in-out infinite;
        }}
        @keyframes glowPulse {{
            0%, 100% {{ transform: scale(0.96); opacity: 0.58; }}
            50% {{ transform: scale(1.14); opacity: 0.96; }}
        }}
        @keyframes auraDrift {{
            0%, 100% {{ transform: scale(1) rotate(0deg); }}
            30% {{ transform: scale(1.05) rotate(8deg); }}
            65% {{ transform: scale(1.02) rotate(-10deg); }}
        }}
        @keyframes coreMorph {{
            0%, 100% {{ border-radius: 50% 50% 50% 50% / 50% 50% 50% 50%; }}
            25% {{ border-radius: 46% 54% 48% 52% / 52% 44% 56% 48%; }}
            60% {{ border-radius: 53% 47% 55% 45% / 47% 57% 43% 53%; }}
        }}
        @keyframes liquidMove {{
            0%, 100% {{ transform: rotate(0deg) scale(1); }}
            35% {{ transform: rotate(18deg) scale(1.05); }}
            70% {{ transform: rotate(-14deg) scale(0.98); }}
        }}
        @keyframes ringSpin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
        }}
        @keyframes ringSpinReverse {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(-360deg); }}
        }}
        @keyframes ringPulse {{
            0%, 100% {{ transform: scale(1); opacity: 0.22; }}
            50% {{ transform: scale(1.08); opacity: 0.42; }}
        }}
        @keyframes particleA {{
            0%, 100% {{ transform: translate(0, 0) scale(0.8); opacity: 0.18; }}
            50% {{ transform: translate(5px, -14px) scale(1.35); opacity: 0.92; }}
        }}
        @keyframes particleB {{
            0%, 100% {{ transform: translate(0, 0) scale(0.75); opacity: 0.14; }}
            50% {{ transform: translate(-5px, -11px) scale(1.18); opacity: 0.82; }}
        }}
        @keyframes particleC {{
            0%, 100% {{ transform: translate(0, 0) scale(0.8); opacity: 0.16; }}
            50% {{ transform: translate(4px, -12px) scale(1.26); opacity: 0.88; }}
        }}
        @keyframes sceneFloat {{
            0%, 100% {{ transform: translateY(0) scale(1); }}
            50% {{ transform: translateY(-4px) scale(1.01); }}
        }}
        @keyframes scenePulse {{
            0%, 100% {{ transform: translateY(0) scale(1); }}
            20% {{ transform: translateY(-4px) scale(1.02) rotate(-0.5deg); }}
            50% {{ transform: translateY(2px) scale(0.985) rotate(0.7deg); }}
            78% {{ transform: translateY(-6px) scale(1.04) rotate(-0.2deg); }}
        }}
        .shell::before {{
            content: "";
            position: absolute;
            inset: 0;
            background:
              radial-gradient(circle at top, {accent_fill} 0%, transparent 36%);
            pointer-events: none;
        }}
        .hint {{
            margin-top: 14px;
            text-align: center;
            color: #9f95b5;
            font-size: 12px;
            line-height: 1.5;
        }}
        </style>
      </head>
      <body>
        <div class="shell {'speaking' if speaking else 'listening' if listening else 'idle'}">
          <div class="soft-grid"></div>
          <div class="hero">
            <div class="eyebrow">Hands-free Voice Mode</div>
            <div class="character">{character_html}</div>
            <div class="status">{html.escape(state_label)}</div>
            <div class="sub">Stay in the conversation. Start talking anytime.</div>
            <div class="orb-scene">
              <div class="orb-wrap">
                <div class="orb-glow"></div>
                <div class="orb-aura"></div>
                <div class="orb-core"></div>
                <div class="orb-liquid"></div>
                <div class="orb-ring"></div>
                <div class="orb-ring-2"></div>
                <div class="orb-ring-3"></div>
                <div class="orb-glass"></div>
                <div class="orb-photo-border">
                  <div class="orb-photo">
                    {avatar_html}
                  </div>
                </div>
                <div class="particle p1"></div>
                <div class="particle p2"></div>
                <div class="particle p3"></div>
                <div class="particle p4"></div>
                <div class="particle p5"></div>
                <div class="particle p6"></div>
              </div>
            </div>
          </div>
          <div class="caption-wrap">
            <div class="caption {'idle' if not speaking else ''}">{caption_html}</div>
          </div>
          <div class="footer-card">
            <div class="footer-label">You</div>
            <div class="footer-value">{transcript_html}</div>
          </div>
          <div class="hint">Close or stop voice mode anytime and the regular chat returns.</div>
        </div>
      </body>
    </html>
    """


WEB_POPUP_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hanauta AI</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f0d18;
      --panel: rgba(24, 20, 36, 0.96);
      --panel-2: rgba(33, 28, 48, 0.86);
      --panel-3: rgba(255,255,255,0.04);
      --line: rgba(214, 195, 255, 0.10);
      --line-2: rgba(214, 195, 255, 0.18);
      --text: #f4effd;
      --text-dim: rgba(244,239,253,0.66);
      --accent: #c6b4ff;
      --accent-2: #8fdfff;
      --accent-3: #b287ff;
      --user-bg: rgba(126, 94, 197, 0.20);
      --assistant-bg: rgba(255,255,255,0.05);
      --shadow: 0 24px 60px rgba(0,0,0,.38);
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      overflow-x: hidden;
      background: transparent;
      color: var(--text);
      font-family: Inter, system-ui, sans-serif;
    }
    *::-webkit-scrollbar:horizontal { height: 0 !important; display: none; }
    * { scrollbar-width: thin; scrollbar-color: rgba(198,180,255,.24) rgba(255,255,255,.04); }
    body {
      background:
        radial-gradient(circle at 20% 10%, rgba(143,223,255,.08), transparent 24%),
        radial-gradient(circle at 80% 10%, rgba(178,135,255,.10), transparent 26%),
        linear-gradient(180deg, #171322 0%, #100d18 100%);
    }
    .app {
      width: 100%;
      height: 100%;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .window {
      flex: 1;
      min-height: 0;
      border-radius: 30px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(27,22,40,.96), rgba(16,13,24,.98));
      box-shadow: var(--shadow);
      overflow: hidden;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    .window.voice-active .header {
      display: none;
    }
    .window.voice-active .body {
      padding-top: 0;
    }
    .window.voice-active .chat-page {
      display: none !important;
    }
    .window.voice-active .voice-page {
      display: block !important;
      flex: 1 1 auto;
      min-height: 0;
      padding: 0;
    }
    .header {
      padding: 14px 16px 12px 16px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand { flex: 1; min-width: 0; }
    .title { font-size: 16px; font-weight: 700; color: var(--text); }
    .status { font-size: 12px; color: var(--text-dim); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .actions { display: flex; gap: 8px; }
    .icon-btn, .pill, .send-btn, .voice-stop {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.04);
      color: var(--text);
      border-radius: 999px;
      cursor: pointer;
      transition: transform .14s ease, background .14s ease, border-color .14s ease;
    }
    .icon-btn:hover, .pill:hover, .send-btn:hover, .voice-stop:hover { transform: translateY(-1px); }
    .icon-btn { width: 34px; height: 34px; font-size: 14px; }
    .body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
    .chat-page { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; padding: 14px 14px 14px 14px; }
    .backend-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .pill { padding: 7px 12px; font-size: 12px; }
    .pill.active { background: rgba(198,180,255,.16); border-color: var(--line-2); color: var(--accent); }
    .conversation {
      flex: 1;
      min-height: 0;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.03);
      padding: 12px;
      overflow-y: auto;
      overflow-x: hidden;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .conversation::-webkit-scrollbar,
    .voice-page::-webkit-scrollbar {
      width: 11px;
    }
    .conversation::-webkit-scrollbar-track,
    .voice-page::-webkit-scrollbar-track {
      background: rgba(255,255,255,.04);
      border-radius: 8px;
    }
    .conversation::-webkit-scrollbar-thumb,
    .voice-page::-webkit-scrollbar-thumb {
      background: linear-gradient(180deg, rgba(198,180,255,.30), rgba(143,223,255,.20));
      border-radius: 8px;
      border: 1px solid rgba(214,195,255,.12);
    }
    .msg { display: flex; gap: 10px; }
    .msg.user { flex-direction: row-reverse; }
    .avatar {
      width: 32px;
      min-width: 32px;
      height: 32px;
      border-radius: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      background: rgba(255,255,255,.08);
      color: var(--accent);
      border: 1px solid rgba(255,255,255,.08);
    }
    .msg.user .avatar {
      background: rgba(198,180,255,.16);
      color: #f6f0ff;
    }
    .bubble {
      flex: 1;
      max-width: calc(100% - 48px);
      min-width: 0;
      border-radius: 24px;
      padding: 14px 16px 16px 16px;
      background: var(--assistant-bg);
      border: 1px solid rgba(255,255,255,.06);
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .msg.user .bubble { background: var(--user-bg); border-color: rgba(198,180,255,.14); }
    .bubble-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
    .bubble-title { font-size: 13px; font-weight: 700; color: var(--accent); }
    .msg.user .bubble-title { color: #efe7ff; }
    .bubble-meta { font-size: 11px; color: var(--text-dim); }
    .bubble-body { font-size: 13px; line-height: 1.58; color: var(--text); }
    .bubble-body p { margin: 0 0 8px 0; }
    .bubble-body img { max-width: 100%; height: auto; }
    .bubble-body pre, .bubble-body code { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .chip { padding: 7px 11px; border-radius: 999px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.05); font-size: 11px; color: var(--text); }
    .audio-btn {
      margin-top: 10px;
      border-radius: 16px;
      border: 1px solid rgba(198,180,255,.18);
      background: linear-gradient(180deg, rgba(42,35,64,.96), rgba(27,22,40,.98));
      padding: 10px 12px;
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: #f5f2ff;
      cursor: pointer;
    }
    .composer {
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.04);
      padding: 12px;
    }
    .composer textarea {
      width: 100%;
      min-height: 76px;
      resize: none;
      border: 1px solid rgba(255,255,255,.06);
      background: rgba(255,255,255,.04);
      color: var(--text);
      border-radius: 18px;
      padding: 12px 14px;
      font: inherit;
      outline: none;
      overflow-x: hidden;
    }
    .composer-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
    .provider { flex: 1; font-size: 12px; color: var(--text-dim); }
    .send-btn { padding: 8px 14px; background: rgba(198,180,255,.18); color: #fff; }
    .voice-page {
      flex: 1;
      min-height: 0;
      padding: 16px;
      overflow-y: auto;
      overflow-x: hidden;
    }
    .voice-page[hidden],
    .chat-page[hidden] {
      display: none !important;
    }
    .voice-shell {
      min-height: 100%;
      border-radius: 26px;
      border: 1px solid rgba(214,195,255,.10);
      background:
        radial-gradient(circle at 50% 8%, rgba(186,160,255,0.09), transparent 22%),
        linear-gradient(180deg, rgba(22,18,35,0.96) 0%, rgba(12,10,20,0.98) 100%);
      padding: 18px;
      position: relative;
      overflow: hidden;
    }
    .voice-topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .voice-topbar-left,
    .voice-topbar-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .voice-nav-btn,
    .voice-stop-btn-top {
      min-height: 40px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.14);
      color: var(--text);
      cursor: pointer;
      transition: transform .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    .voice-nav-btn {
      background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04));
      box-shadow: inset 0 1px 0 rgba(255,255,255,.10);
    }
    .voice-stop-btn-top {
      background: linear-gradient(180deg, rgba(198,180,255,.22), rgba(198,180,255,.12));
      box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 10px 24px rgba(107,82,173,.18);
    }
    .voice-nav-btn:hover,
    .voice-stop-btn-top:hover {
      transform: translateY(-1px);
      border-color: rgba(214,195,255,.24);
    }
    .voice-top { text-align: center; }
    .voice-pill { display: inline-flex; padding: 8px 12px; border-radius: 999px; background: rgba(255,255,255,.04); border: 1px solid rgba(214,195,255,.12); font-size: 11px; color: #ddd6fe; }
    .voice-name { margin-top: 16px; font-size: 15px; font-weight: 700; }
    .voice-status { margin-top: 8px; font-size: 30px; font-weight: 700; }
    .voice-sub { margin-top: 8px; font-size: 13px; color: var(--text-dim); }
    .orb-scene { position: relative; margin: 22px auto 14px auto; width: 330px; height: 330px; }
    .orb-wrap, .orb-glow, .orb-aura, .orb-core, .orb-liquid, .orb-glass, .orb-ring, .orb-ring-2, .orb-ring-3, .orb-photo-border, .orb-photo {
      position: absolute; inset: 0; border-radius: 50%;
    }
    .orb-wrap.speaking { animation: scenePulse 2.6s ease-in-out infinite; }
    .orb-wrap.listening { animation: sceneFloat 3.0s ease-in-out infinite; }
    .orb-wrap.emotion-angry { animation: sceneAngry 1.1s ease-in-out infinite; }
    .orb-wrap.emotion-happy { animation: sceneHappy 2.2s ease-in-out infinite; }
    .orb-wrap.emotion-sad { animation: sceneSad 3.2s ease-in-out infinite; }
    .orb-wrap.emotion-excited { animation: sceneExcited 1.3s ease-in-out infinite; }
    .orb-wrap.emotion-calm { animation: sceneCalm 3.8s ease-in-out infinite; }
    .orb-wrap.emotion-playful,
    .orb-wrap.emotion-teasing,
    .orb-wrap.emotion-flirty { animation: scenePlayful 1.9s ease-in-out infinite; }
    .orb-wrap.emotion-serious { animation: sceneSerious 2.7s ease-in-out infinite; }
    .orb-wrap.emotion-embarrassed,
    .orb-wrap.emotion-shy { animation: sceneShy 2.4s ease-in-out infinite; }
    .orb-wrap.emotion-affectionate { animation: sceneAffectionate 2.6s ease-in-out infinite; }
    .orb-glow { inset: -16%; background: radial-gradient(circle at 50% 50%, rgba(196,181,253,0.30), rgba(129,140,248,0.16) 34%, transparent 68%); filter: blur(30px); animation: glowPulse 3.1s ease-in-out infinite; }
    .orb-aura { inset: -7%; background: radial-gradient(circle at 50% 50%, rgba(255,255,255,0.08), transparent 58%), conic-gradient(from 180deg, rgba(125,211,252,0.14), rgba(192,132,252,0.12), rgba(196,181,253,0.18), rgba(125,211,252,0.14)); animation: auraDrift 5.5s ease-in-out infinite; }
    .orb-core { background: radial-gradient(circle at 32% 24%, rgba(255,255,255,0.94) 0 6%, rgba(255,255,255,0.18) 10%, transparent 18%), radial-gradient(circle at 68% 70%, rgba(191,219,254,0.12), transparent 20%), radial-gradient(circle at 28% 72%, rgba(125,211,252,0.22), transparent 30%), radial-gradient(circle at 72% 34%, rgba(192,132,252,0.24), transparent 28%), linear-gradient(145deg, rgba(17,24,39,0.12), rgba(9,14,30,0.46)), conic-gradient(from 220deg at 50% 50%, #9de4ff, #a471ff, #7fb4ff, #7de2e8, #9de4ff); box-shadow: inset -26px -36px 70px rgba(0,0,0,0.44), inset 10px 16px 46px rgba(255,255,255,0.08), 0 0 0 1px rgba(255,255,255,0.06); overflow: hidden; animation: coreMorph 3.1s ease-in-out infinite; }
    .orb-liquid { inset: 5%; background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.16), transparent 20%), radial-gradient(circle at 64% 44%, rgba(255,255,255,0.10), transparent 22%), conic-gradient(from 120deg, rgba(125,211,252,0.16), rgba(167,139,250,0.10), rgba(196,181,253,0.16), rgba(125,211,252,0.16)); mix-blend-mode: screen; filter: blur(12px); animation: liquidMove 4.6s ease-in-out infinite; }
    .orb-glass { inset: 6%; background: linear-gradient(145deg, rgba(255,255,255,0.22), rgba(255,255,255,0.02) 34%, rgba(255,255,255,0.08) 58%, rgba(255,255,255,0.04) 100%), radial-gradient(circle at 32% 20%, rgba(255,255,255,0.70), rgba(255,255,255,0.12) 16%, transparent 28%); mix-blend-mode: screen; }
    .orb-ring, .orb-ring-2, .orb-ring-3 { border: 1px solid rgba(255,255,255,0.14); }
    .orb-ring { inset: -4%; animation: ringSpin 11s linear infinite; }
    .orb-ring-2 { inset: 4%; animation: ringSpinReverse 14s linear infinite; }
    .orb-ring-3 { inset: 16%; animation: ringPulse 2.4s ease-in-out infinite; }
    .orb-photo-border { inset: 28%; background: linear-gradient(145deg, rgba(255,255,255,0.28), rgba(255,255,255,0.08)); padding: 1px; box-shadow: 0 16px 40px rgba(0,0,0,0.30); }
    .orb-photo { inset: 1px; overflow: hidden; background: radial-gradient(circle at 35% 24%, rgba(255,255,255,0.10), transparent 16%), linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03)), rgba(14,12,24,0.92); display: flex; align-items: center; justify-content: center; }
    .orb-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .orb-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 30px; font-weight: 700; }
    .caption-stack {
      max-width: 760px;
      margin: 8px auto 0 auto;
      display: grid;
      gap: 12px;
    }
    .caption-card {
      position: relative;
      overflow: hidden;
      border-radius: 22px;
      border: 1px solid rgba(255,255,255,0.10);
      background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03));
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.14), 0 18px 40px rgba(0,0,0,0.24);
      padding: 14px 16px 16px 16px;
      backdrop-filter: blur(18px);
    }
    .caption-card::before {
      content: "";
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at top left, rgba(255,255,255,.10), transparent 34%);
      pointer-events: none;
    }
    .caption-card.you {
      background: linear-gradient(135deg, rgba(143,223,255,0.14), rgba(255,255,255,0.03));
      border-color: rgba(143,223,255,0.16);
    }
    .caption-card.ai {
      background: linear-gradient(135deg, rgba(198,180,255,0.16), rgba(255,255,255,0.03));
      border-color: rgba(198,180,255,0.16);
    }
    .caption-head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .caption-badge {
      min-width: 38px;
      height: 38px;
      border-radius: 19px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .02em;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.16);
    }
    .caption-card.you .caption-badge {
      background: linear-gradient(180deg, rgba(143,223,255,.28), rgba(143,223,255,.14));
      color: #dff8ff;
    }
    .caption-card.ai .caption-badge {
      background: linear-gradient(180deg, rgba(198,180,255,.30), rgba(198,180,255,.14));
      color: #f5eeff;
    }
    .caption-labels {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .caption-name {
      font-size: 13px;
      font-weight: 700;
      color: #ffffff;
    }
    .caption-meta {
      font-size: 11px;
      color: var(--text-dim);
    }
    .caption-text {
      color: rgba(255,255,255,0.92);
      font-size: 15px;
      line-height: 1.6;
      text-shadow: 0 1px 14px rgba(255,255,255,0.03);
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .caption-card.idle .caption-text {
      color: rgba(255,255,255,0.48);
    }
    .voice-card { max-width: 620px; margin: 14px auto 0 auto; border-radius: 20px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); padding: 14px 16px 16px 16px; }
    .voice-card .label { color: #c4b5fd; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
    .voice-card .value { color: #f8f7ff; font-size: 14px; line-height: 1.6; }
    .voice-controls { display: flex; justify-content: center; margin-top: 16px; }
    .voice-stop { padding: 10px 16px; }
    @keyframes glowPulse { 0%,100% { transform: scale(.96); opacity:.58; } 50% { transform: scale(1.14); opacity:.96; } }
    @keyframes auraDrift { 0%,100% { transform: scale(1) rotate(0deg);} 30% { transform: scale(1.05) rotate(8deg);} 65% { transform: scale(1.02) rotate(-10deg);} }
    @keyframes coreMorph { 0%,100% { border-radius:50%; } 25% { border-radius:46% 54% 48% 52% / 52% 44% 56% 48%; } 60% { border-radius:53% 47% 55% 45% / 47% 57% 43% 53%; } }
    @keyframes liquidMove { 0%,100% { transform: rotate(0deg) scale(1);} 35% { transform: rotate(18deg) scale(1.05);} 70% { transform: rotate(-14deg) scale(0.98);} }
    @keyframes ringSpin { from { transform: rotate(0deg);} to { transform: rotate(360deg);} }
    @keyframes ringSpinReverse { from { transform: rotate(0deg);} to { transform: rotate(-360deg);} }
    @keyframes ringPulse { 0%,100% { transform: scale(1); opacity:.22;} 50% { transform: scale(1.08); opacity:.42;} }
    @keyframes sceneFloat { 0%,100% { transform: translateY(0) scale(1);} 50% { transform: translateY(-4px) scale(1.01);} }
    @keyframes scenePulse { 0%,100% { transform: translateY(0) scale(1);} 20% { transform: translateY(-4px) scale(1.02) rotate(-0.5deg);} 50% { transform: translateY(2px) scale(0.985) rotate(0.7deg);} 78% { transform: translateY(-6px) scale(1.04) rotate(-0.2deg);} }
    @keyframes sceneAngry { 0%,100% { transform: translateX(0) scale(1.01) rotate(0deg);} 20% { transform: translateX(-6px) scale(1.03) rotate(-1.2deg);} 40% { transform: translateX(6px) scale(1.05) rotate(1.2deg);} 60% { transform: translateX(-5px) scale(1.03) rotate(-0.9deg);} 80% { transform: translateX(5px) scale(1.04) rotate(0.9deg);} }
    @keyframes sceneHappy { 0%,100% { transform: translateY(0) scale(1);} 25% { transform: translateY(-10px) scale(1.04) rotate(-1deg);} 50% { transform: translateY(-2px) scale(1.07) rotate(1deg);} 75% { transform: translateY(-8px) scale(1.03) rotate(-0.6deg);} }
    @keyframes sceneSad { 0%,100% { transform: translateY(0) scale(0.985);} 50% { transform: translateY(8px) scale(0.975);} }
    @keyframes sceneExcited { 0%,100% { transform: translateY(0) scale(1);} 20% { transform: translateY(-12px) scale(1.06);} 40% { transform: translateY(2px) scale(0.99);} 60% { transform: translateY(-9px) scale(1.05);} 80% { transform: translateY(-2px) scale(1.02);} }
    @keyframes sceneCalm { 0%,100% { transform: translateY(0) scale(1);} 50% { transform: translateY(-3px) scale(1.008);} }
    @keyframes scenePlayful { 0%,100% { transform: translateY(0) rotate(0deg);} 25% { transform: translateY(-6px) rotate(-2deg);} 50% { transform: translateY(2px) rotate(2deg);} 75% { transform: translateY(-5px) rotate(-1.5deg);} }
    @keyframes sceneSerious { 0%,100% { transform: translateY(0) scale(1);} 50% { transform: translateY(-2px) scale(1.015);} }
    @keyframes sceneShy { 0%,100% { transform: translateY(0) translateX(0) scale(0.995);} 50% { transform: translateY(3px) translateX(-4px) scale(1.005);} }
    @keyframes sceneAffectionate { 0%,100% { transform: translateY(0) scale(1);} 50% { transform: translateY(-7px) scale(1.03);} }
  </style>
</head>
<body>
  <div class="app">
    <div class="window">
      <div class="header">
        <div class="brand">
          <div class="title">Hanauta AI</div>
          <div class="status" id="headerStatus"></div>
        </div>
        <div class="actions">
          <button class="icon-btn" id="voiceBtn" title="Voice mode">🎙</button>
          <button class="icon-btn" id="settingsBtn" title="Settings">⚙</button>
          <button class="icon-btn" id="charactersBtn" title="Characters">☺</button>
          <button class="icon-btn" id="closeBtn" title="Close">✕</button>
        </div>
      </div>
      <div class="body">
        <div class="chat-page" id="chatPage">
          <div class="backend-row" id="backendRow"></div>
          <div class="conversation" id="conversation"></div>
          <div class="composer">
            <textarea id="composerInput" placeholder="Message the model... Enter to send"></textarea>
            <div class="composer-row">
              <div class="provider" id="providerLabel"></div>
              <button class="send-btn" id="clearBtn">Clear</button>
              <button class="send-btn" id="sendBtn">Send</button>
            </div>
          </div>
        </div>
        <div class="voice-page" id="voicePage" hidden>
          <div class="voice-shell">
            <div class="voice-topbar">
              <div class="voice-topbar-left">
                <button class="voice-nav-btn" id="voiceBackBtn">← Back</button>
              </div>
              <div class="voice-topbar-right">
                <button class="voice-stop-btn-top" id="voiceStopTopBtn">Stop</button>
              </div>
            </div>
            <div class="voice-top">
              <div class="voice-pill">Hands-free Voice Mode</div>
              <div class="voice-name" id="voiceName"></div>
              <div class="voice-status" id="voiceStatus"></div>
              <div class="voice-sub">Stay in the conversation. Start talking anytime.</div>
              <div class="orb-scene">
                <div class="orb-wrap" id="orbWrap">
                  <div class="orb-glow"></div>
                  <div class="orb-aura"></div>
                  <div class="orb-core"></div>
                  <div class="orb-liquid"></div>
                  <div class="orb-ring"></div>
                  <div class="orb-ring-2"></div>
                  <div class="orb-ring-3"></div>
                  <div class="orb-glass"></div>
                  <div class="orb-photo-border">
                    <div class="orb-photo" id="orbPhoto"></div>
                  </div>
                </div>
              </div>
            </div>
            <div class="caption-stack">
              <div class="caption-card you" id="voiceYouCard">
                <div class="caption-head">
                  <div class="caption-badge">YOU</div>
                  <div class="caption-labels">
                    <div class="caption-name">You</div>
                    <div class="caption-meta">Speech to text</div>
                  </div>
                </div>
                <div class="caption-text" id="voiceTranscript"></div>
              </div>
              <div class="caption-card ai" id="voiceAiCard">
                <div class="caption-head">
                  <div class="caption-badge">AI</div>
                  <div class="caption-labels">
                    <div class="caption-name" id="voiceAiName">Hanauta AI</div>
                    <div class="caption-meta">Spoken reply</div>
                  </div>
                </div>
                <div class="caption-text" id="voiceCaption"></div>
              </div>
            </div>
            <div class="voice-card">
              <div class="label">Status</div>
              <div class="value" id="voiceStatusNote">Voice mode is ready.</div>
            </div>
            <div class="voice-controls">
              <button class="voice-stop" id="voiceStopBtn">Return to chat</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <script>
    let bridge = null;
    let state = {};
    const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
    const nl2br = (value) => esc(value).replace(/\n/g, '<br>');

    function renderMessages(messages) {
      const root = document.getElementById('conversation');
      if (!Array.isArray(messages) || !messages.length) {
        root.innerHTML = '<div class="bubble"><div class="bubble-body"><p>No conversation yet.</p></div></div>';
        return;
      }
      root.innerHTML = messages.map((item) => {
        const chips = (item.chips || []).map((chip) => `<span class="chip">${esc(chip)}</span>`).join('');
        const audio = item.audio_path ? `<button class="audio-btn" onclick="toggleAudio(${JSON.stringify(item.audio_path)})">${item.is_active_audio && item.audio_playing ? 'Pause' : 'Play'} audio</button>` : '';
        return `
          <article class="msg ${item.role === 'user' ? 'user' : 'assistant'}">
            <div class="avatar">${item.role === 'user' ? 'Y' : 'AI'}</div>
            <div class="bubble">
              <div class="bubble-head">
                <div class="bubble-title">${esc(item.title || '')}</div>
                <div class="bubble-meta">${esc(item.meta || '')}</div>
              </div>
              <div class="bubble-body">${item.body_html || ''}</div>
              ${audio}
              ${chips ? `<div class="chips">${chips}</div>` : ''}
            </div>
          </article>
        `;
      }).join('');
      root.scrollTop = root.scrollHeight;
    }

    function renderBackends(backends) {
      const row = document.getElementById('backendRow');
      row.innerHTML = (backends || []).map((backend) => `
        <button class="pill ${backend.active ? 'active' : ''}" onclick="selectBackend(${JSON.stringify(backend.key)})">${esc(backend.label)}</button>
      `).join('');
    }

    function renderVoice(voice) {
      const speaking = !!voice.speaking;
      const listening = !!voice.listening;
      document.getElementById('voiceName').textContent = voice.character_name || 'Hanauta AI';
      document.getElementById('voiceAiName').textContent = voice.character_name || 'Hanauta AI';
      document.getElementById('voiceStatus').textContent = voice.status || 'Voice mode';
      document.getElementById('voiceStatusNote').textContent =
        speaking ? 'The reply below is the exact text being spoken.' :
        listening ? 'Listening now. Start talking whenever you want.' :
        (voice.status || 'Voice mode is ready.');
      document.getElementById('voiceTranscript').textContent = voice.transcript || "Say something whenever you're ready.";
      document.getElementById('voiceCaption').textContent = speaking && voice.response ? voice.response : 'The AI reply appears here while speech is playing.';
      document.getElementById('voiceAiCard').classList.toggle('idle', !(speaking && voice.response));
      document.getElementById('voiceYouCard').classList.toggle('idle', !voice.transcript);
      const orb = document.getElementById('orbWrap');
      const emotion = (voice.emotion || 'neutral').toLowerCase().replace(/[^a-z_]/g, '');
      orb.className = `orb-wrap ${speaking ? 'speaking' : listening ? 'listening' : ''} ${emotion ? 'emotion-' + emotion : ''}`;
      const photo = document.getElementById('orbPhoto');
      photo.innerHTML = voice.character_image_url ? `<img src="${esc(voice.character_image_url)}" alt="${esc(voice.character_name || 'Character')}" />` : '<div class="orb-fallback">AI</div>';
    }

    function render(payload) {
      state = payload || {};
      const inVoice = state.mode === 'voice';
      const windowEl = document.querySelector('.window');
      if (windowEl) windowEl.classList.toggle('voice-active', inVoice);
      document.getElementById('headerStatus').textContent = state.header_status || '';
      document.getElementById('providerLabel').textContent = state.provider_label || '';
      renderBackends(state.backends || []);
      renderMessages(state.messages || []);
      renderVoice(state.voice || {});
      document.getElementById('chatPage').hidden = inVoice;
      document.getElementById('voicePage').hidden = !inVoice;
      document.getElementById('voiceBtn').textContent = inVoice ? '■' : '🎙';
    }

    function sendNow() {
      const el = document.getElementById('composerInput');
      const text = (el.value || '').trim();
      if (!text || !bridge || !bridge.sendPrompt) return;
      bridge.sendPrompt(text);
      el.value = '';
    }
    function selectBackend(key) { if (bridge && bridge.selectBackend) bridge.selectBackend(key); }
    function toggleAudio(path) { if (bridge && bridge.toggleAudio) bridge.toggleAudio(path); }

    document.getElementById('sendBtn').addEventListener('click', sendNow);
    document.getElementById('clearBtn').addEventListener('click', () => bridge && bridge.clearChat && bridge.clearChat());
    document.getElementById('settingsBtn').addEventListener('click', () => bridge && bridge.openSettings && bridge.openSettings());
    document.getElementById('charactersBtn').addEventListener('click', () => bridge && bridge.openCharacters && bridge.openCharacters());
    document.getElementById('voiceBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceStopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceStopTopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceBackBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('closeBtn').addEventListener('click', () => bridge && bridge.closeWindow && bridge.closeWindow());
    document.getElementById('composerInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendNow();
      }
    });

    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.bridge;
      bridge.stateChanged.connect(function(raw) {
        try { render(JSON.parse(raw)); } catch (_err) {}
      });
      if (bridge && bridge.jsReady) bridge.jsReady();
    });
  </script>
</body>
</html>
"""


class PopupWebBridge(QObject):
    stateChanged = pyqtSignal(str)

    def __init__(self, owner: "SidebarPanel") -> None:
        super().__init__(owner)
        self.owner = owner

    @pyqtSlot()
    def jsReady(self) -> None:
        self.owner._sync_web_ui()

    @pyqtSlot(str)
    def sendPrompt(self, text: str) -> None:
        self.owner.add_user_message(text)

    @pyqtSlot()
    def openSettings(self) -> None:
        self.owner._open_backend_settings()

    @pyqtSlot()
    def openCharacters(self) -> None:
        self.owner._open_character_library()

    @pyqtSlot()
    def toggleVoiceMode(self) -> None:
        self.owner._toggle_voice_mode()

    @pyqtSlot()
    def clearChat(self) -> None:
        self.owner._clear_cards()

    @pyqtSlot(str)
    def selectBackend(self, key: str) -> None:
        self.owner._select_backend_from_key(key)

    @pyqtSlot(str)
    def toggleAudio(self, path: str) -> None:
        self.owner._toggle_audio_from_web(path)

    @pyqtSlot()
    def closeWindow(self) -> None:
        self.owner._close_popup_window()


class PopupWebView(QWidget):
    def __init__(self, owner: "SidebarPanel", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.owner = owner
        self._loaded = False
        self._pending_state = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if not WEBENGINE_AVAILABLE:
            fallback = QTextBrowser(self)
            fallback.setHtml("<p>QtWebEngine is required for the web-first Hanauta AI popup.</p>")
            layout.addWidget(fallback, 1)
            self.view = fallback  # type: ignore[assignment]
            return
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        self.channel = QWebChannel(self.view.page())
        self.bridge = PopupWebBridge(owner)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.loadFinished.connect(self._on_loaded)
        base_url = QUrl.fromLocalFile(str(PLUGIN_ROOT) + os.sep)
        self.view.setHtml(WEB_POPUP_HTML, base_url)
        layout.addWidget(self.view, 1)

    def _on_loaded(self, ok: bool) -> None:
        self._loaded = bool(ok)
        if ok and self._pending_state:
            self.bridge.stateChanged.emit(self._pending_state)

    def set_state(self, payload: dict[str, object]) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        self._pending_state = raw
        if self._loaded and hasattr(self, "bridge"):
            self.bridge.stateChanged.emit(raw)

class _AudioWebPage(QWebEnginePage):
    link_clicked = pyqtSignal(QUrl)

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            self.link_clicked.emit(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class ChatWebView(QWidget):
    audio_state_changed = pyqtSignal()

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
        self._fade_timer: QTimer | None = None
        self._default_volume = 1.0

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
        self.audio_state_changed.emit()

    def _stop_fade_timer(self) -> None:
        if self._fade_timer is not None:
            self._fade_timer.stop()
            self._fade_timer.deleteLater()
            self._fade_timer = None

    def fade_out_current_audio(self, duration_ms: int = 420) -> None:
        if self._media_player is None or self._audio_output is None:
            return
        if self._media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
        self._pending_play_path = ""
        self._stop_fade_timer()
        try:
            start_volume = float(self._audio_output.volume())
        except Exception:
            start_volume = self._default_volume
        steps = max(4, min(18, int(duration_ms / 35)))
        interval = max(16, int(duration_ms / steps))
        state = {"step": 0}
        timer = QTimer(self)

        def _tick() -> None:
            state["step"] += 1
            ratio = max(0.0, 1.0 - (state["step"] / float(steps)))
            try:
                self._audio_output.setVolume(max(0.0, start_volume * ratio))
            except Exception:
                pass
            if state["step"] < steps:
                return
            self._stop_fade_timer()
            self._media_player.stop()
            try:
                self._audio_output.setVolume(self._default_volume)
            except Exception:
                pass
            if self._active_audio_path:
                self._set_audio_state(Path(self._active_audio_path), False)

        timer.timeout.connect(_tick)
        self._fade_timer = timer
        timer.start(interval)

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
        self.audio_state_changed.emit()

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
        self._stop_fade_timer()
        if self._audio_output is not None:
            try:
                self._audio_output.setVolume(self._default_volume)
            except Exception:
                pass
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


class VoiceModeWebView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._using_webengine = WEBENGINE_AVAILABLE and os.environ.get("HANAUTA_AI_POPUP_WEBENGINE", "0").strip() == "1"
        self._view: QWebEngineView | QTextBrowser
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if self._using_webengine:
            view = QWebEngineView(self)
            page = QWebEnginePage(view)
            page.setBackgroundColor(QColor(CHAT_SURFACE_BG))
            view.setPage(page)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._view = view
        else:
            view = QTextBrowser(self)
            view.setOpenExternalLinks(False)
            view.setOpenLinks(False)
            view.setReadOnly(True)
            view.setFrameShape(QFrame.Shape.NoFrame)
            self._view = view
        layout.addWidget(self._view, 1)
        self._view.setStyleSheet(
            f"""
            QTextBrowser, QWebEngineView {{
                background: transparent;
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
            """
        )

    def set_state(
        self,
        *,
        status: str,
        transcript: str,
        response: str,
        character_name: str = "",
        character_image_url: str = "",
        listening: bool = False,
        speaking: bool = False,
    ) -> None:
        doc = render_voice_mode_html(
            status=status,
            transcript=transcript,
            response=response,
            character_name=character_name,
            character_image_url=character_image_url,
            listening=listening,
            speaking=speaking,
        )
        if self._using_webengine:
            assert isinstance(self._view, QWebEngineView)
            self._view.setHtml(doc)
            return
        assert isinstance(self._view, QTextBrowser)
        self._view.setHtml(doc)


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
        response = _http_post_json(
            f"{url}/sdapi/v1/txt2img",
            request_payload,
            timeout=300.0,
            headers=_sd_auth_headers(self.profile.key, self.settings),
        )
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


class VoiceConversationWorker(QThread):
    status_changed = pyqtSignal(str)
    transcript_ready = pyqtSignal(str)
    response_ready = pyqtSignal(str, str, str, str, str, str)
    barge_in_detected = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: dict[str, object],
        profiles: dict[str, BackendProfile],
        backend_settings: dict[str, dict[str, object]],
        character: CharacterCard | None,
    ) -> None:
        super().__init__()
        self.config = dict(config)
        self.profiles = dict(profiles)
        self.backend_settings = json.loads(json.dumps(backend_settings))
        self.character = CharacterCard(**character.__dict__) if character is not None else None
        self._running = True

    def stop(self) -> None:
        self._running = False

    def _record_seconds(self) -> int:
        try:
            return int(float(str(self.config.get("record_seconds", "5"))))
        except Exception:
            return 5

    def _silence_threshold(self) -> float:
        try:
            return float(str(self.config.get("silence_threshold", "0.012")))
        except Exception:
            return 0.012

    def _barge_in_threshold(self) -> float:
        try:
            configured = float(str(self.config.get("barge_in_threshold", "0.035")))
        except Exception:
            configured = 0.035
        return max(self._silence_threshold() * 1.8, configured)

    def _tts_profile(self) -> BackendProfile:
        key = str(self.config.get("tts_profile", "kokorotts")).strip()
        profile = self.profiles.get(key)
        if profile is None or profile.provider != "tts_local":
            raise RuntimeError("Select KokoroTTS or PocketTTS for voice replies.")
        return profile

    def _tts_payload(self, profile: BackendProfile) -> dict[str, object]:
        payload = dict(self.backend_settings.get(profile.key, {}))
        payload = _with_voice_device(payload, str(self.config.get("tts_device", payload.get("device", "cpu"))))
        if bool(self.config.get("tts_external_api", False)):
            payload["tts_mode"] = "external_api"
        return payload

    def run(self) -> None:
        while self._running:
            try:
                self.status_changed.emit("Listening")
                audio_path = _record_microphone_wav(self._record_seconds())
                if not self._running:
                    break
                rms = _voice_recording_rms(audio_path)
                if rms < self._silence_threshold():
                    self.status_changed.emit("Silence skipped")
                    continue
                self.status_changed.emit("Transcribing")
                transcript = transcribe_voice_audio(audio_path, self.config)
                if not self._running:
                    break
                if not transcript.strip():
                    self.status_changed.emit("No speech detected")
                    continue
                self.transcript_ready.emit(transcript)
                self.status_changed.emit("Thinking")
                answer, llm_label, llm_model, emotion = generate_voice_chat_reply(
                    self.config,
                    self.profiles,
                    self.backend_settings,
                    transcript,
                    self.character if bool(self.config.get("enable_character", True)) else None,
                )
                if not self._running:
                    break
                self.status_changed.emit("Speaking")
                tts_profile = self._tts_profile()
                audio_out, source = synthesize_tts(tts_profile, self._tts_payload(tts_profile), answer)
                if not self._running:
                    break
                self.response_ready.emit(answer, str(audio_out), llm_label, llm_model, source, emotion)
                pause_until = time.time() + min(45.0, max(1.0, _wav_duration_seconds(audio_out) + 0.6))
                while self._running and time.time() < pause_until:
                    if not bool(self.config.get("barge_in_enabled", True)):
                        time.sleep(0.1)
                        continue
                    try:
                        sample = _record_microphone_wav(0.55)
                        if _voice_recording_rms(sample) >= self._barge_in_threshold():
                            self.barge_in_detected.emit()
                            self.status_changed.emit("Listening")
                            break
                    except Exception:
                        time.sleep(0.2)
            except Exception as exc:
                self.failed.emit(str(exc).strip() or exc.__class__.__name__)
                time.sleep(0.8)
        self.status_changed.emit("Voice mode stopped")


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
            QPushButton {{
                background: {rgba(CARD_BG_SOFT, 0.90)};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.98)};
                border-radius: 12px;
                padding: 8px 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_ACCENT};
            }}
            QPushButton:pressed {{
                background: {rgba(ACCENT_SOFT, 0.92)};
                color: {ACCENT_ALT};
                border: 1px solid {rgba(ACCENT_ALT, 0.45)};
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


class VoiceModeDialog(QDialog):
    def __init__(
        self,
        profiles: list[BackendProfile],
        settings: dict[str, dict[str, object]],
        ui_font: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profiles = profiles
        self.settings = settings
        self.config = _voice_mode_settings(settings)
        self.ui_font = ui_font
        self.setWindowTitle("Voice Mode")
        self.resize(600, 680)
        self.setStyleSheet(
            f"""
            QDialog, QScrollArea, QWidget {{
                background: {PANEL_BG_FLOAT};
                color: {TEXT};
            }}
            QLabel, QCheckBox {{
                color: {TEXT};
            }}
            QLineEdit, QComboBox {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QPushButton {{
                background: {rgba(CARD_BG_SOFT, 0.90)};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.98)};
                border-radius: 12px;
                padding: 8px 12px;
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
        root.setSpacing(10)

        title = QLabel("Voice mode")
        title.setFont(QFont(ui_font, 14, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        root.addWidget(title)

        subtitle = QLabel("Hands-free loop: listen, transcribe, ask the text model, speak the answer.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {TEXT_DIM};")
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        scroll.setWidget(body)

        self.enabled_check = QCheckBox("Enable voice mode after saving")
        self.enabled_check.setChecked(bool(self.config.get("enabled", False)))
        form.addWidget(self.enabled_check)

        self.record_seconds_input = QLineEdit(str(self.config.get("record_seconds", "5")))
        self.record_seconds_input.setPlaceholderText("Listening window in seconds")
        form.addWidget(self._labeled("Listen window", self.record_seconds_input))
        self.silence_threshold_input = QLineEdit(str(self.config.get("silence_threshold", "0.012")))
        self.silence_threshold_input.setPlaceholderText("Silence threshold, e.g. 0.012")
        form.addWidget(self._labeled("Silence skip threshold", self.silence_threshold_input))

        form.addWidget(self._section_label("Speech to text"))
        self.stt_external_check = QCheckBox("Use external STT API")
        self.stt_external_check.setChecked(bool(self.config.get("stt_external_api", False)))
        self.stt_external_check.toggled.connect(self._refresh_visibility)
        form.addWidget(self.stt_external_check)
        self.stt_backend_combo = QComboBox()
        self.stt_backend_combo.addItem("Faster Whisper local", "whisper")
        self.stt_backend_combo.addItem("VOSK English local", "vosk")
        self._set_combo_selected(self.stt_backend_combo, str(self.config.get("stt_backend", "whisper")))
        self.stt_backend_combo.currentIndexChanged.connect(self._refresh_visibility)
        form.addWidget(self._labeled("Local STT engine", self.stt_backend_combo))
        self.stt_model_combo = QComboBox()
        for name in ("tiny", "small", "medium", "large"):
            self.stt_model_combo.addItem(f"Whisper {name}", name)
        self._set_combo_selected(self.stt_model_combo, str(self.config.get("stt_model", "small")))
        form.addWidget(self._labeled("Whisper model", self.stt_model_combo))
        self.stt_device_combo = self._device_combo(str(self.config.get("stt_device", "cpu")))
        form.addWidget(self._labeled("STT device", self.stt_device_combo))
        self.stt_vosk_model_input = QLineEdit(str(self.config.get("stt_vosk_model_path", "")))
        self.stt_vosk_model_input.setPlaceholderText("VOSK English model folder")
        form.addWidget(self._labeled("VOSK model folder", self.stt_vosk_model_input))
        self.stt_host_input = QLineEdit(str(self.config.get("stt_host", "api.openai.com")))
        self.stt_host_input.setPlaceholderText("STT API host")
        form.addWidget(self._labeled("STT API host", self.stt_host_input))
        self.stt_remote_model_input = QLineEdit(str(self.config.get("stt_remote_model", "whisper-1")))
        self.stt_remote_model_input.setPlaceholderText("Remote STT model")
        form.addWidget(self._labeled("Remote STT model", self.stt_remote_model_input))
        self.stt_api_key_input = QLineEdit(secure_load_secret("voice_mode:stt_api_key"))
        self.stt_api_key_input.setPlaceholderText("STT API key")
        self.stt_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self._labeled("STT API key", self.stt_api_key_input))

        form.addWidget(self._section_label("Text model"))
        self.llm_external_check = QCheckBox("Use external OpenAI-compatible text API")
        self.llm_external_check.setChecked(bool(self.config.get("llm_external_api", False)))
        self.llm_external_check.toggled.connect(self._refresh_visibility)
        form.addWidget(self.llm_external_check)
        self.llm_profile_combo = QComboBox()
        for profile in profiles:
            if profile.provider in {"openai", "openai_compat"} or profile.key == "ollama":
                self.llm_profile_combo.addItem(profile.label, profile.key)
        self._set_combo_selected(self.llm_profile_combo, str(self.config.get("llm_profile", "koboldcpp")))
        form.addWidget(self._labeled("Local/profile backend", self.llm_profile_combo))
        self.llm_host_input = QLineEdit(str(self.config.get("llm_host", "api.openai.com")))
        self.llm_host_input.setPlaceholderText("OpenAI-compatible API host")
        form.addWidget(self._labeled("External text host", self.llm_host_input))
        self.llm_model_input = QLineEdit(str(self.config.get("llm_model", "gpt-4.1-mini")))
        self.llm_model_input.setPlaceholderText("Text model")
        form.addWidget(self._labeled("External text model", self.llm_model_input))
        self.llm_device_combo = self._device_combo(str(self.config.get("llm_device", "cpu")))
        form.addWidget(self._labeled("Text model device", self.llm_device_combo))
        self.llm_api_key_input = QLineEdit(secure_load_secret("voice_mode:llm_api_key"))
        self.llm_api_key_input.setPlaceholderText("External text API key")
        self.llm_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self._labeled("External text API key", self.llm_api_key_input))

        form.addWidget(self._section_label("Speech output"))
        self.tts_profile_combo = QComboBox()
        for profile in profiles:
            if profile.provider == "tts_local":
                self.tts_profile_combo.addItem(profile.label, profile.key)
        self._set_combo_selected(self.tts_profile_combo, str(self.config.get("tts_profile", "kokorotts")))
        form.addWidget(self._labeled("TTS backend", self.tts_profile_combo))
        self.tts_device_combo = self._device_combo(str(self.config.get("tts_device", "cpu")))
        form.addWidget(self._labeled("TTS device", self.tts_device_combo))
        self.tts_external_check = QCheckBox("Use selected TTS backend in external API mode")
        self.tts_external_check.setChecked(bool(self.config.get("tts_external_api", False)))
        form.addWidget(self.tts_external_check)
        self.barge_in_check = QCheckBox("Stop speech when I start talking")
        self.barge_in_check.setChecked(bool(self.config.get("barge_in_enabled", True)))
        form.addWidget(self.barge_in_check)
        self.barge_in_threshold_input = QLineEdit(str(self.config.get("barge_in_threshold", "0.035")))
        self.barge_in_threshold_input.setPlaceholderText("Barge-in threshold, e.g. 0.035")
        form.addWidget(self._labeled("Barge-in threshold", self.barge_in_threshold_input))
        self.emotion_tags_check = QCheckBox("Enable character emotion tags for orb motion")
        self.emotion_tags_check.setChecked(bool(self.config.get("emotion_tags_enabled", True)))
        form.addWidget(self.emotion_tags_check)

        form.addWidget(self._section_label("Character and notifications"))
        self.character_check = QCheckBox("Enable character")
        self.character_check.setChecked(bool(self.config.get("enable_character", True)))
        form.addWidget(self.character_check)
        self.hide_photo_check = QCheckBox("Hide character photo in closed-popup notifications")
        self.hide_photo_check.setChecked(bool(self.config.get("hide_character_photo", False)))
        form.addWidget(self.hide_photo_check)
        self.hide_answer_check = QCheckBox("Hide answer text in closed-popup notifications")
        self.hide_answer_check.setChecked(bool(self.config.get("hide_answer_text", False)))
        form.addWidget(self.hide_answer_check)
        self.generic_text_input = QLineEdit(str(self.config.get("generic_notification_text", "Notification received")))
        self.generic_text_input.setPlaceholderText("Generic notification text")
        form.addWidget(self._labeled("Generic notification", self.generic_text_input))

        form.addWidget(self._section_label("Compaction and privacy"))
        self.privacy_word_coding_check = QCheckBox("Enable private/NSFW word coding for compaction")
        self.privacy_word_coding_check.setChecked(bool(self.config.get("privacy_word_coding_enabled", False)))
        form.addWidget(self.privacy_word_coding_check)
        self.privacy_words_input = QPlainTextEdit()
        self.privacy_words_input.setPlaceholderText("One private or NSFW word per line")
        self.privacy_words_input.setFixedHeight(96)
        self.privacy_words_input.setPlainText(str(self.config.get("privacy_words", "")))
        form.addWidget(self._labeled("Words to code", self.privacy_words_input))
        self.compaction_host_input = QLineEdit(str(self.config.get("compaction_model_host", "")))
        self.compaction_host_input.setPlaceholderText("Optional compaction model host")
        form.addWidget(self._labeled("Compaction host", self.compaction_host_input))
        self.compaction_model_input = QLineEdit(str(self.config.get("compaction_model_name", "")))
        self.compaction_model_input.setPlaceholderText("Optional compaction model name")
        form.addWidget(self._labeled("Compaction model", self.compaction_model_input))

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save)
        actions.addWidget(save_button)
        close_button = QPushButton("Cancel")
        close_button.clicked.connect(self.reject)
        actions.addWidget(close_button)
        root.addLayout(actions)
        self._refresh_visibility()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(QFont(self.ui_font, 12, QFont.Weight.DemiBold))
        label.setStyleSheet(f"color: {ACCENT}; margin-top: 8px;")
        return label

    def _labeled(self, label_text: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {TEXT_DIM};")
        layout.addWidget(label)
        layout.addWidget(widget)
        return wrap

    def _device_combo(self, selected: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("CPU", "cpu")
        combo.addItem("GPU", "gpu")
        self._set_combo_selected(combo, selected)
        return combo

    def _set_combo_selected(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _refresh_visibility(self) -> None:
        stt_external = self.stt_external_check.isChecked()
        stt_is_vosk = str(self.stt_backend_combo.currentData() or "") == "vosk"
        for widget in (self.stt_backend_combo, self.stt_model_combo, self.stt_device_combo, self.stt_vosk_model_input):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(not stt_external)
        if self.stt_model_combo.parentWidget() is not None:
            self.stt_model_combo.parentWidget().setVisible((not stt_external) and not stt_is_vosk)
        if self.stt_vosk_model_input.parentWidget() is not None:
            self.stt_vosk_model_input.parentWidget().setVisible((not stt_external) and stt_is_vosk)
        for widget in (self.stt_host_input, self.stt_remote_model_input, self.stt_api_key_input):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(stt_external)

        llm_external = self.llm_external_check.isChecked()
        for widget in (self.llm_profile_combo, self.llm_device_combo):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(not llm_external)
        for widget in (self.llm_host_input, self.llm_model_input, self.llm_api_key_input):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(llm_external)

    def _save(self) -> None:
        config = dict(_voice_mode_defaults())
        config.update(
            {
                "enabled": bool(self.enabled_check.isChecked()),
                "record_seconds": self.record_seconds_input.text().strip() or "5",
                "silence_threshold": self.silence_threshold_input.text().strip() or "0.012",
                "stt_backend": str(self.stt_backend_combo.currentData() or "whisper"),
                "stt_model": str(self.stt_model_combo.currentData() or "small"),
                "stt_device": str(self.stt_device_combo.currentData() or "cpu"),
                "stt_external_api": bool(self.stt_external_check.isChecked()),
                "stt_host": self.stt_host_input.text().strip(),
                "stt_remote_model": self.stt_remote_model_input.text().strip() or "whisper-1",
                "stt_vosk_model_path": self.stt_vosk_model_input.text().strip(),
                "llm_profile": str(self.llm_profile_combo.currentData() or "koboldcpp"),
                "llm_device": str(self.llm_device_combo.currentData() or "cpu"),
                "llm_external_api": bool(self.llm_external_check.isChecked()),
                "llm_host": self.llm_host_input.text().strip(),
                "llm_model": self.llm_model_input.text().strip() or "gpt-4.1-mini",
                "tts_profile": str(self.tts_profile_combo.currentData() or "kokorotts"),
                "tts_device": str(self.tts_device_combo.currentData() or "cpu"),
                "tts_external_api": bool(self.tts_external_check.isChecked()),
                "barge_in_enabled": bool(self.barge_in_check.isChecked()),
                "barge_in_threshold": self.barge_in_threshold_input.text().strip() or "0.035",
                "emotion_tags_enabled": bool(self.emotion_tags_check.isChecked()),
                "enable_character": bool(self.character_check.isChecked()),
                "hide_character_photo": bool(self.hide_photo_check.isChecked()),
                "hide_answer_text": bool(self.hide_answer_check.isChecked()),
                "generic_notification_text": self.generic_text_input.text().strip() or "Notification received",
                "privacy_word_coding_enabled": bool(self.privacy_word_coding_check.isChecked()),
                "privacy_words": self.privacy_words_input.toPlainText().strip(),
                "compaction_model_host": self.compaction_host_input.text().strip(),
                "compaction_model_name": self.compaction_model_input.text().strip(),
            }
        )
        self.settings["_voice_mode"] = config
        secure_store_secret("voice_mode:stt_api_key", self.stt_api_key_input.text().strip())
        secure_store_secret("voice_mode:llm_api_key", self.llm_api_key_input.text().strip())
        save_backend_settings(self.settings)
        _write_privacy_codebook(config)
        self.config = config
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
        _write_privacy_codebook(_voice_mode_settings(self.backend_settings))
        self.current_profile: BackendProfile | None = None
        self._card_animations: list[QPropertyAnimation] = []
        self.chat_history = secure_load_chat_history()
        self.character_cards, self.active_character_id = load_character_library()
        self._sd_seen_outputs: dict[str, tuple[str, float]] = {}
        self._image_worker: SdImageWorker | None = None
        self._tts_worker: TtsSynthesisWorker | None = None
        self._voice_worker: VoiceConversationWorker | None = None
        self._local_backend_processes: dict[str, subprocess.Popen[str]] = {}
        self._pending_item: ChatItemData | None = None
        self._voice_last_status = "Voice mode"
        self._voice_last_transcript = ""
        self._voice_last_response = ""
        self._voice_last_emotion = "neutral"
        self._voice_listening = False
        self._voice_speaking = False
        self._web_mode = "chat"
        self._text_response_timer = QTimer(self)
        self._text_response_timer.setSingleShot(True)
        self._text_response_timer.timeout.connect(self._finish_mock_text_response)

        self.setObjectName("sidebarPanel")
        self.setFixedWidth(452)
        self.setStyleSheet(
            f"""
            QFrame#sidebarPanel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {rgba(PANEL_BG_FLOAT, 0.99)},
                    stop:0.45 {rgba(HERO_BOTTOM, 0.975)},
                    stop:1 {rgba(PANEL_BG_DEEP, 0.99)});
                border: 1px solid {rgba(BORDER_HARD, 0.95)};
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
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(13)

        # Keep the legacy widget tree alive off-screen for state plumbing and audio playback,
        # but render the actual popup as a web app via QtWebEngine.
        self._hidden_hero = self._build_hero()
        self._hidden_backend_strip = self._build_backend_strip()
        self.chat_view = ChatWebView()
        self.chat_view.audio_state_changed.connect(self._sync_web_ui)
        self.composer = ComposerBar(ui_font)
        self.composer.send_requested.connect(self.add_user_message)
        self.composer.character_requested.connect(self._open_character_library)
        self.voice_mode_view = VoiceModeWebView()
        self.web_view = PopupWebView(self, self)
        root.addWidget(self.web_view, 1)

        self._render_chat_history()
        self._refresh_available_backends()
        self._update_voice_mode_view()
        self._sync_web_ui()
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self._poll_sd_output_monitors)
        self.monitor_timer.start(8000)

    def _popup_open(self) -> bool:
        win = self.window()
        return bool(win is not None and win.isVisible() and not win.isMinimized())

    def _notify_if_popup_closed(self, title: str, body: str, icon_path: str = "") -> None:
        if not self._popup_open():
            send_desktop_notification(title, body, icon_path=icon_path)

    def _active_character_avatar_icon(self) -> str:
        active = self._active_character()
        if active is None:
            return ""
        avatar = Path(str(active.avatar_path or "").strip()).expanduser()
        if not str(avatar).strip() or not avatar.exists():
            return ""
        return str(avatar)

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
        title_wrap.setSpacing(2)

        title = QLabel("Hanauta AI")
        title.setFont(QFont(self.ui_font, 16, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        title_wrap.addWidget(title)
        subtitle = QLabel("Local-first assistant")
        subtitle.setFont(QFont(self.ui_font, 10, QFont.Weight.Medium))
        subtitle.setStyleSheet(f"color: {TEXT_MID};")
        title_wrap.addWidget(subtitle)
        top.addLayout(title_wrap, 1)

        self.voice_button = ActionIcon("🎙", "Start voice mode", self.ui_font)
        self.voice_button.clicked.connect(self._toggle_voice_mode)
        top.addWidget(self.voice_button)

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
        close_button.clicked.connect(self._close_popup_window)
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

        badges = QHBoxLayout()
        badges.setContentsMargins(0, 0, 0, 0)
        badges.setSpacing(8)
        badges.addWidget(HeaderBadge("Chat", self.ui_font))
        badges.addWidget(HeaderBadge("Images", self.ui_font))
        badges.addWidget(HeaderBadge("TTS", self.ui_font, accent=True))
        badges.addStretch(1)
        layout.addLayout(badges)

        return frame

    def _close_popup_window(self) -> None:
        host = self.window()
        if self._voice_worker is not None and self._voice_worker.isRunning():
            if isinstance(host, QWidget):
                host.hide()
                return
            self.hide()
            return
        if isinstance(host, QWidget):
            host.close()
            return
        self.close()

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
            self._sync_web_ui()
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
            self._sync_web_ui()
            return
        self.header_status.setText(f"{self.current_profile.label}  •  {model}  •  {host}")
        self._sync_web_ui()

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
        self._sync_web_ui()

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
        self._sync_web_ui()

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
        self._sync_web_ui()

    def _open_backend_settings(self) -> None:
        dialog = BackendSettingsDialog(self.profiles, self.backend_settings, self.ui_font, self)
        dialog.exec()
        self.backend_settings = load_backend_settings()
        self._refresh_available_backends()
        self._sync_web_ui()

    def _open_voice_mode_settings(self) -> bool:
        dialog = VoiceModeDialog(self.profiles, self.backend_settings, self.ui_font, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.backend_settings = load_backend_settings()
        return True

    def _voice_character_name(self) -> str:
        config = _voice_mode_settings(self.backend_settings)
        active = self._active_character() if bool(config.get("enable_character", True)) else None
        return active.name if active is not None else "Hanauta AI"

    def _voice_stt_backend_model(self) -> tuple[str, str]:
        config = _voice_mode_settings(self.backend_settings)
        if bool(config.get("stt_external_api", False)):
            return "External STT", str(config.get("stt_remote_model", "whisper-1")).strip() or "whisper-1"
        backend = str(config.get("stt_backend", "whisper")).strip().lower()
        if backend == "vosk":
            path = Path(str(config.get("stt_vosk_model_path", "")).strip()).expanduser()
            return "VOSK", path.name or "english model"
        model = str(config.get("stt_model", "small")).strip().lower() or "small"
        return "Whisper", model.title()

    def _voice_llm_backend_model(self) -> tuple[str, str]:
        config = _voice_mode_settings(self.backend_settings)
        if bool(config.get("llm_external_api", False)):
            return "OpenAI-compatible", str(config.get("llm_model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
        profile = self.profile_by_key.get(profile_key)
        if profile is None:
            return "Unknown", "Unknown"
        payload = dict(self.backend_settings.get(profile.key, {}))
        model = str(payload.get("model", profile.model)).strip() or profile.model
        if profile.key == "koboldcpp":
            gguf_path = _existing_path(payload.get("gguf_path"))
            if gguf_path is not None:
                model = gguf_path.name
        return profile.label, model

    def _voice_character_image_url(self) -> str:
        config = _voice_mode_settings(self.backend_settings)
        active = self._active_character() if bool(config.get("enable_character", True)) else None
        if active is None:
            return ""
        avatar = Path(str(active.avatar_path or "").strip()).expanduser()
        if not str(avatar).strip() or not avatar.exists():
            return ""
        try:
            return avatar.resolve().as_uri()
        except Exception:
            return ""

    def _set_voice_mode_screen(self, enabled: bool) -> None:
        self._web_mode = "voice" if enabled else "chat"
        self._sync_web_ui()

    def _update_voice_mode_view(self, *, listening: bool = False, speaking: bool = False) -> None:
        if not hasattr(self, "voice_mode_view"):
            return
        self.voice_mode_view.set_state(
            status=self._voice_last_status,
            transcript=self._voice_last_transcript,
            response=self._voice_last_response,
            character_name=self._voice_character_name(),
            character_image_url=self._voice_character_image_url(),
            listening=listening,
            speaking=speaking,
        )
        self._voice_listening = bool(listening)
        self._voice_speaking = bool(speaking)
        self._sync_web_ui()

    def _html_message_payload(self, item: ChatItemData) -> dict[str, object]:
        current_audio = str(getattr(self.chat_view, "_active_audio_path", "") or "")
        audio_playing = bool(getattr(self.chat_view, "_audio_playing", False))
        item_audio = str(Path(item.audio_path).expanduser().resolve()) if item.audio_path.strip() else ""
        return {
            "role": item.role,
            "title": item.title,
            "meta": item.meta,
            "body_html": item.body,
            "chips": [chip.text for chip in item.chips],
            "audio_path": item_audio,
            "audio_playing": audio_playing,
            "is_active_audio": bool(item_audio and current_audio == item_audio),
        }

    def _build_web_payload(self) -> dict[str, object]:
        header_status = self.header_status.text().strip() if hasattr(self, "header_status") else ""
        provider_label = self.composer.provider_label.text().strip() if hasattr(self, "composer") else ""
        available_backends = []
        for profile in self.profiles:
            payload = self.backend_settings.get(profile.key, {})
            ready = bool(payload.get("enabled", True) and payload.get("tested", False))
            if ready:
                available_backends.append(
                    {
                        "key": profile.key,
                        "label": profile.label,
                        "active": bool(self.current_profile is not None and self.current_profile.key == profile.key),
                    }
                )
        history = list(self.chat_history)
        if self._pending_item is not None:
            history.append(self._pending_item)
        return {
            "mode": getattr(self, "_web_mode", "chat"),
            "header_status": header_status,
            "provider_label": provider_label,
            "backends": available_backends,
            "messages": [self._html_message_payload(item) for item in history],
            "voice": {
                "status": self._voice_last_status,
                "transcript": self._voice_last_transcript,
                "response": self._voice_last_response,
                "emotion": self._voice_last_emotion,
                "character_name": self._voice_character_name(),
                "character_image_url": self._voice_character_image_url(),
                "listening": bool(getattr(self, "_voice_listening", False)),
                "speaking": bool(getattr(self, "_voice_speaking", False)),
            },
        }

    def _sync_web_ui(self) -> None:
        if hasattr(self, "web_view"):
            self.web_view.set_state(self._build_web_payload())

    def _select_backend_from_key(self, key: str) -> None:
        profile = self.profile_by_key.get(key)
        button = self.backend_buttons.get(key)
        if profile is None or button is None:
            return
        self._select_backend(profile, button)

    def _toggle_audio_from_web(self, path_text: str) -> None:
        clean = str(path_text).strip()
        if not clean:
            return
        self.chat_view._toggle_audio_path(Path(clean))
        self._sync_web_ui()

    def _toggle_voice_mode(self) -> None:
        if self._voice_worker is not None and self._voice_worker.isRunning():
            self._stop_voice_mode()
            return
        config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            if not self._open_voice_mode_settings():
                return
            config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            return
        self._start_voice_mode(config)

    def _start_voice_mode(self, config: dict[str, object]) -> None:
        if self._voice_worker is not None and self._voice_worker.isRunning():
            return
        if not bool(config.get("llm_external_api", False)):
            profile = self.profile_by_key.get(str(config.get("llm_profile", "koboldcpp")).strip())
            if profile is not None and profile.key == "koboldcpp":
                self.backend_settings.setdefault(profile.key, {})["device"] = str(config.get("llm_device", "cpu"))
                self._maybe_launch_koboldcpp(profile)
        character = self._active_character() if bool(config.get("enable_character", True)) else None
        worker = VoiceConversationWorker(config, self.profile_by_key, self.backend_settings, character)
        self._voice_worker = worker
        worker.status_changed.connect(self._handle_voice_status)
        worker.transcript_ready.connect(self._handle_voice_transcript)
        worker.response_ready.connect(self._handle_voice_response)
        worker.barge_in_detected.connect(self._handle_voice_barge_in)
        worker.failed.connect(self._handle_voice_failed)
        worker.finished.connect(self._finish_voice_worker)
        worker.start()
        self._voice_last_status = "Listening"
        self._voice_last_transcript = ""
        self._voice_last_response = ""
        self._voice_last_emotion = "neutral"
        self.voice_button.setText("■")
        self.voice_button.setToolTip("Stop voice mode")
        self.header_status.setText("Voice mode listening.")
        self._set_voice_mode_screen(True)
        self._update_voice_mode_view(listening=True)
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Voice mode",
                meta="started",
                body="<p>Voice mode is listening. Speak naturally; replies will be spoken automatically.</p>",
            )
        )

    def _stop_voice_mode(self) -> None:
        worker = self._voice_worker
        if worker is not None:
            worker.stop()
        try:
            self.chat_view.fade_out_current_audio(220)
        except Exception:
            LOGGER.exception("voice mode stop fadeout failed")
        self.voice_button.setText("🎙")
        self.voice_button.setToolTip("Start voice mode")
        self.header_status.setText("Voice mode stopping.")
        self._voice_last_status = "Voice mode stopped"
        self._voice_last_emotion = "neutral"
        self._set_voice_mode_screen(False)

    def _finish_voice_worker(self) -> None:
        self._voice_worker = None
        self.voice_button.setText("🎙")
        self.voice_button.setToolTip("Start voice mode")
        self._set_voice_mode_screen(False)
        self._refresh_backend_hint()

    def _handle_voice_status(self, message: str) -> None:
        clean = str(message).strip() or "Voice mode"
        self._voice_last_status = clean
        self.header_status.setText(clean)
        self._update_voice_mode_view(
            listening=(clean.lower() == "listening"),
            speaking=(clean.lower() == "speaking"),
        )

    def _handle_voice_transcript(self, transcript: str) -> None:
        stt_backend, stt_model = self._voice_stt_backend_model()
        _voice_log("stt", stt_backend, stt_model, transcript.strip())
        self._voice_last_transcript = transcript.strip()
        self._voice_last_emotion = "neutral"
        self._update_voice_mode_view(listening=False, speaking=False)
        safe = html.escape(transcript).replace("\n", "<br>")
        chips: list[SourceChipData] = [SourceChipData("voice")]
        active_character = self._active_character()
        if active_character is not None:
            chips.append(SourceChipData(f"character:{active_character.name}"))
        self.add_card(ChatItemData(role="user", title="You", body=f"<p>{safe}</p>", meta="voice prompt", chips=chips))

    def _handle_voice_response(self, answer: str, audio_path_text: str, llm_label: str, llm_model: str, source: str, emotion: str) -> None:
        _voice_log("llm", llm_label, llm_model, answer.strip())
        self._voice_last_response = answer.strip()
        self._voice_last_emotion = emotion.strip().lower() or "neutral"
        self._voice_last_status = "Speaking"
        self._update_voice_mode_view(speaking=True)
        resolved_audio = Path(audio_path_text).expanduser().resolve()
        waveform = _waveform_from_hanauta_service(resolved_audio, bars=24)
        config = _voice_mode_settings(self.backend_settings)
        active_character = self._active_character() if bool(config.get("enable_character", True)) else None
        title = active_character.name if active_character is not None else "Hanauta AI"
        chips = [SourceChipData("voice"), SourceChipData(llm_label), SourceChipData(source)]
        self.add_card(
            ChatItemData(
                role="assistant",
                title=title,
                meta="voice reply",
                body=f"<p>{html.escape(answer).replace(chr(10), '<br>')}</p>",
                chips=chips,
                audio_path=str(resolved_audio),
                audio_waveform=waveform,
            )
        )
        try:
            self.chat_view.autoplay_audio(resolved_audio)
        except Exception:
            LOGGER.exception("voice mode autoplay failed for %s", resolved_audio)
        body = str(config.get("generic_notification_text", "Notification received")).strip() or "Notification received"
        if not bool(config.get("hide_answer_text", False)):
            body = answer.strip() or body
        icon_path = ""
        if active_character is not None and not bool(config.get("hide_character_photo", False)):
            icon_path = self._active_character_avatar_icon()
        self._notify_if_popup_closed(title, body, icon_path=icon_path)

    def _handle_voice_barge_in(self) -> None:
        self._voice_last_status = "Listening"
        self._update_voice_mode_view(listening=True)
        self.header_status.setText("Listening")
        try:
            self.chat_view.fade_out_current_audio(420)
        except Exception:
            LOGGER.exception("voice barge-in fadeout failed")

    def _handle_voice_failed(self, message: str) -> None:
        self._voice_last_status = f"Voice mode: {message}"
        self._voice_last_emotion = "neutral"
        self._update_voice_mode_view(listening=False, speaking=False)
        self.header_status.setText(f"Voice mode: {message}")
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Voice mode",
                meta="error",
                body=f"<p>{html.escape(message)}</p>",
                chips=[SourceChipData("voice")],
            )
        )

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
        self._sync_web_ui()

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
        self._sync_web_ui()

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
        self._sync_web_ui()

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
        self._sync_web_ui()

    def _clear_pending_state(self) -> None:
        LOGGER.debug("clear_pending_state")
        self._pending_item = None
        self.composer.entry.setEnabled(self.current_profile is not None)
        self._render_chat_history()
        self._sync_web_ui()

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
        waveform = _waveform_from_hanauta_service(resolved_audio, bars=24)
        self.add_card(
            ChatItemData(
                role="assistant",
                title=profile_label,
                meta="tts",
                body="<p><b>Speech generated.</b> Playback was started automatically.</p>",
                chips=[SourceChipData("tts"), SourceChipData(source)],
                audio_path=str(resolved_audio),
                audio_waveform=waveform,
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
        send_desktop_notification(
            "New AI answer",
            summary,
            icon_path=self._active_character_avatar_icon(),
        )

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
        if command == "/voice":
            LOGGER.debug("command /voice")
            self._toggle_voice_mode()
            return
        if command == "/voice settings":
            LOGGER.debug("command /voice settings")
            self._open_voice_mode_settings()
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

    def present(self) -> None:
        if self.isMinimized():
            self.showNormal()
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def toggle_visible(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
            return
        self.present()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class PopupCommandServer(QObject):
    def __init__(self, window: DemoWindow, host: str, port: int) -> None:
        super().__init__(window)
        self.window = window
        self.host = host.strip() or "127.0.0.1"
        self.port = max(1, min(65535, int(port)))
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._buffers: dict[int, bytearray] = {}

    def start(self) -> tuple[bool, str]:
        address = QHostAddress(self.host)
        if address.isNull():
            return False, f"Invalid host: {self.host}"
        if not self._server.listen(address, self.port):
            return False, self._server.errorString()
        return True, f"Listening on {self.host}:{self.port}"

    def stop(self) -> None:
        if self._server.isListening():
            self._server.close()

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket_obj = self._server.nextPendingConnection()
            if socket_obj is None:
                continue
            self._buffers[id(socket_obj)] = bytearray()
            socket_obj.readyRead.connect(lambda s=socket_obj: self._on_ready_read(s))
            socket_obj.disconnected.connect(lambda s=socket_obj: self._on_disconnected(s))

    def _on_disconnected(self, socket_obj: QTcpSocket) -> None:
        self._buffers.pop(id(socket_obj), None)
        socket_obj.deleteLater()

    def _on_ready_read(self, socket_obj: QTcpSocket) -> None:
        sock_id = id(socket_obj)
        bucket = self._buffers.setdefault(sock_id, bytearray())
        data = bytes(socket_obj.readAll())
        if data:
            bucket.extend(data)
        if not bucket:
            return
        if b"\n" not in bucket and len(bucket) < 2048:
            return
        line = bytes(bucket).splitlines()[0].decode("utf-8", errors="ignore").strip().lower()
        response = self._handle_command(line)
        socket_obj.write((response + "\n").encode("utf-8"))
        socket_obj.flush()
        socket_obj.disconnectFromHost()

    def _handle_command(self, command: str) -> str:
        if command == "show":
            self.window.present()
            return "ok shown"
        if command == "hide":
            self.window.hide()
            return "ok hidden"
        if command == "toggle":
            self.window.toggle_visible()
            return "ok toggled"
        if command == "status":
            visible = self.window.isVisible() and not self.window.isMinimized()
            return "open" if visible else "hidden"
        if command == "quit":
            QTimer.singleShot(0, QApplication.instance().quit)
            return "ok quitting"
        return "error unsupported command"


def _send_server_command(command: str, host: str, port: int) -> tuple[bool, str]:
    payload = (command.strip().lower() + "\n").encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=0.8) as sock:
            sock.sendall(payload)
            sock.settimeout(0.8)
            response = sock.recv(2048).decode("utf-8", errors="ignore").strip()
            return True, response or "ok"
    except Exception as exc:
        return False, str(exc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hanauta AI popup")
    parser.add_argument(
        "--server",
        action="store_true",
        help="Enable popup command server (show/hide/toggle/status/quit).",
    )
    parser.add_argument(
        "--host",
        default=str(os.environ.get("HANAUTA_AI_POPUP_HOST", "127.0.0.1")),
        help="Server host for command mode.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(str(os.environ.get("HANAUTA_AI_POPUP_PORT", "59687")) or 59687),
        help="Server port for command mode.",
    )
    parser.add_argument(
        "--command",
        choices=["show", "hide", "toggle", "status", "quit"],
        help="Send command to a running popup server and exit.",
    )
    parser.add_argument(
        "--start-hidden",
        action="store_true",
        help="Start window hidden (mostly useful with --server).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    host = str(args.host or "127.0.0.1").strip() or "127.0.0.1"
    port = max(1, min(65535, int(args.port)))

    if args.command:
        ok, message = _send_server_command(str(args.command), host, port)
        if message:
            print(message)
        return 0 if ok else 1

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
    if args.server:
        command_server = PopupCommandServer(window, host, port)
        ok, detail = command_server.start()
        if ok:
            LOGGER.info("Popup command server started: %s", detail)
        else:
            LOGGER.warning("Popup command server unavailable: %s", detail)
        window._popup_command_server = command_server  # type: ignore[attr-defined]
    if not args.start_hidden:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
