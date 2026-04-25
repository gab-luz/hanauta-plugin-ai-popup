from __future__ import annotations

import html
import re
import wave
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from PyQt6.QtCore import Qt, QTimer, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import ChatItemData, SourceChipData
from .runtime import BACKEND_ICONS_DIR
from .style import (
    ACCENT, ACCENT_SOFT, BORDER_ACCENT, BORDER_SOFT, CARD_BG, CARD_BG_SOFT,
    HOVER_BG, TEXT, TEXT_DIM, TEXT_MID, UI_ICON_ACTIVE, UI_ICON_DIM, THEME,
    mix, rgba, ACCENT_ALT, ASSISTANT_BG, CHAT_SURFACE_BG, CHAT_TEXT, UI_TEXT_STRONG, USER_BG,)
from .fonts import load_ui_font, button_css_weight

import logging
LOGGER = logging.getLogger("hanauta.ai_popup")


def _button_qfont_weight(ui_font: str) -> QFont.Weight:
    return QFont.Weight.Medium if "rubik" in (ui_font or "").strip().lower() else QFont.Weight.DemiBold


def _button_css_weight(ui_font: str) -> int:
    return button_css_weight(ui_font)


class ClickableLineEdit(QLineEdit):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _apply_antialias_font(widget: QWidget) -> None:
    font = widget.font()
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    widget.setFont(font)
    for child in widget.findChildren(QWidget):
        child_font = child.font()
        child_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        child.setFont(child_font)

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

    def set_highlighted(self, enabled: bool) -> None:
        if enabled:
            self.setStyleSheet(
                f"""
                QToolButton {{
                    background: {rgba(ACCENT_SOFT, 0.16)};
                    color: #d9ffe7;
                    border: 1px solid rgba(104, 255, 159, 0.92);
                    border-radius: 15px;
                    box-shadow: 0 0 0 2px rgba(104, 255, 159, 0.20);
                }}
                QToolButton:hover {{
                    background: rgba(104, 255, 159, 0.16);
                    color: #f4fff8;
                    border: 1px solid rgba(104, 255, 159, 1.0);
                }}
                """
            )
            return
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


from .web.popup_html import render_popup_html  # noqa: E402


