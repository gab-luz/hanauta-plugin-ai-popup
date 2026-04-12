#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

PLUGIN_ROOT = Path(__file__).resolve().parent
AI_POPUP_APP = PLUGIN_ROOT / "ai_popup.py"
SERVICE_KEY = "ai_popup"

DEFAULT_SERVICE = {
    "enabled": True,
    "show_in_notification_center": False,
    "show_in_bar": True,
}
DEFAULT_POPUP = {
    "window_width": 452,
    "window_height": 930,
}


def _save_settings(window) -> None:
    module = sys.modules.get(window.__class__.__module__)
    save_function = (
        getattr(module, "save_settings_state", None) if module is not None else None
    )
    if callable(save_function):
        save_function(window.settings_state)
        return
    callback = getattr(window, "_save_settings", None)
    if callable(callback):
        callback()


def _service_state(window) -> dict[str, object]:
    services = window.settings_state.setdefault("services", {})
    service = services.setdefault(SERVICE_KEY, dict(DEFAULT_SERVICE))
    if not isinstance(service, dict):
        service = dict(DEFAULT_SERVICE)
        services[SERVICE_KEY] = service
    for key, value in DEFAULT_SERVICE.items():
        service.setdefault(key, value)
    return service


def _popup_state(window) -> dict[str, object]:
    popup = window.settings_state.setdefault("ai_popup", {})
    if not isinstance(popup, dict):
        popup = dict(DEFAULT_POPUP)
        window.settings_state["ai_popup"] = popup
    for key, value in DEFAULT_POPUP.items():
        popup.setdefault(key, value)
    return popup


def _save_popup_size(window, width_input: QLineEdit, height_input: QLineEdit) -> None:
    popup = _popup_state(window)
    try:
        width = max(360, min(1600, int(width_input.text().strip() or "452")))
    except Exception:
        width = 452
    try:
        height = max(520, min(1800, int(height_input.text().strip() or "930")))
    except Exception:
        height = 930
    popup["window_width"] = width
    popup["window_height"] = height
    width_input.setText(str(width))
    height_input.setText(str(height))
    _save_settings(window)
    status = getattr(window, "ai_popup_status", None)
    if isinstance(status, QLabel):
        status.setText(f"AI popup size saved: {width}x{height}.")


def _launch_popup(window, api: dict[str, object]) -> None:
    if not AI_POPUP_APP.exists():
        status = getattr(window, "ai_popup_status", None)
        if isinstance(status, QLabel):
            status.setText("ai_popup.py not found in plugin folder.")
        return

    entry_command = api.get("entry_command")
    run_bg = api.get("run_bg")
    command: list[str] = []
    if callable(entry_command):
        try:
            command = list(entry_command(AI_POPUP_APP))
        except Exception:
            command = []
    if not command:
        command = ["python3", str(AI_POPUP_APP)]

    if callable(run_bg):
        try:
            run_bg(command)
        except Exception:
            pass

    status = getattr(window, "ai_popup_status", None)
    if isinstance(status, QLabel):
        status.setText("AI popup launched.")


def build_ai_popup_service_section(window, api: dict[str, object]) -> QWidget:
    SettingsRow = api["SettingsRow"]
    SwitchButton = api["SwitchButton"]
    ExpandableServiceSection = api["ExpandableServiceSection"]
    material_icon = api["material_icon"]
    icon_path = str(api.get("plugin_icon_path", "")).strip()

    service = _service_state(window)
    popup = _popup_state(window)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    display_switch = SwitchButton(bool(service.get("show_in_notification_center", False)))
    display_switch.toggledValue.connect(
        lambda enabled: window._set_service_notification_visibility(SERVICE_KEY, enabled)
    )
    window.service_display_switches[SERVICE_KEY] = display_switch
    layout.addWidget(
        SettingsRow(
            material_icon("widgets"),
            "Show in notification center",
            "Expose AI popup controls in the notification center service list.",
            window.icon_font,
            window.ui_font,
            display_switch,
        )
    )

    bar_switch = SwitchButton(bool(service.get("show_in_bar", True)))
    bar_switch.toggledValue.connect(
        lambda enabled: window._set_service_bar_visibility(SERVICE_KEY, enabled)
    )
    layout.addWidget(
        SettingsRow(
            material_icon("auto_awesome"),
            "Show on bar",
            "Keep AI popup available from the bar button when supported by the bar.",
            window.icon_font,
            window.ui_font,
            bar_switch,
        )
    )

    size_wrap = QWidget()
    size_layout = QHBoxLayout(size_wrap)
    size_layout.setContentsMargins(0, 0, 0, 0)
    size_layout.setSpacing(8)
    width_input = QLineEdit(str(popup.get("window_width", 452)))
    width_input.setPlaceholderText("452")
    width_input.setFixedWidth(90)
    height_input = QLineEdit(str(popup.get("window_height", 930)))
    height_input.setPlaceholderText("930")
    height_input.setFixedWidth(90)
    save_size_button = QPushButton("Save size")
    save_size_button.setObjectName("secondaryButton")
    save_size_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    save_size_button.clicked.connect(
        lambda: _save_popup_size(window, width_input, height_input)
    )
    size_layout.addWidget(width_input)
    size_layout.addWidget(height_input)
    size_layout.addWidget(save_size_button)
    size_layout.addStretch(1)
    layout.addWidget(
        SettingsRow(
            material_icon("crop_square"),
            "Popup size (width x height)",
            "Controls the AI popup window size on launch.",
            window.icon_font,
            window.ui_font,
            size_wrap,
        )
    )

    open_button = QPushButton("Open AI popup")
    open_button.setObjectName("secondaryButton")
    open_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    open_button.clicked.connect(lambda: _launch_popup(window, api))
    layout.addWidget(
        SettingsRow(
            material_icon("open_in_new"),
            "Open popup",
            "Launch the AI popup window immediately.",
            window.icon_font,
            window.ui_font,
            open_button,
        )
    )

    status_label = QLabel("AI popup plugin ready.")
    status_label.setWordWrap(True)
    status_label.setStyleSheet("color: rgba(246,235,247,0.72);")
    layout.addWidget(status_label)
    window.ai_popup_status = status_label

    section = ExpandableServiceSection(
        SERVICE_KEY,
        "AI Popup",
        "Local AI chat popup integration for Hanauta.",
        "?",
        window.icon_font,
        window.ui_font,
        content,
        window._service_enabled(SERVICE_KEY),
        lambda enabled: window._set_service_enabled(SERVICE_KEY, enabled),
        icon_path=icon_path,
    )
    window.service_sections[SERVICE_KEY] = section
    return section


def register_hanauta_plugin() -> dict[str, object]:
    return {
        "id": SERVICE_KEY,
        "name": "AI Popup",
        "api_min_version": 1,
        "service_sections": [
            {
                "key": SERVICE_KEY,
                "builder": build_ai_popup_service_section,
                "supports_show_on_bar": True,
            }
        ],
    }
