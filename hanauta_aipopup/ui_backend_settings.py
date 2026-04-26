from __future__ import annotations

import json
import time
from pathlib import Path
from urllib import error

from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .models import BackendProfile, ChatItemData, SourceChipData
from .runtime import (
    AI_STATE_DIR,
    BACKEND_SETTINGS_FILE,
    GGUF_GALLERY_DIR,
    KOKORO_SYNTH_LOG_FILE,
    POCKETTTS_LANGUAGES,
    POCKETTTS_PRESET_VOICES,
    SKILLS_SETTINGS_FILE,
    trigger_fullscreen_alert,
)
from .style import (
    ACCENT, ACCENT_ALT, ACCENT_SOFT, BORDER_ACCENT, BORDER_HARD, BORDER_SOFT,
    CARD_BG, CARD_BG_SOFT, HOVER_BG, INPUT_BG, PANEL_BG, PANEL_BG_FLOAT,
    TEXT, TEXT_DIM, TEXT_MID, THEME, UI_ICON_DIM, UI_TEXT_MUTED, UI_TEXT_STRONG,
    mix, rgba,
)
from .storage import secure_load_secret, secure_store_secret
from .http import (
    _normalize_host_url,
    _http_json,
    _http_post_bytes,
    _sd_auth_headers,
    _sdapi_not_found_message,
    _openai_compat_alive,
    send_desktop_notification,
)
from .backends import _existing_path, _is_pid_alive, _is_pgid_alive, koboldcpp_status as _koboldcpp_status, start_koboldcpp as _start_koboldcpp, stop_koboldcpp as _stop_koboldcpp
from .catalog import MODEL_CATALOG, _dir_size_bytes, _format_bytes
from .tts import (
    synthesize_tts, validate_backend,
    _start_kokoro_server, _stop_kokoro_server, _kokoro_server_status,
    _start_pocket_server, _stop_pocket_server, _pocket_server_status,
    _set_kokoro_autostart, _set_pocket_autostart,
    _install_pockettts_server,
    _default_tts_model_dir, _list_kokoro_voice_names, _list_pocket_voice_references,
    _pocket_preset_voice_path, _ensure_pocket_preset_voice,
    _default_pocket_language, _default_tts_mode, _default_tts_repo, _default_tts_bundle_url,
    _ensure_tts_assets, _ensure_tts_runtime_venv,
    _waveform_from_hanauta_service,
    _WAVEFORM_CACHE,
)
from .ui_widgets import (
    SurfaceFrame, ClickableLineEdit, _apply_antialias_font,
    _button_css_weight, _button_qfont_weight,
)
from .fonts import button_css_weight

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    QT_MULTIMEDIA_AVAILABLE = True
except Exception:
    QAudioOutput = object  # type: ignore[assignment]
    QMediaPlayer = object  # type: ignore[assignment]
    QT_MULTIMEDIA_AVAILABLE = False

import logging
import os
import socket
LOGGER = logging.getLogger("hanauta.ai_popup")

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
        card = SurfaceFrame(bg=rgba(THEME.background, 0.985), border=BORDER_ACCENT, radius=30)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(14)
        card_layout.setStyleSheet(f"background: {rgba(PANEL_BG_FLOAT, 0.9)}; border: 1px solid {BORDER_HARD}; border-radius: 24px;")
        overline = QLabel("FULLSCREEN REMINDER")
        overline.setStyleSheet(f"color: {UI_ICON_DIM}; font-weight: 700; letter-spacing: 1px;")
        card_layout.addWidget(overline)
        headline = QLabel(title.strip() or "Download complete")
        headline.setWordWrap(True)
        headline.setStyleSheet(f"color: {UI_TEXT_STRONG}; font-size: 24px; font-weight: 700;")
        card_layout.addWidget(headline)
        detail = QLabel(body.strip())
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {UI_TEXT_MUTED}; font-size: 14px;")
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


class GgufModelDownloadWorker(QThread):
    progress = pyqtSignal(str, int, str)
    finished_ok = pyqtSignal(str, str)
    failed = pyqtSignal(str, str)

    def __init__(self, entry_id: str, repo_id: str, filename: str, destination: Path) -> None:
        super().__init__()
        self.entry_id = entry_id
        self.repo_id = repo_id
        self.filename = filename
        self.destination = destination

    def run(self) -> None:
        try:
            url = _hf_resolve_url(self.repo_id, self.filename)

            def _emit(written: int, total: int) -> None:
                if total > 0:
                    value = int(max(0.0, min(1.0, written / float(total))) * 100)
                    message = f"{_format_bytes(written)} / {_format_bytes(total)}"
                else:
                    value = 30 if written > 0 else 0
                    message = f"{_format_bytes(written)}"
                self.progress.emit(self.entry_id, value, message)

            self.progress.emit(self.entry_id, 0, "Starting download…")
            _download_file(url, self.destination, timeout=1800.0, progress_cb=_emit)
        except Exception as exc:
            self.failed.emit(self.entry_id, str(exc).strip() or "Download failed.")
            return
        self.progress.emit(self.entry_id, 100, "Download complete")
        self.finished_ok.emit(self.entry_id, str(self.destination))


class GgufDownloadManager(QObject):
    progress_changed = pyqtSignal(str, int, str)
    download_finished = pyqtSignal(str, str)
    download_failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__(None)
        self._workers: dict[str, GgufModelDownloadWorker] = {}
        self._status: dict[str, dict[str, object]] = {}

    def status(self, entry_id: str) -> dict[str, object]:
        return dict(self._status.get(entry_id, {}))

    def is_running(self, entry_id: str) -> bool:
        worker = self._workers.get(entry_id)
        return worker is not None and worker.isRunning()

    def start(self, entry: dict[str, object]) -> bool:
        entry_id = str(entry.get("id", "")).strip()
        repo_id = str(entry.get("repo_id", "")).strip()
        filename = str(entry.get("file", "")).strip()
        if not entry_id or not repo_id or not filename:
            return False
        if self.is_running(entry_id):
            return False
        destination = GGUF_GALLERY_DIR / filename
        worker = GgufModelDownloadWorker(entry_id, repo_id, filename, destination)
        self._workers[entry_id] = worker
        self._status[entry_id] = {"running": True, "progress": 0, "message": "Starting download"}
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda key=entry_id: self._workers.pop(key, None))
        worker.start()
        return True

    def _on_progress(self, entry_id: str, value: int, message: str) -> None:
        self._status[entry_id] = {"running": True, "progress": int(value), "message": message}
        self.progress_changed.emit(entry_id, int(value), str(message))

    def _on_finished(self, entry_id: str, path: str) -> None:
        self._status[entry_id] = {"running": False, "progress": 100, "message": "Download complete", "path": path}
        self.download_finished.emit(entry_id, path)

    def _on_failed(self, entry_id: str, message: str) -> None:
        self._status[entry_id] = {"running": False, "progress": 0, "message": message}
        self.download_failed.emit(entry_id, message)


_GGUF_DOWNLOAD_MANAGER: GgufDownloadManager | None = None


def get_gguf_download_manager() -> GgufDownloadManager:
    global _GGUF_DOWNLOAD_MANAGER
    if _GGUF_DOWNLOAD_MANAGER is None:
        _GGUF_DOWNLOAD_MANAGER = GgufDownloadManager()
    return _GGUF_DOWNLOAD_MANAGER


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.resize(720, 760)
        self.setModal(True)
        
        # Comprehensive stylesheet for all widgets
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {PANEL_BG_FLOAT};
                color: {UI_TEXT_STRONG};
            }}
            QLabel {{
                color: {UI_TEXT_MUTED};
            }}
            QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
                background: {INPUT_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 10px;
                padding: 8px 12px;
                selection-background-color: {ACCENT_SOFT};
                font-size: 11px;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {ACCENT};
                background: {INPUT_BG};
            }}
            QComboBox::drop-down {{
                border: none;
                background: transparent;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {CARD_BG};
                color: {UI_TEXT_STRONG};
                selection-background-color: {ACCENT_SOFT};
                border: 1px solid {BORDER_SOFT};
                border-radius: 8px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 10px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background: {ACCENT_SOFT};
            }}
            QCheckBox {{
                color: {UI_TEXT_STRONG};
                spacing: 8px;
                margin: 4px 0px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {BORDER_SOFT};
                background: {INPUT_BG};
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid {ACCENT};
                background: {ACCENT_SOFT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT};
                border: 1px solid {ACCENT};
            }}
            QPushButton {{
                min-height: 32px;
                background: {CARD_BG_SOFT};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
                color: {UI_TEXT_STRONG};
            }}
            QPushButton:pressed {{
                background: {ACCENT_SOFT};
                border: 1px solid {BORDER_ACCENT};
            }}
            QProgressBar {{
                background: {CARD_BG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 6px;
                height: 20px;
                text-align: center;
                color: {UI_TEXT_STRONG};
            }}
            QProgressBar::chunk {{
                background: {ACCENT};
                border-radius: 4px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_SOFT};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {BORDER_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {BORDER_SOFT};
                border-radius: 5px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {BORDER_ACCENT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                border: none;
                background: none;
            }}
            QSpinBox {{
                background: {INPUT_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 8px;
                padding: 4px 8px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: transparent;
                border: none;
                width: 20px;
            }}
            QDoubleSpinBox {{
                background: {INPUT_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 8px;
                padding: 4px 8px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background: transparent;
                border: none;
                width: 20px;
            }}
            QSlider::groove:horizontal {{
                background: {BORDER_SOFT};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {ACCENT};
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {ACCENT_SOFT};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
                background: transparent;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background: {CARD_BG_SOFT};
                color: {UI_TEXT_MUTED};
                border: 1px solid {BORDER_SOFT};
                border-radius: 10px 10px 0px 0px;
                padding: 8px 18px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 11px;
            }}
            QTabBar::tab:hover {{
                background: {CARD_BG_SOFT};
                border-color: {BORDER_ACCENT};
            }}
            QTabBar::tab:selected {{
                background: {ACCENT_SOFT};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_ACCENT};
            }}
        """)
        root.addWidget(self._tabs)

        # --- Backends tab ---
        backends_widget = QWidget()
        backends_root = QVBoxLayout(backends_widget)
        backends_root.setContentsMargins(0, 0, 0, 0)
        backends_root.setSpacing(0)

        shell = SurfaceFrame(bg=rgba(THEME.background, 0.98), border=BORDER_SOFT, radius=28)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(18, 18, 18, 18)
        shell_layout.setSpacing(12)
        backends_root.addWidget(shell)
        self._tabs.addTab(backends_widget, "Backends")

        header_row = QWidget()
        header_layout = QVBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title = QLabel("Backend settings")
        title.setFont(QFont(ui_font, 14, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        header_layout.addWidget(title)

        subtitle = QLabel("Teste e habilite os providers antes de expor os ícones na sidebar.")
        subtitle.setFont(QFont(ui_font, 10))
        subtitle.setStyleSheet(f"color: {UI_ICON_DIM}; border: none;")
        header_layout.addWidget(subtitle)
        shell_layout.addWidget(header_row)

        self.backend_combo = QComboBox()
        for profile in profiles:
            self.backend_combo.addItem(profile.label, profile.key)
        self.backend_combo.currentIndexChanged.connect(self._load_selected_backend)
        shell_layout.addWidget(self.backend_combo)

        self.enabled_check = QCheckBox("Mostrar backend na barra após teste bem-sucedido")
        shell_layout.addWidget(self.enabled_check)

        url_binary_row = QWidget()
        url_binary_layout = QHBoxLayout(url_binary_row)
        url_binary_layout.setContentsMargins(0, 0, 0, 0)
        url_binary_layout.setSpacing(10)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Host")
        url_binary_layout.addWidget(self.host_input, 1)
        self.binary_path_input = ClickableLineEdit()
        self.binary_path_input.setPlaceholderText("Local binary path")
        self.binary_path_input.setToolTip("Click to browse for a local binary or model folder")
        self.binary_path_input.clicked.connect(self._browse_binary_path)
        url_binary_layout.addWidget(self.binary_path_input, 1)
        shell_layout.addWidget(url_binary_row)

        self.sd_auth_user_input = QLineEdit()
        self.sd_auth_user_input.setPlaceholderText("SD WebUI username (optional)")
        shell_layout.addWidget(self.sd_auth_user_input)
        self.sd_auth_pass_input = QLineEdit()
        self.sd_auth_pass_input.setPlaceholderText("SD WebUI password (optional)")
        self.sd_auth_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        shell_layout.addWidget(self.sd_auth_pass_input)

        model_device_row = QWidget()
        model_device_layout = QHBoxLayout(model_device_row)
        model_device_layout.setContentsMargins(0, 0, 0, 0)
        model_device_layout.setSpacing(10)
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Model")
        model_device_layout.addWidget(self.model_input, 1)
        cpu_gpu_label = QLabel("CPU/GPU")
        cpu_gpu_label.setStyleSheet("border: none;")
        model_device_layout.addWidget(cpu_gpu_label)
        self.device_combo = QComboBox()
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("GPU", "gpu")
        self.device_combo.setToolTip("Execution device")
        model_device_layout.addWidget(self.device_combo, 1)
        shell_layout.addWidget(model_device_row)

        self.token_saver_check = QCheckBox("Token saver (compress voice prompts before LLM)")
        self.token_saver_check.setToolTip("Voice mode only: reduces prompt tokens by compressing STT transcripts before sending to this backend.")
        shell_layout.addWidget(self.token_saver_check)

        self.voice_barge_in_check = QCheckBox("Voice barge-in fadeout (interrupt TTS when you speak)")
        self.voice_barge_in_check.setToolTip("Voice mode only: if you start talking during TTS, fade out speech and let you speak immediately.")
        shell_layout.addWidget(self.voice_barge_in_check)

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

        self.binary_info_label = QLabel("")
        self.binary_info_label.setWordWrap(True)
        self.binary_info_label.setStyleSheet(f"color: {UI_ICON_DIM}; border: none;")
        shell_layout.addWidget(self.binary_info_label)

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
        self.tts_server_status_label.setStyleSheet(f"color: {UI_ICON_DIM}; border: none;")
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

        self.kobold_server_row = QWidget()
        kobold_server_layout = QHBoxLayout(self.kobold_server_row)
        kobold_server_layout.setContentsMargins(0, 0, 0, 0)
        kobold_server_layout.setSpacing(8)
        self.kobold_server_status_label = QLabel("Server status: unknown")
        self.kobold_server_status_label.setStyleSheet(f"color: {UI_ICON_DIM}; border: none;")
        kobold_server_layout.addWidget(self.kobold_server_status_label, 1)
        self.kobold_start_button = QPushButton("Start")
        self.kobold_start_button.clicked.connect(self._start_kobold_clicked)
        kobold_server_layout.addWidget(self.kobold_start_button)
        self.kobold_restart_button = QPushButton("Restart")
        self.kobold_restart_button.clicked.connect(self._restart_kobold_clicked)
        kobold_server_layout.addWidget(self.kobold_restart_button)
        self.kobold_stop_button = QPushButton("Stop")
        self.kobold_stop_button.clicked.connect(self._stop_kobold_clicked)
        kobold_server_layout.addWidget(self.kobold_stop_button)
        shell_layout.addWidget(self.kobold_server_row)

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
        self.tts_test_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
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

        self.gguf_path_input = ClickableLineEdit()
        self.gguf_path_input.setPlaceholderText("GGUF model path")
        self.gguf_path_input.setToolTip("Click to browse for a GGUF model file")
        self.gguf_path_input.clicked.connect(self._browse_gguf_path)
        shell_layout.addWidget(self.gguf_path_input)

        self.gguf_info_label = QLabel("")
        self.gguf_info_label.setWordWrap(True)
        self.gguf_info_label.setStyleSheet(f"color: {UI_ICON_DIM}; border: none;")
        shell_layout.addWidget(self.gguf_info_label)

        self.gguf_download_progress = QProgressBar()
        self.gguf_download_progress.setRange(0, 100)
        self.gguf_download_progress.setValue(0)
        self.gguf_download_progress.hide()
        shell_layout.addWidget(self.gguf_download_progress)
        self.gguf_download_progress_label = QLabel("")
        self.gguf_download_progress_label.setStyleSheet(f"color: {UI_ICON_DIM};")
        self.gguf_download_progress_label.hide()
        shell_layout.addWidget(self.gguf_download_progress_label)

        self.gguf_gallery_title = QLabel("Curated model gallery (GGUF)")
        self.gguf_gallery_title.setFont(QFont(ui_font, 11, QFont.Weight.DemiBold))
        self.gguf_gallery_title.setStyleSheet(f"color: {UI_TEXT_MUTED}; border: none;")
        shell_layout.addWidget(self.gguf_gallery_title)
        self.gguf_gallery_scroll = QScrollArea()
        self.gguf_gallery_scroll.setWidgetResizable(True)
        self.gguf_gallery_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.gguf_gallery_scroll.setFixedHeight(230)
        self.gguf_gallery_scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {mix(ACCENT, CARD_BG, 0.35)};
                border-radius: 5px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {mix(ACCENT, CARD_BG, 0.50)};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                height: 0px;
            }}
            """
        )
        self.gguf_gallery_body = QWidget()
        self.gguf_gallery_grid = QGridLayout(self.gguf_gallery_body)
        self.gguf_gallery_grid.setContentsMargins(0, 0, 0, 0)
        self.gguf_gallery_grid.setHorizontalSpacing(10)
        self.gguf_gallery_grid.setVerticalSpacing(10)
        self.gguf_gallery_scroll.setWidget(self.gguf_gallery_body)
        shell_layout.addWidget(self.gguf_gallery_scroll)

        text_mmproj_row = QWidget()
        text_mmproj_layout = QHBoxLayout(text_mmproj_row)
        text_mmproj_layout.setContentsMargins(0, 0, 0, 0)
        text_mmproj_layout.setSpacing(10)
        self.text_model_path_input = ClickableLineEdit()
        self.text_model_path_input.setPlaceholderText("Optional text model path")
        self.text_model_path_input.setToolTip("Click to browse for an optional text model path")
        self.text_model_path_input.clicked.connect(self._browse_text_model_path)
        text_mmproj_layout.addWidget(self.text_model_path_input, 1)
        self.mmproj_path_input = ClickableLineEdit()
        self.mmproj_path_input.setPlaceholderText("Optional mmproj path")
        self.mmproj_path_input.setToolTip("Click to browse for an optional mmproj file")
        self.mmproj_path_input.clicked.connect(self._browse_mmproj_path)
        text_mmproj_layout.addWidget(self.mmproj_path_input, 1)
        shell_layout.addWidget(text_mmproj_row)

        self.kobold_jinja_check = QCheckBox("Enable Jinja chat template support")
        self.kobold_jinja_check.setToolTip("Useful for Gemma 4 and other chat templates that expect Jinja support in KoboldCpp.")
        shell_layout.addWidget(self.kobold_jinja_check)
        self.kobold_gemma4_audio_stt_check = QCheckBox("Use Gemma 4 audio for STT (Whisper won't be used)")
        self.kobold_gemma4_audio_stt_check.setToolTip(
            "Voice mode only: when enabled and supported by your KoboldCpp build/model, STT runs through the same Gemma 4 model via audio input. "
            "This avoids loading Whisper and can reduce VRAM usage."
        )
        shell_layout.addWidget(self.kobold_gemma4_audio_stt_check)
        self.kobold_test_prompt_input = QLineEdit()
        self.kobold_test_prompt_input.setPlaceholderText("Test prompt for KoboldCpp")
        self.kobold_test_prompt_input.setToolTip("This message is sent by the Test button to confirm the model is answering.")
        shell_layout.addWidget(self.kobold_test_prompt_input)

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

        self.output_dir_input = ClickableLineEdit()
        self.output_dir_input.setPlaceholderText("SD output folder for monitor notifications")
        self.output_dir_input.setToolTip("Click to browse for an output folder")
        self.output_dir_input.clicked.connect(self._browse_output_dir)
        shell_layout.addWidget(self.output_dir_input)

        self.monitor_check = QCheckBox("Notify when new SD images appear in the output folder")
        shell_layout.addWidget(self.monitor_check)
        self.sd_options_refresh_button = QPushButton("Refresh SD samplers/checkpoints")
        self.sd_options_refresh_button.clicked.connect(self._refresh_sd_options_clicked)
        shell_layout.addWidget(self.sd_options_refresh_button)

        self.status_label = QLabel("Configure um backend e clique em Test.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED}; border: none;")
        self.status_row = QWidget()
        status_row_layout = QHBoxLayout(self.status_row)
        status_row_layout.setContentsMargins(0, 0, 0, 0)
        status_row_layout.setSpacing(8)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_row_layout.addWidget(self.status_label, 1)

        def _icon_button(label: str, tooltip: str, callback) -> QToolButton:
            btn = QToolButton()
            btn.setText(label)
            btn.setFont(QFont(self.ui_font, 14))
            btn.setToolTip(tooltip)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(
                f"""
                QToolButton {{
                    border: none;
                    background: transparent;
                    color: {UI_TEXT_STRONG};
                    padding: 4px;
                    border-radius: 6px;
                }}
                QToolButton:hover {{
                    background: {HOVER_BG};
                }}
                """
            )
            btn.clicked.connect(callback)
            return btn

        self.copy_status_button = _icon_button("\ue14d", "Copy status to clipboard", self._copy_backend_errors)
        status_row_layout.addWidget(self.copy_status_button)
        self.copy_log_button = _icon_button("\ueb50", "Copy error log", self._copy_error_log)
        status_row_layout.addWidget(self.copy_log_button)
        shell_layout.addWidget(self.status_row)
        self.validation_badge = QLabel("○ Not validated")
        self.validation_badge.setStyleSheet(f"color: {UI_TEXT_MUTED}; font-weight: 600; font-size: 11px; border: none;")
        shell_layout.addWidget(self.validation_badge)

        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.hide()
        shell_layout.addWidget(self.download_progress)

        self.download_progress_label = QLabel("")
        self.download_progress_label.setStyleSheet(f"color: {UI_ICON_DIM};")
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

        self.install_kokoclone_button = QPushButton("Install KokoClone (voice cloning TTS)")
        self.install_kokoclone_button.clicked.connect(self._install_kokoclone)
        actions.addWidget(self.install_kokoclone_button)

        actions.addStretch(1)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._save_current_backend)
        self.save_button.setStyleSheet(
            f"""
            QPushButton {{
                min-height: 42px;
                min-width: 110px;
                background: {ACCENT};
                color: {THEME.active_text};
                border: 1px solid {ACCENT};
                border-radius: 21px;
                padding: 0 20px;
                font-family: {ui_font};
                font-size: 15px;
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
        self.close_button.setStyleSheet(
            f"""
            QPushButton {{
                min-height: 42px;
                min-width: 110px;
                background: {CARD_BG_SOFT};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 21px;
                padding: 0 20px;
                font-family: {ui_font};
                font-size: 15px;
                font-weight: {_button_css_weight(ui_font)};
            }}
            QPushButton:hover {{
                background: {HOVER_BG};
                border: 1px solid {BORDER_ACCENT};
            }}
            """
        )
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        shell_layout.addLayout(actions)

        # --- Skills tab ---
        self._tabs.addTab(self._build_skills_tab(), "Skills")

        _apply_antialias_font(self)
        self._download_manager = get_tts_download_manager()
        self._gguf_download_manager = get_gguf_download_manager()
        self._tts_preview_worker: TtsSynthesisWorker | None = None
        self._preview_audio_output: QAudioOutput | None = None
        self._preview_media_player: QMediaPlayer | None = None
        self._runtime_worker: TtsRuntimeInstallWorker | None = None
        self._pocket_voice_worker: PocketPresetVoiceWorker | None = None
        self._download_manager.progress_changed.connect(self._on_tts_download_progress)
        self._download_manager.download_finished.connect(self._on_tts_download_finished)
        self._download_manager.download_failed.connect(self._on_tts_download_failed)
        self._gguf_download_manager.progress_changed.connect(self._on_gguf_download_progress)
        self._gguf_download_manager.download_finished.connect(self._on_gguf_download_finished)
        self._gguf_download_manager.download_failed.connect(self._on_gguf_download_failed)
        self.gguf_path_input.textChanged.connect(lambda _=None: (self._refresh_gguf_info(), self._refresh_kobold_gemma4_audio_toggle()))
        self.binary_path_input.textChanged.connect(lambda _=None: self._refresh_binary_info())
        self._pending_kobold_ready_profile: str = ""
        self._pending_kobold_ready_host: str = ""
        self._kobold_ready_timer = QTimer(self)
        self._kobold_ready_timer.setInterval(1500)
        self._kobold_ready_timer.timeout.connect(self._poll_pending_kobold_ready)
        self._populate_gguf_gallery()
        self._load_selected_backend()

    # ------------------------------------------------------------------ skills

    def _load_skills_settings(self) -> dict:
        try:
            return json.loads(SKILLS_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_skills_settings(self, data: dict) -> None:
        AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _build_skills_tab(self) -> QWidget:
        """Build the Skills configuration tab."""
        settings = self._load_skills_settings()
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # Global toggle
        global_check = QCheckBox("Enable skills (tool calling) for AI responses")
        global_check.setChecked(bool(settings.get("skills_enabled", True)))
        global_check.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        layout.addWidget(global_check)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_SOFT};")
        layout.addWidget(sep)

        # ── Apprise ──────────────────────────────────────────────────────────
        apprise_cfg = settings.get("apprise", {})
        apprise_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        apprise_layout = QVBoxLayout(apprise_frame)
        apprise_layout.setContentsMargins(14, 12, 14, 12)
        apprise_layout.setSpacing(8)

        apprise_header = QHBoxLayout()
        apprise_title = QLabel("Apprise — Notifications")
        apprise_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        apprise_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        apprise_header.addWidget(apprise_title)
        apprise_header.addStretch()
        apprise_enabled = QCheckBox("Enabled")
        apprise_enabled.setChecked(bool(apprise_cfg.get("enabled", True)))
        apprise_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        apprise_header.addWidget(apprise_enabled)
        apprise_layout.addLayout(apprise_header)

        apprise_desc = QLabel(
            "One URL per line. Supports Telegram, Discord, Slack, email, Pushover, ntfy, and 100+ more.\n"
            "Format: tgram://bottoken/chatid  •  discord://webhook_id/token  •  ntfy://topic"
        )
        apprise_desc.setWordWrap(True)
        apprise_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        apprise_layout.addWidget(apprise_desc)

        apprise_urls_edit = QTextEdit()
        apprise_urls_edit.setPlaceholderText("tgram://bottoken/chatid\ndiscord://webhook_id/token")
        apprise_urls_edit.setFixedHeight(90)
        raw_urls = apprise_cfg.get("urls", [])
        if isinstance(raw_urls, list):
            apprise_urls_edit.setPlainText("\n".join(str(u) for u in raw_urls))
        else:
            apprise_urls_edit.setPlainText(str(raw_urls))
        apprise_urls_edit.setStyleSheet(
            f"background: {INPUT_BG}; color: {UI_TEXT_STRONG}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 10px; padding: 6px;"
        )
        apprise_layout.addWidget(apprise_urls_edit)
        layout.addWidget(apprise_frame)

        # ── Docker ───────────────────────────────────────────────────────────
        docker_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        docker_layout = QVBoxLayout(docker_frame)
        docker_layout.setContentsMargins(14, 12, 14, 12)
        docker_layout.setSpacing(6)
        docker_header = QHBoxLayout()
        docker_title = QLabel("Docker")
        docker_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        docker_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        docker_header.addWidget(docker_title)
        docker_header.addStretch()
        docker_enabled = QCheckBox("Enabled")
        docker_enabled.setChecked(bool(settings.get("docker", {}).get("enabled", True)))
        docker_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        docker_header.addWidget(docker_enabled)
        docker_layout.addLayout(docker_header)
        docker_desc = QLabel("Requires docker CLI in PATH. No credentials needed for local socket.")
        docker_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        docker_layout.addWidget(docker_desc)
        layout.addWidget(docker_frame)

        # ── Mail ─────────────────────────────────────────────────────────────
        mail_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        mail_layout = QVBoxLayout(mail_frame)
        mail_layout.setContentsMargins(14, 12, 14, 12)
        mail_layout.setSpacing(6)
        mail_header = QHBoxLayout()
        mail_title = QLabel("Mail (notmuch + msmtp)")
        mail_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        mail_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        mail_header.addWidget(mail_title)
        mail_header.addStretch()
        mail_enabled = QCheckBox("Enabled")
        mail_enabled.setChecked(bool(settings.get("mail", {}).get("enabled", True)))
        mail_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        mail_header.addWidget(mail_enabled)
        mail_layout.addLayout(mail_header)
        mail_desc = QLabel("Requires notmuch (read/search) and msmtp (send) in PATH.")
        mail_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        mail_layout.addWidget(mail_desc)
        layout.addWidget(mail_frame)

        # ── KDE Connect ──────────────────────────────────────────────────────
        kde_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        kde_layout = QVBoxLayout(kde_frame)
        kde_layout.setContentsMargins(14, 12, 14, 12)
        kde_layout.setSpacing(6)
        kde_header = QHBoxLayout()
        kde_title = QLabel("KDE Connect")
        kde_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        kde_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        kde_header.addWidget(kde_title)
        kde_header.addStretch()
        kde_enabled = QCheckBox("Enabled")
        kde_enabled.setChecked(bool(settings.get("kdeconnect", {}).get("enabled", True)))
        kde_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        kde_header.addWidget(kde_enabled)
        kde_layout.addLayout(kde_header)
        kde_desc = QLabel("Requires kdeconnect-cli in PATH and a paired device.")
        kde_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        kde_layout.addWidget(kde_desc)
        layout.addWidget(kde_frame)

        # ── PC Sensors ───────────────────────────────────────────────────────
        sensors_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        sensors_layout = QVBoxLayout(sensors_frame)
        sensors_layout.setContentsMargins(14, 12, 14, 12)
        sensors_layout.setSpacing(6)
        sensors_header = QHBoxLayout()
        sensors_title = QLabel("PC Sensors")
        sensors_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        sensors_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        sensors_header.addWidget(sensors_title)
        sensors_header.addStretch()
        sensors_enabled = QCheckBox("Enabled")
        sensors_enabled.setChecked(bool(settings.get("pc_sensors", {}).get("enabled", True)))
        sensors_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        sensors_header.addWidget(sensors_enabled)
        sensors_layout.addLayout(sensors_header)
        sensors_desc = QLabel("Requires psutil (pip install psutil). GPU needs nvidia-smi. Temps need lm-sensors.")
        sensors_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        sensors_layout.addWidget(sensors_desc)
        layout.addWidget(sensors_frame)

        # ── Desktop ──────────────────────────────────────────────────────────
        desktop_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        desktop_layout = QVBoxLayout(desktop_frame)
        desktop_layout.setContentsMargins(14, 12, 14, 12)
        desktop_layout.setSpacing(6)
        desktop_header = QHBoxLayout()
        desktop_title = QLabel("Hanauta Desktop (i3)")
        desktop_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        desktop_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        desktop_header.addWidget(desktop_title)
        desktop_header.addStretch()
        desktop_enabled = QCheckBox("Enabled")
        desktop_enabled.setChecked(bool(settings.get("hanauta_desktop", {}).get("enabled", True)))
        desktop_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        desktop_header.addWidget(desktop_enabled)
        desktop_layout.addLayout(desktop_header)
        desktop_desc = QLabel("Requires i3-msg in PATH. Controls workspaces, windows, wallpaper, notifications.")
        desktop_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        desktop_layout.addWidget(desktop_desc)
        layout.addWidget(desktop_frame)

        # ── Emotion Engine ────────────────────────────────────────────────────
        emotion_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        emotion_layout = QVBoxLayout(emotion_frame)
        emotion_layout.setContentsMargins(14, 12, 14, 12)
        emotion_layout.setSpacing(6)
        emotion_header = QHBoxLayout()
        emotion_title = QLabel("Emotion Engine")
        emotion_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        emotion_title.setStyleSheet(f"color: {UI_TEXT_STRONG}; border: none;")
        emotion_header.addWidget(emotion_title)
        emotion_header.addStretch()
        emotion_enabled = QCheckBox("Enabled")
        emotion_enabled.setChecked(bool(settings.get("emotion_engine", {}).get("enabled", True)))
        emotion_enabled.setStyleSheet(f"color: {UI_TEXT_STRONG};")
        emotion_header.addWidget(emotion_enabled)
        emotion_layout.addLayout(emotion_header)
        emotion_desc = QLabel(
            "Tracks the user's emotional state across the conversation. "
            "All skills and the AI's tone adapt automatically. No external dependencies."
        )
        emotion_desc.setWordWrap(True)
        emotion_desc.setStyleSheet(f"color: {UI_ICON_DIM}; border: none; font-size: 11px;")
        emotion_layout.addWidget(emotion_desc)
        layout.addWidget(emotion_frame)

        # ── Home Assistant ────────────────────────────────────────────────────
        ha_cfg = settings.get("homeassistant", {})
        ha_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        ha_layout = QVBoxLayout(ha_frame)
        ha_layout.setContentsMargins(14, 12, 14, 12)
        ha_layout.setSpacing(8)

        ha_header = QHBoxLayout()
        ha_title = QLabel("Home Assistant")
        ha_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        ha_title.setStyleSheet(f"color: {TEXT}; border: none;")
        ha_header.addWidget(ha_title)
        ha_header.addStretch()
        ha_enabled = QCheckBox("Enabled")
        ha_enabled.setChecked(bool(ha_cfg.get("enabled", True)))
        ha_enabled.setStyleSheet(f"color: {TEXT};")
        ha_header.addWidget(ha_enabled)
        ha_layout.addLayout(ha_header)

        ha_desc = QLabel(
            "Control lights, switches, climate, covers, automations and more "
            "via the Home Assistant REST API."
        )
        ha_desc.setWordWrap(True)
        ha_desc.setStyleSheet(f"color: {TEXT_DIM}; border: none; font-size: 11px;")
        ha_layout.addWidget(ha_desc)

        # URL + port row
        ha_url_row = QHBoxLayout()
        ha_url_row.setSpacing(8)
        ha_url_input = QLineEdit()
        ha_url_input.setPlaceholderText("http://homeassistant.local")
        ha_url_input.setText(str(ha_cfg.get("url", "")).strip())
        ha_url_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        ha_url_row.addWidget(ha_url_input, 3)
        ha_port_input = QLineEdit()
        ha_port_input.setPlaceholderText("8123")
        ha_port_input.setMaximumWidth(90)
        ha_port_input.setText(str(ha_cfg.get("port", "")).strip())
        ha_port_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        ha_url_row.addWidget(ha_port_input, 1)
        ha_layout.addLayout(ha_url_row)

        # Token
        ha_token_input = QLineEdit()
        ha_token_input.setPlaceholderText("Long-lived access token (stored encrypted)")
        ha_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        _ha_stored_token = secure_load_secret("skills:homeassistant:token")
        ha_token_input.setText(_ha_stored_token)
        ha_token_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        ha_layout.addWidget(ha_token_input)

        # Test connection button
        ha_test_row = QHBoxLayout()
        ha_test_btn = QPushButton("Test connection")
        ha_test_btn.setStyleSheet(
            f"background: {CARD_BG_SOFT}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 6px 14px;"
        )
        ha_status_label = QLabel("")
        ha_status_label.setStyleSheet(f"color: {TEXT_DIM}; border: none; font-size: 11px;")

        def _test_ha() -> None:
            url = ha_url_input.text().strip().rstrip("/")
            port = ha_port_input.text().strip()
            token = ha_token_input.text().strip()
            if port:
                from urllib.parse import urlparse
                parsed = urlparse(url if "://" in url else f"http://{url}")
                url = f"{parsed.scheme}://{parsed.hostname}:{port}"
            if not url or not token:
                ha_status_label.setText("Set URL and token first.")
                return
            try:
                from urllib import request as _req
                req = _req.Request(
                    f"{url}/api/",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with _req.urlopen(req, timeout=5) as resp:
                    data = __import__('json').loads(resp.read())
                msg = data.get("message", "Connected")
                ha_status_label.setText(f"✓ {msg}")
                ha_status_label.setStyleSheet(f"color: #7dff9a; border: none; font-size: 11px;")
            except Exception as exc:
                ha_status_label.setText(f"✗ {exc}")
                ha_status_label.setStyleSheet(f"color: #ff7d7d; border: none; font-size: 11px;")

        ha_test_btn.clicked.connect(_test_ha)
        ha_test_row.addWidget(ha_test_btn)
        ha_test_row.addWidget(ha_status_label, 1)
        ha_layout.addLayout(ha_test_row)
        layout.addWidget(ha_frame)

        # ── Calendar ───────────────────────────────────────────────────────────
        cal_cfg = settings.get("calendar", {})
        cal_frame = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.7), border=BORDER_SOFT, radius=16)
        cal_layout = QVBoxLayout(cal_frame)
        cal_layout.setContentsMargins(14, 12, 14, 12)
        cal_layout.setSpacing(8)

        cal_header = QHBoxLayout()
        cal_title = QLabel("Calendar")
        cal_title.setFont(QFont(self.ui_font, 11, QFont.Weight.DemiBold))
        cal_title.setStyleSheet(f"color: {TEXT}; border: none;")
        cal_header.addWidget(cal_title)
        cal_header.addStretch()
        cal_enabled = QCheckBox("Enabled")
        cal_enabled.setChecked(bool(cal_cfg.get("enabled", True)))
        cal_enabled.setStyleSheet(f"color: {TEXT};")
        cal_header.addWidget(cal_enabled)
        cal_layout.addLayout(cal_header)

        cal_desc = QLabel(
            "Read and create events via CalDAV (Nextcloud, Radicale, Google, iCloud) "
            "or a local ICS file."
        )
        cal_desc.setWordWrap(True)
        cal_desc.setStyleSheet(f"color: {TEXT_DIM}; border: none; font-size: 11px;")
        cal_layout.addWidget(cal_desc)

        # Backend selector
        cal_backend_row = QHBoxLayout()
        cal_backend_row.setSpacing(8)
        cal_backend_label = QLabel("Backend")
        cal_backend_label.setStyleSheet(f"color: {TEXT_MID}; border: none;")
        cal_backend_row.addWidget(cal_backend_label)
        cal_backend_combo = QComboBox()
        cal_backend_combo.addItem("CalDAV", "caldav")
        cal_backend_combo.addItem("Local ICS file", "ics")
        stored_backend = str(cal_cfg.get("backend", "caldav"))
        cal_backend_combo.setCurrentIndex(0 if stored_backend == "caldav" else 1)
        cal_backend_combo.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 6px 12px;"
        )
        cal_backend_row.addWidget(cal_backend_combo, 1)
        cal_layout.addLayout(cal_backend_row)

        # CalDAV URL
        cal_url_input = QLineEdit()
        cal_url_input.setPlaceholderText("CalDAV URL, e.g. https://nextcloud.example.com/remote.php/dav/calendars/user/")
        cal_url_input.setText(str(cal_cfg.get("url", "")).strip())
        cal_url_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        cal_layout.addWidget(cal_url_input)

        # Username + password row
        cal_creds_row = QHBoxLayout()
        cal_creds_row.setSpacing(8)
        cal_user_input = QLineEdit()
        cal_user_input.setPlaceholderText("Username")
        cal_user_input.setText(str(cal_cfg.get("username", "")).strip())
        cal_user_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        cal_creds_row.addWidget(cal_user_input, 1)
        cal_pass_input = QLineEdit()
        cal_pass_input.setPlaceholderText("Password (stored encrypted)")
        cal_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        cal_pass_input.setText(secure_load_secret("skills:calendar:password"))
        cal_pass_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        cal_creds_row.addWidget(cal_pass_input, 1)
        cal_layout.addLayout(cal_creds_row)

        # ICS file path
        cal_ics_input = ClickableLineEdit()
        cal_ics_input.setPlaceholderText("Local ICS file path (click to browse)")
        cal_ics_input.setText(str(cal_cfg.get("ics_path", "")).strip())
        cal_ics_input.setStyleSheet(
            f"background: {INPUT_BG}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 8px 12px;"
        )
        cal_ics_input.clicked.connect(
            lambda: cal_ics_input.setText(
                QFileDialog.getOpenFileName(None, "Select ICS file", str(Path.home()), "Calendar files (*.ics)")[0]
                or cal_ics_input.text()
            )
        )
        cal_layout.addWidget(cal_ics_input)

        # Show/hide fields based on backend
        def _on_cal_backend_changed() -> None:
            is_caldav = cal_backend_combo.currentData() == "caldav"
            cal_url_input.setVisible(is_caldav)
            cal_creds_row_widget = cal_url_input.parent()
            for w in [cal_user_input, cal_pass_input]:
                w.setVisible(is_caldav)
            cal_ics_input.setVisible(not is_caldav)

        cal_backend_combo.currentIndexChanged.connect(_on_cal_backend_changed)
        _on_cal_backend_changed()

        # Test button
        cal_test_row = QHBoxLayout()
        cal_test_btn = QPushButton("Test connection")
        cal_test_btn.setStyleSheet(
            f"background: {CARD_BG_SOFT}; color: {TEXT}; border: 1px solid {BORDER_SOFT};"
            f"border-radius: 18px; padding: 6px 14px;"
        )
        cal_status_label = QLabel("")
        cal_status_label.setStyleSheet(f"color: {TEXT_DIM}; border: none; font-size: 11px;")

        def _test_cal() -> None:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "skills.calendar",
                Path(__file__).parent.parent.parent / "skills" / "calendar.py",
            )
            _mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            test_cfg = {
                "enabled": True,
                "backend": cal_backend_combo.currentData(),
                "url": cal_url_input.text().strip(),
                "username": cal_user_input.text().strip(),
                "password": cal_pass_input.text().strip(),
                "ics_path": cal_ics_input.text().strip(),
            }
            try:
                if test_cfg["backend"] == "ics":
                    p = Path(test_cfg["ics_path"]).expanduser()
                    if not p.exists():
                        raise FileNotFoundError(f"File not found: {p}")
                    events = _mod._read_ics_file(test_cfg)
                    cal_status_label.setText(f"✓ {len(events)} events found in ICS file")
                else:
                    cals = _mod._caldav_list_calendars(test_cfg)
                    cal_status_label.setText(f"✓ Connected — {len(cals)} calendar(s)")
                cal_status_label.setStyleSheet("color: #7dff9a; border: none; font-size: 11px;")
            except Exception as exc:
                cal_status_label.setText(f"✗ {exc}")
                cal_status_label.setStyleSheet("color: #ff7d7d; border: none; font-size: 11px;")

        cal_test_btn.clicked.connect(_test_cal)
        cal_test_row.addWidget(cal_test_btn)
        cal_test_row.addWidget(cal_status_label, 1)
        cal_layout.addLayout(cal_test_row)
        layout.addWidget(cal_frame)

        layout.addStretch()

        # Save button
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_skills_btn = QPushButton("Save Skills Settings")
        save_skills_btn.setStyleSheet(
            f"""
            QPushButton {{
                min-height: 38px; min-width: 160px;
                background: {ACCENT}; color: {THEME.active_text};
                border: 1px solid {ACCENT}; border-radius: 19px;
                padding: 0 18px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {mix(ACCENT, '#ffffff', 0.08)}; }}
            """
        )

        def _save_skills() -> None:
            urls = [u.strip() for u in apprise_urls_edit.toPlainText().splitlines() if u.strip()]
            # Build HA URL with port
            ha_url = ha_url_input.text().strip().rstrip("/")
            ha_port = ha_port_input.text().strip()
            if ha_port:
                from urllib.parse import urlparse
                parsed = urlparse(ha_url if "://" in ha_url else f"http://{ha_url}")
                ha_url = f"{parsed.scheme}://{parsed.hostname}:{ha_port}"
            # Save token encrypted
            ha_token = ha_token_input.text().strip()
            if ha_token:
                secure_store_secret("skills:homeassistant:token", ha_token)
            data = self._load_skills_settings()
            data["skills_enabled"] = global_check.isChecked()
            data["apprise"] = {"enabled": apprise_enabled.isChecked(), "urls": urls}
            data["docker"] = {"enabled": docker_enabled.isChecked()}
            data["mail"] = {"enabled": mail_enabled.isChecked()}
            data["kdeconnect"] = {"enabled": kde_enabled.isChecked()}
            data["pc_sensors"] = {"enabled": sensors_enabled.isChecked()}
            data["hanauta_desktop"] = {"enabled": desktop_enabled.isChecked()}
            data["emotion_engine"] = {"enabled": emotion_enabled.isChecked()}
            data["homeassistant"] = {
                "enabled": ha_enabled.isChecked(),
                "url": ha_url,
                "port": ha_port_input.text().strip(),
            }
            # Save calendar password encrypted
            cal_pw = cal_pass_input.text().strip()
            if cal_pw:
                secure_store_secret("skills:calendar:password", cal_pw)
            data["calendar"] = {
                "enabled": cal_enabled.isChecked(),
                "backend": cal_backend_combo.currentData(),
                "url": cal_url_input.text().strip(),
                "username": cal_user_input.text().strip(),
                "ics_path": cal_ics_input.text().strip(),
            }
            self._save_skills_settings(data)
            save_skills_btn.setText("Saved ✓")
            QTimer.singleShot(2000, lambda: save_skills_btn.setText("Save Skills Settings"))

        save_skills_btn.clicked.connect(_save_skills)
        save_row.addWidget(save_skills_btn)
        outer.addLayout(save_row)

        return container

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
                "jinja": bool(self.kobold_jinja_check.isChecked()),
                "gemma4_audio_stt_enabled": bool(self.kobold_gemma4_audio_stt_check.isChecked()) if hasattr(self, "kobold_gemma4_audio_stt_check") else False,
                "test_prompt": self.kobold_test_prompt_input.text().strip(),
                "device": str(self.device_combo.currentData()),
                "token_saver_enabled": bool(self.token_saver_check.isChecked()),
                "voice_barge_in_enabled": bool(self.voice_barge_in_check.isChecked()),
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
        if profile.key == "koboldcpp":
            gguf_name = Path(str(existing.get("gguf_path", "")).strip()).name
            if not _looks_like_gemma4_model_name(gguf_name):
                existing["gemma4_audio_stt_enabled"] = False
                existing["gemma4_audio_supported"] = False
                existing["gemma4_audio_checked_at"] = 0.0
                existing["gemma4_audio_checked_gguf"] = ""
            else:
                checked_gguf = str(existing.get("gemma4_audio_checked_gguf", "")).strip()
                if checked_gguf and checked_gguf != gguf_name:
                    existing["gemma4_audio_supported"] = False
                    existing["gemma4_audio_checked_at"] = 0.0
                    existing["gemma4_audio_checked_gguf"] = ""
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
        self.kobold_jinja_check.setChecked(bool(payload.get("jinja", False)))
        self.kobold_gemma4_audio_stt_check.setChecked(bool(payload.get("gemma4_audio_stt_enabled", False)))
        self.kobold_test_prompt_input.setText(str(payload.get("test_prompt", "Tell me that KoboldCpp is working.")))
        self.token_saver_check.setChecked(bool(payload.get("token_saver_enabled", True)))
        self.voice_barge_in_check.setChecked(bool(payload.get("voice_barge_in_enabled", True)))
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
        is_text = profile.provider in {"openai", "openai_compat", "ollama"}
        device_enabled = is_kobold or is_tts
        self.sd_auth_user_input.setVisible(is_sd)
        self.sd_auth_pass_input.setVisible(is_sd)
        self.binary_path_input.setVisible(is_kobold or (is_tts and mode == "local_onnx"))
        self.binary_info_label.setVisible(self.binary_path_input.isVisible())
        self.tts_mode_combo.setVisible(is_tts and profile.key != "pockettts")
        self.pocket_mode_row.setVisible(is_tts and profile.key == "pockettts")
        self.tts_repo_input.setVisible(is_tts and mode == "local_onnx")
        self.tts_bundle_url_input.setVisible(is_tts and mode == "local_onnx")
        show_tts_server_controls = is_tts and profile.key in {"kokorotts", "pockettts"} and mode == "local_onnx"
        show_kobold_controls = is_kobold
        self.tts_server_command_input.setVisible(show_tts_server_controls)
        self.tts_server_row.setVisible(show_tts_server_controls)
        self.kokoro_autostart_check.setVisible(show_tts_server_controls)
        self.kobold_server_row.setVisible(show_kobold_controls)
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
        self.gguf_info_label.setVisible(is_kobold)
        self.gguf_download_progress.setVisible(False if not is_kobold else self.gguf_download_progress.isVisible())
        self.gguf_download_progress_label.setVisible(False if not is_kobold else self.gguf_download_progress_label.isVisible())
        self.gguf_gallery_title.setVisible(is_kobold)
        self.gguf_gallery_scroll.setVisible(is_kobold)
        self.text_model_path_input.setVisible(is_kobold)
        self.mmproj_path_input.setVisible(is_kobold)
        self.kobold_jinja_check.setVisible(is_kobold)
        self.kobold_gemma4_audio_stt_check.setVisible(is_kobold)
        self.kobold_test_prompt_input.setVisible(is_kobold)
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
        self.token_saver_check.setVisible(is_text)
        self.voice_barge_in_check.setVisible(is_tts)
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
        if show_kobold_controls:
            self._refresh_kobold_status(payload)
        self._refresh_download_progress(profile.key if is_tts else "")
        if is_tts:
            self._apply_tts_mode_visibility()
        tested = bool(payload.get("tested", False))
        last_status = str(payload.get("last_status", "Configure um backend e clique em Test."))
        self.status_label.setText(last_status if last_status else "Configure um backend e clique em Test.")
        self.status_label.setStyleSheet(f"color: {ACCENT if tested else UI_TEXT_MUTED}; border: none;")
        self.validation_badge.setText("✓ Validated" if tested else "○ Not validated")
        self.validation_badge.setStyleSheet(
            f"color: {ACCENT if tested else UI_ICON_DIM}; font-weight: 700; border: none;"
        )
        self._refresh_kobold_gemma4_audio_toggle()

    def _test_current_backend(self) -> None:
        profile = self._selected_profile()
        if profile.provider == "tts_local" and profile.key == "pockettts":
            self._test_tts_synthesis()
            return
        payload = self._current_payload()
        ok, message = validate_backend(profile, payload)
        if ok and profile.key == "koboldcpp":
            host = str(payload.get("host", profile.host)).strip()
            if not host or not _openai_compat_alive(host):
                ok = False
                message = "Start KoboldCpp first so the Test prompt can reach the API."
            else:
                test_prompt = str(payload.get("test_prompt", "")).strip() or "Tell me that KoboldCpp is working."
                try:
                    reply = _generate_openai_style_reply(
                        host,
                        str(payload.get("model", profile.model)).strip() or profile.model,
                        [{"role": "user", "content": test_prompt}],
                    ).strip()
                    preview = reply[:220] + ("..." if len(reply) > 220 else "")
                    message = f"Reply ok: {preview}" if preview else "KoboldCpp answered successfully."
                    gguf_name = Path(str(payload.get("gguf_path", "")).strip()).name
                    if bool(payload.get("gemma4_audio_stt_enabled", False)) and _looks_like_gemma4_model_name(gguf_name):
                        ok_audio = _probe_openai_style_audio_input_support(
                            host,
                            str(payload.get("model", profile.model)).strip() or profile.model,
                            secure_load_secret(f"{profile.key}:api_key").strip(),
                        )
                        payload["gemma4_audio_supported"] = bool(ok_audio)
                        payload["gemma4_audio_checked_at"] = float(time.time())
                        payload["gemma4_audio_checked_gguf"] = gguf_name
                        suffix = "supported" if ok_audio else "NOT supported"
                        message = f"{message} (Gemma 4 audio: {suffix})"
                except Exception as exc:
                    ok = False
                    message = str(exc).strip() or "KoboldCpp test failed."
        payload["tested"] = ok
        payload["last_status"] = message
        self.settings[profile.key] = payload
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")
        self.validation_badge.setText("✓ Validated" if ok else "○ Not validated")
        self.validation_badge.setStyleSheet(
            f"color: {ACCENT if ok else ACCENT_ALT}; font-weight: 700; border: none;"
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
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
        if profile.key == "koboldcpp":
            self._refresh_kobold_status(payload)

    def _install_kokoclone(self) -> None:
        profile = self._selected_profile()
        if profile.key != "kokoclone":
            self.status_label.setText("Select the KokoClone backend first.")
            return
        self.install_kokoclone_button.setEnabled(False)
        self.install_kokoclone_button.setText("Installing KokoClone\u2026")
        self.status_label.setText("Installing KokoClone (this may take several minutes)\u2026")

        from PyQt6.QtCore import QThread, pyqtSignal as _sig

        class _Worker(QThread):
            progress = _sig(int, str)
            finished_ok = _sig()
            failed = _sig(str)

            def run(self) -> None:
                try:
                    from .tts import _ensure_kokoclone_installed
                    _ensure_kokoclone_installed(
                        progress_cb=lambda done, total, label: self.progress.emit(
                            int(done / max(1, total) * 100), label
                        )
                    )
                    self.finished_ok.emit()
                except Exception as exc:
                    self.failed.emit(str(exc))

        worker = _Worker(self)
        self._kokoclone_install_worker = worker

        def _on_progress(pct: int, label: str) -> None:
            self.download_progress.setValue(pct)
            self.download_progress.show()
            self.download_progress_label.setText(label)
            self.download_progress_label.show()

        def _on_ok() -> None:
            self.install_kokoclone_button.setEnabled(True)
            self.install_kokoclone_button.setText("Install KokoClone (voice cloning TTS)")
            self.download_progress.hide()
            self.download_progress_label.hide()
            self.status_label.setText("KokoClone installed successfully.")
            self.status_label.setStyleSheet(f"color: {ACCENT};")

        def _on_fail(msg: str) -> None:
            self.install_kokoclone_button.setEnabled(True)
            self.install_kokoclone_button.setText("Install KokoClone (voice cloning TTS)")
            self.download_progress.hide()
            self.download_progress_label.hide()
            self.status_label.setText(f"KokoClone install failed: {msg[:200]}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

        worker.progress.connect(_on_progress)
        worker.finished_ok.connect(_on_ok)
        worker.failed.connect(_on_fail)
        worker.start()

    def _install_pockettts(self) -> None:
        profile = self._selected_profile()
        if profile.key != "pockettts":
            return
        payload = self._current_payload()
        started = self._download_manager.start(profile, payload, install_server=True)
        if not started:
            self.status_label.setText("PocketTTS install is already running.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            self._refresh_download_progress(profile.key)
            return
        self.status_label.setText("PocketTTS install started in background (server + model files + runtime + voices).")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
        self._refresh_download_progress(profile.key)

    def _install_tts_runtime_clicked(self) -> None:
        profile = self._selected_profile()
        if profile.provider != "tts_local":
            return
        if self._runtime_worker is not None and self._runtime_worker.isRunning():
            self.status_label.setText("A runtime install is already running.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        worker = TtsRuntimeInstallWorker(profile.key)
        self._runtime_worker = worker
        self.download_progress.show()
        self.download_progress_label.show()
        self.download_progress.setValue(0)
        self.download_progress_label.setText("Preparing runtime install…")
        self.status_label.setText(f"Installing runtime deps for {profile.label}…")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

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
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        payload = self._current_payload()
        started = self._download_manager.start(profile, payload)
        if not started:
            self.status_label.setText("A model download is already running for this backend.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            self._refresh_download_progress(profile.key)
            return
        self.status_label.setText("Background model download started. You can close this dialog safely.")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
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

    def _copy_error_log(self) -> None:
        try:
            text = AI_POPUP_ERROR_LOG_FILE.read_text(encoding="utf-8")
        except Exception as exc:
            self.status_label.setText(f"Unable to read error log: {exc}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")
            return
        if not text.strip():
            send_desktop_notification("Clipboard", "The error log is currently empty.")
            return
        QGuiApplication.clipboard().setText(text)
        send_desktop_notification("Clipboard", "Copied error log.")

    def _styled_path_dialog(self) -> QFileDialog:
        dialog = QFileDialog(self)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet(
            f"""
            QFileDialog, QWidget {{
                background: {CARD_BG};
                color: {UI_TEXT_STRONG};
            }}
            QLineEdit, QComboBox {{
                background: {INPUT_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QListView, QTreeView {{
                background: {rgba(PANEL_BG, 0.96)};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
            }}
            QListView::item:selected, QTreeView::item:selected {{
                background: {ACCENT_SOFT};
                color: {UI_TEXT_STRONG};
            }}
            QPushButton {{
                min-height: 34px;
                background: {CARD_BG_SOFT};
                color: {UI_TEXT_STRONG};
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
        return dialog

    def _pick_existing_file(self, title: str, start_path: str, filters: list[str]) -> str:
        dialog = self._styled_path_dialog()
        dialog.setWindowTitle(title)
        base = Path(start_path).expanduser() if start_path.strip() else Path.home()
        dialog.setDirectory(str(base.parent if base.exists() and base.is_file() else base))
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilters(filters)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        files = dialog.selectedFiles()
        return files[0] if files else ""

    def _pick_existing_dir(self, title: str, start_path: str) -> str:
        dialog = self._styled_path_dialog()
        dialog.setWindowTitle(title)
        base = Path(start_path).expanduser() if start_path.strip() else Path.home()
        dialog.setDirectory(str(base if base.exists() and base.is_dir() else base.parent if base.parent.exists() else Path.home()))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        files = dialog.selectedFiles()
        return files[0] if files else ""

    def _browse_binary_path(self) -> None:
        profile = self._selected_profile()
        current = self.binary_path_input.text().strip()
        if profile.key == "koboldcpp":
            picked = self._pick_existing_file(
                "Select KoboldCpp binary",
                current,
                ["Executable files (*)", "All files (*)"],
            )
        else:
            picked = self._pick_existing_dir("Select local model folder", current)
        if picked:
            self.binary_path_input.setText(picked)

    def _browse_gguf_path(self) -> None:
        picked = self._pick_existing_file(
            "Select GGUF model",
            self.gguf_path_input.text().strip(),
            ["GGUF models (*.gguf)", "All files (*)"],
        )
        if picked:
            self.gguf_path_input.setText(picked)

    def _browse_text_model_path(self) -> None:
        current = self.text_model_path_input.text().strip()
        picked = self._pick_existing_file(
            "Select text model path",
            current,
            ["Model files (*)", "All files (*)"],
        )
        if not picked and current:
            picked = self._pick_existing_dir("Select text model folder", current)
        if picked:
            self.text_model_path_input.setText(picked)

    def _browse_mmproj_path(self) -> None:
        picked = self._pick_existing_file(
            "Select mmproj file",
            self.mmproj_path_input.text().strip(),
            ["Projector files (*)", "All files (*)"],
        )
        if picked:
            self.mmproj_path_input.setText(picked)

    def _browse_output_dir(self) -> None:
        picked = self._pick_existing_dir("Select SD output folder", self.output_dir_input.text().strip())
        if picked:
            self.output_dir_input.setText(picked)

    def _refresh_kobold_status(self, payload: dict[str, object]) -> None:
        active, message = _koboldcpp_status(payload)
        self.kobold_server_status_label.setText(f"Server status: {message}")
        self.kobold_server_status_label.setStyleSheet(f"color: {ACCENT if active else UI_ICON_DIM}; border: none;")

    def _persist_selected_backend_payload(self, payload: dict[str, object]) -> None:
        profile = self._selected_profile()
        self.settings[profile.key] = payload
        save_backend_settings(self.settings)

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
        payload = self._current_payload()
        display_model = model_name or label
        payload["last_status"] = f"{label} ready — {display_model}"
        self._persist_selected_backend_payload(payload)
        self._refresh_kobold_status(payload)
        self.status_label.setText(f"{label} ready — model loaded: {display_model}")
        self.status_label.setStyleSheet(f"color: {ACCENT};")

    def _start_kobold_clicked(self) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            return
        payload = self._current_payload()
        # Guard: don't spawn if already alive
        host = str(payload.get("host", profile.host)).strip()
        if (host and _openai_compat_alive(host)) or _koboldcpp_status(payload)[0]:
            self.status_label.setText("KoboldCpp is already running.")
            self.status_label.setStyleSheet(f"color: {ACCENT};")
            return
        ok, message = _start_koboldcpp(payload)
        self._persist_selected_backend_payload(payload)
        self._refresh_kobold_status(payload)
        if ok:
            self._schedule_kobold_ready_notification(profile, payload)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")

    def _stop_kobold_clicked(self) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            return
        payload = self._current_payload()
        ok, message = _stop_koboldcpp(payload)
        self._persist_selected_backend_payload(payload)
        self._refresh_kobold_status(payload)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED if ok else ACCENT_ALT};")

    def _restart_kobold_clicked(self) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            return
        payload = self._current_payload()
        _stop_koboldcpp(payload)
        ok, message = _start_koboldcpp(payload)
        self._persist_selected_backend_payload(payload)
        self._refresh_kobold_status(payload)
        if ok:
            self._schedule_kobold_ready_notification(profile, payload)
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT};")

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
                color: {UI_TEXT_STRONG};
            }}
            QLineEdit, QComboBox {{
                background: {INPUT_BG};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: {ACCENT_SOFT};
            }}
            QListView, QTreeView {{
                background: {rgba(PANEL_BG, 0.96)};
                color: {UI_TEXT_STRONG};
                border: 1px solid {BORDER_SOFT};
                border-radius: 12px;
            }}
            QListView::item:selected, QTreeView::item:selected {{
                background: {ACCENT_SOFT};
                color: {UI_TEXT_STRONG};
            }}
            QPushButton {{
                min-height: 34px;
                background: {CARD_BG_SOFT};
                color: {UI_TEXT_STRONG};
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
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        payload = self._current_payload()
        model_dir = _default_tts_model_dir(profile, payload)
        self.download_progress.show()
        self.download_progress_label.show()
        self.download_progress.setValue(0)
        self.download_progress_label.setText("Starting voice download…")
        self.status_label.setText(f"Downloading PocketTTS voice: {preset}…")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
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
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

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
            self.status_label.setStyleSheet(f"color: {ACCENT if ok else ACCENT_ALT}; border: none;")
            self.validation_badge.setText("✓ Validated" if ok else "○ Not validated")
            self.validation_badge.setStyleSheet(
                f"color: {ACCENT if ok else ACCENT_ALT}; font-weight: 700; border: none;"
            )
        send_desktop_notification("TTS model ready", f"{profile_key} model files installed at {model_dir}.")

    def _on_tts_download_failed(self, profile_key: str, message: str) -> None:
        selected = self._selected_profile()
        if selected.key == profile_key:
            self._refresh_download_progress(profile_key)
            self.status_label.setText(f"Model download failed: {message}")
            self.status_label.setStyleSheet(f"color: {ACCENT_ALT};")

    def _refresh_binary_info(self) -> None:
        """
        Show basic size/info for the binary/model-folder field (KoboldCpp binary or local ONNX folder).
        """
        current = self.binary_path_input.text().strip()
        if not current:
            self.binary_info_label.setText("")
            return
        path = Path(current).expanduser()
        if not path.exists():
            self.binary_info_label.setText("Not found on disk.")
            return
        if path.is_dir():
            total = _dir_size_bytes(path)
            self.binary_info_label.setText(f"Folder size: {_format_bytes(total)}")
            return
        try:
            size = int(path.stat().st_size)
        except Exception:
            size = 0
        self.binary_info_label.setText(f"File size: {_format_bytes(size)}")

    def _refresh_gguf_info(self) -> None:
        current = self.gguf_path_input.text().strip()
        if not current:
            self.gguf_info_label.setText("")
            return
        path = Path(current).expanduser()
        if not path.exists():
            self.gguf_info_label.setText("GGUF not found on disk.")
            return
        try:
            size = int(path.stat().st_size)
        except Exception:
            size = 0
        name = path.name
        quant = ""
        lowered = name.lower()
        for token in ("q2_k", "q3_k_s", "q3_k_m", "q3_k_l", "q4_0", "q4_k_m", "q5_0", "q5_k_m", "q6_k", "q8_0", "fp16"):
            if token in lowered:
                quant = token.upper()
                break
        catalog = MODEL_CATALOG.get("llm_gguf", [])
        matched = next((row for row in catalog if str(row.get("file", "")).strip() == name), None)
        extra = ""
        if isinstance(matched, dict):
            bits = []
            title = str(matched.get("title", "")).strip()
            if title:
                bits.append(title)
            params = str(matched.get("params", "")).strip()
            if params:
                bits.append(f"params {params}")
            ctx = matched.get("context", "")
            if isinstance(ctx, (int, float, str)) and str(ctx).strip():
                bits.append(f"context {ctx}")
            if bits:
                extra = " • " + " • ".join(bits)
        suffix = f" • {quant}" if quant else ""
        self.gguf_info_label.setText(f"{name} — {_format_bytes(size)}{suffix}{extra}")

    def _refresh_kobold_gemma4_audio_toggle(self) -> None:
        if not hasattr(self, "kobold_gemma4_audio_stt_check"):
            return
        profile = self._selected_profile()
        is_kobold = profile.key == "koboldcpp"
        self.kobold_gemma4_audio_stt_check.setVisible(is_kobold)
        if not is_kobold:
            self.kobold_gemma4_audio_stt_check.setChecked(False)
            self.kobold_gemma4_audio_stt_check.setEnabled(False)
            return

        gguf_name = Path(str(self.gguf_path_input.text() or "").strip()).name
        is_gemma4 = _looks_like_gemma4_model_name(gguf_name)
        if not is_gemma4:
            self.kobold_gemma4_audio_stt_check.setChecked(False)
            self.kobold_gemma4_audio_stt_check.setEnabled(False)
            self.kobold_gemma4_audio_stt_check.setToolTip("Select a Gemma 4 GGUF to enable Gemma 4 audio STT.")
            return

        supported = False
        checked_at = 0.0
        try:
            payload = dict(self.settings.get("koboldcpp", {}) or {})
            supported = bool(payload.get("gemma4_audio_supported", False))
            checked_at = float(payload.get("gemma4_audio_checked_at", 0.0) or 0.0)
            checked_gguf = str(payload.get("gemma4_audio_checked_gguf", "")).strip()
            if checked_gguf and checked_gguf != gguf_name:
                supported = False
                checked_at = 0.0
        except Exception:
            supported = False
            checked_at = 0.0

        self.kobold_gemma4_audio_stt_check.setEnabled(True)
        hint = ""
        if supported:
            hint = "Audio input verified."
        elif checked_at > 0:
            hint = "Audio input not supported on this build/model."
        else:
            hint = "Click Test to verify audio input support."
        if _looks_like_gemma4_audio_variant(gguf_name):
            variant_hint = "Gemma 4 audio variant detected."
        else:
            variant_hint = "Gemma 4 variant unknown (audio may or may not work)."
        self.kobold_gemma4_audio_stt_check.setToolTip(f"{variant_hint} {hint}")

    def _populate_gguf_gallery(self) -> None:
        # Clear previous widgets.
        while self.gguf_gallery_grid.count():
            item = self.gguf_gallery_grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        entries = MODEL_CATALOG.get("llm_gguf", [])
        if not isinstance(entries, list) or not entries:
            empty = QLabel("No bundled models found. (model_catalog.json missing?)")
            empty.setStyleSheet(f"color: {UI_ICON_DIM};")
            self.gguf_gallery_grid.addWidget(empty, 0, 0)
            return
        col_count = 2
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            card = SurfaceFrame(bg=rgba(CARD_BG_SOFT, 0.88), border=BORDER_SOFT, radius=18)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(6)
            title = QLabel(str(entry.get("title", "")).strip() or str(entry.get("id", "")).strip() or "Model")
            title.setWordWrap(True)
            title.setStyleSheet(f"color: {UI_TEXT_STRONG}; font-weight: 700;")
            lay.addWidget(title)
            meta_bits = []
            params = str(entry.get("params", "")).strip()
            if params:
                meta_bits.append(params)
            quant = str(entry.get("quant", "")).strip()
            if quant:
                meta_bits.append(quant)
            ctx = entry.get("context", "")
            if isinstance(ctx, (int, float, str)) and str(ctx).strip():
                meta_bits.append(f"ctx {ctx}")
            size_bytes = entry.get("size_bytes", 0)
            try:
                meta_bits.append(_format_bytes(int(size_bytes)))
            except Exception:
                pass
            license_name = str(entry.get("license", "")).strip()
            if license_name:
                meta_bits.append(license_name)
            meta = QLabel(" • ".join(meta_bits))
            meta.setWordWrap(True)
            meta.setStyleSheet(f"color: {UI_ICON_DIM};")
            lay.addWidget(meta)
            notes = QLabel(str(entry.get("notes", "")).strip())
            notes.setWordWrap(True)
            notes.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            if notes.text().strip():
                lay.addWidget(notes)
            actions = QHBoxLayout()
            actions.setContentsMargins(0, 6, 0, 0)
            actions.setSpacing(8)
            download_btn = QToolButton()
            download_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
            download_btn.setToolTip("Download this GGUF into Hanauta cache and select it")
            download_btn.setFixedSize(44, 38)

            def _clicked(_checked: bool = False, payload: dict[str, object] = dict(entry)) -> None:
                self._download_gguf(payload)
                del _checked

            download_btn.clicked.connect(_clicked)
            actions.addWidget(download_btn)
            repo_id = str(entry.get("repo_id", "")).strip()
            filename = str(entry.get("file", "")).strip()
            link = QLabel(f"{repo_id} / {filename}".strip(" /"))
            link.setWordWrap(True)
            link.setStyleSheet(f"color: {UI_ICON_DIM};")
            actions.addWidget(link, 1)
            lay.addLayout(actions)
            row = idx // col_count
            col = idx % col_count
            self.gguf_gallery_grid.addWidget(card, row, col)
        self.gguf_gallery_grid.setColumnStretch(0, 1)
        self.gguf_gallery_grid.setColumnStretch(1, 1)

    def _download_gguf(self, entry: dict[str, object]) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            self.status_label.setText("GGUF gallery is only available for KoboldCpp.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        entry_id = str(entry.get("id", "")).strip() or str(entry.get("file", "")).strip()
        if not entry_id:
            return
        started = self._gguf_download_manager.start(entry)
        if not started:
            self.status_label.setText("A download is already running for this model.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        self.gguf_download_progress.show()
        self.gguf_download_progress_label.show()
        self.gguf_download_progress.setValue(0)
        self.gguf_download_progress_label.setText("Starting download…")
        self.status_label.setText(f"Downloading: {str(entry.get('title', entry_id)).strip()}")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

    def _on_gguf_download_progress(self, entry_id: str, value: int, message: str) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            return
        self.gguf_download_progress.show()
        self.gguf_download_progress_label.show()
        self.gguf_download_progress.setValue(max(0, min(100, int(value))))
        self.gguf_download_progress_label.setText(str(message).strip())
        self.status_label.setText(f"Downloading GGUF ({entry_id})… {value}%")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

    def _on_gguf_download_finished(self, entry_id: str, path: str) -> None:
        profile = self._selected_profile()
        if profile.key == "koboldcpp":
            self.gguf_path_input.setText(path)
            self.gguf_download_progress.setValue(100)
            self.gguf_download_progress_label.setText("Download complete")
            self.status_label.setText(f"GGUF downloaded: {Path(path).name}")
            self.status_label.setStyleSheet(f"color: {ACCENT};")
        send_desktop_notification("GGUF ready", f"Downloaded {entry_id} to {path}.")

    def _on_gguf_download_failed(self, entry_id: str, message: str) -> None:
        profile = self._selected_profile()
        if profile.key != "koboldcpp":
            return
        self.gguf_download_progress.hide()
        self.gguf_download_progress_label.hide()
        self.status_label.setText(f"GGUF download failed ({entry_id}): {message}")
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
            f"color: {ACCENT if active else UI_ICON_DIM}; font-weight: 600;"
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
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        if self._tts_preview_worker is not None and self._tts_preview_worker.isRunning():
            self.status_label.setText("A TTS preview is already running.")
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")
            return
        payload = self._current_payload()
        worker = TtsSynthesisWorker(profile, payload, text)
        self._tts_preview_worker = worker
        label = "PocketTTS" if profile.key == "pockettts" else "Kokoro"
        self.status_label.setText(f"Gerando preview de {label}…")
        self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

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
            self.status_label.setStyleSheet(f"color: {UI_TEXT_MUTED};")

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
