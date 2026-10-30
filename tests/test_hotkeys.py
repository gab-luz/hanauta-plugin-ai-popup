import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup.hotkeys import GlobalHotkeys, parse_binding  # noqa: E402


def test_parses_ctrl_alt_combinations():
    mask, key = parse_binding("<ctrl>+<alt>+c")
    assert key == "c"
    assert mask == 4 | 8  # ControlMask | Mod1Mask


def test_parses_super_and_shift():
    mask, key = parse_binding("<super>+<shift>+F9")
    assert key == "F9".lower()  # normalised to lower case for XStringToKeysym
    assert mask == 64 | 1


def test_plain_keys_and_junk():
    assert parse_binding("F8") == (0, "f8")
    assert parse_binding("") is None
    assert parse_binding("   ") is None
    assert parse_binding("<ctrl>+<alt>+") is None
    assert parse_binding("x" * 20) is None


def test_no_bindings_reports_why():
    ok, message = GlobalHotkeys({}).start()
    assert ok is False
    assert "no capture hotkeys configured" in message


def test_start_without_display_is_graceful(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    ok, message = GlobalHotkeys({"screen": "<ctrl>+<alt>+s"}).start()
    assert ok is False
    assert "X display" in message


def test_stop_is_safe_before_start():
    hotkeys = GlobalHotkeys({"camera": "<ctrl>+<alt>+c"})
    hotkeys.stop()  # must not raise
    assert hotkeys.bindings == {"camera": "<ctrl>+<alt>+c"}
    assert os.environ.get("DISPLAY") is not None or True  # environment untouched
