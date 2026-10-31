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


def test_auto_tune_treats_saved_defaults_as_unset(monkeypatch, tmp_path):
    # The dialog always saves device=cpu and unchecked boxes, so those values
    # must not be read as "the user said no" on a machine with a GPU.
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": True})
    _patch_binary(monkeypatch, tmp_path, gpu=True)
    tuned = backends.auto_tune_payload(
        {"llama_flash_attn": False, "llama_mtp_enabled": False, "device": "cpu", "llama_mtp_draft_model": "/d.gguf"}
    )
    assert tuned["llama_flash_attn"] is True
    assert tuned["llama_mtp_enabled"] is True
    assert tuned["device"] == "gpu"


def test_auto_tune_opt_out_switch(monkeypatch, tmp_path):
    monkeypatch.setattr("hanauta_aipopup.hardware.acceleration_defaults", lambda payload: {"flash_attn": True, "mtp": True})
    _patch_binary(monkeypatch, tmp_path, gpu=True)
    off = backends.auto_tune_payload({"llama_auto_accelerate": False, "device": "cpu"})
    assert "llama_flash_attn" not in off and off["device"] == "cpu"


def test_busy_port_is_reported_before_launching():
    import socket as _socket

    dummy = _socket.socket()
    dummy.bind(("127.0.0.1", 0))
    dummy.listen(1)
    port = dummy.getsockname()[1]
    try:
        note = backends._port_in_use_note({"host": f"127.0.0.1:{port}"})
        assert f"Port {port}" in note and "already in use" in note
    finally:
        dummy.close()
    # A closed port must not block a launch.
    assert backends._port_in_use_note({"host": "127.0.0.1:1"}) == ""
    assert backends._port_in_use_note({}) == ""


def test_busy_port_is_reassigned_to_a_free_one():
    import socket as _socket

    dummy = _socket.socket()
    dummy.bind(("127.0.0.1", 0))
    dummy.listen(1)
    busy = dummy.getsockname()[1]
    try:
        payload = {"host": f"127.0.0.1:{busy}"}
        note = backends._reassign_busy_port(payload)
        assert note and not note.startswith("!")
        assert "busy" in note
        new_port = int(str(payload["host"]).split(":")[1])
        assert new_port > busy
    finally:
        dummy.close()
    # A free port is left alone.
    untouched = {"host": "127.0.0.1:1"}
    assert backends._reassign_busy_port(untouched) == ""
    assert untouched["host"] == "127.0.0.1:1"


def test_cpu_build_reports_no_devices(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backends.subprocess, "run",
        lambda cmd, **kwargs: _Result("Available devices:\n"),
    )
    binary = tmp_path / "llama-server"
    binary.write_text("x")
    assert backends.llama_gpu_devices(binary) == []


def test_gpu_probe_sets_the_runtime_library_path(monkeypatch, tmp_path):
    # A CUDA build only loads libggml-cuda.so when its own directory is on the
    # library path; without it --list-devices reports nothing.
    seen = {}

    def fake_run(cmd, **kwargs):
        seen[cmd[-1]] = kwargs.get("env", {}).get("LD_LIBRARY_PATH", "")
        # Exactly what the real binary prints; note the line has no "device" word.
        listing = "Available devices:\n  CUDA0: NVIDIA GeForce RTX 3060 (12029 MiB, 5096 MiB free)\n"
        return _Result(listing if "--list-devices" in cmd else "--flash-attn")

    monkeypatch.setattr(backends.subprocess, "run", fake_run)
    binary = tmp_path / "llama-server"
    binary.write_text("x")
    assert backends.llama_gpu_devices(binary) == [
        "CUDA0: NVIDIA GeForce RTX 3060 (12029 MiB, 5096 MiB free)"
    ]
    assert str(tmp_path) in seen["--list-devices"]
    assert backends.llama_supports_flag(binary, "--flash-attn") is True
    assert str(tmp_path) in seen["--help"]


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


def test_draft_flags_follow_the_build_dialect(monkeypatch, tmp_path):
    new = _patch_binary(monkeypatch, tmp_path, gpu=True, flags=("--spec-draft-model", "--spec-draft-n-max"))
    assert backends._draft_model_args(new, "/d.gguf") == ["--spec-draft-model", "/d.gguf"]
    assert backends._draft_max_args(new, "16") == ["--spec-draft-n-max", "16"]
    old = _patch_binary(monkeypatch, tmp_path, gpu=True, flags=("--model-draft", "--draft-max"))
    assert backends._draft_model_args(old, "/d.gguf") == ["--model-draft", "/d.gguf"]
    assert backends._draft_max_args(old, "16") == ["--draft-max", "16"]


REAL_HELP = "\n".join([
    "-fa,   --flash-attn [on|off|auto]       set Flash Attention use",
    "--batch-size N                          logical maximum batch size",
    "--spec-type none,draft-simple,draft-mtp,ngram-cache",
    "--draft, --draft-n, --draft-max N       the argument has been removed. use --spec-draft-n-max",
])


def _help_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(backends, "_help_text", lambda binary: REAL_HELP)
    binary = tmp_path / "llama-server"
    binary.write_text("x")
    return binary


def test_unknown_extra_args_are_dropped(monkeypatch, tmp_path):
    binary = _help_binary(monkeypatch, tmp_path)
    kept, dropped = backends._supported_extra_args(
        binary, ["--spec-type", "nextn", "-fa", "on", "--batch-size", "1024", "--no-such-flag"]
    )
    assert kept == ["-fa", "on", "--batch-size", "1024"]
    assert dropped == ["--spec-type nextn", "--no-such-flag"]


def test_removed_and_unknown_values_are_dropped(monkeypatch, tmp_path):
    # --draft-max is documented as removed and --spec-type nextn is not a type
    # this build knows; either would abort startup.
    binary = _help_binary(monkeypatch, tmp_path)
    kept, dropped = backends._supported_extra_args(
        binary, ["--spec-type", "nextn", "--batch-size", "512", "--draft-max", "2", "-fa", "on"]
    )
    assert kept == ["--batch-size", "512", "-fa", "on"]
    assert "--spec-type nextn" in dropped and "--draft-max" in dropped


def test_invalid_cache_type_value_is_dropped(monkeypatch, tmp_path):
    # `-ctk turbo3` exists only in another fork's help; this build allows a
    # fixed list and exits on anything else.
    help_text = (
        "-ctk,  --cache-type-k TYPE              KV cache data type for K\n"
        "                                        allowed values: f32, f16, bf16, q8_0\n"
    )
    monkeypatch.setattr(backends, "_help_text", lambda binary: help_text)
    binary = tmp_path / "llama-server"
    binary.write_text("x")
    kept, dropped = backends._supported_extra_args(binary, ["-ctk", "turbo3", "-ctk", "q8_0"])
    assert kept == ["-ctk", "q8_0"]
    assert dropped == ["-ctk turbo3"]


def test_valid_spec_type_is_kept(monkeypatch, tmp_path):
    binary = _help_binary(monkeypatch, tmp_path)
    kept, dropped = backends._supported_extra_args(binary, ["--spec-type", "draft-mtp", "-fa", "on"])
    assert kept == ["--spec-type", "draft-mtp", "-fa", "on"]
    assert dropped == []


def test_missing_weights_message_is_actionable():
    note = backends._missing_model_note({"gguf_path": "/models/nope.gguf", "llama_runtime_flavor": "lfm3"})
    assert "Q6_K" in note and "mmproj" in note and "/models/nope.gguf" in note
    assert "Download LFM3" in note
    generic = backends._missing_model_note({"gguf_path": "/models/nope.gguf"})
    assert "No GGUF model is configured" in generic


def test_cpu_runtime_is_found_for_the_gpu_fallback(monkeypatch, tmp_path):
    (tmp_path / "cpu").mkdir()
    (tmp_path / "cpu" / "llama-server").write_text("x")
    monkeypatch.setattr(backends, "_runtime_root", lambda payload: tmp_path)
    assert backends._cpu_runtime_binary({}) == tmp_path / "cpu" / "llama-server"


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
