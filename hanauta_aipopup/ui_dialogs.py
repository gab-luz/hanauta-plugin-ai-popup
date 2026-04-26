from __future__ import annotations

import html
import json
import logging
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QIcon, QColor, QBrush, QLinearGradient, QCursor, QFont, QGuiApplication, QPixmap, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QAbstractItemView,
    QPlainTextEdit,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import BackendProfile, CharacterCard, ChatItemData, SourceChipData
from .runtime import (
    AI_STATE_DIR,
    CHARACTER_AVATARS_DIR,
    POCKETTTS_LANGUAGES,
    POCKETTTS_PRESET_VOICES,
)
from .style import (
    ACCENT, ACCENT_SOFT, BORDER_ACCENT, BORDER_SOFT, CARD_BG, CARD_BG_SOFT,
    HOVER_BG, INPUT_BG, PANEL_BG, TEXT, TEXT_DIM, TEXT_MID, THEME,
    mix, rgba, ACCENT_ALT, PANEL_BG_FLOAT, UI_TEXT_STRONG,)
from .storage import secure_load_secret, secure_store_secret
from .http import send_desktop_notification
from .characters import (
    load_character_library as _load_character_library,
    save_character_library as _save_character_library,
    import_character_from_file,
)
from .ui_widgets import SurfaceFrame, _apply_antialias_font, _button_css_weight, _button_qfont_weight
from .tts import (
    _default_tts_model_dir, _list_pocket_voice_references,
    _ensure_pocket_preset_voice, _default_pocket_language,
    _waveform_from_hanauta_service,
)

LOGGER = logging.getLogger("hanauta.ai_popup")

class CharacterLibraryDialog(QDialog):
    def __init__(self, cards: list[CharacterCard], active_id: str, ui_font: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui_font = ui_font
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
            QPlainTextEdit {{
                background: {INPUT_BG};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QListWidget {{
                background: {rgba(PANEL_BG, 0.92)};
                color: {TEXT};
                border: 1px solid {rgba(BORDER_SOFT, 0.95)};
                border-radius: 16px;
                padding: 10px;
            }}
            QListWidget::item {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 8px 6px 10px 6px;
            }}
            QListWidget::item:selected {{
                background: {rgba(ACCENT_SOFT, 0.60)};
                border: 1px solid {rgba(BORDER_ACCENT, 0.92)};
                color: {UI_TEXT_STRONG};
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

        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(88, 88))
        self.grid.setGridSize(QSize(118, 128))
        self.grid.setSpacing(10)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setFont(QFont(ui_font, 10, QFont.Weight.DemiBold))
        self.grid.itemSelectionChanged.connect(self._refresh_preview)
        self.grid.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        layout.addWidget(self.grid)

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

        voice_sample_button = QPushButton("\U0001f3a4 Set voice sample")
        voice_sample_button.setToolTip(
            "Set a WAV/MP3 voice sample for this character.\n"
            "Used by KokoClone to clone the character's voice."
        )
        voice_sample_button.clicked.connect(self._set_voice_sample)
        row.addWidget(voice_sample_button)

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

        self._reload_grid()

    def _character_icon(self, card: CharacterCard | None) -> QIcon:
        size = 88
        avatar_path = ""
        if card is not None:
            avatar_path = str(card.avatar_path or "").strip()
        if avatar_path:
            path = Path(avatar_path).expanduser()
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    pix = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    return QIcon(pix)
        # Fallback: gradient badge with initials.
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, size, size)
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor(ACCENT))
        grad.setColorAt(1.0, QColor(ACCENT_ALT))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(QColor(BORDER_ACCENT), 2))
        painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -1.5), 22, 22)
        text = "AI"
        if card is not None and str(card.name or "").strip():
            parts = [p for p in str(card.name).strip().split(" ") if p]
            initials = "".join(p[0] for p in parts[:2]).upper()
            text = initials or "AI"
        painter.setPen(QColor(UI_TEXT_STRONG))
        font = QFont(self.ui_font, 20, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), text)
        painter.end()
        return QIcon(pix)

    def _reload_grid(self) -> None:
        self.grid.blockSignals(True)
        self.grid.clear()
        none_item = QListWidgetItem("None")
        none_item.setData(Qt.ItemDataRole.UserRole, "")
        none_item.setIcon(self._character_icon(None))
        none_item.setTextAlignment(int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop))
        self.grid.addItem(none_item)

        selected_row = 0
        for idx, card in enumerate(self.cards, start=1):
            item = QListWidgetItem(card.name)
            item.setData(Qt.ItemDataRole.UserRole, card.id)
            item.setIcon(self._character_icon(card))
            item.setTextAlignment(int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop))
            self.grid.addItem(item)
            if self.selected_id and card.id == self.selected_id:
                selected_row = idx
        self.grid.setCurrentRow(selected_row)
        self.grid.blockSignals(False)
        self._refresh_preview()

    def _current_card(self) -> CharacterCard | None:
        items = self.grid.selectedItems() if hasattr(self, "grid") else []
        current_id = str(items[0].data(Qt.ItemDataRole.UserRole) or "").strip() if items else ""
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

    def _select_character_files(self) -> list[str]:
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Import character cards")
        dialog.setDirectory(str(Path.home()))
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilters(
            [
                "Character Cards (*.json *.png)",
                "JSON (*.json)",
                "PNG (*.png)",
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
            return []
        return list(dialog.selectedFiles())

    def _import_cards(self) -> None:
        paths = self._select_character_files()
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
        self._reload_grid()
        if imported_names:
            send_desktop_notification("Character import", f"Imported: {', '.join(imported_names[:4])}")

    def _remove_selected(self) -> None:
        card = self._current_card()
        if card is None:
            return
        self.cards = [row for row in self.cards if row.id != card.id]
        if self.selected_id == card.id:
            self.selected_id = ""
        self._reload_grid()

    def _set_voice_sample(self) -> None:
        card = self._current_card()
        if card is None:
            send_desktop_notification("Voice sample", "Select a character first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Voice sample for {card.name}",
            str(Path.home()),
            "Audio files (*.wav *.mp3 *.ogg *.flac *.m4a *.aac)",
        )
        if not path:
            return
        card.voice_sample_path = str(Path(path).expanduser())
        from .characters import save_character_library
        save_character_library(self.cards, self.selected_id)
        send_desktop_notification(
            "Voice sample set",
            f"{card.name}: {Path(path).name}",
        )

    def _disable_character(self) -> None:
        self.selected_id = ""
        self.accept()

    def _accept_selected(self) -> None:
        card = self._current_card()
        self.selected_id = card.id if card is not None else ""
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
        self.setAutoFillBackground(True)

        def _qcolor(value: str, fallback: str) -> QColor:
            raw = str(value or "").strip()
            q = QColor(raw)
            if (not q.isValid()) and raw.startswith("#") and len(raw) == 9:
                q = QColor("#" + raw[-6:])
            if not q.isValid():
                q = QColor(str(fallback or "#121218"))
            return q

        try:
            fusion = QStyleFactory.create("Fusion")
        except Exception:
            fusion = None
        if fusion is not None:
            self.setStyle(fusion)
        palette = self.palette()
        palette.setColor(palette.ColorRole.Window, _qcolor(THEME.surface_container, "#121218"))
        palette.setColor(palette.ColorRole.Base, _qcolor(THEME.surface_container_high, "#1b1b24"))
        palette.setColor(palette.ColorRole.AlternateBase, _qcolor(THEME.surface_container, "#161620"))
        palette.setColor(palette.ColorRole.Text, _qcolor(THEME.on_surface, "#ffffff"))
        palette.setColor(palette.ColorRole.WindowText, _qcolor(THEME.on_surface, "#ffffff"))
        palette.setColor(palette.ColorRole.Button, _qcolor(THEME.surface_container_high, "#1b1b24"))
        palette.setColor(palette.ColorRole.ButtonText, _qcolor(THEME.on_surface, "#ffffff"))
        palette.setColor(palette.ColorRole.Highlight, _qcolor(THEME.primary, "#7d5cff"))
        palette.setColor(palette.ColorRole.HighlightedText, _qcolor(THEME.on_primary, "#101114"))
        self.setPalette(palette)

        bg = THEME.surface_container
        bg_raised = THEME.surface_container_high
        border = THEME.outline
        text = THEME.on_surface
        text_dim = THEME.on_surface_variant
        accent = THEME.primary
        accent_soft = f"rgba({_qcolor(accent, '#7d5cff').red()}, {_qcolor(accent, '#7d5cff').green()}, {_qcolor(accent, '#7d5cff').blue()}, 0.18)"
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {bg};
                color: {text};
            }}
            QWidget {{
                background: transparent;
                color: {text};
            }}
            QLabel, QCheckBox {{
                color: {text};
            }}
            QLineEdit, QComboBox {{
                background: {bg_raised};
                color: {text};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QPlainTextEdit {{
                background: {bg_raised};
                color: {text};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QComboBox QAbstractItemView {{
                background: {bg};
                color: {text};
                border: 1px solid {border};
                selection-background-color: {accent_soft};
                selection-color: {text};
                outline: none;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea QWidget#qt_scrollarea_viewport {{
                background: transparent;
            }}
            QWidget#fieldWrap {{
                background: {bg_raised};
                border: 1px solid {border};
                border-radius: 16px;
                padding: 10px 12px;
            }}
            QLabel#fieldLabel {{
                color: {text_dim};
                font-weight: 750;
            }}
            QLabel#sectionLabel {{
                color: {accent};
                font-weight: 800;
                margin-top: 12px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 6px;
                border: 1px solid {border};
                background: {bg_raised};
            }}
            QCheckBox::indicator:checked {{
                background: {accent};
                border: 1px solid {accent};
            }}
            QPushButton {{
                background: {bg_raised};
                color: {text};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 8px 12px;
                font-weight: {_button_css_weight(ui_font)};
            }}
            QPushButton:hover {{
                background: {accent_soft};
                border: 1px solid {accent};
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

        self.eos_adaptive_check = QCheckBox("Adaptive end-of-speech (recommended)")
        self.eos_adaptive_check.setToolTip("Estimates mic noise floor so short breaths and quiet syllables are less likely to be cut off.")
        self.eos_adaptive_check.setChecked(bool(self.config.get("eos_adaptive_enabled", True)))
        form.addWidget(self.eos_adaptive_check)
        self.eos_noise_margin_input = QLineEdit(str(self.config.get("eos_noise_margin", "0.004")))
        self.eos_noise_margin_input.setPlaceholderText("e.g. 0.004")
        form.addWidget(self._labeled("Adaptive noise margin", self.eos_noise_margin_input))
        self.eos_hysteresis_input = QLineEdit(str(self.config.get("eos_hysteresis", "0.82")))
        self.eos_hysteresis_input.setPlaceholderText("0.50 to 0.98 (lower = more forgiving)")
        form.addWidget(self._labeled("Silence hysteresis ratio", self.eos_hysteresis_input))

        self.speech_end_silence_input = QLineEdit(str(self.config.get("speech_end_silence_ms", "750")))
        self.speech_end_silence_input.setPlaceholderText("e.g. 750 (0 disables)")
        form.addWidget(self._labeled("Stop after silence (ms)", self.speech_end_silence_input))
        self.listen_chunk_input = QLineEdit(str(self.config.get("listen_chunk_seconds", "0.75")))
        self.listen_chunk_input.setPlaceholderText("e.g. 0.75")
        form.addWidget(self._labeled("Listen chunk (seconds)", self.listen_chunk_input))
        self.min_speech_input = QLineEdit(str(self.config.get("min_speech_ms", "260")))
        self.min_speech_input.setPlaceholderText("e.g. 260")
        form.addWidget(self._labeled("Minimum speech (ms)", self.min_speech_input))

        form.addWidget(self._section_label("Speech to text"))
        self.stt_external_check = QCheckBox("Use external STT API")
        self.stt_external_check.setChecked(bool(self.config.get("stt_external_api", False)))
        self.stt_external_check.toggled.connect(self._refresh_visibility)
        form.addWidget(self.stt_external_check)
        self.stt_backend_combo = QComboBox()
        self.stt_backend_combo.addItem("Faster Whisper local", "whisper")
        self.stt_backend_combo.addItem("LLM audio (Gemma 4 / KoboldCpp)", "llm_audio")
        self.stt_backend_combo.addItem("WhisperLive (OpenAI REST)", "whisperlive")
        self.stt_backend_combo.addItem("VOSK English local", "vosk")
        self._set_combo_selected(self.stt_backend_combo, str(self.config.get("stt_backend", "whisper")))
        self.stt_backend_combo.currentIndexChanged.connect(self._refresh_visibility)
        form.addWidget(self._labeled("Local STT engine", self.stt_backend_combo))
        self.stt_model_combo = QComboBox()
        self.stt_model_combo.setEditable(True)
        if self.stt_model_combo.lineEdit() is not None:
            self.stt_model_combo.lineEdit().setPlaceholderText("tiny/small/… or HF repo id or local path")
        for name in ("tiny", "small", "medium", "large"):
            self.stt_model_combo.addItem(f"Whisper {name}", name)
        # Helpful HF repo suggestions (still routed through faster-whisper / CTranslate2).
        self.stt_model_combo.addItem("Systran/faster-whisper-small", "Systran/faster-whisper-small")
        self.stt_model_combo.addItem("Systran/faster-whisper-large-v3", "Systran/faster-whisper-large-v3")
        # Distil-Whisper family (may require a CTranslate2-converted repo to work with faster-whisper).
        self.stt_model_combo.addItem("distil-whisper/distil-small.en", "distil-whisper/distil-small.en")
        self.stt_model_combo.addItem("distil-whisper/distil-medium.en", "distil-whisper/distil-medium.en")
        configured_model = str(self.config.get("stt_model", "small")).strip()
        if configured_model and self.stt_model_combo.findData(configured_model) < 0:
            self.stt_model_combo.addItem(configured_model, configured_model)
        self._set_combo_selected(self.stt_model_combo, configured_model or "small")
        form.addWidget(self._labeled("Whisper model", self.stt_model_combo))
        self.stt_device_combo = self._device_combo(str(self.config.get("stt_device", "cpu")))
        form.addWidget(self._labeled("STT device", self.stt_device_combo))
        self.whisperlive_host_input = QLineEdit(str(self.config.get("stt_whisperlive_host", "127.0.0.1:9090")))
        self.whisperlive_host_input.setPlaceholderText("WhisperLive host, e.g. 127.0.0.1:9090")
        form.addWidget(self._labeled("WhisperLive host", self.whisperlive_host_input))
        self.whisperlive_model_input = QLineEdit(str(self.config.get("stt_whisperlive_model", "small")))
        self.whisperlive_model_input.setPlaceholderText("small / medium / … or HF repo id")
        form.addWidget(self._labeled("WhisperLive model", self.whisperlive_model_input))
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

        form.addWidget(self._section_label("Streaming mode"))
        self.stt_streaming_check = QCheckBox("Live transcript (streaming STT)")
        self.stt_streaming_check.setChecked(bool(self.config.get("stt_streaming_enabled", False)))
        form.addWidget(self.stt_streaming_check)
        self.llm_streaming_check = QCheckBox("Stream LLM tokens (KoboldCpp/OpenAI-compatible)")
        self.llm_streaming_check.setChecked(bool(self.config.get("llm_streaming_enabled", True)))
        form.addWidget(self.llm_streaming_check)
        self.tts_streaming_check = QCheckBox("Speak while generating (PocketTTS/Kokoro)")
        self.tts_streaming_check.setChecked(bool(self.config.get("tts_streaming_enabled", True)))
        form.addWidget(self.tts_streaming_check)
        self.tts_streaming_min_chars_input = QLineEdit(str(self.config.get("tts_streaming_min_chars", "42")))
        self.tts_streaming_min_chars_input.setPlaceholderText("e.g. 42")
        form.addWidget(self._labeled("Speak after (min chars)", self.tts_streaming_min_chars_input))
        self.tts_streaming_max_chars_input = QLineEdit(str(self.config.get("tts_streaming_max_chars", "180")))
        self.tts_streaming_max_chars_input.setPlaceholderText("e.g. 180")
        form.addWidget(self._labeled("Max chunk size (chars)", self.tts_streaming_max_chars_input))

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

        form.addWidget(self._section_label("Prompt smarts"))
        self.token_saver_check = QCheckBox("Token saver (compress transcript before sending to the text model)")
        self.token_saver_check.setChecked(bool(self.config.get("token_saver_enabled", True)))
        form.addWidget(self.token_saver_check)

        self.memory_check = QCheckBox("Embeddings memory (inject relevant past snippets)")
        self.memory_check.setChecked(bool(self.config.get("memory_enabled", False)))
        self.memory_check.toggled.connect(self._refresh_visibility)
        form.addWidget(self.memory_check)
        self.memory_host_input = QLineEdit(str(self.config.get("memory_host", "127.0.0.1:1234")))
        self.memory_host_input.setPlaceholderText("Embeddings host (OpenAI-compatible), e.g. 127.0.0.1:1234")
        form.addWidget(self._labeled("Embeddings host", self.memory_host_input))
        self.memory_model_input = QLineEdit(str(self.config.get("memory_model", "nomic-embed-text-v2-moe")))
        self.memory_model_input.setPlaceholderText("Embeddings model, e.g. nomic-embed-text-v2-moe")
        form.addWidget(self._labeled("Embeddings model", self.memory_model_input))
        self.memory_api_key_input = QLineEdit(secure_load_secret("voice_mode:memory_api_key"))
        self.memory_api_key_input.setPlaceholderText("Embeddings API key (optional)")
        self.memory_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self._labeled("Embeddings API key", self.memory_api_key_input))
        self.memory_top_k_input = QLineEdit(str(self.config.get("memory_top_k", "4")))
        self.memory_top_k_input.setPlaceholderText("e.g. 4")
        form.addWidget(self._labeled("Memory top-k", self.memory_top_k_input))
        self.memory_max_chars_input = QLineEdit(str(self.config.get("memory_max_chars", "1100")))
        self.memory_max_chars_input.setPlaceholderText("e.g. 1100")
        form.addWidget(self._labeled("Memory max chars", self.memory_max_chars_input))

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

        form.addWidget(self._section_label("Voice commands"))
        self.stop_phrases_check = QCheckBox("Enable stop phrases (\"stop voice mode\")")
        self.stop_phrases_check.setChecked(bool(self.config.get("stop_phrases_enabled", True)))
        form.addWidget(self.stop_phrases_check)
        self.stop_lang_combo = QComboBox()
        self.stop_lang_combo.addItem("English (en-us)", "en-us")
        self.stop_lang_combo.addItem("Portuguese (ptbr)", "ptbr")
        self.stop_lang_combo.addItem("Spanish (es)", "es")
        self._set_combo_selected(self.stop_lang_combo, str(self.config.get("stop_phrases_language", "en-us")))
        form.addWidget(self._labeled("Stop phrases language", self.stop_lang_combo))
        self.stop_single_check = QCheckBox("Allow single-word stop (more false positives)")
        self.stop_single_check.setChecked(bool(self.config.get("stop_phrases_allow_single_word", False)))
        form.addWidget(self.stop_single_check)

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
        label.setObjectName("sectionLabel")
        label.setStyleSheet("margin-top: 6px;")
        return label

    def _labeled(self, label_text: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("fieldWrap")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
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
        stt_is_whisperlive = str(self.stt_backend_combo.currentData() or "") == "whisperlive"
        stt_is_llm_audio = str(self.stt_backend_combo.currentData() or "") == "llm_audio"
        for widget in (
            self.stt_backend_combo,
            self.stt_model_combo,
            self.stt_device_combo,
            self.whisperlive_host_input,
            self.whisperlive_model_input,
            self.stt_vosk_model_input,
        ):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(not stt_external)
        if self.stt_model_combo.parentWidget() is not None:
            self.stt_model_combo.parentWidget().setVisible((not stt_external) and (not stt_is_vosk) and (not stt_is_whisperlive) and (not stt_is_llm_audio))
        if self.stt_device_combo.parentWidget() is not None:
            self.stt_device_combo.parentWidget().setVisible((not stt_external) and (not stt_is_whisperlive) and (not stt_is_llm_audio))
        if self.stt_vosk_model_input.parentWidget() is not None:
            self.stt_vosk_model_input.parentWidget().setVisible((not stt_external) and stt_is_vosk)
        if self.whisperlive_host_input.parentWidget() is not None:
            self.whisperlive_host_input.parentWidget().setVisible((not stt_external) and stt_is_whisperlive)
        if self.whisperlive_model_input.parentWidget() is not None:
            self.whisperlive_model_input.parentWidget().setVisible((not stt_external) and stt_is_whisperlive)
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

        memory_enabled = self.memory_check.isChecked()
        for widget in (
            self.memory_host_input,
            self.memory_model_input,
            self.memory_api_key_input,
            self.memory_top_k_input,
            self.memory_max_chars_input,
        ):
            wrapper = widget.parentWidget()
            if wrapper is not None:
                wrapper.setVisible(memory_enabled)

    def _save(self) -> None:
        stt_model = str(self.stt_model_combo.currentData() or "").strip()
        typed_model = str(self.stt_model_combo.currentText() or "").strip()
        if typed_model:
            stt_model = typed_model
        if not stt_model:
            stt_model = "small"
        config = dict(_voice_mode_defaults())
        config.update(
            {
                "enabled": bool(self.enabled_check.isChecked()),
                "record_seconds": self.record_seconds_input.text().strip() or "5",
                "silence_threshold": self.silence_threshold_input.text().strip() or "0.012",
                "eos_adaptive_enabled": bool(self.eos_adaptive_check.isChecked()),
                "eos_noise_margin": self.eos_noise_margin_input.text().strip() or "0.004",
                "eos_hysteresis": self.eos_hysteresis_input.text().strip() or "0.82",
                "speech_end_silence_ms": self.speech_end_silence_input.text().strip() or "750",
                "listen_chunk_seconds": self.listen_chunk_input.text().strip() or "0.75",
                "min_speech_ms": self.min_speech_input.text().strip() or "260",
                "stt_backend": str(self.stt_backend_combo.currentData() or "whisper"),
                "stt_model": stt_model,
                "stt_device": str(self.stt_device_combo.currentData() or "cpu"),
                "stt_whisperlive_host": self.whisperlive_host_input.text().strip(),
                "stt_whisperlive_model": self.whisperlive_model_input.text().strip() or "small",
                "stt_external_api": bool(self.stt_external_check.isChecked()),
                "stt_host": self.stt_host_input.text().strip(),
                "stt_remote_model": self.stt_remote_model_input.text().strip() or "whisper-1",
                "stt_vosk_model_path": self.stt_vosk_model_input.text().strip(),
                "stt_streaming_enabled": bool(self.stt_streaming_check.isChecked()),
                "llm_streaming_enabled": bool(self.llm_streaming_check.isChecked()),
                "tts_streaming_enabled": bool(self.tts_streaming_check.isChecked()),
                "tts_streaming_min_chars": self.tts_streaming_min_chars_input.text().strip() or "42",
                "tts_streaming_max_chars": self.tts_streaming_max_chars_input.text().strip() or "180",
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
                "token_saver_enabled": bool(self.token_saver_check.isChecked()),
                "memory_enabled": bool(self.memory_check.isChecked()),
                "memory_host": self.memory_host_input.text().strip(),
                "memory_model": self.memory_model_input.text().strip() or "nomic-embed-text-v2-moe",
                "memory_top_k": self.memory_top_k_input.text().strip() or "4",
                "memory_max_chars": self.memory_max_chars_input.text().strip() or "1100",
                "stop_phrases_enabled": bool(self.stop_phrases_check.isChecked()),
                "stop_phrases_language": str(self.stop_lang_combo.currentData() or "en-us"),
                "stop_phrases_allow_single_word": bool(self.stop_single_check.isChecked()),
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
        secure_store_secret("voice_mode:memory_api_key", self.memory_api_key_input.text().strip())
        save_backend_settings(self.settings)
        _write_privacy_codebook(config)
        self.config = config
        self.accept()


