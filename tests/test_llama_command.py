"""Tests for the llama-server invocation used to serve LFM3-Omni.

The model card serves the model as:
    llama-server -m ...Q6_K.gguf --mmproj ...BF16.gguf --jinja --reasoning off
so the launcher must produce those flags, and only for models that need them.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import backends  # noqa: E402


class _FakeProcess:
    pid = 4242


@pytest.fixture()
def capture_command(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_popen(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProcess()

    monkeypatch.setattr(backends.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(backends.os, "getpgid", lambda pid: pid)
    return captured


def _files(tmp_path: Path, model_name: str):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    model = tmp_path / model_name
    model.write_text("gguf")
    mmproj = tmp_path / "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf"
    mmproj.write_text("gguf")
    return binary, model, mmproj


def test_lfm3_gets_mmproj_jinja_and_reasoning_off(capture_command, tmp_path):
    binary, model, mmproj = _files(tmp_path, "LFM3-Omni-2B-Abliter8-Q6_K.gguf")
    ok, message = backends.start_llamacpp(
        {"binary_path": str(binary), "gguf_path": str(model), "mmproj_path": str(mmproj)}
    )
    assert ok, message
    cmd = capture_command["cmd"]
    assert str(binary) in cmd
    assert "-m" in cmd and str(model) in cmd
    assert "--mmproj" in cmd and str(mmproj) in cmd
    assert "--jinja" in cmd
    assert "--reasoning" in cmd and cmd[cmd.index("--reasoning") + 1] == "off"


def test_non_lfm3_model_does_not_get_reasoning_off(capture_command, tmp_path):
    binary, model, _mmproj = _files(tmp_path, "qwen2.5-3b-instruct-q4_k_m.gguf")
    ok, message = backends.start_llamacpp({"binary_path": str(binary), "gguf_path": str(model)})
    assert ok, message
    cmd = capture_command["cmd"]
    assert "--reasoning" not in cmd
    assert "--mmproj" not in cmd


def test_extra_flags_are_passed_through(capture_command, tmp_path):
    binary, model, _mmproj = _files(tmp_path, "LFM3-Omni-2B-Abliter8-Q6_K.gguf")
    ok, message = backends.start_llamacpp(
        {
            "binary_path": str(binary),
            "gguf_path": str(model),
            "llama_extra_flags": ["--ctx-size", "32768", ""],
        }
    )
    assert ok, message
    cmd = capture_command["cmd"]
    assert "--ctx-size" in cmd and "32768" in cmd
    assert "" not in cmd


def test_reasoning_flag_can_be_overridden_off_model(capture_command, tmp_path):
    binary, model, _mmproj = _files(tmp_path, "generic-model.gguf")
    ok, message = backends.start_llamacpp(
        {"binary_path": str(binary), "gguf_path": str(model), "llama_reasoning_off": True}
    )
    assert ok, message
    assert "--reasoning" in capture_command["cmd"]
