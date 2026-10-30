"""Tests for the llama.cpp runtime build plan (flavor, repo, ref, prebuilt)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import backends  # noqa: E402


def test_auto_flavor_picks_atomic_for_mtp():
    plan = backends.llama_build_plan({"llama_runtime_flavor": "auto", "llama_mtp_enabled": True})
    assert plan["flavor"] == "atomic"
    assert "atomic" in str(plan["install_root"])


def test_auto_flavor_defaults_to_upstream():
    plan = backends.llama_build_plan({"llama_runtime_flavor": "auto"})
    assert plan["flavor"] == "upstream"


def test_lfm3_flavor_has_its_own_install_dir():
    plan = backends.llama_build_plan({"llama_runtime_flavor": "lfm3"})
    assert plan["flavor"] == "lfm3"
    assert str(plan["install_root"]).endswith("lfm3-llama-cpp")
    assert str(plan["source_dir"]).endswith("src")


def test_unknown_flavor_falls_back_to_upstream():
    plan = backends.llama_build_plan({"llama_runtime_flavor": "nonsense"})
    assert plan["flavor"] == "upstream"


def test_explicit_repo_and_ref_override_defaults():
    plan = backends.llama_build_plan(
        {
            "llama_runtime_flavor": "lfm3",
            "llama_git_url": "https://github.com/someone/lfm3-llama.cpp.git",
            "llama_git_ref": "lfm3-omni",
        }
    )
    assert plan["repo_url"] == "https://github.com/someone/lfm3-llama.cpp.git"
    assert plan["git_ref"] == "lfm3-omni"


def test_runtime_dir_is_respected(tmp_path):
    plan = backends.llama_build_plan({"llama_runtime_flavor": "lfm3", "runtime_dir": str(tmp_path)})
    assert str(plan["install_root"]).startswith(str(tmp_path))


def test_explicit_binary_path_is_used_without_building(tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    found = backends._prebuilt_llama_server(
        {"llama_runtime_flavor": "lfm3", "runtime_dir": str(tmp_path), "llama_server_binary": str(binary)}
    )
    assert found == binary


def test_installed_binary_is_detected(tmp_path):
    install = tmp_path / "runtimes" / "lfm3-llama-cpp"
    install.mkdir(parents=True)
    binary = install / "llama-server"
    binary.write_text("x")
    binary.chmod(0o755)
    found = backends._prebuilt_llama_server({"llama_runtime_flavor": "lfm3", "runtime_dir": str(tmp_path)})
    assert found == binary


def test_no_binary_means_build_is_required(tmp_path):
    assert backends._prebuilt_llama_server(
        {"llama_runtime_flavor": "lfm3", "runtime_dir": str(tmp_path)}
    ) is None


def test_non_executable_explicit_path_is_ignored(tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text("not executable")
    binary.chmod(0o644)
    assert backends._prebuilt_llama_server(
        {"llama_runtime_flavor": "lfm3", "runtime_dir": str(tmp_path), "llama_server_binary": str(binary)}
    ) is None
    assert os.access(binary, os.X_OK) is False


@pytest.fixture(autouse=True)
def _ignore_vendored_runtime(monkeypatch, tmp_path):
    """Keep prebuilt detection isolated from the binary shipped in vendor/."""
    from hanauta_aipopup import backends

    monkeypatch.setattr(backends, "_VENDOR_LLAMA_DIR", tmp_path / "no-vendor")
