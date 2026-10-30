"""On-screen capture indicator for voice mode.

While the camera or the screen is shared with the model, the user needs to know
it is happening. This module provides:

* :class:`CaptureOverlay` — a small, click-through, always-on-top pill row with
  one badge per active source (camera, screen).
* A short chime when a source *starts* capturing, so it is noticed even when the
  popup is behind a game.

Sounds are generated on first use (no binary assets in the repo) and played with
QtMultimedia, which the app already loads.
"""
from __future__ import annotations

import math
import struct
import time
import wave
from pathlib import Path

from PyQt6.QtCore import QObject, QRectF, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .runtime import AI_STATE_DIR

SOUND_DIR = AI_STATE_DIR / "voice-sounds"

# kind -> (frequencies in Hz, duration in seconds)
CAPTURE_SOUNDS: dict[str, tuple[tuple[int, ...], float]] = {
    # Rising two-tone: "recording has started".
    "camera": ((660, 990), 0.14),
    # Single soft tone, deliberately different from the camera chime.
    "screen": ((520,), 0.16),
}

_LABELS = {"camera": "Camera", "screen": "Screen"}


def capture_sound_path(kind: str) -> Path:
    """Return the WAV path for a capture chime, generating it if missing."""
    freqs, duration = CAPTURE_SOUNDS[kind]
    path = SOUND_DIR / f"capture-{kind}.wav"
    if path.exists() and path.stat().st_size > 44:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    total = max(1, int(rate * duration))
    frames = bytearray()
    for index in range(total):
        moment = index / rate
        # Split the duration evenly across the tones.
        step = min(len(freqs) - 1, int(index / total * len(freqs)))
        envelope = math.sin(math.pi * (index / max(1, total - 1)))
        sample = int(11000 * envelope * math.sin(2 * math.pi * freqs[step] * moment))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


class _CaptureSounds(QObject):
    """Plays the per-source chime, tolerating a missing audio backend."""

    def __init__(self) -> None:
        super().__init__()
        self._effects: dict[str, object] = {}
        try:
            from PyQt6.QtMultimedia import QSoundEffect
        except Exception:
            return
        for kind in CAPTURE_SOUNDS:
            try:
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(capture_sound_path(kind))))
                effect.setVolume(0.35)
                self._effects[kind] = effect
            except Exception:
                continue

    def play(self, kind: str) -> None:
        effect = self._effects.get(kind)
        if effect is None:
            return
        try:
            effect.play()  # type: ignore[attr-defined]
        except Exception:
            pass


class CaptureOverlay(QWidget):
    """Click-through badge row showing which sources are capturing."""

    trigger = pyqtSignal(str)

    _BADGE = 30
    _GAP = 8
    _PAD = 8
    _CAPTION_SECONDS = 4.0

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Hanauta capture indicator")
        self._active: list[str] = []
        self._caption = ""
        self._caption_until = 0.0
        self._sounds = _CaptureSounds()
        self.trigger.connect(self._on_capture)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._refresh_visibility)

    def set_active(self, kinds: list[str]) -> None:
        """Declare which sources are enabled; the badge stays while enabled."""
        ordered = [kind for kind in CAPTURE_SOUNDS if kind in kinds]
        if ordered == self._active:
            self._refresh_visibility()
            return
        self._active = ordered
        self._relayout()
        self._refresh_visibility()
        self.update()

    def active_sources(self) -> list[str]:
        return list(self._active)

    def _on_capture(self, kind: str) -> None:
        """Called (via signal) the first time a source actually grabs a frame."""
        if kind not in CAPTURE_SOUNDS:
            return
        self._sounds.play(kind)
        self._caption = f"{_LABELS[kind]} capture started"
        self._caption_until = time.time() + self._CAPTION_SECONDS
        if kind not in self._active:
            self._active.append(kind)
            self._relayout()
        self._hide_timer.start(int(self._CAPTION_SECONDS * 1000) + 200)
        self.show()
        self.update()

    def _relayout(self) -> None:
        count = max(1, len(self._active))
        width = self._PAD * 2 + count * (self._BADGE + 8) + 120
        self.resize(width, self._BADGE + self._PAD * 2)
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - width - 24, area.bottom() - self.height() - 72)

    def _refresh_visibility(self) -> None:
        if self._active or time.time() < self._caption_until:
            self.show()
        else:
            self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = (self._BADGE + self._PAD * 2) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 12, 26, 205))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)

        x = float(self._PAD)
        top = float(self._PAD)
        for kind in self._active:
            badge = QRectF(x, top, self._BADGE, self._BADGE)
            painter.setBrush(QColor(255, 255, 255, 26))
            painter.drawEllipse(badge)
            painter.setPen(QPen(QColor(235, 230, 250), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "camera":
                body = QRectF(badge.left() + 6, badge.top() + 9, badge.width() - 12, badge.height() - 17)
                painter.drawRoundedRect(body, 3, 3)
                painter.drawEllipse(QRectF(body.center().x() - 3.4, body.center().y() - 3.4, 6.8, 6.8))
            else:
                body = QRectF(badge.left() + 6, badge.top() + 7, badge.width() - 12, badge.height() - 15)
                painter.drawRoundedRect(body, 2.5, 2.5)
                painter.drawLine(
                    int(body.center().x()), int(body.bottom()),
                    int(body.center().x()), int(badge.bottom() - 4),
                )
            x += self._BADGE + 8

        caption = self._caption if time.time() < self._caption_until else ""
        if caption:
            painter.setPen(QColor(225, 220, 240))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                QRectF(x + 4, 0, self.width() - x - self._PAD, self.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                caption,
            )
        painter.end()


__all__ = ["CAPTURE_SOUNDS", "CaptureOverlay", "SOUND_DIR", "capture_sound_path"]
