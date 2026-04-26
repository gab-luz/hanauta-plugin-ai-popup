#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import faulthandler
import logging
import os
import signal
import socket
import sys
import threading
import traceback

from PyQt6.QtCore import QObject, QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from .fonts import load_ui_font
from .runtime import (
    AI_POPUP_CRASH_FILE,
    AI_POPUP_ERROR_LOG_FILE,
    AI_STATE_DIR,
    palette_mtime,
)
from .style import apply_theme_globals, focused_workspace
from .http import (
    load_backend_settings as _load_backend_settings,
    save_backend_settings as _save_backend_settings,
    send_desktop_notification,
    maybe_notify_koboldcpp_release,
)
from .ui_panel import SidebarPanel

LOGGER = logging.getLogger("hanauta.ai_popup")


def _setup_diagnostics() -> None:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not LOGGER.handlers:
        LOGGER.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(AI_POPUP_ERROR_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.WARNING)
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

    from PyQt6.QtCore import qInstallMessageHandler

    def _qt_message_handler(mode, context, message) -> None:
        try:
            file_name = getattr(context, "file", "") or ""
            line = int(getattr(context, "line", 0) or 0)
            category = getattr(context, "category", "") or ""
            prefix = f"Qt[{category}] {file_name}:{line}".strip()
        except Exception:
            prefix = "Qt"
        LOGGER.warning(f"{prefix} {message}")

    try:
        qInstallMessageHandler(_qt_message_handler)
    except Exception as exc:
        LOGGER.warning("Failed to install Qt message handler: %s", exc)


_setup_diagnostics()

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

        self.resize(452, 650)
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
                    self.move(int(rect.get("x", 0)) + 16, int(rect.get("y", 0)) + 32)
                    return
                except Exception:
                    pass
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(16, 32)
            return
        geo = screen.availableGeometry()
        self.move(geo.x() + 16, geo.y() + 32)

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
            # Hide instead of quitting. Voice mode can keep running in the background.
            self.hide()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # Treat "close" like "hide" so the popup can keep its background services alive.
        self.hide()
        event.ignore()


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
