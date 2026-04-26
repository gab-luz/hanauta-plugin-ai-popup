from __future__ import annotations

import html
import json
import logging
import time
import os
import re
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot, QObject, QThread
from PyQt6.QtGui import QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QTextBrowser,
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

from .models import BackendProfile, CharacterCard, ChatItemData, SourceChipData
from .runtime import (
    AI_STATE_DIR,
    IMAGE_OUTPUT_DIR,
    TTS_OUTPUT_DIR,
    VOICE_RECORDINGS_DIR,
    PLUGIN_ROOT,
)
from .style import (
    ACCENT, ACCENT_SOFT, BORDER_SOFT, CARD_BG, CARD_BG_SOFT,
    HOVER_BG, TEXT, TEXT_DIM, TEXT_MID, THEME,
    mix, rgba, BORDER_ACCENT, CHAT_SURFACE_BG, popup_web_theme_css,)
from .storage import secure_load_secret
from .http import (
    _api_url_from_host,
    _http_post_json,
    _normalize_host_url,
    _openai_compat_alive,
    _sd_auth_headers,
    send_desktop_notification,
)
from .backends import _existing_path, start_koboldcpp as _start_koboldcpp
from .tts import (
    synthesize_tts, _waveform_from_hanauta_service,
    _iter_openai_sse_deltas,
    _ensure_voice_whisper_script,
    _ensure_voice_whisper_stream_script,
    _transcribe_with_whisper,
    _transcribe_with_whisperlive,
    _default_tts_mode,
    _host_reachable,
)
from .ui_widgets import (
    SurfaceFrame, FadeCard, AvatarBadge, ActionIcon,
    _audio_chip_href, _audio_chip_path, _audio_duration_label,
    _audio_wave_inline_html, render_chat_html, render_voice_mode_html,
    _button_qfont_weight, _button_css_weight,
)
from .characters import _character_compose_prompt
from .web.popup_html import render_popup_html
from .voice import (
    _voice_mode_defaults,
    VOICE_EMOTIONS,
    _replace_sensitive_words,
    _restore_sensitive_words,
    _privacy_word_list,
    _extract_emotion_and_clean_text,
    _emotion_prompt_suffix,
    _record_microphone_wav,
    _voice_recording_rms,
    _wav_duration_seconds,
    _matches_stop_phrase,
    _ensure_voice_venv,
    _voice_venv_dir,
    _voice_venv_python,
)
from .tts import (
    synthesize_tts, _waveform_from_hanauta_service,
    transcribe_voice_audio, generate_voice_chat_reply,
    _voice_mode_settings, _with_voice_device,
    _voice_token_saver_enabled, _compress_voice_prompt,
    _voice_memory_recall, _voice_memory_store_pair,
    _chat_messages_for_prompt, _chat_messages_with_memory,
    _stream_openai_style_reply,
    _render_llm_text_html,
    _strip_simple_markdown,
)

LOGGER = logging.getLogger("hanauta.ai_popup")

class PopupWebBridge(QObject):
    stateChanged = pyqtSignal(str)
    attachmentsPicked = pyqtSignal(str)

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
    def refreshState(self) -> None:
        self.owner._sync_web_ui()

    @pyqtSlot(str)
    def startVoiceModels(self, selection_json: str) -> None:
        self.owner._web_request_start_voice_models(selection_json)

    @pyqtSlot()
    def stopVoiceModels(self) -> None:
        self.owner._web_stop_voice_models()

    @pyqtSlot()
    def transcribeOnce(self) -> None:
        self.owner._web_transcribe_once()

    @pyqtSlot()
    def pickAttachments(self) -> None:
        self.owner._web_pick_attachments()

    @pyqtSlot(int)
    def ackDraft(self, draft_id: int) -> None:
        self.owner._web_ack_draft(draft_id)

    @pyqtSlot()
    def clearChat(self) -> None:
        self.owner._clear_cards()

    @pyqtSlot()
    def archiveChat(self) -> None:
        self.owner._archive_cards()

    @pyqtSlot()
    def exportChat(self) -> None:
        self.owner._export_cards()

    @pyqtSlot(str)
    def selectBackend(self, key: str) -> None:
        self.owner._select_backend_from_key(key)

    @pyqtSlot(str, str)
    def selectBackendAndSay(self, key: str, text: str) -> None:
        """Switch to a TTS backend and immediately synthesize the given text."""
        self.owner._select_backend_from_key(key)
        self.owner._start_tts_generation_by_key(key, text)

    @pyqtSlot(str)
    def selectTtsForVoice(self, key: str) -> None:
        """Select a TTS backend for voice mode and restart voice session."""
        self.owner._select_tts_for_voice(key)

    @pyqtSlot()
    def launchKobold(self) -> None:
        """Launch KoboldCpp from the prompt card."""
        self.owner._launch_kobold_from_prompt()

    @pyqtSlot(str)
    def dismissCard(self, card_id: str) -> None:
        """Remove a card by its id from the chat history."""
        self.owner._dismiss_card(card_id)

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
        self.view.setPage(_PopupWebPage(self.view))
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.setStyleSheet("background: transparent; border: none;")
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
        self.view.setHtml(render_popup_html(popup_web_theme_css()), base_url)
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


class _PopupWebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            scheme = (url.scheme() or "").lower()
            if scheme in {"http", "https", "mailto", "file"}:
                QDesktopServices.openUrl(url)
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
        self._audio_queue: list[str] = []
        self._queue_enabled: bool = True

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
        # Voice mode can enqueue multiple chunks; fadeout should also clear the queue so it truly stops.
        self._audio_queue.clear()
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
        # If an audio queue is active, advance automatically when playback ends.
        try:
            if (
                self._queue_enabled
                and state == QMediaPlayer.PlaybackState.StoppedState
                and self._audio_queue
                and not self._pending_play_path
            ):
                next_path = self._audio_queue.pop(0)
                self._pending_play_path = next_path
                self._media_player.setSource(QUrl.fromLocalFile(next_path))
                self._media_player.play()
                self._set_audio_state(Path(next_path), True)
                QTimer.singleShot(350, lambda p=next_path: self._ensure_playback_started(p))
                return
        except Exception:
            pass
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

    def enqueue_audio(self, path: Path, *, clear: bool = False) -> None:
        absolute = path.expanduser().resolve()
        if not absolute.exists():
            return
        if clear:
            self._audio_queue.clear()
        # If nothing is playing, start immediately; else queue it.
        if self._media_player is None:
            _play_audio_file(absolute)
            self._set_audio_state(absolute, True)
            return
        state = self._media_player.playbackState()
        if state != QMediaPlayer.PlaybackState.PlayingState and not self._pending_play_path:
            self._pending_play_path = str(absolute)
            self._media_player.setSource(QUrl.fromLocalFile(str(absolute)))
            self._media_player.play()
            self._set_audio_state(absolute, True)
            QTimer.singleShot(350, lambda p=str(absolute): self._ensure_playback_started(p))
            return
        self._audio_queue.append(str(absolute))

    def clear_audio_queue(self) -> None:
        self._audio_queue.clear()

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


class TextReplyWorker(QThread):
    """Sends a chat message to an OpenAI-compatible or Ollama backend and returns the reply."""
    finished_ok = pyqtSignal(str, str, str)  # reply, profile_label, model
    failed = pyqtSignal(str)

    def __init__(
        self,
        profile: "BackendProfile",
        payload: dict,
        backend_settings: dict,
        text: str,
        character=None,
    ) -> None:
        super().__init__()
        self.profile = profile
        self.payload = dict(payload)
        self.backend_settings = dict(backend_settings)
        self.text = text
        self.character = character

    def run(self) -> None:
        try:
            from .tts import (
                generate_voice_chat_reply,
                _chat_messages_with_memory,
                _generate_openai_style_reply,
                _load_skills,
                _api_url_from_host,
            )
            from .http import _http_post_json
            from .storage import secure_load_secret
            from .user_profile import load_profile_state, preferred_user_name, load_ai_popup_user_profile

            profile = self.profile
            payload = self.payload
            host = str(payload.get("host", profile.host)).strip()
            model = str(payload.get("model", profile.model)).strip() or profile.model
            api_key = secure_load_secret(f"{profile.key}:api_key").strip()
            user_name = preferred_user_name(load_profile_state())
            tools = _load_skills()
            user_profile = load_ai_popup_user_profile()
            user_info = user_profile.get("about", "") if user_profile.get("enabled", False) else ""

            messages = _chat_messages_with_memory(
                self.text,
                self.character,
                tools=tools or None,
                user_name=user_name,
                user_info=user_info,
            )

            if profile.key == "ollama":
                response = _http_post_json(
                    f"{_api_url_from_host(host)}/api/chat",
                    {"model": model, "messages": messages, "stream": False},
                    timeout=240.0,
                )
                msg = response.get("message", {})
                reply = str(msg.get("content", "")).strip() if isinstance(msg, dict) else ""
                if not reply:
                    raise RuntimeError("Ollama returned no text.")
            else:
                reply = _generate_openai_style_reply(
                    host, model, messages, api_key,
                    tools=tools or None,
                )

            if profile.key == "koboldcpp":
                from .backends import _existing_path
                gguf = _existing_path(payload.get("gguf_path"))
                if gguf:
                    model = gguf.name

            self.finished_ok.emit(reply, profile.label, model)
        except Exception as exc:
            self.failed.emit(str(exc))


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


class OneShotSttWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self,
        config: dict[str, object],
        profiles: dict[str, BackendProfile] | None = None,
        backend_settings: dict[str, dict[str, object]] | None = None,
    ) -> None:
        super().__init__()
        self.config = dict(config)
        self.profiles = dict(profiles) if profiles is not None else None
        self.backend_settings = json.loads(json.dumps(backend_settings)) if backend_settings is not None else None

    def _silence_threshold(self) -> float:
        try:
            return float(str(self.config.get("silence_threshold", "0.012")))
        except Exception:
            return 0.012

    def _eos_adaptive_enabled(self) -> bool:
        return bool(self.config.get("eos_adaptive_enabled", True))

    def _eos_noise_margin(self) -> float:
        try:
            return float(str(self.config.get("eos_noise_margin", "0.004")))
        except Exception:
            return 0.004

    def _eos_hysteresis(self) -> float:
        try:
            value = float(str(self.config.get("eos_hysteresis", "0.82")))
        except Exception:
            value = 0.82
        return float(max(0.50, min(0.98, value)))

    def _speech_end_silence_ms(self) -> int:
        try:
            return int(float(str(self.config.get("speech_end_silence_ms", "750"))))
        except Exception:
            return 750

    def _record_seconds(self) -> int:
        try:
            return int(float(str(self.config.get("record_seconds", "5"))))
        except Exception:
            return 5

    def _listen_chunk_seconds(self) -> float:
        try:
            return float(str(self.config.get("listen_chunk_seconds", "0.75")))
        except Exception:
            return 0.75

    def _min_speech_ms(self) -> int:
        try:
            return int(float(str(self.config.get("min_speech_ms", "260"))))
        except Exception:
            return 260

    def _record_until_silence(self) -> Path:
        max_seconds = float(max(1.0, min(30.0, float(self._record_seconds()))))
        stop_silence_ms = max(0, int(self._speech_end_silence_ms()))
        chunk = float(max(0.25, min(3.0, self._listen_chunk_seconds())))
        min_speech_ms = max(0, int(self._min_speech_ms()))
        threshold = float(self._silence_threshold())
        hysteresis = float(self._eos_hysteresis())
        adaptive = bool(self._eos_adaptive_enabled())
        noise_margin = float(self._eos_noise_margin())
        noise_floor = max(0.0, threshold * 0.35)

        start = time.time()
        silence_ms = 0
        speech_ms = 0
        speech_seen = False
        parts: list[Path] = []

        while (time.time() - start) < max_seconds:
            part = _record_microphone_wav(chunk)
            parts.append(part)
            dur = _wav_duration_seconds(part) or chunk
            rms = _voice_recording_rms(part)
            if adaptive and ((not speech_seen) or rms < (threshold * hysteresis)):
                # Best-effort noise floor tracking. EMA keeps it stable without heavy deps.
                if noise_floor <= 0:
                    noise_floor = rms
                else:
                    noise_floor = (noise_floor * 0.92) + (rms * 0.08)
            effective = threshold
            if adaptive:
                effective = max(threshold, noise_floor + noise_margin)
                effective = min(effective, threshold * 4.0)
            silence_cut = effective * hysteresis

            if rms >= effective:
                speech_seen = True
                speech_ms += int(dur * 1000.0)
                silence_ms = 0
            else:
                if speech_seen:
                    # Only count silence when we're meaningfully below the silence cut.
                    # Between (silence_cut..effective) we treat as "soft speech" to avoid cutting
                    # the user off during quiet syllables or a short breath.
                    if rms < silence_cut:
                        silence_ms += int(dur * 1000.0)
                    else:
                        silence_ms = 0
            if stop_silence_ms > 0 and speech_seen and speech_ms >= min_speech_ms and silence_ms >= stop_silence_ms:
                break

        VOICE_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        out = VOICE_RECORDINGS_DIR / f"stt_once_{int(time.time() * 1000)}.wav"
        try:
            with wave.open(str(out), "wb") as dst:
                written = False
                for part in parts:
                    with wave.open(str(part), "rb") as src:
                        if not written:
                            dst.setnchannels(src.getnchannels())
                            dst.setsampwidth(src.getsampwidth())
                            dst.setframerate(src.getframerate())
                            written = True
                        frames = src.readframes(int(src.getnframes() or 0))
                        if frames:
                            dst.writeframes(frames)
            if out.exists() and out.stat().st_size > 44:
                return out
        except Exception:
            pass
        return parts[-1] if parts else _record_microphone_wav(self._record_seconds())

    def run(self) -> None:
        try:
            self.status.emit("Listening")
            audio_path = self._record_until_silence() if self._speech_end_silence_ms() > 0 else _record_microphone_wav(self._record_seconds())
            self.status.emit("Transcribing")
            text = transcribe_voice_audio(audio_path, self.config, self.profiles, self.backend_settings).strip()
            if not text:
                raise RuntimeError("No speech detected.")
            self.finished_ok.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc).strip() or exc.__class__.__name__)


class VoiceModelsWarmupWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: dict[str, object],
        profiles: dict[str, BackendProfile],
        backend_settings: dict[str, dict[str, object]],
        selection: dict[str, bool],
    ) -> None:
        super().__init__()
        self.config = dict(config)
        self.profiles = dict(profiles)
        self.backend_settings = json.loads(json.dumps(backend_settings))
        self.selection = dict(selection)

    def _emit(self, title: str, detail: str) -> None:
        logging.info(f"[VoiceModels] {title}: {detail}")
        self.progress.emit(str(title).strip() or "Models", str(detail).strip())

    def run(self) -> None:
        logging.info(f"[VoiceModels] START selection={self.selection} config keys={list(self.config.keys())}")
        try:
            updates: dict[str, dict[str, object]] = {}
            loaded: dict[str, bool] = {"stt": False, "llm": False, "tts": False}

            if self.selection.get("stt", False):
                logging.info("[VoiceModels] === STT warmup start ===")
                self._emit("Starting STT", "Preparing speech-to-text backend.")
                stt_updates = self._warm_stt()
                logging.info(f"[VoiceModels] === STT warmup done updates={stt_updates} ===")
                if stt_updates:
                    updates.update(stt_updates)
                loaded["stt"] = True

            if self.selection.get("llm", False):
                logging.info("[VoiceModels] === LLM warmup start ===")
                self._emit("Starting LLM", "Preparing the chat backend for voice mode.")
                llm_updates = self._warm_llm()
                logging.info(f"[VoiceModels] === LLM warmup done updates={llm_updates} ===")
                if llm_updates:
                    updates.update(llm_updates)
                loaded["llm"] = True

            if self.selection.get("tts", False):
                logging.info("[VoiceModels] === TTS warmup start ===")
                self._emit("Starting TTS", "Preparing speech synthesis backend.")
                self._warm_tts()
                logging.info("[VoiceModels] === TTS warmup done ===")
                loaded["tts"] = True

            payload = {
                "loaded": loaded,
                "updates": updates,
            }
            logging.info(f"[VoiceModels] DONE loaded={loaded}")
            self.finished_ok.emit(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logging.exception(f"[VoiceModels] FAILED: {exc}")
            message = str(exc).strip() or exc.__class__.__name__
            self.failed.emit(message)

    def _warm_stt(self) -> dict[str, dict[str, object]]:
        logging.info("[VoiceModels] _warm_stt: enter")
        updates: dict[str, dict[str, object]] = {}
        if bool(self.config.get("stt_external_api", False)):
            host = str(self.config.get("stt_host", "")).strip()
            if not host:
                raise RuntimeError("STT external API host is not configured.")
            if not _host_reachable(host):
                raise RuntimeError(f"Unable to reach STT host: {_normalize_host_url(host)}")
            return updates
        backend = str(self.config.get("stt_backend", "whisper")).strip().lower()
        logging.info(f"[VoiceModels] _warm_stt: backend={backend}")
        if backend == "llm_audio":
            # If LLM is also being started, let the LLM warmup own the startup.
            if bool(self.selection.get("llm", False)):
                return updates
            return self._warm_llm()
        if backend == "vosk":
            model_path = Path(str(self.config.get("stt_vosk_model_path", "")).strip()).expanduser()
            logging.info(f"[VoiceModels] _warm_stt: vosk model_path={model_path} exists={model_path.exists()}")
            if not model_path.exists():
                raise RuntimeError("Set a valid VOSK model folder in Voice Mode settings.")
            # Ensure venv and import; do not transcribe in warmup (fast feedback).
            _ensure_voice_venv("vosk", "warmup", "cpu", ["vosk"], "vosk")
            return updates

        if backend == "whisperlive":
            host = str(self.config.get("stt_whisperlive_host", "")).strip()
            logging.info(f"[VoiceModels] _warm_stt: whisperlive host={host}")
            if not host:
                raise RuntimeError("WhisperLive host is not configured.")
            if not _host_reachable(host):
                raise RuntimeError(f"Unable to reach WhisperLive: {_normalize_host_url(host)}")
            return updates

        # Whisper (faster-whisper): ensure venv and do one short transcribe to warm model cache.
        raw_model = str(self.config.get("stt_model", "small")).strip()
        lowered = raw_model.lower()
        model_name = lowered if lowered in {"tiny", "small", "medium", "large"} else (raw_model or "small")
        device = "gpu" if str(self.config.get("stt_device", "cpu")).lower() == "gpu" else "cpu"
        logging.info(f"[VoiceModels] _warm_stt: whisper model={model_name} device={device}")
        _ensure_voice_venv("whisper", model_name, device, ["faster-whisper", "huggingface-hub"], "faster_whisper")
        _ensure_voice_whisper_script()

        try:
            import wave
            import struct
        except Exception:
            raise RuntimeError("Python wave module is unavailable.")
        warmup_wav = AI_STATE_DIR / "voice-runtime" / "warmup_silence.wav"
        warmup_wav.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 16000
        frames = int(sample_rate * 0.35)
        with wave.open(str(warmup_wav), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(struct.pack("<" + "h" * frames, *([0] * frames)))
        _transcribe_with_whisper(warmup_wav, self.config)
        return updates

    def _warm_llm(self) -> dict[str, dict[str, object]]:
        logging.info("[VoiceModels] _warm_llm: enter")
        updates: dict[str, dict[str, object]] = {}
        if bool(self.config.get("llm_external_api", False)):
            host = str(self.config.get("llm_host", "")).strip()
            logging.info(f"[VoiceModels] _warm_llm: external_api host={host}")
            if not host:
                raise RuntimeError("LLM external API host is not configured.")
            if not _host_reachable(host):
                raise RuntimeError(f"Unable to reach LLM host: {_normalize_host_url(host)}")
            return updates
        profile_key = str(self.config.get("llm_profile", "koboldcpp")).strip()
        profile = self.profiles.get(profile_key)
        logging.info(f"[VoiceModels] _warm_llm: profile_key={profile_key} profile={profile}")
        if profile is None:
            raise RuntimeError("Select an LLM backend in Voice Mode settings.")
        payload = dict(self.backend_settings.get(profile.key, {}))
        logging.info(f"[VoiceModels] _warm_llm: profile.key={profile.key} payload keys={list(payload.keys())}")
        if profile.key == "koboldcpp":
            ok, message = _start_koboldcpp(payload)
            logging.info(f"[VoiceModels] _warm_llm: koboldcpp start ok={ok} msg={message}")
            if not ok:
                raise RuntimeError(message)
            updates[profile.key] = payload
            return updates
        host = str(payload.get("host", profile.host)).strip()
        if not host:
            raise RuntimeError(f"{profile.label} host is not configured.")
        if not _host_reachable(host):
            raise RuntimeError(f"Unable to reach {profile.label}: {_normalize_host_url(host)}")
        return updates

    def _warm_tts(self) -> None:
        logging.info("[VoiceModels] _warm_tts: enter")
        profile_key = str(self.config.get("tts_profile", "kokorotts")).strip()
        profile = self.profiles.get(profile_key)
        logging.info(f"[VoiceModels] _warm_tts: profile_key={profile_key} profile={profile}")
        if profile is None:
            raise RuntimeError("Select a TTS backend in Voice Mode settings.")
        payload = dict(self.backend_settings.get(profile.key, {}))
        mode = _default_tts_mode(payload)
        logging.info(f"[VoiceModels] _warm_tts: profile.key={profile.key} mode={mode} payload keys={list(payload.keys())}")
        if mode == "external_api":
            host = str(payload.get("host", profile.host)).strip()
            logging.info(f"[VoiceModels] _warm_tts: external_api host={host}")
            if not host:
                raise RuntimeError("TTS external API host is not configured.")
            if not _host_reachable(host):
                raise RuntimeError(f"Unable to reach TTS host: {_normalize_host_url(host)}")
            return
        # Local ONNX warmup: run a tiny synth and delete the output file.
        audio, _src = synthesize_tts(profile, payload, "Warmup.")
        try:
            audio.unlink(missing_ok=True)
        except Exception:
            pass


class VoiceConversationWorker(QThread):
    status_changed = pyqtSignal(str)
    transcript_partial = pyqtSignal(str)
    transcript_ready = pyqtSignal(str)
    llm_started = pyqtSignal(str, str)
    response_partial = pyqtSignal(str, str, str, str)
    tts_chunk_ready = pyqtSignal(str, str)
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
        self._whisper_stream_proc: subprocess.Popen[str] | None = None
        self._whisper_stream_last_prompt: str = ""

    def stop(self) -> None:
        self._running = False
        proc = self._whisper_stream_proc
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                    proc.stdin.flush()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            self._whisper_stream_proc = None

    def _stt_streaming_enabled(self) -> bool:
        return bool(self.config.get("stt_streaming_enabled", False))

    def _llm_streaming_enabled(self) -> bool:
        return bool(self.config.get("llm_streaming_enabled", True))

    def _tts_streaming_enabled(self) -> bool:
        return bool(self.config.get("tts_streaming_enabled", True))

    def _tts_streaming_min_chars(self) -> int:
        try:
            return int(float(str(self.config.get("tts_streaming_min_chars", "42"))))
        except Exception:
            return 42

    def _tts_streaming_max_chars(self) -> int:
        try:
            return int(float(str(self.config.get("tts_streaming_max_chars", "180"))))
        except Exception:
            return 180

    def _tts_barge_in_enabled(self, profile: BackendProfile | None, payload: dict[str, object]) -> bool:
        if not bool(self.config.get("barge_in_enabled", True)):
            return False
        try:
            if profile is None:
                return True
            if profile.provider != "tts_local":
                return True
            return bool(payload.get("voice_barge_in_enabled", True))
        except Exception:
            return True

    def _whisper_stream_start(self) -> subprocess.Popen[str] | None:
        if bool(self.config.get("stt_external_api", False)):
            return None
        backend = str(self.config.get("stt_backend", "whisper")).strip().lower()
        if backend != "whisper":
            return None
        raw_model = str(self.config.get("stt_model", "small")).strip()
        lowered = raw_model.lower()
        model_name = lowered if lowered in {"tiny", "small", "medium", "large"} else (raw_model or "small")
        device = "gpu" if str(self.config.get("stt_device", "cpu")).lower() == "gpu" else "cpu"
        python_bin = _ensure_voice_venv("whisper", model_name, device, ["faster-whisper", "huggingface-hub"], "faster_whisper")
        script_path = _ensure_voice_whisper_stream_script()
        model_cache = _voice_venv_dir("whisper", model_name, device) / "model-cache"
        model_cache.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.Popen(
                [str(python_bin), str(script_path), "--model", model_name, "--device", device, "--model-cache", str(model_cache)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception:
            return None
        # Read the ready line (non-blocking-ish with short timeout via polling).
        try:
            if proc.stdout:
                proc.stdout.readline()
        except Exception:
            pass
        return proc

    def _whisper_stream_transcribe(self, audio_path: Path, prompt: str) -> str:
        if self._whisper_stream_proc is None:
            self._whisper_stream_proc = self._whisper_stream_start()
        proc = self._whisper_stream_proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            # Fallback to one-shot transcription.
            return transcribe_voice_audio(audio_path, self.config, self.profiles, self.backend_settings)
        payload = {"cmd": "transcribe", "audio": str(audio_path.expanduser()), "prompt": prompt}
        try:
            proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
        except Exception:
            return transcribe_voice_audio(audio_path, self.config, self.profiles, self.backend_settings)
        try:
            msg = json.loads((line or "").strip())
        except Exception:
            return ""
        if isinstance(msg, dict) and bool(msg.get("ok", False)):
            return str(msg.get("text", "")).strip()
        return ""

    def _record_seconds(self) -> int:
        try:
            return int(float(str(self.config.get("record_seconds", "5"))))
        except Exception:
            return 5

    def _speech_end_silence_ms(self) -> int:
        try:
            return int(float(str(self.config.get("speech_end_silence_ms", "750"))))
        except Exception:
            return 750

    def _listen_chunk_seconds(self) -> float:
        try:
            return float(str(self.config.get("listen_chunk_seconds", "0.75")))
        except Exception:
            return 0.75

    def _min_speech_ms(self) -> int:
        try:
            return int(float(str(self.config.get("min_speech_ms", "260"))))
        except Exception:
            return 260

    def _silence_threshold(self) -> float:
        try:
            return float(str(self.config.get("silence_threshold", "0.012")))
        except Exception:
            return 0.012

    def _eos_adaptive_enabled(self) -> bool:
        return bool(self.config.get("eos_adaptive_enabled", True))

    def _eos_noise_margin(self) -> float:
        try:
            return float(str(self.config.get("eos_noise_margin", "0.004")))
        except Exception:
            return 0.004

    def _eos_hysteresis(self) -> float:
        try:
            value = float(str(self.config.get("eos_hysteresis", "0.82")))
        except Exception:
            value = 0.82
        return float(max(0.50, min(0.98, value)))

    def _barge_in_threshold(self) -> float:
        try:
            configured = float(str(self.config.get("barge_in_threshold", "0.035")))
        except Exception:
            configured = 0.035
        return max(self._silence_threshold() * 1.8, configured)

    def _tts_profile(self) -> BackendProfile | None:
        key = str(self.config.get("tts_profile", "kokorotts")).strip()
        profile = self.profiles.get(key)
        if profile is None or profile.provider != "tts_local":
            return None
        return profile

    def _tts_payload(self, profile: BackendProfile) -> dict[str, object]:
        payload = dict(self.backend_settings.get(profile.key, {}))
        payload = _with_voice_device(payload, str(self.config.get("tts_device", payload.get("device", "cpu"))))
        if bool(self.config.get("tts_external_api", False)):
            payload["tts_mode"] = "external_api"
        return payload

    def _record_until_silence(self) -> Path:
        """
        Best-effort end-of-speech recording using repeated short recordings.
        This avoids cutting the user off mid-sentence and keeps dependencies minimal.
        """
        max_seconds = float(max(1.0, min(30.0, float(self._record_seconds()))))
        stop_silence_ms = max(0, int(self._speech_end_silence_ms()))
        chunk = float(max(0.25, min(3.0, self._listen_chunk_seconds())))
        min_speech_ms = max(0, int(self._min_speech_ms()))
        threshold = float(self._silence_threshold())
        hysteresis = float(self._eos_hysteresis())
        adaptive = bool(self._eos_adaptive_enabled())
        noise_margin = float(self._eos_noise_margin())
        noise_floor = max(0.0, threshold * 0.35)

        start = time.time()
        silence_ms = 0
        speech_ms = 0
        speech_seen = False
        parts: list[Path] = []

        while self._running and (time.time() - start) < max_seconds:
            part = _record_microphone_wav(chunk)
            parts.append(part)
            dur = _wav_duration_seconds(part) or chunk
            rms = _voice_recording_rms(part)
            if adaptive and ((not speech_seen) or rms < (threshold * hysteresis)):
                if noise_floor <= 0:
                    noise_floor = rms
                else:
                    noise_floor = (noise_floor * 0.92) + (rms * 0.08)
            effective = threshold
            if adaptive:
                effective = max(threshold, noise_floor + noise_margin)
                effective = min(effective, threshold * 4.0)
            silence_cut = effective * hysteresis

            if rms >= effective:
                speech_seen = True
                speech_ms += int(dur * 1000.0)
                silence_ms = 0
            else:
                if speech_seen:
                    if rms < silence_cut:
                        silence_ms += int(dur * 1000.0)
                    else:
                        silence_ms = 0
            if stop_silence_ms > 0 and speech_seen and speech_ms >= min_speech_ms and silence_ms >= stop_silence_ms:
                break

        # Combine parts into one WAV (same sample rate/channels enforced by recorder).
        VOICE_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        out = VOICE_RECORDINGS_DIR / f"voice_concat_{int(time.time() * 1000)}.wav"
        try:
            with wave.open(str(out), "wb") as dst:
                written = False
                for idx, part in enumerate(parts):
                    try:
                        with wave.open(str(part), "rb") as src:
                            if not written:
                                dst.setnchannels(src.getnchannels())
                                dst.setsampwidth(src.getsampwidth())
                                dst.setframerate(src.getframerate())
                                written = True
                            frames = src.readframes(int(src.getnframes() or 0))
                            if frames:
                                dst.writeframes(frames)
                    except Exception:
                        LOGGER.debug("voice record combine skipped part %d: %s", idx, part)
            if out.exists() and out.stat().st_size > 44:
                return out
        except Exception:
            LOGGER.exception("voice record combine failed")

        # Fallback: return the last recorded chunk.
        return parts[-1] if parts else _record_microphone_wav(self._record_seconds())

    def run(self) -> None:
        while self._running:
            try:
                self.status_changed.emit("Listening")
                transcript = ""
                if (
                    self._stt_streaming_enabled()
                    and (not bool(self.config.get("stt_external_api", False)))
                    and str(self.config.get("stt_backend", "whisper")).strip().lower() in {"whisper", "whisperlive"}
                ):
                    # Live transcription while recording chunks. (Best-effort; depends on recorder chunk cadence.)
                    stt_backend = str(self.config.get("stt_backend", "whisper")).strip().lower()
                    max_seconds = float(max(1.0, min(30.0, float(self._record_seconds()))))
                    stop_silence_ms = max(0, int(self._speech_end_silence_ms()))
                    chunk = float(max(0.25, min(3.0, self._listen_chunk_seconds())))
                    min_speech_ms = max(0, int(self._min_speech_ms()))
                    threshold = float(self._silence_threshold())
                    hysteresis = float(self._eos_hysteresis())
                    adaptive = bool(self._eos_adaptive_enabled())
                    noise_margin = float(self._eos_noise_margin())
                    noise_floor = max(0.0, threshold * 0.35)
                    start = time.time()
                    silence_ms = 0
                    speech_ms = 0
                    speech_seen = False
                    partial = ""
                    while self._running and (time.time() - start) < max_seconds:
                        part = _record_microphone_wav(chunk)
                        dur = _wav_duration_seconds(part) or chunk
                        rms = _voice_recording_rms(part)
                        if adaptive and ((not speech_seen) or rms < (threshold * hysteresis)):
                            if noise_floor <= 0:
                                noise_floor = rms
                            else:
                                noise_floor = (noise_floor * 0.92) + (rms * 0.08)
                        effective = threshold
                        if adaptive:
                            effective = max(threshold, noise_floor + noise_margin)
                            effective = min(effective, threshold * 4.0)
                        silence_cut = effective * hysteresis

                        if rms >= effective:
                            speech_seen = True
                            speech_ms += int(dur * 1000.0)
                            silence_ms = 0
                        else:
                            if speech_seen:
                                if rms < silence_cut:
                                    silence_ms += int(dur * 1000.0)
                                else:
                                    silence_ms = 0
                        if rms >= effective:
                            if stt_backend == "whisper":
                                piece = self._whisper_stream_transcribe(part, partial[-240:])
                            else:
                                piece = _transcribe_with_whisperlive(part, self.config, prompt=partial[-240:])
                            if piece:
                                if partial and not partial.endswith((" ", "\n")):
                                    partial += " "
                                partial += piece.strip()
                                self.transcript_partial.emit(partial)
                        if stop_silence_ms > 0 and speech_seen and speech_ms >= min_speech_ms and silence_ms >= stop_silence_ms:
                            break
                    transcript = partial.strip()
                else:
                    audio_path = self._record_until_silence() if self._speech_end_silence_ms() > 0 else _record_microphone_wav(self._record_seconds())
                    if not self._running:
                        break
                    rms = _voice_recording_rms(audio_path)
                    if rms < self._silence_threshold():
                        self.status_changed.emit("Silence skipped")
                        continue
                    self.status_changed.emit("Transcribing")
                    transcript = transcribe_voice_audio(audio_path, self.config, self.profiles, self.backend_settings)
                if not self._running:
                    break
                if not transcript.strip():
                    self.status_changed.emit("No speech detected")
                    continue
                self.transcript_ready.emit(transcript)
                if _matches_stop_phrase(transcript, self.config):
                    self.status_changed.emit("Stop command")
                    break
                self.status_changed.emit("Thinking")
                # LLM generation: optionally stream tokens (OpenAI-compatible / KoboldCpp).
                llm_label = "LLM"
                llm_model = ""
                emotion = "neutral"
                answer = ""
                streaming_llm = False
                try:
                    streaming_llm = self._llm_streaming_enabled() and (
                        bool(self.config.get("llm_external_api", False))
                        or (
                            str(self.config.get("llm_profile", "koboldcpp")).strip() in self.profiles
                            and self.profiles[str(self.config.get("llm_profile", "koboldcpp")).strip()].provider in {"openai", "openai_compat"}
                        )
                    )
                except Exception:
                    streaming_llm = False

                if not streaming_llm:
                    answer, llm_label, llm_model, emotion = generate_voice_chat_reply(
                        self.config,
                        self.profiles,
                        self.backend_settings,
                        transcript,
                        self.character if bool(self.config.get("enable_character", True)) else None,
                    )
                    try:
                        # Non-streaming: emit after generation returns so we log the final chosen backend/model.
                        self.llm_started.emit(str(llm_label), str(llm_model))
                    except Exception:
                        pass
                else:
                    privacy_mapping: dict[str, str] = {}
                    masked_prompt = transcript
                    if bool(self.config.get("privacy_word_coding_enabled", False)):
                        masked_prompt, privacy_mapping = _replace_sensitive_words(transcript, _privacy_word_list(self.config))
                    memo = ""
                    try:
                        memo = _voice_memory_recall(self.config, masked_prompt)
                    except Exception:
                        memo = ""
                    prompt_for_llm = masked_prompt
                    try:
                        if _voice_token_saver_enabled(self.config, self.profiles, self.backend_settings):
                            prompt_for_llm = _compress_voice_prompt(masked_prompt, self.config)
                    except Exception:
                        prompt_for_llm = masked_prompt
                    from .user_profile import load_ai_popup_user_profile
                    user_profile = load_ai_popup_user_profile()
                    user_info = user_profile.get("about", "") if user_profile.get("enabled", False) else ""
                    messages = _chat_messages_with_memory(
                        prompt_for_llm,
                        self.character if bool(self.config.get("enable_character", True)) else None,
                        emotion_tags=bool(self.config.get("emotion_tags_enabled", False)),
                        memory=memo,
                        user_info=user_info,
                    )
                    host = ""
                    model = ""
                    api_key = ""
                    if bool(self.config.get("llm_external_api", False)):
                        host = str(self.config.get("llm_host", "")).strip()
                        model = str(self.config.get("llm_model", "")).strip() or "gpt-4.1-mini"
                        api_key = secure_load_secret("voice_mode:llm_api_key").strip()
                        llm_label = "OpenAI-compatible"
                        llm_model = model
                    else:
                        profile_key = str(self.config.get("llm_profile", "koboldcpp")).strip()
                        profile = self.profiles.get(profile_key)
                        if profile is None:
                            raise RuntimeError("Select a valid text backend for voice mode.")
                        payload = dict(self.backend_settings.get(profile.key, {}))
                        host = str(payload.get("host", profile.host)).strip()
                        model = str(payload.get("model", profile.model)).strip() or profile.model
                        api_key = secure_load_secret(f"{profile.key}:api_key").strip()
                        llm_label = profile.label
                        llm_model = model
                        if profile.key == "koboldcpp":
                            gguf_path = _existing_path(payload.get("gguf_path"))
                            if gguf_path is not None:
                                llm_model = gguf_path.name
                    raw_accum = ""
                    clean_accum = ""
                    tag_parsed = False
                    llm_started_emitted = False
                    speak_cursor = 0
                    total_audio = 0.0
                    tts_profile = self._tts_profile()
                    if tts_profile is None:
                        self.failed.emit("No TTS backend selected for voice mode.")
                        return
                    tts_payload = self._tts_payload(tts_profile)
                    min_chars = max(12, self._tts_streaming_min_chars())
                    max_chars = max(min_chars + 10, self._tts_streaming_max_chars())
                    interrupted = False
                    last_barge_check = 0.0

                    def _flush_tts(force: bool = False) -> None:
                        nonlocal speak_cursor, total_audio
                        if not self._tts_streaming_enabled():
                            return
                        text = clean_accum
                        if speak_cursor >= len(text):
                            return
                        remaining = text[speak_cursor:]
                        candidate = remaining[:max_chars]
                        split_at = -1
                        if not force:
                            if len(candidate) < min_chars:
                                return
                            # sentence/line boundaries first
                            for mark in ("\n", ".", "?", "!", ":", ";"):
                                idx = candidate.rfind(mark)
                                if idx >= min_chars - 1:
                                    split_at = idx + 1
                                    break
                            if split_at < 0 and len(candidate) >= max_chars:
                                sp = candidate.rfind(" ")
                                split_at = sp if sp > 0 else len(candidate)
                        else:
                            split_at = len(candidate)
                        if split_at <= 0:
                            return
                        chunk_text = remaining[:split_at].strip()
                        if not chunk_text:
                            speak_cursor += split_at
                            return
                        spoken_chunk = _strip_simple_markdown(chunk_text).strip()
                        if not spoken_chunk:
                            speak_cursor += split_at
                            return
                        try:
                            audio_out, source = synthesize_tts(tts_profile, tts_payload, spoken_chunk)
                            self.tts_chunk_ready.emit(str(audio_out), spoken_chunk)
                            total_audio += float(_wav_duration_seconds(audio_out) or 0.0)
                        except Exception:
                            source = "tts"
                        speak_cursor += split_at

                    for delta in _stream_openai_style_reply(host, model, messages, api_key):
                        if not self._running:
                            break
                        if not llm_started_emitted:
                            llm_started_emitted = True
                            try:
                                self.llm_started.emit(str(llm_label), str(llm_model))
                            except Exception:
                                pass
                        raw_accum += delta
                        if not tag_parsed:
                            m = re.match(r"^\s*\[([a-zA-Z_ -]{2,24})\]\s*", raw_accum)
                            if m:
                                tag = m.group(1).strip().lower().replace(" ", "_")
                                emotion = tag if tag in VOICE_EMOTIONS else "neutral"
                                tag_parsed = True
                                raw_accum = raw_accum[m.end():]
                        clean_accum = raw_accum.strip()
                        restored = _restore_sensitive_words(clean_accum, privacy_mapping)
                        clean_accum = restored
                        self.response_partial.emit(clean_accum, emotion, llm_label, llm_model)
                        # Try to speak progressively.
                        _flush_tts(force=False)
                        # Barge-in: if the user starts talking while TTS is speaking, interrupt the reply.
                        if (
                            speak_cursor > 0
                            and self._tts_barge_in_enabled(tts_profile, tts_payload)
                            and (time.time() - last_barge_check) >= 0.85
                        ):
                            last_barge_check = time.time()
                            try:
                                sample = _record_microphone_wav(0.40)
                                if _voice_recording_rms(sample) >= self._barge_in_threshold():
                                    interrupted = True
                                    self.barge_in_detected.emit()
                                    self.status_changed.emit("Listening")
                                    break
                            except Exception:
                                pass
                    if not self._running:
                        break
                    if interrupted:
                        continue
                    # Flush remaining.
                    _flush_tts(force=True)
                    answer = clean_accum.strip()
                    if not answer:
                        raise RuntimeError("LLM endpoint returned no assistant text.")
                    # Give the UI a final snapshot.
                    self.response_partial.emit(answer, emotion, llm_label, llm_model)
                    # Wait roughly for queued audio to finish (best-effort) and allow barge-in.
                    self.status_changed.emit("Speaking")
                    pause_until = time.time() + min(60.0, max(1.0, total_audio + 0.8))
                    while self._running and time.time() < pause_until:
                        if not self._tts_barge_in_enabled(tts_profile, tts_payload):
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
                    # Mark as a streaming run; emit a final "ready" without forcing autoplay.
                    try:
                        _voice_memory_store_pair(self.config, masked_prompt, answer)
                    except Exception:
                        pass
                    self.response_ready.emit(answer, "", llm_label, llm_model, "streaming-chunks", emotion)
                    continue
                if not self._running:
                    break
                self.status_changed.emit("Speaking")
                tts_profile = self._tts_profile()
                if tts_profile is None:
                    self.failed.emit("No TTS backend selected for voice mode.")
                    break
                tts_payload = self._tts_payload(tts_profile)
                spoken_answer = _strip_simple_markdown(answer).strip()
                audio_out, source = synthesize_tts(tts_profile, tts_payload, spoken_answer or answer)
                if not self._running:
                    break
                self.response_ready.emit(answer, str(audio_out), llm_label, llm_model, source, emotion)
                pause_until = time.time() + min(45.0, max(1.0, _wav_duration_seconds(audio_out) + 0.6))
                while self._running and time.time() < pause_until:
                    if not self._tts_barge_in_enabled(tts_profile, tts_payload):
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
                LOGGER.exception("voice loop crashed")
                self.failed.emit(str(exc).strip() or exc.__class__.__name__)
                time.sleep(0.8)
        self.status_changed.emit("Voice mode stopped")
