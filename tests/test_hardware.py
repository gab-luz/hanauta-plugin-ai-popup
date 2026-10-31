import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup import backends, hardware  # noqa: E402


class _Result:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


class _FakeBinary:
    """Stands in for a llama-server build with a known --help/--list-devices."""

    def __init__(self, path, devices: str = "", help_text: str = "") -> None:
        self.path = path
        self.devices = devices
        self.help_text = help_text


def _patch_binary(monkeypatch, tmp_path, *, gpu: bool, flags: tuple[str, ...] = ("--flash-attn", "--model-draft")):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    devices = "Device 0: CUDA0 (NVIDIA GeForce RTX 3060)\n" if gpu else ""
    help_text = "\n".join(flags)

    def fake_run(cmd, **kwargs):
        if "--list-devices" in cmd:
            return _Result(devices)
        if "--help" in cmd:
            return _Result(help_text)
        return _Result("")

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    monkeypatch.setattr(backends, "_prebuilt_llama_server", lambda payload: binary)
    return binary


def test_nvidia_is_detected(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.setattr(hardware, "_run", lambda cmd, timeout=4.0: _Result("NVIDIA GeForce RTX 3060\n"))
    gpu = hardware.detect_gpu()
    assert gpu["vendor"] == "nvidia"
    assert gpu["count"] == 1
    assert hardware.has_gpu() is True


def test_no_probe_tools_means_no_gpu(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda name: None)
    assert hardware.detect_gpu()["vendor"] == "none"
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
    assert hardware.acceleration_defaults({"llama_mtp_draft_model": "/models/draft.gguf"})["mtp"] is True
    assert hardware.draft_model_configured({"llama_hf_draft_repo": "org/d", "llama_hf_draft_file": "d.gguf"}) is True


def test_acceleration_off_without_gpu(monkeypatch):
    monkeypatch.setattr(hardware, "has_gpu", lambda: False)
    assert hardware.acceleration_defaults({"llama_mtp_draft_model": "/d.gguf"}) == {"flash_attn": False, "mtp": False}


def test_auto_tune_stays_off_when_no_binary_resolves(monkeypatch):
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": True})
    monkeypatch.setattr(backends, "_prebuilt_llama_server", lambda payload: None)
    tuned = backends.auto_tune_payload({})
    assert "llama_flash_attn" not in tuned
    assert "device" not in tuned
    assert "no llama.cpp binary" in " ".join(tuned["llama_autotune_notes"])


def test_auto_tune_enables_gpu_offload_and_flash_on_a_gpu_build(monkeypatch, tmp_path):
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": True})
    _patch_binary(monkeypatch, tmp_path, gpu=True)
    tuned = backends.auto_tune_payload({"llama_mtp_draft_model": "/d.gguf"})
    assert tuned["device"] == "gpu"
    assert tuned["llama_flash_attn"] is True
    assert tuned["llama_mtp_enabled"] is True


def test_auto_tune_refuses_flags_on_a_cpu_build(monkeypatch, tmp_path):
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": False})
    _patch_binary(monkeypatch, tmp_path, gpu=False)
    tuned = backends.auto_tune_payload({})
    assert "llama_flash_attn" not in tuned
    assert "device" not in tuned
    assert "no GPU backend" in " ".join(tuned["llama_autotune_notes"])


def test_auto_tune_respects_explicit_choices(monkeypatch, tmp_path):
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": True})
    _patch_binary(monkeypatch, tmp_path, gpu=True)
    kept = backends.auto_tune_payload({"llama_flash_attn": False, "llama_mtp_enabled": False, "device": "cpu"})
    assert kept["llama_flash_attn"] is False
    assert kept["llama_mtp_enabled"] is False
    assert kept["device"] == "cpu"
    # The opt-out switch disables tuning entirely.
    off = backends.auto_tune_payload({"llama_auto_accelerate": False})
    assert "llama_flash_attn" not in off and "device" not in off


def test_flash_attn_passes_a_value_when_the_build_demands_one(monkeypatch, tmp_path):
    # The LFM3 pin declares `--flash-attn [on|off|auto]`; a bare flag aborts startup.
    pinned = _patch_binary(
        monkeypatch, tmp_path, gpu=True,
        flags=("-fa,   --flash-attn [on|off|auto]       set Flash Attention use",),
    )
    assert backends._flash_attn_args(pinned) == ["--flash-attn", "on"]
    old = _patch_binary(monkeypatch, tmp_path, gpu=True, flags=("--flash-attn",))
    assert backends._flash_attn_args(old) == ["--flash-attn"]
    assert backends._flash_attn_args(None) == ["--flash-attn"]


def test_vendored_cuda_binary_wins_over_the_cpu_drop_in(monkeypatch, tmp_path):
    cpu_dir = tmp_path / "vendor-cpu"
    cuda_dir = tmp_path / "vendor-cuda"
    cpu_dir.mkdir()
    cuda_dir.mkdir()
    (cpu_dir / "llama-server").write_text("cpu")
    (cuda_dir / "llama-server").write_text("cuda")
    monkeypatch.setattr(backends, "_VENDOR_LLAMA_DIR", cpu_dir)
    monkeypatch.setattr(backends, "_VENDOR_LLAMA_CUDA_DIR", cuda_dir)
    monkeypatch.setattr(backends, "_runtime_root", lambda payload: tmp_path / "runtime")
    found = backends._prebuilt_llama_server({"llama_runtime_flavor": "lfm3"})
    assert found == cuda_dir / "llama-server"
