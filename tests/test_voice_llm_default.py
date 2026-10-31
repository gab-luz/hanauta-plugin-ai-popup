import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from hanauta_aipopup.models import BackendProfile  # noqa: E402
from hanauta_aipopup.tts import _voice_mode_settings  # noqa: E402
from hanauta_aipopup.ui_dialogs import VoiceModeDialog  # noqa: E402

_APP = QApplication.instance() or QApplication([])

LFM3 = BackendProfile(
    "lfm3", "LFM3-Omni 2B", "openai_compat", "lfm3-omni-2b",
    "127.0.0.1:8095", "koboldcpp", False, True,
)
KOBOLD = BackendProfile(
    "koboldcpp", "KoboldCpp", "openai_compat", "kobold",
    "127.0.0.1:5001", "koboldcpp", False, True,
)


def _settings(llm_profile: str = "koboldcpp", gguf_path: str = "/models/lfm3.gguf") -> dict:
    return {"lfm3": {"gguf_path": gguf_path}, "_voice_mode": {"llm_profile": llm_profile}}


def test_configured_lfm3_replaces_the_untouched_voice_default():
    # The stored default is always "koboldcpp", so it must not win over a
    # backend whose weights are actually on disk.
    assert _voice_mode_settings(_settings())["llm_profile"] == "lfm3"


def test_an_explicit_voice_choice_is_kept():
    assert _voice_mode_settings(_settings(llm_profile="llamacpp"))["llm_profile"] == "llamacpp"


def test_choosing_koboldcpp_after_saving_sticks():
    # Saving the dialog writes llm_profile_explicit, so picking KoboldCpp must
    # survive instead of being read as "never touched" on the next open.
    settings = _settings(llm_profile="koboldcpp")
    settings["_voice_mode"]["llm_profile_explicit"] = True
    assert _voice_mode_settings(settings)["llm_profile"] == "koboldcpp"


def test_without_lfm3_weights_voice_stays_on_kobold():
    assert _voice_mode_settings(_settings(gguf_path=""))["llm_profile"] == "koboldcpp"


def test_voice_mode_dialog_selects_lfm3_for_text():
    dialog = VoiceModeDialog([KOBOLD, LFM3], _settings(), "Sans")
    assert dialog.llm_profile_combo.currentData() == "lfm3"
    assert dialog.llm_profile_combo.currentText() == "LFM3-Omni 2B"


def test_voice_mode_dialog_offers_lfm3_alongside_other_backends():
    dialog = VoiceModeDialog([KOBOLD, LFM3], _settings(llm_profile="koboldcpp"), "Sans")
    options = {dialog.llm_profile_combo.itemData(i) for i in range(dialog.llm_profile_combo.count())}
    assert {"koboldcpp", "lfm3"} <= options
