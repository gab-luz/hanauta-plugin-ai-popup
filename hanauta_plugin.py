#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

PLUGIN_ROOT = Path(__file__).resolve().parent
AI_POPUP_APP = PLUGIN_ROOT / "ai_popup.py"
SERVICE_KEY = "ai_popup"

DEFAULT_SERVICE = {
    "enabled": True,
    "show_in_notification_center": False,
    "show_in_bar": True,
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
