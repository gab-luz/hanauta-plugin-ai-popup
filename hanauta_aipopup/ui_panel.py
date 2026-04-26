from __future__ import annotations

import html
import json
import logging
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QPixmap, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import BackendProfile, CharacterCard, ChatItemData, SourceChipData
from .runtime import (
    AI_STATE_DIR,
    BACKEND_SETTINGS_FILE,
    CHARACTER_LIBRARY_FILE,
    NOTIFICATION_CENTER_SETTINGS_FILE,
    create_close_button,
    palette_mtime,
)
from .style import (
    ACCENT, ACCENT_SOFT, BORDER_ACCENT, BORDER_SOFT, CARD_BG, CARD_BG_SOFT,
    HERO_TOP, HERO_BOTTOM, HOVER_BG, PANEL_BG, PANEL_BG_FLOAT,
    TEXT, TEXT_DIM, TEXT_MID, THEME, UI_ICON_DIM, UI_ICON_ACTIVE, UI_TEXT_STRONG,
    apply_theme_globals, focused_workspace, mix, rgba,
)
from .storage import (
    secure_load_secret, secure_store_secret,
    secure_append_chat, secure_load_chat_history, secure_clear_chat_history,
    list_chat_archives, load_chat_archive,
)
from .http import (
    load_backend_settings,
    save_backend_settings,
    send_desktop_notification,
    send_desktop_notification_with_action,
    maybe_notify_koboldcpp_release,
    _api_url_from_host,
    _openai_compat_alive,
    _looks_like_gemma4_model_name,
    _looks_like_gemma4_audio_variant,
    _probe_openai_style_audio_input_support,
    _wait_for_http_ready,
)
from .characters import (
    load_character_library,
    save_character_library,
    _character_compose_prompt,
)
from .voice import (
    _voice_mode_defaults,
    _replace_sensitive_words, _restore_sensitive_words,
    _privacy_word_list, _write_privacy_codebook,
    _extract_emotion_and_clean_text,
)
from .backends import (
    _existing_path,
    koboldcpp_status as _koboldcpp_status,
    start_koboldcpp as _start_koboldcpp,
    stop_koboldcpp as _stop_koboldcpp,
)
from .user_profile import load_ai_popup_user_profile, save_ai_popup_user_profile
from .tts import (
    synthesize_tts, _waveform_from_hanauta_service,
    _start_kokoro_server, _stop_kokoro_server,
    _start_pocket_server, _stop_pocket_server,
    transcribe_voice_audio, generate_voice_chat_reply,
    _voice_mode_settings, _voice_log,
    _render_llm_text_html,
    _compress_voice_prompt, _voice_token_saver_enabled,
    _voice_memory_recall, _voice_memory_store_pair,
    _chat_messages_for_prompt, _chat_messages_with_memory,
    _default_tts_mode, _default_tts_model_dir,
)
from .ui_backend_settings import BackendSettingsDialog, get_tts_download_manager
from .storage import _chat_timestamp_label, _chat_export_payload, archive_chat_history
from .fonts import load_material_icon_font, load_ui_font
from .ui_widgets import (
    SurfaceFrame, FadeCard, BackendPill, AntiAliasButton, ActionIcon,
    HeaderBadge, _backend_icon, _apply_antialias_font,
    _button_css_weight, _button_qfont_weight,
    _audio_duration_label,
)
from .ui_chat import (
    ChatWebView, VoiceModeWebView, PopupWebView,
    SdImageWorker, TtsSynthesisWorker, VoiceConversationWorker,
    OneShotSttWorker, VoiceModelsWarmupWorker,
)
from .ui_chat_cards import MessageCard, ComposerBar
from .ui_dialogs import CharacterLibraryDialog, VoiceModeDialog
from .html_sanitize import sanitize_message_html

LOGGER = logging.getLogger("hanauta.ai_popup")

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
            BackendProfile("kokoclone", "KokoClone", "tts_local", "en", "", "kokorotts", False, False),
            BackendProfile("pockettts", "PocketTTS", "tts_local", "pocket", "127.0.0.1:8890", "pockettts", False, True),
        ]
        self.profile_by_key = {profile.key: profile for profile in self.profiles}
        self.backend_settings = load_backend_settings()
        _write_privacy_codebook(_voice_mode_settings(self.backend_settings))
        try:
            from .tts import _PROMPT_SMARTNESS
            _PROMPT_SMARTNESS.ensure_token_compressor_file()
        except Exception:
            pass
        self.current_profile: BackendProfile | None = None
        self._card_animations: list[QPropertyAnimation] = []
        self.chat_history = secure_load_chat_history()
        self.character_cards, self.active_character_id = load_character_library()
        self._sd_seen_outputs: dict[str, tuple[str, float]] = {}
        self._image_worker: SdImageWorker | None = None
        self._tts_worker: TtsSynthesisWorker | None = None
        self._text_worker = None
        self._pending_user_message: str = ""
        self._voice_worker: VoiceConversationWorker | None = None
        self._local_backend_processes: dict[str, subprocess.Popen[str]] = {}
        self._pending_item: ChatItemData | None = None
        self._voice_last_status = "Voice mode"
        self._voice_last_transcript = ""
        self._voice_last_response = ""
        self._voice_last_emotion = "neutral"
        self._voice_llm_started: bool = False
        self._voice_tts_in_progress: bool = False
        self._voice_llm_log_last_ts: float = 0.0
        self._voice_llm_log_last_len: int = 0
        self._voice_listening = False
        self._voice_speaking = False
        self._web_mode = "chat"
        self._voice_models_loaded: dict[str, bool] = {"stt": False, "llm": False, "tts": False}
        self._voice_models_busy: bool = False
        self._voice_models_warning: str = ""
        self._voice_models_needs_confirm: bool = False
        self._voice_models_last_selection: dict[str, bool] = {"stt": True, "llm": True, "tts": True}
        self._voice_models_worker: VoiceModelsWarmupWorker | None = None
        self._stt_once_worker: OneShotSttWorker | None = None
        self._user_profile = load_ai_popup_user_profile()
        self._web_draft_text: str = ""
        self._web_draft_id: int = 0
        self._pending_kobold_ready_profile: str = ""
        self._pending_kobold_ready_host: str = ""
        self._text_response_timer = QTimer(self)
        self._text_response_timer.setSingleShot(True)
        self._text_response_timer.timeout.connect(self._finish_mock_text_response)
        self._kobold_ready_timer = QTimer(self)
        self._kobold_ready_timer.setInterval(1800)
        self._kobold_ready_timer.timeout.connect(self._poll_pending_kobold_ready)

        self.setObjectName("sidebarPanel")
        self.setFixedWidth(452)
        self.setStyleSheet(
            f"""
            QFrame#sidebarPanel {{
                background: transparent;
                border: none;
                border-radius: 28px;
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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Build hero off-screen — its child widgets (voice_button, header_status, etc.)
        # are referenced throughout the panel but the frame itself is not shown.
        self._hidden_hero = self._build_hero()
        self._hidden_backend_strip = self._build_backend_strip()

        chat_header = QFrame()
        chat_header.setFixedHeight(44)
        chat_header.setStyleSheet(f"background: {rgba(CARD_BG, 0.85)}; border-bottom: 1px solid {rgba(BORDER_SOFT, 0.5)};")
        chat_header_layout = QHBoxLayout(chat_header)
        chat_header_layout.setContentsMargins(16, 0, 16, 0)
        self.chat_list_btn = QPushButton("☰  Chat list")
        self.chat_list_btn.setFont(QFont(self.ui_font, 11, QFont.Weight.Medium))
        self.chat_list_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.chat_list_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {UI_TEXT_STRONG};
                padding: 8px 12px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background: {rgba(HOVER_BG, 0.6)};
            }}
        """)
        self.chat_list_btn.clicked.connect(self._show_chat_list)
        chat_header_layout.addWidget(self.chat_list_btn)
        chat_header_layout.addStretch()
        root.addWidget(chat_header)

        self.chat_view = ChatWebView()
        self.chat_view.audio_state_changed.connect(self._sync_web_ui)
        self.chat_view.audio_state_changed.connect(self._handle_audio_state_changed)
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
        QTimer.singleShot(2200, maybe_notify_koboldcpp_release)
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
        user_profile = load_ai_popup_user_profile()
        if not user_profile.get("setup_shown", False):
            self._prompt_user_profile_setup()
            user_profile["setup_shown"] = True
            save_ai_popup_user_profile(user_profile)
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

    def _prompt_user_profile_setup(self) -> None:
        user_profile = load_ai_popup_user_profile()
        existing_name = user_profile.get("first_name") or user_profile.get("nickname") or ""
        if not existing_name:
            try:
                from pyqt.shared.profile import load_profile_state as _nc_load_profile
                nc_profile = _nc_load_profile()
                existing_name = nc_profile.get("first_name") or nc_profile.get("nickname") or ""
            except Exception:
                pass

        dialog = QDialog(self)
        dialog.setWindowTitle("Your Profile")
        dialog.setMinimumWidth(420)
        bg = PANEL_BG_FLOAT
        txt = TEXT
        txt_dim = TEXT_DIM
        border = BORDER_SOFT
        dialog.setStyleSheet(
            f"""
            QDialog {{
                background: {bg};
                color: {txt};
            }}
            QLabel {{
                color: {txt_dim};
            }}
            QLineEdit, QPlainTextEdit {{
                background: {CARD_BG};
                color: {txt};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 8px 10px;
            }}
            QPushButton {{
                background: {ACCENT};
                color: #fff;
                border: none;
                border-radius: 12px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ACCENT_SOFT};
            }}
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title = QLabel("Set up your profile for the AI to know you")
        title.setFont(QFont(self.ui_font, 12, QFont.Weight.Bold))
        layout.addWidget(title)

        name_label = QLabel("What should the AI call you?")
        name_input = QLineEdit(existing_name)
        name_input.setPlaceholderText("Your name")
        layout.addWidget(name_label)
        layout.addWidget(name_input)

        info_label = QLabel("Tell the AI about yourself (optional):")
        info_input = QPlainTextEdit(user_profile.get("about", ""))
        info_input.setFixedHeight(80)
        info_input.setPlaceholderText("Your interests, background, preferences...")
        layout.addWidget(info_label)
        layout.addWidget(info_input)

        enable_label = QLabel("Make this info available to the AI?")
        enable_check = QCheckBox("Yes, use my profile in system prompts")
        enable_check.setChecked(bool(user_profile.get("enabled", False)))
        layout.addWidget(enable_label)
        layout.addWidget(enable_check)

        note = QLabel("You can change this anytime from the character library.")
        note.setStyleSheet(f"color: {txt_dim}; font-size: 11px;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(dialog.accept)
        buttons.addWidget(save_btn)

        skip_btn = QPushButton("Skip for now")
        skip_btn.clicked.connect(dialog.reject)
        buttons.addWidget(skip_btn)
        layout.addLayout(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = {
            "first_name": name_input.text().strip(),
            "about": info_input.toPlainText().strip(),
            "enabled": enable_check.isChecked(),
            "setup_shown": True,
        }
        user_profile.update(updated)
        save_ai_popup_user_profile(user_profile)
        self._user_profile = user_profile

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
        self._apply_voice_button_state()
        self._sync_web_ui()

    def _open_backend_settings(self) -> None:
        dialog = BackendSettingsDialog(self.profiles, self.backend_settings, self.ui_font, self)
        dialog.exec()
        self.backend_settings = load_backend_settings()
        self._refresh_available_backends()
        self._apply_voice_button_state()
        self._sync_web_ui()

    def _open_voice_mode_settings(self) -> bool:
        dialog = VoiceModeDialog(self.profiles, self.backend_settings, self.ui_font, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.backend_settings = load_backend_settings()
        self._apply_voice_button_state()
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
        if backend == "llm_audio":
            llm_backend, llm_model = self._voice_llm_backend_model()
            return "LLM Audio", f"{llm_backend} • {llm_model}"
        if backend == "vosk":
            path = Path(str(config.get("stt_vosk_model_path", "")).strip()).expanduser()
            return "VOSK", path.name or "english model"
        if backend == "whisperlive":
            model = str(config.get("stt_whisperlive_model", "small")).strip() or "small"
            return "WhisperLive", model
        model = str(config.get("stt_model", "small")).strip() or "small"
        lowered = model.lower()
        return "Whisper", lowered.title() if lowered in {"tiny", "small", "medium", "large"} else model

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

    def _voice_tts_backend_model(self) -> tuple[str, str, str, str]:
        config = _voice_mode_settings(self.backend_settings)
        profile_key = str(config.get("tts_profile", "kokorotts")).strip() or "kokorotts"
        profile = self.profile_by_key.get(profile_key)
        if profile is None:
            return "TTS", "Unknown", "", ""
        payload = dict(self.backend_settings.get(profile.key, {}))
        mode = _default_tts_mode(payload)
        device = str(payload.get("tts_device", payload.get("device", "cpu"))).strip().lower() or "cpu"
        if mode == "external_api":
            host = str(payload.get("host", profile.host)).strip()
            model = str(payload.get("tts_remote_model", payload.get("model", profile.model))).strip() or profile.model
            return profile.label, model, device, f"external • {host or profile.host}"
        model = str(payload.get("model", profile.model)).strip() or profile.model
        return profile.label, model, device, "local"

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

    def _assistant_display_name(self) -> str:
        active = self._active_character()
        return active.name if active is not None else "Hanauta AI"

    def _assistant_avatar_url(self) -> str:
        active = self._active_character()
        if active is None:
            return ""
        config = _voice_mode_settings(self.backend_settings)
        if bool(config.get("hide_character_photo", False)):
            return ""
        avatar = Path(str(active.avatar_path or "").strip()).expanduser()
        if not str(avatar).strip() or not avatar.exists():
            return ""
        try:
            return avatar.resolve().as_uri()
        except Exception:
            return ""

    def _voice_stack_ready(self) -> bool:
        config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            return False
        stt_ready = False
        if bool(config.get("stt_external_api", False)):
            stt_ready = bool(str(config.get("stt_host", "")).strip())
        else:
            backend = str(config.get("stt_backend", "whisper")).strip().lower()
            if backend == "vosk":
                stt_ready = bool(str(config.get("stt_vosk_model_path", "")).strip())
            elif backend == "llm_audio":
                stt_ready = True
            else:
                stt_ready = bool(str(config.get("stt_model", "small")).strip())
        if bool(config.get("llm_external_api", False)):
            llm_ready = bool(str(config.get("llm_host", "")).strip())
        else:
            profile = self.profile_by_key.get(str(config.get("llm_profile", "koboldcpp")).strip())
            if profile is None:
                llm_ready = False
            else:
                payload = dict(self.backend_settings.get(profile.key, {}))
                if profile.key == "koboldcpp":
                    llm_ready = _existing_path(payload.get("binary_path")) is not None and _existing_path(payload.get("gguf_path")) is not None
                elif profile.provider == "ollama":
                    llm_ready = bool(str(payload.get("host", profile.host)).strip())
                else:
                    llm_ready = bool(str(payload.get("host", profile.host)).strip())
        tts_profile = self.profile_by_key.get(str(config.get("tts_profile", "kokorotts")).strip())
        if tts_profile is None:
            tts_ready = False
        else:
            payload = dict(self.backend_settings.get(tts_profile.key, {}))
            mode = _default_tts_mode(payload)
            if mode == "external_api":
                tts_ready = bool(str(payload.get("host", tts_profile.host)).strip())
            else:
                model_dir = _default_tts_model_dir(tts_profile, payload)
                tts_ready = model_dir.exists()
        return bool(stt_ready and llm_ready and tts_ready)

    def _voice_models_payload(self) -> dict[str, object]:
        config = _voice_mode_settings(self.backend_settings)
        stt_backend, stt_model = self._voice_stt_backend_model()
        llm_backend, llm_model = self._voice_llm_backend_model()
        tts_backend, tts_model, tts_device, tts_mode = self._voice_tts_backend_model()
        stt_device = "gpu" if str(config.get("stt_device", "cpu")).strip().lower() == "gpu" else "cpu"
        llm_device = "gpu" if str(config.get("llm_device", "cpu")).strip().lower() == "gpu" else "cpu"
        if str(config.get("stt_backend", "whisper")).strip().lower() == "llm_audio":
            stt_device = llm_device
        selection = dict(self._voice_models_last_selection or {})
        return {
            "active": bool(any(self._voice_models_loaded.values())),
            "busy": bool(self._voice_models_busy),
            "warning": str(self._voice_models_warning or ""),
            "needs_confirm": bool(self._voice_models_needs_confirm),
            "selection": selection,
            "stt": {"backend": stt_backend, "model": stt_model, "device": stt_device, "mode": "external" if bool(config.get("stt_external_api", False)) else "local", "loaded": bool(self._voice_models_loaded.get("stt", False))},
            "llm": {"backend": llm_backend, "model": llm_model, "device": llm_device, "mode": "external" if bool(config.get("llm_external_api", False)) else "local", "loaded": bool(self._voice_models_loaded.get("llm", False))},
            "tts": {"backend": tts_backend, "model": tts_model, "device": tts_device, "mode": tts_mode, "loaded": bool(self._voice_models_loaded.get("tts", False))},
        }

    def _web_info_payload(self) -> dict[str, object]:
        config = _voice_mode_settings(self.backend_settings)
        lines: list[str] = []
        if self.current_profile is not None:
            lines.append(f"Chat backend: {self.current_profile.label}")
        header = self.header_status.text().strip() if hasattr(self, "header_status") else ""
        if header:
            lines.append(header)
        if bool(config.get("enabled", False)):
            stt_backend, stt_model = self._voice_stt_backend_model()
            llm_backend, llm_model = self._voice_llm_backend_model()
            tts_backend, tts_model, _tts_device, tts_mode = self._voice_tts_backend_model()
            ready = "ready" if self._voice_stack_ready() else "not ready"
            lines.append(f"Voice stack: {ready}")
            lines.append(f"STT: {stt_backend} • {stt_model}")
            lines.append(f"LLM: {llm_backend} • {llm_model}")
            lines.append(f"TTS: {tts_backend} • {tts_model} • {tts_mode}")
        else:
            lines.append("Voice mode: disabled")
        loaded_bits = []
        if self._voice_models_loaded.get("stt", False):
            loaded_bits.append("STT")
        if self._voice_models_loaded.get("llm", False):
            loaded_bits.append("LLM")
        if self._voice_models_loaded.get("tts", False):
            loaded_bits.append("TTS")
        if loaded_bits:
            lines.append("Loaded: " + ", ".join(loaded_bits))
        return {"title": "Information", "lines": lines}

    def _apply_voice_button_state(self) -> None:
        active = self._voice_worker is not None and self._voice_worker.isRunning()
        if active:
            self.voice_button.set_highlighted(True)
            return
        self.voice_button.set_highlighted(self._voice_stack_ready())

    def _reopen_popup_from_notification(self) -> None:
        host = self.window()
        if host is not None and hasattr(host, "present"):
            QTimer.singleShot(0, getattr(host, "present"))
            return
        if host is not None:
            QTimer.singleShot(0, host.show)

    def _schedule_kobold_ready_notification(self, profile: BackendProfile, payload: dict[str, object]) -> None:
        host = str(payload.get("host", profile.host)).strip()
        if not host:
            return
        self._pending_kobold_ready_profile = profile.label
        self._pending_kobold_ready_host = host
        if not self._kobold_ready_timer.isActive():
            self._kobold_ready_timer.start()

    def _poll_pending_kobold_ready(self) -> None:
        host = self._pending_kobold_ready_host.strip()
        if not host:
            self._kobold_ready_timer.stop()
            return
        from .backends import _koboldcpp_model_loaded
        loaded, model_name = _koboldcpp_model_loaded(host)
        if not loaded:
            return  # keep polling
        label = self._pending_kobold_ready_profile or "KoboldCpp"
        self._pending_kobold_ready_profile = ""
        self._pending_kobold_ready_host = ""
        self._kobold_ready_timer.stop()
        display_model = model_name or label
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Runtime",
                meta="koboldcpp ready",
                body=(
                    f"<p><b>{html.escape(label)}</b> is ready.</p>"
                    f"<p>Model loaded: <b>{html.escape(display_model)}</b></p>"
                    f"<p>You can now send messages or start voice mode.</p>"
                ),
                chips=[SourceChipData("koboldcpp"), SourceChipData("ready")],
            )
        )
        if not self._popup_open():
            send_desktop_notification_with_action(
                "KoboldCpp ready",
                f"{label} is ready. Reopen chat?",
                "show",
                "Reopen chat",
                callback=self._reopen_popup_from_notification,
            )
        self._apply_voice_button_state()

    def _wait_for_voice_llm_backend(self, config: dict[str, object]) -> tuple[bool, str]:
        if bool(config.get("llm_external_api", False)):
            host = str(config.get("llm_host", "")).strip()
            if not host:
                return False, "Voice mode needs an LLM host."
            ready = _wait_for_http_ready(f"{_api_url_from_host(host)}/v1/models", timeout=8.0)
            if ready:
                return True, ""
            return False, (
                f"Voice mode could not reach {_normalize_host_url(host)}. "
                "Check whether the external LLM endpoint is online and listening on the configured port."
            )
        profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
        profile = self.profile_by_key.get(profile_key)
        if profile is None:
            return False, "Select a valid text backend for voice mode."
        payload = dict(self.backend_settings.get(profile.key, {}))
        host = str(payload.get("host", profile.host)).strip()
        if not host:
            return True, ""
        if profile.provider in {"openai", "openai_compat"}:
            ready = _wait_for_http_ready(f"{_api_url_from_host(host)}/v1/models", timeout=8.0)
        elif profile.provider == "ollama":
            ready = _wait_for_http_ready(f"{_api_url_from_host(host)}/api/tags", timeout=8.0)
        else:
            ready = _host_reachable(host, timeout=1.5)
        if ready:
            return True, ""
        return False, (
            f"Voice mode could not reach {profile.label} at {_normalize_host_url(host)}. "
            "The backend may still be starting or may be using a different host/port."
        )

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
        waveform: list[int] = []
        duration_label = ""
        if item_audio:
            waveform = list(item.audio_waveform or [])
            if not waveform:
                try:
                    waveform = _waveform_from_hanauta_service(Path(item_audio), bars=28)
                    item.audio_waveform = list(waveform)
                except Exception:
                    waveform = []
            duration_label = _audio_duration_label(item_audio)
        return {
            "role": item.role,
            "title": item.title,
            "meta": item.meta,
            "timestamp": float(item.created_at or time.time()),
            "timestamp_label": _chat_timestamp_label(item.created_at),
            "body_html": sanitize_message_html(item.body, allow_html=True),
            "chips": [chip.text for chip in item.chips],
            "audio_path": item_audio,
            "audio_waveform": waveform,
            "audio_duration": duration_label,
            "audio_playing": audio_playing,
            "is_active_audio": bool(item_audio and current_audio == item_audio),
            "pending": bool(item.pending),
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
        assistant_name = self._assistant_display_name()
        assistant_avatar = self._assistant_avatar_url()
        return {
            "mode": getattr(self, "_web_mode", "chat"),
            "header_status": header_status,
            "provider_label": provider_label,
            "draft": {"id": int(self._web_draft_id or 0), "text": str(self._web_draft_text or "")},
            "assistant": {"name": assistant_name, "avatar_url": assistant_avatar},
            "info": self._web_info_payload(),
            "models": self._voice_models_payload(),
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
                "stack_ready": bool(self._voice_stack_ready()),
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

    def _start_tts_generation_by_key(self, key: str, text: str) -> None:
        """Switch to a TTS backend by key and immediately synthesize text."""
        profile = self.profile_by_key.get(key)
        if profile is None or profile.provider != "tts_local":
            return
        self._start_tts_generation(profile, text)

    def _dismiss_card(self, card_id: str) -> None:
        """Remove a card from chat history by its id field."""
        self.chat_history = [c for c in self.chat_history if getattr(c, 'id', None) != card_id]
        self._render_chat_history()
        self._sync_web_ui()

    def _select_tts_for_voice(self, key: str) -> None:
        """Select a TTS backend for voice mode and restart the voice session."""
        profile = self.profile_by_key.get(key)
        if profile is None or profile.provider != "tts_local":
            return
        self.config["tts_profile"] = key
        self.config["tts_device"] = str(self.backend_settings.get(key, {}).get("device", "cpu"))
        self._save_config()
        if self._voice_worker is not None and self._voice_worker.isRunning():
            self._stop_voice_mode()
        self._start_voice_mode(self.config)

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
        self._maybe_probe_kobold_gemma4_audio_support()
        config = _voice_mode_settings(self.backend_settings)
        self._start_voice_mode(config)

    def _maybe_probe_kobold_gemma4_audio_support(self) -> None:
        """
        If the user opted into Gemma 4 audio STT on KoboldCpp, probe support and cache it.
        This enables voice mode to auto-switch STT to LLM-audio and avoid loading Whisper.
        """
        kobold_payload = dict(self.backend_settings.get("koboldcpp", {}) or {})
        if not bool(kobold_payload.get("gemma4_audio_stt_enabled", False)):
            return
        gguf_name = Path(str(kobold_payload.get("gguf_path", "")).strip()).name
        if not _looks_like_gemma4_model_name(gguf_name):
            return
        # If we've already checked, don't re-probe during normal operation.
        try:
            checked_at = float(kobold_payload.get("gemma4_audio_checked_at", 0.0) or 0.0)
            if checked_at > 0 and (time.time() - checked_at) < (24 * 60 * 60):
                return
        except Exception:
            pass
        profile = self.profile_by_key.get("koboldcpp")
        default_host = profile.host if profile is not None else ""
        default_model = profile.model if profile is not None else "koboldcpp"
        host = str(kobold_payload.get("host", default_host)).strip()
        if not host or not _openai_compat_alive(host):
            return
        model = str(kobold_payload.get("model", default_model)).strip() or default_model
        api_key = secure_load_secret("koboldcpp:api_key").strip()
        ok_audio = _probe_openai_style_audio_input_support(host, model, api_key)
        kobold_payload["gemma4_audio_supported"] = bool(ok_audio)
        kobold_payload["gemma4_audio_checked_at"] = float(time.time())
        kobold_payload["gemma4_audio_checked_gguf"] = gguf_name
        self.backend_settings["koboldcpp"] = kobold_payload
        save_backend_settings(self.backend_settings)

    def _voice_models_preflight_warning(self, selection: dict[str, bool]) -> str:
        config = _voice_mode_settings(self.backend_settings)
        warnings: list[str] = []
        if not bool(config.get("enabled", False)):
            warnings.append("Voice mode is disabled. Enable it in Settings first.")

        # Heuristic memory warning: compare model weight/file sizes to available memory.
        ram_avail = 0
        try:
            import psutil  # type: ignore

            ram_avail = int(getattr(psutil.virtual_memory(), "available", 0) or 0)
        except Exception:
            ram_avail = 0

        def _fmt_bytes(n: int) -> str:
            if n <= 0:
                return ""
            for unit in ("B", "KB", "MB", "GB", "TB"):
                if n < 1024:
                    return f"{n:.0f}{unit}"
                n = n / 1024
            return f"{n:.0f}PB"

        # STT estimate
        stt_est = 0
        if selection.get("stt", False) and not bool(config.get("stt_external_api", False)):
            backend = str(config.get("stt_backend", "whisper")).strip().lower()
            if backend == "whisper":
                model = str(config.get("stt_model", "small")).strip().lower() or "small"
                stt_est = {
                    "tiny": 180 * 1024 * 1024,
                    "small": 640 * 1024 * 1024,
                    "medium": 1700 * 1024 * 1024,
                    "large": 3300 * 1024 * 1024,
                }.get(model, 700 * 1024 * 1024)

        # LLM estimate (GGUF file size when local koboldcpp)
        llm_est = 0
        if selection.get("llm", False) and not bool(config.get("llm_external_api", False)):
            profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
            profile = self.profile_by_key.get(profile_key)
            if profile is not None and profile.key == "koboldcpp":
                payload = dict(self.backend_settings.get(profile.key, {}))
                gguf_path = _existing_path(payload.get("gguf_path"))
                if gguf_path is not None:
                    try:
                        llm_est = int(gguf_path.stat().st_size)
                    except Exception:
                        llm_est = 0

        # TTS estimate (small constant; local ONNX)
        tts_est = 0
        if selection.get("tts", False):
            tts_est = 450 * 1024 * 1024

        est_total = int(stt_est + llm_est + tts_est)
        if ram_avail and est_total and est_total > int(ram_avail * 0.80):
            warnings.append(
                f"Estimated model footprint is about {_fmt_bytes(est_total)} but available RAM is about {_fmt_bytes(ram_avail)}. "
                "This may stutter or fail."
            )

        # Optional VRAM warning for GPU paths.
        if selection.get("llm", False) and str(config.get("llm_device", "cpu")).strip().lower() == "gpu":
            try:
                completed = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=2,
                )
                if completed.returncode == 0:
                    first = (completed.stdout or "").strip().splitlines()[:1]
                    if first:
                        free_mb = int(float(first[0].strip() or "0"))
                        if free_mb and free_mb < 1200:
                            warnings.append(f"Free VRAM looks low ({free_mb} MB). GPU loading may fail.")
            except Exception:
                pass

        # Guard: don't start while already busy.
        if self._voice_models_worker is not None and self._voice_models_worker.isRunning():
            warnings.append("Models are already starting. Wait for the current start to finish.")

        return " ".join(warnings).strip()

    def _web_request_start_voice_models(self, selection_json: str) -> None:
        try:
            raw = json.loads(selection_json or "{}")
        except Exception:
            raw = {}
        selection = {
            "stt": bool(raw.get("stt", False)) if isinstance(raw, dict) else False,
            "llm": bool(raw.get("llm", False)) if isinstance(raw, dict) else False,
            "tts": bool(raw.get("tts", False)) if isinstance(raw, dict) else False,
        }
        if not any(selection.values()):
            self._voice_models_warning = "Select at least one model to start."
            self._voice_models_needs_confirm = False
            self._voice_models_last_selection = selection
            self._sync_web_ui()
            return

        warning = self._voice_models_preflight_warning(selection)
        if warning and not (self._voice_models_needs_confirm and self._voice_models_last_selection == selection):
            self._voice_models_warning = f"{warning} Click Start Selected again to continue."
            self._voice_models_needs_confirm = True
            self._voice_models_last_selection = selection
            self._sync_web_ui()
            return

        self._voice_models_warning = ""
        self._voice_models_needs_confirm = False
        self._voice_models_last_selection = selection

        self._maybe_probe_kobold_gemma4_audio_support()
        config = _voice_mode_settings(self.backend_settings)
        self._voice_models_busy = True
        self._sync_web_ui()

        self._add_runtime_status_card(
            "Model Warmup",
            "Starting selected voice backends. This may take a moment on first run.",
            chips=["voice", "models"],
        )
        worker = VoiceModelsWarmupWorker(config, self.profile_by_key, self.backend_settings, selection)
        self._voice_models_worker = worker

        def _on_progress(title: str, detail: str) -> None:
            self._add_runtime_status_card(str(title), str(detail), chips=["voice", "models"])

        def _on_ok(raw_payload: str) -> None:
            self._voice_models_busy = False
            self._voice_models_worker = None
            try:
                payload = json.loads(raw_payload or "{}")
            except Exception:
                payload = {}
            updates = payload.get("updates", {}) if isinstance(payload, dict) else {}
            loaded = payload.get("loaded", {}) if isinstance(payload, dict) else {}
            if isinstance(updates, dict):
                for key, value in updates.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        self.backend_settings[key] = dict(value)
                if updates:
                    save_backend_settings(self.backend_settings)
            if isinstance(loaded, dict):
                for k in ("stt", "llm", "tts"):
                    if k in loaded:
                        self._voice_models_loaded[k] = bool(loaded.get(k, False))
            self._apply_voice_button_state()
            self._sync_web_ui()
            # Build an honest status message based on what actually loaded
            config = _voice_mode_settings(self.backend_settings)
            profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
            profile = self.profile_by_key.get(profile_key)
            status_lines: list[str] = []
            if profile is not None and profile.key == "koboldcpp":
                kpayload = dict(self.backend_settings.get(profile.key, {}))
                host = str(kpayload.get("host", profile.host)).strip()
                from .backends import _koboldcpp_model_loaded
                kloaded, kmodel = _koboldcpp_model_loaded(host)
                if kloaded:
                    status_lines.append(f"KoboldCpp ready — model: <b>{html.escape(kmodel)}</b>")
                else:
                    status_lines.append("KoboldCpp process started but model is still loading…")
            elif profile is not None:
                kpayload = dict(self.backend_settings.get(profile.key, {}))
                host = str(kpayload.get("host", profile.host)).strip()
                from .http import _openai_compat_alive
                if host and _openai_compat_alive(host):
                    status_lines.append(f"{html.escape(profile.label)} is reachable at <code>{html.escape(host)}</code>")
                else:
                    status_lines.append(f"{html.escape(profile.label)} did not respond at <code>{html.escape(host)}</code>")
            body = "<p>" + "</p><p>".join(status_lines) + "</p>" if status_lines else "<p>Warmup complete.</p>"
            tone = "success" if status_lines and "loading" not in body and "not respond" not in body else "warn"
            self._add_runtime_status_card(
                "Model Warmup Complete",
                body,
                tone=tone,
                chips=["voice", "models"],
            )

        def _on_fail(message: str) -> None:
            self._voice_models_busy = False
            self._voice_models_worker = None
            clean = str(message).strip() or "Model warmup failed."
            self._voice_models_warning = clean
            self._sync_web_ui()
            self._add_runtime_status_card(
                "Model Warmup Failed",
                clean,
                tone="warn",
                chips=["voice", "models", "error"],
            )

        worker.progress.connect(_on_progress)
        worker.finished_ok.connect(_on_ok)
        worker.failed.connect(_on_fail)
        worker.start()

    def _web_stop_voice_models(self) -> None:
        if self._voice_models_worker is not None and self._voice_models_worker.isRunning():
            self._voice_models_warning = "Models are busy starting; stop is disabled until warmup finishes."
            self._sync_web_ui()
            return
        if self._voice_worker is not None and self._voice_worker.isRunning():
            self._stop_voice_mode()
        config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("llm_external_api", False)):
            profile = self.profile_by_key.get(str(config.get("llm_profile", "koboldcpp")).strip())
            if profile is not None and profile.key == "koboldcpp":
                payload = dict(self.backend_settings.get(profile.key, {}))
                ok, message = _stop_koboldcpp(payload)
                self.backend_settings[profile.key] = dict(payload)
                save_backend_settings(self.backend_settings)
                self._add_runtime_status_card(
                    "Stop LLM",
                    message,
                    tone="success" if ok else "warn",
                    chips=["voice", "llm", "stop"],
                )
        # Stop any tracked TTS server process (Kokoro/Pocket) if it was started from backend settings.
        tts_profile = self.profile_by_key.get(str(config.get("tts_profile", "kokorotts")).strip())
        if tts_profile is not None and tts_profile.provider == "tts_local":
            payload = dict(self.backend_settings.get(tts_profile.key, {}))
            pid = int(payload.get("tts_server_pid", 0) or 0)
            stopped = False
            message = ""
            if tts_profile.key == "kokorotts":
                stopped, message = _stop_kokoro_server(payload)
            elif tts_profile.key == "pockettts":
                stopped, message = _stop_pocket_server(payload)
            if stopped or pid:
                self.backend_settings[tts_profile.key] = dict(payload)
                save_backend_settings(self.backend_settings)
                self._add_runtime_status_card(
                    "Stop TTS Server",
                    message or "Stopped TTS server.",
                    tone="success" if stopped else "warn",
                    chips=["voice", "tts", "stop"],
                )
        self._voice_models_loaded = {"stt": False, "llm": False, "tts": False}
        self._voice_models_warning = ""
        self._voice_models_needs_confirm = False
        self._apply_voice_button_state()
        self._sync_web_ui()

    def _web_ack_draft(self, draft_id: int) -> None:
        if int(draft_id or 0) != int(self._web_draft_id or 0):
            return
        self._web_draft_text = ""
        self._sync_web_ui()

    def _web_pick_attachments(self) -> None:
        dialog = QFileDialog(self, "Add attachments")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        fusion = None
        try:
            fusion = QStyleFactory.create("Fusion")
        except Exception:
            fusion = None
        if fusion is not None:
            dialog.setStyle(fusion)
        palette = dialog.palette()
        palette.setColor(palette.ColorRole.Window, QColor(PANEL_BG_FLOAT))
        palette.setColor(palette.ColorRole.Base, QColor(CARD_BG))
        palette.setColor(palette.ColorRole.AlternateBase, QColor(CARD_BG_SOFT))
        palette.setColor(palette.ColorRole.Text, QColor(TEXT))
        palette.setColor(palette.ColorRole.WindowText, QColor(TEXT))
        palette.setColor(palette.ColorRole.Button, QColor(CARD_BG_SOFT))
        palette.setColor(palette.ColorRole.ButtonText, QColor(TEXT))
        palette.setColor(palette.ColorRole.Highlight, QColor(ACCENT))
        palette.setColor(palette.ColorRole.HighlightedText, QColor(THEME.on_primary))
        dialog.setPalette(palette)
        dialog.setStyleSheet(
            f"""
            QFileDialog {{
                background: {PANEL_BG_FLOAT};
                color: {TEXT};
            }}
            QLabel, QTreeView, QListView, QComboBox, QLineEdit, QAbstractItemView {{
                background: {CARD_BG};
                color: {TEXT};
                selection-background-color: {ACCENT_SOFT};
                selection-color: {TEXT};
            }}
            QTreeView::item, QListView::item {{
                padding: 4px 6px;
            }}
            QTreeView::item:selected, QListView::item:selected {{
                background: {ACCENT_SOFT};
                color: {TEXT};
            }}
            QPushButton {{
                background: {CARD_BG_SOFT};
                color: {TEXT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 10px;
                padding: 7px 12px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border-color: {BORDER_ACCENT};
            }}
            """
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        attachments: list[dict[str, str]] = []
        for path_text in dialog.selectedFiles()[:8]:
            path = Path(path_text).expanduser()
            item = {
                "name": path.name or "attachment",
                "kind": "file",
                "note": "Selected file",
            }
            try:
                size = path.stat().st_size
                item["note"] = f"{size} bytes"
                if size <= 256000 and path.suffix.lower() in {
                    ".txt",
                    ".md",
                    ".json",
                    ".csv",
                    ".log",
                    ".py",
                    ".js",
                    ".ts",
                    ".css",
                    ".html",
                    ".xml",
                    ".yaml",
                    ".yml",
                    ".toml",
                }:
                    item["kind"] = "text"
                    item["text"] = path.read_text(encoding="utf-8", errors="replace")[:24000]
            except Exception as exc:
                item["note"] = f"Could not read file: {exc}"
            attachments.append(item)
        if attachments and hasattr(self, "web_view") and hasattr(self.web_view, "bridge"):
            self.web_view.bridge.attachmentsPicked.emit(json.dumps(attachments, ensure_ascii=False))

    def _web_transcribe_once(self) -> None:
        if self._stt_once_worker is not None and self._stt_once_worker.isRunning():
            self._voice_models_warning = "STT is already running."
            self._sync_web_ui()
            return
        config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            if not self._open_voice_mode_settings():
                return
            config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            return
        self._add_runtime_status_card("STT", "Listening for dictation…", chips=["stt", "dictation"])
        worker = OneShotSttWorker(config, self.profile_by_key, self.backend_settings)
        self._stt_once_worker = worker

        def _on_status(label: str) -> None:
            self._add_runtime_status_card("STT", str(label), chips=["stt", "dictation"])

        def _on_ok(text: str) -> None:
            self._stt_once_worker = None
            self._web_draft_id = int(self._web_draft_id or 0) + 1
            self._web_draft_text = str(text).strip()
            self._sync_web_ui()
            self._add_runtime_status_card("STT Ready", "Dictation inserted into the composer.", tone="success", chips=["stt", "dictation"])

        def _on_fail(message: str) -> None:
            self._stt_once_worker = None
            self._add_runtime_status_card("STT Failed", str(message).strip() or "STT failed.", tone="warn", chips=["stt", "dictation", "error"])

        worker.status.connect(_on_status)
        worker.finished_ok.connect(_on_ok)
        worker.failed.connect(_on_fail)
        worker.start()

    def _start_voice_mode(self, config: dict[str, object]) -> None:
        if self._voice_worker is not None and self._voice_worker.isRunning():
            return
        if not bool(config.get("llm_external_api", False)):
            profile = self.profile_by_key.get(str(config.get("llm_profile", "koboldcpp")).strip())
            if profile is not None and profile.key == "koboldcpp":
                self.backend_settings.setdefault(profile.key, {})["device"] = str(config.get("llm_device", "cpu"))
                if not self._maybe_launch_koboldcpp(profile):
                    self.add_card(
                        ChatItemData(
                            role="assistant",
                            title="Voice mode",
                            meta="error",
                            body="<p>Voice mode could not start because KoboldCpp is not ready.</p>",
                            chips=[SourceChipData("voice")],
                        )
                    )
                    return
        ready, detail = self._wait_for_voice_llm_backend(config)
        if not ready:
            llm_profile = self.profile_by_key.get(str(config.get("llm_profile", "koboldcpp")).strip())
            if llm_profile is not None and llm_profile.key == "koboldcpp":
                payload = dict(self.backend_settings.get(llm_profile.key, {}))
                self._schedule_kobold_ready_notification(llm_profile, payload)
                detail = (
                    f"{detail} You'll be notified here as soon as KoboldCpp finishes starting."
                )
            self.header_status.setText(detail)
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Voice mode",
                    meta="error",
                    body=f"<p>{html.escape(detail)}</p>",
                    chips=[SourceChipData("voice")],
                )
            )
            return
        stt_backend, stt_model = self._voice_stt_backend_model()
        llm_backend, llm_model = self._voice_llm_backend_model()
        tts_profile = self.profile_by_key.get(str(config.get("tts_profile", "kokorotts")).strip())
        tts_profiles_available = [p for p in self.profiles if p.provider == "tts_local"]
        if tts_profile is None or tts_profile.provider != "tts_local":
            if tts_profiles_available:
                tts_key = tts_profiles_available[0].key
                card_id = f"voice-tts-pick-{int(time.time()*1000)}"
                btn_style = (
                    "display:inline-block;margin:4px 6px 4px 0;"
                    "padding:7px 16px;border-radius:20px;border:none;cursor:pointer;"
                    "font-size:12px;font-weight:700;"
                )
                buttons_html = "".join(
                    f'<button style="{btn_style}background:var(--accent,#9b8fff);color:#fff" '
                    f'onclick="bridge&&bridge.selectTtsForVoice&&bridge.selectTtsForVoice({json.dumps(p.key)});">{html.escape(p.label)}</button>'
                    for p in tts_profiles_available
                )
                dismiss_btn = (
                    f'<button style="{btn_style}background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.6)" '
                    f'onclick="bridge&&bridge.dismissCard&&bridge.dismissCard({json.dumps(card_id)});">Dismiss</button>'
                )
                body = (
                    f"<p>Select a TTS engine for voice replies:</p>"
                    f"<p>{buttons_html}{dismiss_btn}</p>"
                )
                item = ChatItemData(
                    role="assistant",
                    title="Voice mode",
                    body=body,
                    meta="voice tts",
                )
                item.id = card_id
                self.add_card(item)
                self._voice_pending_tts_select = True
                return
            self.add_card(
                ChatItemData(
                    role="assistant",
                    title="Voice mode",
                    meta="error",
                    body="<p>No TTS backend configured. Add KokoroTTS or PocketTTS in Settings → Backends.</p>",
                    chips=[SourceChipData("voice")],
                )
            )
            return
        tts_label = tts_profile.label if tts_profile is not None else "TTS"
        tts_model = str(self.backend_settings.get(tts_profile.key, {}).get("model", tts_profile.model)).strip() if tts_profile is not None else "default"
        self._add_runtime_status_card("Voice Session Ready", f"STT {stt_backend} {stt_model} • LLM {llm_backend} {llm_model} • TTS {tts_label} {tts_model}", tone="success", chips=["voice", "models"])
        character = self._active_character() if bool(config.get("enable_character", True)) else None
        worker = VoiceConversationWorker(config, self.profile_by_key, self.backend_settings, character)
        self._voice_worker = worker
        worker.status_changed.connect(self._handle_voice_status)
        worker.transcript_partial.connect(self._handle_voice_transcript_partial)
        worker.transcript_ready.connect(self._handle_voice_transcript)
        worker.llm_started.connect(self._handle_voice_llm_started)
        worker.response_partial.connect(self._handle_voice_response_partial)
        worker.tts_chunk_ready.connect(self._handle_voice_tts_chunk)
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
        self._apply_voice_button_state()
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
        self._apply_voice_button_state()
        self.header_status.setText("Voice mode stopping.")
        self._voice_last_status = "Voice mode stopped"
        self._voice_last_emotion = "neutral"
        self._set_voice_mode_screen(False)
        self._add_runtime_status_card("Voice Session Stopped", "Voice mode was stopped. STT, LLM, and TTS backends are now idle.", tone="warn", chips=["voice", "idle"])

    def _finish_voice_worker(self) -> None:
        self._voice_worker = None
        self.voice_button.setText("🎙")
        self.voice_button.setToolTip("Start voice mode")
        self._apply_voice_button_state()
        self._set_voice_mode_screen(False)
        self._refresh_backend_hint()

    def _handle_voice_status(self, message: str) -> None:
        clean = str(message).strip() or "Voice mode"
        self._voice_last_status = clean
        self.header_status.setText(clean)
        lowered = clean.lower()
        if lowered == "listening":
            # Reset per-turn flags so audio end detection can flip us back to listening cleanly.
            self._voice_llm_started = False
            self._voice_tts_in_progress = False
            self._voice_llm_log_last_ts = 0.0
            self._voice_llm_log_last_len = 0
        if lowered == "transcribing":
            backend, model = self._voice_stt_backend_model()
            self._add_runtime_status_card("Loading STT", f"Preparing {backend} ({model}) for transcription.", chips=["voice", "stt"])
        elif lowered == "thinking":
            # Clear the previous spoken answer once a new answer begins generating.
            self._voice_last_response = ""
            backend, model = self._voice_llm_backend_model()
            self._add_runtime_status_card("Loading LLM", f"Generating a reply with {backend} ({model}).", chips=["voice", "llm"])
        elif lowered == "speaking":
            config = _voice_mode_settings(self.backend_settings)
            profile = self.profile_by_key.get(str(config.get("tts_profile", "kokorotts")).strip())
            label = profile.label if profile is not None else "TTS"
            model = str(self.backend_settings.get(profile.key, {}).get("model", profile.model)).strip() if profile is not None else "default"
            self._add_runtime_status_card("Loading TTS", f"Synthesizing speech with {label} ({model}).", chips=["voice", "tts"])
        self._update_voice_mode_view(
            listening=(clean.lower() == "listening"),
            speaking=(clean.lower() == "speaking"),
        )

    def _handle_voice_llm_started(self, llm_label: str, llm_model: str) -> None:
        self._voice_llm_started = True
        self._voice_llm_log_last_ts = 0.0
        self._voice_llm_log_last_len = 0
        # Surface this immediately so it doesn't look like the TTS is "ahead" of the UI/logs.
        _voice_log("llm", str(llm_label).strip() or "LLM", str(llm_model).strip() or "model", "started generating…")

    def _handle_audio_state_changed(self) -> None:
        # When TTS stops and the LLM had started, flip back to Listening right away.
        worker = self._voice_worker
        if worker is None or not worker.isRunning():
            return
        config = _voice_mode_settings(self.backend_settings)
        if not bool(config.get("enabled", False)):
            return
        playing = bool(getattr(self.chat_view, "_audio_playing", False))
        pending = bool(getattr(self.chat_view, "_pending_play_path", ""))
        queued = len(getattr(self.chat_view, "_audio_queue", []) or []) > 0
        audio_idle = (not playing) and (not pending) and (not queued)
        if audio_idle and self._voice_tts_in_progress and self._voice_llm_started:
            self._voice_last_status = "Listening"
            self.header_status.setText("Listening")
            self._update_voice_mode_view(listening=True, speaking=False)

    def _handle_voice_transcript_partial(self, transcript: str) -> None:
        clean = str(transcript).strip()
        if not clean:
            return
        self._voice_last_transcript = clean
        self._voice_last_emotion = "neutral"
        self._voice_last_status = "Listening"
        self._update_voice_mode_view(listening=True, speaking=False)

    def _handle_voice_transcript(self, transcript: str) -> None:
        stt_backend, stt_model = self._voice_stt_backend_model()
        _voice_log("stt", stt_backend, stt_model, transcript.strip())
        self._add_runtime_status_card("STT Ready", f"{stt_backend} ({stt_model}) finished transcription.", tone="success", chips=["voice", "stt"])
        self._voice_last_transcript = transcript.strip()
        self._voice_last_emotion = "neutral"
        self._update_voice_mode_view(listening=False, speaking=False)
        safe = html.escape(transcript).replace("\n", "<br>")
        chips: list[SourceChipData] = [SourceChipData("voice")]
        active_character = self._active_character()
        if active_character is not None:
            chips.append(SourceChipData(f"character:{active_character.name}"))
        self.add_card(ChatItemData(role="user", title="You", body=f"<p>{safe}</p>", meta="voice prompt", chips=chips))

    def _handle_voice_response_partial(self, text: str, emotion: str, llm_label: str, llm_model: str) -> None:
        clean = str(text).strip()
        if not clean:
            return
        self._voice_last_response = clean
        self._voice_last_emotion = str(emotion).strip().lower() or "neutral"
        self._voice_last_status = f"{llm_label}"
        self._update_voice_mode_view(listening=False, speaking=True)
        # Stream logs to terminal (throttled) so the UI/logs keep pace with PocketTTS audio.
        now = time.time()
        if (now - self._voice_llm_log_last_ts) >= 1.0 and len(clean) >= (self._voice_llm_log_last_len + 60):
            self._voice_llm_log_last_ts = now
            self._voice_llm_log_last_len = len(clean)
            preview = clean[-260:].strip()
            _voice_log("llm", str(llm_label), str(llm_model), preview)

    def _handle_voice_tts_chunk(self, audio_path_text: str, chunk_text: str) -> None:
        try:
            path = Path(audio_path_text).expanduser().resolve()
        except Exception:
            return
        if not path.exists():
            return
        try:
            # Queue chunked audio so it speaks continuously.
            self.chat_view.enqueue_audio(path)
            self._voice_tts_in_progress = True
        except Exception:
            try:
                self.chat_view.autoplay_audio(path)
                self._voice_tts_in_progress = True
            except Exception:
                pass

    def _handle_voice_response(self, answer: str, audio_path_text: str, llm_label: str, llm_model: str, source: str, emotion: str) -> None:
        _voice_log("llm", llm_label, llm_model, answer.strip())
        self._add_runtime_status_card("LLM Ready", f"{llm_label} ({llm_model}) generated a reply.", tone="success", chips=["voice", "llm"])
        self._voice_last_response = answer.strip()
        self._voice_last_emotion = emotion.strip().lower() or "neutral"
        self._voice_last_status = "Speaking"
        self._update_voice_mode_view(speaking=True)
        config = _voice_mode_settings(self.backend_settings)
        active_character = self._active_character() if bool(config.get("enable_character", True)) else None
        title = active_character.name if active_character is not None else "Hanauta AI"
        chips = [SourceChipData("voice"), SourceChipData(llm_label), SourceChipData(source)]
        resolved_audio: Path | None = None
        waveform: list[int] = []
        if str(audio_path_text).strip():
            try:
                resolved_audio = Path(audio_path_text).expanduser().resolve()
                waveform = _waveform_from_hanauta_service(resolved_audio, bars=24)
            except Exception:
                resolved_audio = None
        self.add_card(
            ChatItemData(
                role="assistant",
                title=title,
                meta="voice reply",
                body=_render_llm_text_html(answer),
                chips=chips,
                audio_path=str(resolved_audio) if resolved_audio is not None else "",
                audio_waveform=waveform,
            )
        )
        if source != "streaming-chunks" and resolved_audio is not None:
            self._add_runtime_status_card("TTS Ready", f"{source} finished audio synthesis and playback started.", tone="success", chips=["voice", "tts"])
            try:
                self.chat_view.autoplay_audio(resolved_audio)
                self._voice_tts_in_progress = True
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
        LOGGER.warning("Voice mode failed: %s", message)
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

    def _add_runtime_status_card(self, title: str, detail: str, *, tone: str = "info", chips: list[str] | None = None) -> None:
        palette = {
            "info": ("#d7ccff", "rgba(198,180,255,0.18)"),
            "success": ("#b8f5d0", "rgba(121,255,186,0.16)"),
            "warn": ("#ffe0a8", "rgba(255,191,94,0.18)"),
            "error": ("#ffb9c7", "rgba(255,107,139,0.18)"),
        }
        fg, bg = palette.get(tone, palette["info"])
        # If detail already contains HTML tags, use it as-is; otherwise escape it
        import re as _re
        detail_html = detail if _re.search(r'<[a-zA-Z]', detail) else html.escape(detail)
        body = (
            f'<p><span style="display:inline-flex;padding:4px 10px;border-radius:999px;'
            f'background:{bg};color:{fg};font-weight:700;">{html.escape(title)}</span></p>'
            f"<p>{detail_html}</p>"
        )
        self.add_card(
            ChatItemData(
                role="assistant",
                title="Runtime",
                meta="model status",
                body=body,
                chips=[SourceChipData(chip) for chip in (chips or [])],
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

    def _show_chat_list(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Chat History")
        dialog.setFixedSize(400, 500)
        dialog.setStyleSheet(f"background: {rgba(CARD_BG, 0.98)};")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Choose a chat to restore")
        title.setFont(QFont(self.ui_font, 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        layout.addWidget(title)

        list_widget = QListWidget()
        list_widget.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: 1px solid {rgba(BORDER_SOFT, 0.5)};
                border-radius: 8px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 10px;
                border-radius: 6px;
                margin: 2px 0;
                color: {TEXT};
            }}
            QListWidget::item:selected {{
                background: {rgba(ACCENT_SOFT, 0.5)};
            }}
            QListWidget::item:hover {{
                background: {rgba(HOVER_BG, 0.4)};
            }}
        """)
        layout.addWidget(list_widget)

        archives = list_chat_archives()
        for arch in archives:
            label = f"{arch['filename']} — {arch['message_count']} messages"
            item = QListWidgetItem(label)
            item.setData(1, arch['path'])
            list_widget.addItem(item)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {rgba(BORDER_SOFT, 0.4)};
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                color: {TEXT};
            }}
            QPushButton:hover {{
                background: {rgba(BORDER_SOFT, 0.7)};
            }}
        """)
        cancel_btn.clicked.connect(dialog.close)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        def on_select():
            current = list_widget.currentItem()
            if current is None:
                return
            path = current.data(1)
            loaded = load_chat_archive(path)
            if loaded is not None:
                self.chat_history = loaded
                secure_clear_chat_history()
                for item in loaded:
                    secure_append_chat(item)
                self._render_chat_history()
                dialog.close()

        list_widget.itemDoubleClicked.connect(on_select)

        dialog.exec()

    def _maybe_launch_koboldcpp(self, profile: BackendProfile) -> bool:
        payload = dict(self.backend_settings.get(profile.key, {}))
        host = str(payload.get("host", profile.host)).strip()
        # Already reachable via HTTP — don't launch again
        if host and _openai_compat_alive(host):
            return True
        # Process already tracked and alive — don't launch again
        active, _message = _koboldcpp_status(payload)
        if active:
            return True
        binary_path = _existing_path(payload.get("binary_path"))
        gguf_path = _existing_path(payload.get("gguf_path"))
        if binary_path is None or gguf_path is None:
            return False
        answer = QMessageBox.question(
            self,
            "Start KoboldCpp",
            f"KoboldCpp is not running.\nStart it now with {gguf_path.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        ok, message = self._launch_koboldcpp_process(profile, payload)
        self.add_card(ChatItemData(
            role="assistant", title="Hanauta AI",
            meta="runtime launch" if ok else "runtime launch failed",
            body=f"<p>{html.escape(message)}</p>",
        ))
        return ok

    def _launch_koboldcpp_process(self, profile: BackendProfile, payload: dict[str, object]) -> tuple[bool, str]:
        # Final guard: don't spawn if already alive
        host = str(payload.get("host", profile.host)).strip()
        if host and _openai_compat_alive(host):
            return True, "KoboldCpp is already running."
        active, _ = _koboldcpp_status(payload)
        if active:
            return True, "KoboldCpp process is already running."
        ok, message = _start_koboldcpp(payload)
        if ok:
            self.backend_settings[profile.key] = dict(payload)
            save_backend_settings(self.backend_settings)
            self._schedule_kobold_ready_notification(profile, payload)
            gguf_path = _existing_path(payload.get("gguf_path"))
            if gguf_path is not None:
                send_desktop_notification("KoboldCpp starting", f"{profile.label} is starting with {gguf_path.name}.")
        return ok, message

    def _clear_cards(self) -> None:
        self.chat_history = []
        self._pending_item = None
        self._text_response_timer.stop()
        secure_clear_chat_history()
        self._render_chat_history()
        self._sync_web_ui()

    def _archive_cards(self) -> None:
        if not self.chat_history:
            send_desktop_notification("Archive chat", "There are no chat messages to archive.")
            return
        try:
            archive_path = archive_chat_history(self.chat_history)
        except Exception as exc:
            send_desktop_notification("Archive failed", str(exc))
            return
        self._clear_cards()
        send_desktop_notification("Chat archived", str(archive_path))

    def _export_cards(self) -> None:
        if not self.chat_history:
            send_desktop_notification("Export chat", "There are no chat messages to export.")
            return
        suggested = f"hanauta-chat-export-{time.strftime('%Y%m%d-%H%M%S', time.localtime())}.zip"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export chat",
            str(AI_STATE_DIR / suggested),
            "ZIP archive (*.zip);;JSON file (*.json)",
        )
        if not target:
            return
        target_path = Path(target).expanduser()
        payload = _chat_export_payload(self.chat_history)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.suffix.lower() == ".json":
                target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                if target_path.suffix.lower() != ".zip":
                    target_path = target_path.with_suffix(".zip")
                with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("conversation.json", json.dumps(payload, ensure_ascii=False, indent=2))
                    archive.writestr("conversation.txt", str(payload.get("plain_text", "")))
            send_desktop_notification("Chat exported", str(target_path))
        except Exception as exc:
            send_desktop_notification("Export failed", str(exc))

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
        # Inject active character's voice sample for KokoClone
        if profile.key == "kokoclone":
            active_char = self._active_character()
            if active_char is not None and active_char.voice_sample_path:
                payload["_character_voice_sample"] = active_char.voice_sample_path
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
        """Replaced mock: check backend status and show real situation."""
        LOGGER.debug("_finish_mock_text_response: checking real backend status")
        self._clear_pending_state()
        if self.current_profile is None:
            return
        profile = self.current_profile
        payload = dict(self.backend_settings.get(profile.key, {}))
        host = str(payload.get("host", profile.host)).strip()

        # Check if backend is reachable
        alive = False
        try:
            from .http import _openai_compat_alive
            alive = _openai_compat_alive(host) if host else False
        except Exception:
            pass

        if profile.key == "koboldcpp":
            active, status_msg = _koboldcpp_status(payload)
            if not active:
                gguf = _existing_path(payload.get("gguf_path"))
                binary = _existing_path(payload.get("binary_path"))
                if binary is None:
                    body = "<p>KoboldCpp binary not configured. Set it in <b>Backend Settings</b>.</p>"
                elif gguf is None:
                    body = "<p>No GGUF model selected. Choose one in <b>Backend Settings → KoboldCpp</b>.</p>"
                else:
                    body = (
                        f"<p>KoboldCpp is not running.</p>"
                        f"<p>Model: <b>{html.escape(gguf.name)}</b></p>"
                        f"<p>Click the <b>KoboldCpp icon</b> in the sidebar to start it, "
                        f"or use <b>Backend Settings → Start</b>.</p>"
                    )
                self.add_card(ChatItemData(
                    role="assistant", title="Hanauta AI", meta="backend offline",
                    body=body, chips=[SourceChipData("koboldcpp")],
                ))
                return
        elif not alive:
            if not host:
                body = f"<p>No host configured for <b>{html.escape(profile.label)}</b>. Set it in <b>Backend Settings</b>.</p>"
            else:
                body = (
                    f"<p><b>{html.escape(profile.label)}</b> is not reachable at "
                    f"<code>{html.escape(host)}</code>.</p>"
                    f"<p>Make sure the backend is running and the host/port are correct.</p>"
                )
            self.add_card(ChatItemData(
                role="assistant", title="Hanauta AI", meta="backend offline",
                body=body, chips=[SourceChipData(profile.provider)],
            ))
            return

        # Backend is alive — send the real message
        if self._pending_user_message:
            self._dispatch_real_llm(profile, payload, self._pending_user_message)
        self._pending_user_message = ""

    def _dispatch_real_llm(self, profile: BackendProfile, payload: dict, text: str) -> None:
        """Send a real chat message to the LLM backend in a worker thread."""
        from .ui_chat import TextReplyWorker
        if hasattr(self, "_text_worker") and self._text_worker is not None and self._text_worker.isRunning():
            return
        self._set_pending_state(profile.label, "Generating response…", "text generation")
        character = self._active_character()
        worker = TextReplyWorker(
            profile=profile,
            payload=payload,
            backend_settings=self.backend_settings,
            text=text,
            character=character,
        )
        self._text_worker = worker
        worker.finished_ok.connect(self._handle_text_reply)
        worker.failed.connect(self._handle_text_reply_failed)
        worker.finished.connect(lambda: setattr(self, "_text_worker", None))
        worker.start()

    def _handle_text_reply(self, reply: str, profile_label: str, model: str) -> None:
        self._clear_pending_state()
        from .tts import _render_llm_text_html
        self.add_card(ChatItemData(
            role="assistant",
            title=profile_label,
            meta=model,
            body=_render_llm_text_html(reply),
            chips=[SourceChipData(profile_label)],
        ))
        send_desktop_notification(
            "New AI answer", reply[:120],
            icon_path=self._active_character_avatar_icon(),
        )

    def _handle_text_reply_failed(self, message: str) -> None:
        self._clear_pending_state()
        self.add_card(ChatItemData(
            role="assistant", title="Hanauta AI", meta="error",
            body=f"<p>{html.escape(message)}</p>",
        ))

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
                import json as _json
                safe_text = _json.dumps(speak_prompt)  # JS-safe quoted string
                card_id = f"tts-pick-{int(time.time()*1000)}"
                tts_profiles = [
                    p for p in self.profiles if p.provider == "tts_local"
                ]
                btn_style = (
                    "display:inline-block;margin:4px 6px 4px 0;"
                    "padding:7px 16px;border-radius:20px;border:none;cursor:pointer;"
                    "font-size:12px;font-weight:700;"
                )
                buttons_html = "".join(
                    f'<button style="{btn_style}background:var(--accent,#9b8fff);color:#fff" onclick="bridge&&bridge.selectBackendAndSay&&bridge.selectBackendAndSay({_json.dumps(p.key)},{safe_text});">{html.escape(p.label)}</button>'
                    for p in tts_profiles
                )
                dismiss_btn = (
                    f'<button style="{btn_style}background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.6)" '
                    f'onclick="bridge&&bridge.dismissCard&&bridge.dismissCard({_json.dumps(card_id)});">'
                    f"Dismiss</button>"
                )
                body = (
                    f"<p>Choose a TTS engine to speak this with:</p>"
                    f"<p><code>{html.escape(speak_prompt[:80])}{'...' if len(speak_prompt)>80 else ''}</code></p>"
                    f"<p>{buttons_html}{dismiss_btn}</p>"
                )
                item = ChatItemData(
                    role="assistant",
                    title="Hanauta AI",
                    body=body,
                    meta="tts command",
                )
                item.id = card_id  # type: ignore[attr-defined]
                self.add_card(item)
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

        LOGGER.debug("starting real LLM dispatch (backend check + send)")
        self._pending_user_message = text
        self._set_pending_state(self.current_profile.label, "Connecting to backend…", "text generation")
        self._text_response_timer.start(200)

