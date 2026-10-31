import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup import voice  # noqa: E402

AREONE_LIST = """**** List of CAPTURE Hardware Devices ****
card 2: Generic_1 [HD-Audio Generic], device 0: ALC892 Analog [ALC892 Analog]
  Subdevices: 1/1
card 3: Device [USB PnP Audio Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
card 4: C920 [HD Pro Webcam C920], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
"""


class _Run:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def test_usb_microphones_are_tried_before_onboard_analog(monkeypatch):
    # The onboard analog jack records pure silence on this machine; the USB mic
    # and the webcam are the inputs that actually carry audio.
    monkeypatch.setattr(voice.shutil, "which", lambda name: "/usr/bin/arecord" if name == "arecord" else None)
    monkeypatch.setattr(voice.subprocess, "run", lambda cmd, **kw: _Run(AREONE_LIST))
    devices = voice._capture_devices()
    assert devices == ["plughw:3,0", "plughw:4,0", "plughw:2,0"]


def test_missing_arecord_means_no_devices(monkeypatch):
    monkeypatch.setattr(voice.shutil, "which", lambda name: None)
    assert voice._capture_devices() == []


def test_a_silent_device_falls_through_to_a_working_one(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_INPUT_DEVICE_CACHE", "")
    monkeypatch.setattr(voice, "VOICE_RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(voice.shutil, "which", lambda name: "/usr/bin/arecord" if name == "arecord" else None)
    monkeypatch.setattr(voice, "_capture_devices", lambda: ["plughw:2,0", "plughw:3,0"])
    monkeypatch.delenv("HANAUTA_MIC_DEVICE", raising=False)
    calls: list[str] = []

    def run_and_track(cmd, **kw):
        calls.append(cmd[cmd.index("-D") + 1])
        (tmp_path / pathlib.Path(cmd[-1]).name).write_bytes(b"0" * 1000)
        return _Run()

    monkeypatch.setattr(voice.subprocess, "run", run_and_track)
    # The onboard analog device is silent; the USB one carries sound.
    monkeypatch.setattr(
        voice, "_voice_recording_rms", lambda path: 0.0 if calls[-1] == "plughw:2,0" else 0.02
    )

    path = voice._record_microphone_wav(0.5)
    assert path.exists()
    assert calls == ["plughw:2,0", "plughw:3,0"]
    assert voice._INPUT_DEVICE_CACHE == "plughw:3,0"


def test_all_silent_raises_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_INPUT_DEVICE_CACHE", "")
    monkeypatch.setattr(voice, "VOICE_RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(voice.shutil, "which", lambda name: "/usr/bin/arecord" if name == "arecord" else None)
    monkeypatch.setattr(voice, "_capture_devices", lambda: ["plughw:2,0"])
    monkeypatch.delenv("HANAUTA_MIC_DEVICE", raising=False)
    monkeypatch.setattr(
        voice.subprocess, "run",
        lambda cmd, **kw: (tmp_path / pathlib.Path(cmd[-1]).name).write_bytes(b"0" * 1000) or _Run(),
    )
    monkeypatch.setattr(voice, "_voice_recording_rms", lambda path: 0.0)
    try:
        voice._record_microphone_wav(0.5)
    except RuntimeError as exc:
        assert "only silence" in str(exc)
    else:
        raise AssertionError("expected a silent-microphone error")
