#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hanauta AI popup — Material Design 3, built on the Hanauta Nest view.

The presentation comes from ``hanauta_nest/hanauta_nest.py``: a stack of rounded
MD3 cards (header, model, chat, composer), 48dp action tiles and 20dp bubbles.
The behaviour is carried over from the existing modules:

* backend settings and runtime state      -> hanauta_aipopup.http / .backends
* chat transport (OpenAI-compatible SSE)  -> hanauta_aipopup.tts prompts
* history persistence                     -> hanauta_aipopup.storage
* dictation                               -> hanauta_aipopup.voice / .tts
* backend configuration dialog            -> hanauta_aipopup.ui_backend_settings

Nothing here creates a second QApplication: ``main()`` is the only entry point.
"""
from __future__ import annotations

import html
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hanauta_aipopup.characters import _chat_messages_for_prompt, load_character_library
from hanauta_aipopup.fonts import load_ui_font
from hanauta_aipopup.http import load_backend_settings, save_backend_settings
from hanauta_aipopup.models import BackendProfile, ChatItemData, SourceChipData
from hanauta_aipopup.runtime import AI_STATE_DIR
from hanauta_aipopup.storage import secure_append_chat, secure_load_chat_history
from hanauta_aipopup.style import THEME

SETUP_ID = "hanauta:setup"
SCREENSHOT_DIR = Path(AI_STATE_DIR) / "voice-screen"


# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
def _rgb(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if text.startswith("#"):
        return text
    if "(" in text:  # "rgba(208, 188, 255, 1.0)" from the matugen palette
        try:
            inner = text[text.index("(") + 1 : text.rindex(")")]
            parts = [p.strip() for p in inner.split(",")]
            r, g, b = (int(float(p)) for p in parts[:3])
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return fallback
    return fallback


@dataclass(frozen=True)
class Theme:
    background: str = "#141218"
    surface: str = "#211e27"
    raised: str = "#302b3a"
    hover: str = "#40384e"
    primary: str = "#d0bcff"
    on_primary: str = "#381e72"
    text: str = "#f7f4ff"
    muted: str = "#bdb4ca"
    positive: str = "#a6dfc0"
    error: str = "#ffb4ab"


def theme_from_palette() -> Theme:
    """Map the app's Matugen palette onto the MD3 roles Nest uses."""
    primary = _rgb(getattr(THEME, "primary", ""), Theme.primary)
    return Theme(
        background=_rgb(getattr(THEME, "panel_bg", ""), Theme.background),
        surface=_rgb(getattr(THEME, "app_running_bg", ""), Theme.surface),
        raised=_rgb(getattr(THEME, "chip_bg", ""), Theme.raised),
        hover=_rgb(getattr(THEME, "hover_bg", ""), Theme.hover),
        primary=primary,
        on_primary=_rgb(getattr(THEME, "on_primary", ""), Theme.on_primary),
        text=_rgb(getattr(THEME, "text", ""), Theme.text),
        muted=_rgb(getattr(THEME, "text_muted", ""), Theme.muted),
        positive=_rgb(getattr(THEME, "positive", ""), Theme.positive),
        error=_rgb(getattr(THEME, "error", ""), Theme.error),
    )


# --------------------------------------------------------------------------- #
# Icons (painter fallbacks, as in the reference)
# --------------------------------------------------------------------------- #
def icon(name: str, color: str, size: int = 24) -> QIcon:
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * 2 / 24, size * 2 / 24)
    pen = QPen(QColor(color), 1.65)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    if name == "close":
        p.drawLine(6, 6, 18, 18); p.drawLine(18, 6, 6, 18)
    elif name == "history":
        p.drawEllipse(3, 3, 18, 18); p.drawLine(12, 6, 12, 12); p.drawLine(12, 12, 16, 15)
    elif name in ("settings", "tune"):
        for y, x in ((6, 15), (12, 8), (18, 14)):
            p.drawLine(3, y, 21, y)
            p.setBrush(QColor(color))
            p.drawEllipse(x - 2, y - 2, 4, 4)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "model":
        path = QPainterPath()
        for a, b in [((12, 2), (21, 7)), ((21, 7), (21, 17)), ((21, 17), (12, 22)),
                     ((12, 22), (3, 17)), ((3, 17), (3, 7)), ((3, 7), (12, 2)),
                     ((3, 7), (12, 12)), ((21, 7), (12, 12)), ((12, 12), (12, 22))]:
            path.moveTo(*a); path.lineTo(*b)
        p.drawPath(path)
    elif name == "mic":
        p.drawRoundedRect(9, 2, 6, 13, 3, 3)
        p.drawArc(6, 7, 12, 12, 180 * 16, 180 * 16)
        p.drawLine(12, 19, 12, 22); p.drawLine(8, 22, 16, 22)
    elif name == "screen":
        p.drawRoundedRect(2, 3, 20, 14, 2, 2)
        p.drawLine(12, 17, 12, 21); p.drawLine(7, 21, 17, 21)
    elif name == "send":
        path = QPainterPath(); path.moveTo(3, 3); path.lineTo(22, 12)
        path.lineTo(3, 21); path.lineTo(7, 12); path.closeSubpath()
        p.drawPath(path); p.drawLine(7, 12, 17, 12)
    elif name == "attach":
        path = QPainterPath(); path.moveTo(9, 17); path.lineTo(17, 9)
        path.cubicTo(21, 5, 16, 0, 12, 4); path.lineTo(4, 12)
        path.cubicTo(-2, 18, 6, 26, 12, 20); path.lineTo(21, 11)
        p.drawPath(path)
    else:  # leaf mark
        path = QPainterPath(); path.moveTo(12, 22)
        path.cubicTo(12, 12, 2, 8, 2, 14); path.cubicTo(2, 20, 12, 20, 12, 22)
        path.moveTo(12, 22); path.cubicTo(12, 12, 22, 8, 22, 14)
        path.cubicTo(22, 20, 12, 20, 12, 22)
        path.moveTo(12, 17); path.cubicTo(4, 10, 12, 2, 12, 2)
        path.cubicTo(20, 10, 12, 17, 12, 17); p.drawPath(path)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


class Editor(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            if not event.isAutoRepeat():
                self.submitted.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


# --------------------------------------------------------------------------- #
# Backend resolution
# --------------------------------------------------------------------------- #
def _llama_payload(settings: dict, key: str = "lfm3") -> dict:
    return dict(settings.get(key, {}) or {})


def resolve_llm(settings: dict) -> tuple[str, str, str, str]:
    """Return ``(label, host, model, api_key)`` for the configured text backend."""
    voice = dict(settings.get("_voice_mode", {}) or {})
    key = str(voice.get("llm_profile", "")).strip()
    if not key or key == "koboldcpp":
        lfm3 = _llama_payload(settings)
        if lfm3.get("gguf_path"):
            key = "lfm3"
    payload = _llama_payload(settings, key) if key else {}
    if key in {"lfm3", "llamacpp"}:
        host = str(payload.get("host", "127.0.0.1:8082")).strip() or "127.0.0.1:8082"
        model = Path(str(payload.get("gguf_path", ""))).name or "lfm3"
        label = "LFM3-Omni 2B" if key == "lfm3" else "llama.cpp"
    elif key == "koboldcpp":
        payload = _llama_payload(settings, "koboldcpp")
        host = str(payload.get("host", "127.0.0.1:5001")).strip() or "127.0.0.1:5001"
        model = Path(str(payload.get("gguf_path", ""))).name or "koboldcpp"
        label = "KoboldCpp"
    else:
        host, model, label = "", "", ""
    api_key = ""
    if key:
        try:
            from hanauta_aipopup.storage import secure_load_secret

            api_key = secure_load_secret(f"{key}:api_key").strip()
        except Exception:
            api_key = ""
    return label, host, model, api_key


def _base_url(host: str) -> str:
    clean = host.strip().rstrip("/")
    if not clean:
        return ""
    if clean.startswith(("http://", "https://")):
        return clean
    return f"http://{clean}"


def stream_chat(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
    on_delta: callable | None = None,
    timeout: float = 300.0,
) -> str:
    """POST an OpenAI-style chat completion, forwarding SSE deltas."""
    url = f"{_base_url(host)}/v1/chat/completions"
    body = json.dumps(
        {"model": model or "model", "messages": messages, "stream": True, "temperature": 0.7}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Hanauta AI/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers)
    answer = ""
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            data = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
            answer = str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
            if answer and on_delta:
                on_delta(answer)
            return answer
        for raw in response:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except Exception:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {}) or {}
            piece = delta.get("content") or ""
            if piece:
                answer += piece
                if on_delta:
                    on_delta(piece)
    return answer


# --------------------------------------------------------------------------- #
# Workers
# --------------------------------------------------------------------------- #
class ChatWorker(QThread):
    delta = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, host: str, model: str, messages: list[dict[str, str]], api_key: str = "") -> None:
        super().__init__()
        self._host = host
        self._model = model
        self._messages = messages
        self._api_key = api_key
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            answer = stream_chat(
                self._host,
                self._model,
                self._messages,
                self._api_key,
                on_delta=None if self._cancelled else self.delta.emit,
            )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                detail = ""
            self.failed.emit(f"{exc.code} {exc.reason}. {detail}".strip())
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(answer.strip())


class DictationWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config: dict, profiles: dict, settings: dict, seconds: float = 8.0) -> None:
        super().__init__()
        self._config = dict(config)
        self._profiles = profiles
        self._settings = settings
        self._seconds = seconds

    def run(self) -> None:
        try:
            from hanauta_aipopup.tts import transcribe_voice_audio
            from hanauta_aipopup.voice import _record_microphone_wav

            audio = _record_microphone_wav(self._seconds)
            text = transcribe_voice_audio(audio, self._config, self._profiles, self._settings)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        if not text.strip():
            self.failed.emit("No speech detected.")
            return
        self.finished_ok.emit(text.strip())


# --------------------------------------------------------------------------- #
# View (from the Nest reference)
# --------------------------------------------------------------------------- #
class NestView(QFrame):
    send_requested = pyqtSignal(str)
    configure_requested = pyqtSignal()
    history_requested = pyqtSignal()
    attachment_requested = pyqtSignal()
    microphone_requested = pyqtSignal()
    screen_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent=None, theme: Theme | None = None) -> None:
        super().__init__(parent)
        self.theme = theme or Theme()
        self._connected = False
        self._busy = False
        self._messages: dict[str, QLabel] = {}
        self.setObjectName("nest")
        self.setMinimumSize(400, 580)
        self._build()
        self.apply_theme(self.theme)
        self.set_backend_state(False)

    def _panel(self, name: str = "surface") -> QFrame:
        frame = QFrame()
        frame.setObjectName(name)
        return frame

    def _button(self, glyph: str, title: str, signal, primary: bool = False) -> QPushButton:
        button = QPushButton(title if primary else "")
        button.setObjectName("primary" if primary else "iconButton")
        button.setProperty("glyph", glyph)
        button.setProperty("primary", primary)
        button.setAccessibleName(title)
        button.setToolTip(title)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(40 if primary else 48)
        if not primary:
            button.setFixedWidth(48)
        button.clicked.connect(lambda checked=False: signal.emit())
        return button

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 12, 10, 12)
        root.setSpacing(10)

        header = self._panel()
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 10, 10, 10)
        self.brand = QLabel()
        self.brand.setObjectName("brand")
        self.brand.setFixedSize(48, 48)
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.brand)
        labels = QVBoxLayout()
        labels.setSpacing(3)
        title = QLabel("Hanauta AI")
        title.setObjectName("title")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("muted")
        labels.addWidget(title)
        labels.addWidget(self.subtitle)
        h.addLayout(labels, 1)
        for glyph, text, signal in (
            ("history", self.tr("History"), self.history_requested),
            ("settings", self.tr("Settings"), self.configure_requested),
            ("close", self.tr("Close"), self.close_requested),
        ):
            h.addWidget(self._button(glyph, text, signal))
        root.addWidget(header)

        model = self._panel()
        m = QVBoxLayout(model)
        m.setContentsMargins(10, 10, 10, 10)
        m.setSpacing(8)
        row = QHBoxLayout()
        self.model_icon = QLabel()
        self.model_icon.setObjectName("tile")
        self.model_icon.setFixedSize(48, 48)
        self.model_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.model_icon)
        ml = QVBoxLayout()
        ml.setSpacing(3)
        ml.addWidget(QLabel(self.tr("AI model")))
        self.model_label = QLabel()
        self.model_label.setObjectName("muted")
        ml.addWidget(self.model_label)
        row.addLayout(ml, 1)
        self.status = QPushButton()
        self.status.setObjectName("status")
        self.status.setMinimumHeight(48)
        self.status.clicked.connect(lambda: self.configure_requested.emit())
        row.addWidget(self.status)
        m.addLayout(row)
        self.configure = self._button("tune", self.tr("Configure model"), self.configure_requested, True)
        m.addWidget(self.configure)
        root.addWidget(model)

        chat = self._panel()
        cl = QVBoxLayout(chat)
        cl.setContentsMargins(10, 12, 10, 12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript = QWidget()
        self.transcript.setObjectName("transcript")
        self.messages_layout = QVBoxLayout(self.transcript)
        self.messages_layout.setContentsMargins(0, 0, 0, 0)
        self.messages_layout.setSpacing(14)
        self.messages_layout.addStretch(1)
        self.scroll.setWidget(self.transcript)
        cl.addWidget(self.scroll)
        root.addWidget(chat, 1)

        composer = self._panel()
        c = QHBoxLayout(composer)
        c.setContentsMargins(10, 10, 10, 10)
        c.setSpacing(6)
        input_panel = self._panel("input")
        il = QHBoxLayout(input_panel)
        il.setContentsMargins(2, 2, 6, 2)
        il.addWidget(self._button("attach", self.tr("Attach file"), self.attachment_requested))
        self.editor = Editor()
        self.editor.setAcceptRichText(False)
        self.editor.setPlaceholderText(self.tr("Message the model…  Enter sends, Shift+Enter adds a line"))
        self.editor.setAccessibleName(self.tr("Message"))
        self.editor.setFixedHeight(46)
        self.editor.setTabChangesFocus(True)
        self.editor.textChanged.connect(self._sync_send)
        self.editor.submitted.connect(self._submit)
        il.addWidget(self.editor, 1)
        c.addWidget(input_panel, 1)
        c.addWidget(self._button("mic", self.tr("Dictate"), self.microphone_requested))
        c.addWidget(self._button("screen", self.tr("Screen context"), self.screen_requested))
        self.send_button = self._button("send", self.tr("Send message"), self.editor.submitted)
        c.addWidget(self.send_button)
        root.addWidget(composer)

    def apply_theme(self, theme: Theme) -> None:
        self.theme = theme
        t = theme
        # load_ui_font() returns a family name (str), not a QFont.
        family = str(load_ui_font() or "Noto Sans")
        self.setStyleSheet(f"""
        QFrame#nest {{ background:{t.background}; border-radius:30px; }}
        QFrame#nest QWidget {{ color:{t.text}; font-family:"{family}","Noto Sans",sans-serif; font-size:13px; }}
        QFrame#surface {{ background:{t.surface}; border-radius:24px; }}
        QLabel {{ background:transparent; }}
        QFrame#nest QLabel#title {{ font-size:17px; font-weight:600; }}
        QFrame#nest QLabel#muted {{ color:{t.muted}; font-size:11px; }}
        QLabel#brand {{ background:{t.primary}; border-radius:24px; }}
        QLabel#tile {{ background:{t.raised}; border-radius:18px; }}
        QPushButton {{ border:0; padding:6px; border-radius:17px; background:{t.raised}; }}
        QPushButton:hover {{ background:{t.hover}; }}
        QPushButton:focus {{ border:2px solid {t.primary}; }}
        QFrame#nest QPushButton#primary {{ background:{t.primary}; color:{t.on_primary}; font-weight:600; border-radius:20px; }}
        QPushButton:disabled {{ color:{t.muted}; background:{t.raised}; }}
        QFrame#input {{ background:{t.raised}; border-radius:20px; }}
        QTextEdit {{ background:transparent; border:0; padding-top:7px; selection-background-color:{t.primary}; selection-color:{t.on_primary}; }}
        QScrollArea, QScrollArea>QWidget>QWidget, QWidget#transcript {{ background:transparent; border:0; }}
        QScrollBar:vertical {{ background:transparent; width:5px; margin:0; }}
        QScrollBar::handle:vertical {{ background:{t.hover}; border-radius:2px; min-height:24px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        """)
        for button in self.findChildren(QPushButton):
            if button.property("glyph"):
                button.setIcon(
                    icon(
                        button.property("glyph"),
                        t.on_primary if button.property("primary") else t.primary,
                    )
                )
                button.setIconSize(QSize(22, 22))
        self.brand.setPixmap(icon("leaf", t.on_primary).pixmap(30, 30))
        self.model_icon.setPixmap(icon("model", t.primary).pixmap(26, 26))
        for bubble in self.findChildren(QFrame, "bubble"):
            self._style_bubble(bubble, bool(bubble.property("user")))

    def _style_bubble(self, bubble: QFrame, user: bool) -> None:
        t = self.theme
        bubble.setStyleSheet(
            f"QFrame#bubble {{background:{t.primary if user else t.raised}; border-radius:20px;}} "
            f"QFrame#bubble QLabel {{color:{t.on_primary if user else t.text};background:transparent;}}"
        )

    def set_backend_state(self, connected: bool, model_name: str = "") -> None:
        self._connected = bool(connected)
        if connected:
            self.subtitle.setText(model_name or self.tr("Model connected"))
        else:
            self.subtitle.setText(self.tr("Model not configured"))
        self.model_label.setText(model_name or (self.tr("Connected") if connected else self.tr("Not configured")))
        self.status.setText(self.tr("● Connected  ›") if connected else self.tr("● Disconnected  ›"))
        self.status.setAccessibleName(self.status.text())
        self.configure.setVisible(not connected)
        if hasattr(self, "setup_card"):
            self.setup_card.setVisible(not connected)
        self._sync_send()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_send()

    def _sync_send(self) -> None:
        enabled = self._connected and not self._busy and bool(self.editor.toPlainText().strip())
        self.send_button.setEnabled(enabled)
        self.send_button.setIcon(icon("send", self.theme.primary if enabled else "#69616f"))

    def _submit(self) -> None:
        if self.send_button.isEnabled():
            self.send_requested.emit(self.editor.toPlainText().strip())

    def clear_draft(self) -> None:
        self.editor.clear()

    def add_message(self, message_id: str, role: str, text: str, timestamp: str = "") -> QFrame:
        if role not in ("user", "assistant", "system"):
            raise ValueError("role must be user, assistant or system")
        if message_id in self._messages:
            raise ValueError("duplicate message_id")
        user = role == "user"
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setProperty("user", user)
        bubble.setMaximumWidth(310)
        b = QVBoxLayout(bubble)
        b.setContentsMargins(14, 12, 14, 12)
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        b.addWidget(label)
        self._messages[message_id] = label
        if timestamp:
            meta = QLabel(timestamp)
            meta.setAlignment(Qt.AlignmentFlag.AlignRight)
            meta.setStyleSheet("font-size:10px;")
            b.addWidget(meta)
        if user:
            h.addStretch(1)
        h.addWidget(bubble)
        if not user:
            h.addStretch(1)
        self._style_bubble(bubble, user)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        self._scroll_bottom()
        return bubble

    def update_message(self, message_id: str, text: str) -> None:
        bar = self.scroll.verticalScrollBar()
        near_bottom = bar.maximum() - bar.value() < 40
        self._messages[message_id].setText(text)
        if near_bottom:
            self._scroll_bottom()

    def show_setup_card(self) -> None:
        if hasattr(self, "setup_card"):
            return
        self.setup_card = self.add_message(SETUP_ID, "system", self.tr("Configure a model\nto get started."))
        self.setup_card.setMinimumWidth(270)
        self.setup_card.layout().addWidget(
            self._button("tune", self.tr("Configure model"), self.configure_requested, True)
        )
        self.setup_card.setVisible(not self._connected)

    def clear_messages(self) -> None:
        self._messages.clear()
        if hasattr(self, "setup_card"):
            del self.setup_card
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_bottom(self) -> None:
        QTimer.singleShot(
            0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        )


# --------------------------------------------------------------------------- #
# History dialog
# --------------------------------------------------------------------------- #
class HistoryDialog(QDialog):
    def __init__(self, items: list[ChatItemData], theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chat history")
        self.setMinimumSize(420, 460)
        self.selected_item: ChatItemData | None = None
        self.setStyleSheet(
            f"QDialog{{background:{theme.background};}} QLabel{{color:{theme.text};}}"
            f"QListWidget{{background:{theme.surface}; border:0; border-radius:16px; padding:6px; color:{theme.text};}}"
            f"QListWidget::item{{padding:10px; border-radius:10px;}}"
            f"QListWidget::item:selected{{background:{theme.primary}; color:{theme.on_primary};}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Restore a conversation")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(title)
        self.list = QListWidget()
        for index, item in enumerate(items):
            text = f"{item.role}: {item.body[:90]}"
            row = QListWidgetItem(text)
            row.setData(Qt.ItemDataRole.UserRole, index)
            self.list.addItem(row)
        self.items = items
        self.list.itemActivated.connect(lambda _i: self._accept())
        self.list.itemDoubleClicked.connect(lambda _i: self._accept())
        layout.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._accept)
        buttons.addWidget(open_button)
        layout.addLayout(buttons)

    def _accept(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.selected_item = self.items[row]
            self.accept()


# --------------------------------------------------------------------------- #
# Window: real wiring
# --------------------------------------------------------------------------- #
class PopupWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Hanauta AI")
        self.setStyleSheet("background: transparent;")
        self.resize(440, 650)

        self.settings = load_backend_settings()
        self.theme = theme_from_palette()
        self.view = NestView(theme=self.theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self._attachments: list[Path] = []
        self._worker: ChatWorker | None = None
        self._dictation: DictationWorker | None = None
        self._pending_id = ""
        self._pending_text = ""
        self._last_flush = 0.0
        self._history: list[ChatItemData] = []

        self.view.send_requested.connect(self.accept_message)
        self.view.configure_requested.connect(self.open_settings)
        self.view.history_requested.connect(self.open_history)
        self.view.attachment_requested.connect(self.attach_file)
        self.view.microphone_requested.connect(self.dictate)
        self.view.screen_requested.connect(self.attach_screen)
        self.view.close_requested.connect(self.hide)

        self.refresh_backend()
        self.restore_history()

    # -- backend ---------------------------------------------------------- #
    def refresh_backend(self) -> None:
        self.settings = load_backend_settings()
        label, host, model, _key = resolve_llm(self.settings)
        alive = False
        if host:
            try:
                with urllib.request.urlopen(f"{_base_url(host)}/v1/models", timeout=2.5):
                    alive = True
            except Exception:
                alive = False
        pretty = f"{label} · {model}" if label and model else (label or "")
        self.view.set_backend_state(alive, pretty)
        if not alive:
            self.view.show_setup_card()

    def open_settings(self) -> None:
        from hanauta_aipopup.ui_backend_settings import BackendSettingsDialog

        profiles = [
            BackendProfile("lfm3", "LFM3-Omni 2B", "openai_compat", "lfm3-omni-2b", "127.0.0.1:8082", "koboldcpp", False, True),
            BackendProfile("llamacpp", "llama.cpp", "openai_compat", "llama", "127.0.0.1:8080", "koboldcpp", False, True),
            BackendProfile("koboldcpp", "KoboldCpp", "openai_compat", "kobold", "127.0.0.1:5001", "koboldcpp", False, True),
        ]
        dialog = BackendSettingsDialog(profiles, self.settings, str(load_ui_font() or "Noto Sans"), self)
        dialog.exec()
        self.refresh_backend()

    # -- conversation ----------------------------------------------------- #
    def restore_history(self) -> None:
        try:
            items = secure_load_chat_history()
        except Exception:
            return
        for index, item in enumerate(items[-40:]):
            try:
                self.view.add_message(f"h{index}", item.role, item.body, item.meta)
            except ValueError:
                continue

    def open_history(self) -> None:
        try:
            items = secure_load_chat_history()
        except Exception:
            items = []
        if not items:
            self.view.add_message(f"sys{int(time.time())}", "system", "No archived messages yet.")
            return
        dialog = HistoryDialog(items, self.theme, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_item is not None:
            self.view.clear_messages()
            self.view.add_message(
                f"r{int(time.time())}",
                dialog.selected_item.role,
                dialog.selected_item.body,
                dialog.selected_item.meta,
            )

    def attach_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Attach file")
        if not path:
            return
        self._attachments.append(Path(path))
        names = ", ".join(p.name for p in self._attachments)
        self.view.editor.setPlaceholderText(f"Attached: {names}")

    def attach_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        target = SCREENSHOT_DIR / f"screen_{int(time.time() * 1000)}.png"
        if not screen.grabWindow(0).save(str(target), "PNG"):
            self.view.add_message(f"sys{int(time.time())}", "system", "Screen capture failed.")
            return
        self._attachments.append(target)
        self.view.add_message(
            f"sys{int(time.time())}", "system", f"Screen context attached: {target.name}"
        )

    def dictate(self) -> None:
        from hanauta_aipopup.tts import _voice_mode_settings
        from hanauta_aipopup.voice import _voice_mode_defaults

        if self._dictation is not None and self._dictation.isRunning():
            return
        config = _voice_mode_settings(self.settings) if self.settings else _voice_mode_defaults()
        profiles = {"lfm3": self.profile_for("lfm3")}
        self.view.add_message(f"sys{int(time.time())}", "system", "Listening for dictation…")
        worker = DictationWorker(config, profiles, self.settings)
        self._dictation = worker
        worker.finished_ok.connect(self._dictation_done)
        worker.failed.connect(self._dictation_failed)
        worker.start()

    def profile_for(self, key: str) -> BackendProfile:
        payload = dict(self.settings.get(key, {}) or {})
        return BackendProfile(
            key,
            "LFM3-Omni 2B",
            "openai_compat",
            Path(str(payload.get("gguf_path", "lfm3"))).name,
            str(payload.get("host", "127.0.0.1:8082")),
            "koboldcpp",
            False,
            True,
        )

    def _dictation_done(self, text: str) -> None:
        self._dictation = None
        self.view.editor.setPlainText(text)
        self.view.editor.setFocus()

    def _dictation_failed(self, message: str) -> None:
        self._dictation = None
        self.view.add_message(f"sys{int(time.time() * 1000)}", "system", f"STT failed: {message}")

    def accept_message(self, text: str) -> None:
        prompt = text.strip()
        if not prompt:
            return
        label, host, model, api_key = resolve_llm(self.settings)
        if not host:
            self.view.set_backend_state(False)
            return
        if self._worker is not None and self._worker.isRunning():
            return

        attached = ""
        if self._attachments:
            attached = "\n\nAttached files:\n" + "\n".join(str(p) for p in self._attachments)
            prompt += attached

        user_id = f"u{int(time.time() * 1000)}"
        self.view.add_message(user_id, "user", text.strip(), datetime.now().strftime("%H:%M"))
        self.view.clear_draft()
        self.view.set_busy(True)
        self._attachments.clear()
        self.view.editor.setPlaceholderText("Message the model…  Enter sends, Shift+Enter adds a line")

        self._history.append(ChatItemData(role="user", title="You", body=text.strip()))
        self._persist(user_id, "user", text.strip())

        character = None
        try:
            library = load_character_library()
            if library:
                character = library[0]
        except Exception:
            character = None
        messages = _chat_messages_for_prompt(prompt, character, False)
        history = [
            {"role": item.role if item.role != "system" else "system", "content": item.body}
            for item in self._history[-12:]
            if item.body.strip()
        ]
        messages = [messages[0]] + history

        assistant_id = f"a{int(time.time() * 1000)}"
        self.view.add_message(assistant_id, "assistant", "…")
        self._pending_id = assistant_id
        self._pending_text = ""
        self._last_flush = 0.0

        worker = ChatWorker(host, model, messages, api_key)
        self._worker = worker
        worker.delta.connect(self._on_delta)
        worker.finished_ok.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.start()

    def _on_delta(self, piece: str) -> None:
        self._pending_text += piece
        now = time.monotonic()
        if now - self._last_flush >= 0.05:  # coalesce to ~20 fps
            self._last_flush = now
            self.view.update_message(self._pending_id, self._pending_text)

    def _on_done(self, answer: str) -> None:
        final = answer or self._pending_text
        self.view.update_message(self._pending_id, final or "(empty reply)")
        self.view.set_busy(False)
        self._worker = None
        self._history.append(ChatItemData(role="assistant", title="Hanauta AI", body=final))
        self._persist(self._pending_id, "assistant", final)

    def _on_failed(self, message: str) -> None:
        self.view.update_message(self._pending_id, f"The backend did not answer.\n{message}")
        self.view.set_busy(False)
        self._worker = None
        self.view.set_backend_state(False)

    def _persist(self, message_id: str, role: str, body: str) -> None:
        if not body.strip():
            return
        try:
            item = ChatItemData(role=role, title="You" if role == "user" else "Hanauta AI", body=body)
            item.id = message_id
            secure_append_chat(item)
        except Exception:
            pass


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Hanauta AI")
    window = PopupWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
