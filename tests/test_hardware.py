import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup import hardware  # noqa: E402


class _Result:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def test_nvidia_is_detected(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.setattr(hardware, "_run", lambda cmd, timeout=4.0: _Result("NVIDIA GeForce RTX 3060\nNVIDIA GeForce RTX 3060\n"))
    gpu = hardware.detect_gpu()
    assert gpu["vendor"] == "nvidia"
    assert gpu["count"] == 2
    assert hardware.has_gpu() is True


def test_no_probe_tools_means_no_gpu(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: None)
    gpu = hardware.detect_gpu()
    assert gpu["vendor"] == "none"
    assert hardware.has_gpu() is False


def test_lspci_fallback(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: "/usr/bin/lspci" if name == "lspci" else None)
    monkeypatch.setattr(
        hardware, "_run",
        lambda cmd, timeout=4.0: _Result("05:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23\n"),
    )
    assert hardware.detect_gpu()["vendor"] == "amd"


def test_acceleration_needs_a_draft_model_for_mtp(monkeypatch):
    monkeypatch.setattr(hardware, "has_gpu", lambda: True)
    assert hardware.acceleration_defaults({}) == {"flash_attn": True, "mtp": False}
    with_draft = {"llama_mtp_draft_model": "/models/draft.gguf"}
    assert hardware.acceleration_defaults(with_draft)["mtp"] is True
    # HF draft repo + file also counts.
    assert hardware.draft_model_configured({"llama_hf_draft_repo": "org/d", "llama_hf_draft_file": "d.gguf"}) is True


def test_acceleration_off_without_gpu(monkeypatch):
    monkeypatch.setattr(hardware, "has_gpu", lambda: False)
    assert hardware.acceleration_defaults({"llama_mtp_draft_model": "/d.gguf"}) == {"flash_attn": False, "mtp": False}


def test_auto_tune_respects_explicit_choices(monkeypatch):
    from hanauta_aipopup import backends

    monkeypatch.setattr(
        "hanauta_aipopup.hardware.acceleration_defaults",
        lambda payload: {"flash_attn": True, "mtp": True},
    )
    monkeypatch.setattr(backends, "_prebuilt_llama_server", lambda payload: None)
    # Never toggled: filled from hardware.
    tuned = backends.auto_tune_payload({})
    assert tuned["llama_flash_attn"] is True and tuned["llama_mtp_enabled"] is True
    # Explicitly saved off: untouched.
    kept = backends.auto_tune_payload({"llama_flash_attn": False, "llama_mtp_enabled": False})
    assert kept["llama_flash_attn"] is False and kept["llama_mtp_enabled"] is False
    # Opt-out switch disables tuning entirely.
    off = backends.auto_tune_payload({"llama_auto_accelerate": False})
    assert "llama_flash_attn" not in off


def test_auto_tune_drops_flags_the_build_lacks(monkeypatch, tmp_path):
    from hanauta_aipopup import backends

    monkeypatch.setattr(
        "hanauta_aipopup.hardware.acceleration_defaults",
        lambda payload: {"flash_attn": True, "mtp": False},
    )
    fake = tmp_path / "llama-server"
    fake.write_text("#!/bin/sh\necho 'usage: --ctx-size'\n")
    monkeypatch.setattr(backends, "_prebuilt_llama_server", lambda payload: fake)
    tuned = backends.auto_tune_payload({})
    # The stub build does not advertise --flash-attn, so it must not be enabled.
    assert tuned["llama_flash_attn"] is False
