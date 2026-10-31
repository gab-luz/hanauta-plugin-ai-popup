import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from hanauta_aipopup.models import BackendProfile  # noqa: E402
from hanauta_aipopup.ui_backend_settings import BackendSettingsDialog  # noqa: E402

_APP = QApplication.instance() or QApplication([])

LFM3 = BackendProfile(
    "lfm3", "LFM3-Omni 2B", "openai_compat", "lfm3-omni-2b",
    "127.0.0.1:8081", "koboldcpp", False, True,
)


def test_lfm3_backend_is_preconfigured_in_settings():
    dialog = BackendSettingsDialog([LFM3], {"lfm3": {}}, "Sans")
    assert dialog._selected_profile().key == "lfm3"
    # The Omni card's requirements are filled in, not left for the user to type.
    assert dialog.llama_context_input.text() == "32768"
    assert dialog.llama_runtime_flavor_combo.currentData() == "lfm3"
    assert dialog.llama_model_path_input.isVisibleTo(dialog)
    assert dialog.llama_mmproj_path_input.isVisibleTo(dialog)


def test_saved_values_win_over_lfm3_defaults():
    payload = {"llama_context": "8192", "llama_runtime_flavor": "upstream"}
    dialog = BackendSettingsDialog([LFM3], {"lfm3": payload}, "Sans")
    assert dialog.llama_context_input.text() == "8192"
    assert dialog.llama_runtime_flavor_combo.currentData() == "upstream"


def test_lfm3_payload_saves_paths_and_context():
    dialog = BackendSettingsDialog([LFM3], {"lfm3": {}}, "Sans")
    dialog.llama_model_path_input.setText("/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf")
    dialog.llama_mmproj_path_input.setText("/models/mmproj-BF16.gguf")
    dialog._save_current_backend()
    saved = dialog.settings["lfm3"]
    assert saved["gguf_path"].endswith("Q6_K.gguf")
    assert saved["mmproj_path"].endswith("mmproj-BF16.gguf")
    assert saved["llama_context"] == "32768"
    assert saved["llama_runtime_flavor"] == "lfm3"
    # Both switches are exposed in the UI rather than being JSON-only keys.
    assert saved["llama_autostart"] is True
    assert saved["llama_auto_accelerate"] is True
    dialog.llama_autostart_check.setChecked(False)
    dialog.llama_auto_accelerate_check.setChecked(False)
    dialog._save_current_backend()
    saved = dialog.settings["lfm3"]
    assert saved["llama_autostart"] is False
    assert saved["llama_auto_accelerate"] is False
