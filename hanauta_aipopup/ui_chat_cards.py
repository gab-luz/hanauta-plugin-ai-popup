from __future__ import annotations

import html
import logging
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtProperty
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import ChatItemData, SourceChipData
from .html_sanitize import sanitize_message_html
from .style import (
    ACCENT, ACCENT_SOFT, BORDER_SOFT, CARD_BG, CARD_BG_SOFT,
    HOVER_BG, TEXT, TEXT_DIM, TEXT_MID, THEME,
    mix, rgba, ACCENT_ALT, ASSISTANT_BG, BORDER_ACCENT, BOTTOM_BG, CHAT_TEXT, INPUT_BG, USER_BG,)
from .ui_widgets import (
    FadeCard, SurfaceFrame, AvatarBadge, ActionIcon, ChatInputEdit, AntiAliasButton,
    _audio_chip_href, _audio_duration_label, _audio_wave_inline_html,
    _button_qfont_weight, _button_css_weight,
)
from .ui_chat import ChatWebView

LOGGER = logging.getLogger("hanauta.ai_popup")

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
        browser.setHtml(sanitize_message_html(item.body, allow_html=True))
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

