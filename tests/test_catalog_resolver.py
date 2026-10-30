"""Tests for gallery entry resolution (GGUF quant + vision projector)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import catalog  # noqa: E402

# Real filenames as published in abliter8-ai/lfm3-2b-omni-abliter8-gguf.
REPO_FILES = [
    "README.md",
    "LFM3-Omni-2B-Abliter8-BF16.gguf",
    "LFM3-Omni-2B-Abliter8-Q8_0.gguf",
    "LFM3-Omni-2B-Abliter8-Q6_K.gguf",
    "LFM3-Omni-2B-Abliter8-Q4_K_M.gguf",
    "LFM3-Omni-2B-Abliter8-Q4_0.gguf",
    "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf",
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Never touch HuggingFace in tests."""
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: [])


def _entry(entry_id: str) -> dict:
    entries = {item["id"]: item for item in catalog.MODEL_CATALOG["llm_gguf"]}
    return entries[entry_id]


def test_lfm3_omni_entry_is_in_the_gallery():
    entry = _entry("lfm3_omni_2b_abliter8")
    assert entry["repo_id"] == "abliter8-ai/lfm3-2b-omni-abliter8-gguf"
    assert entry["mmproj"] == "auto"


def test_entry_matches_the_model_card():
    entry = _entry("lfm3_omni_2b_abliter8")
    assert entry["context"] == 32768
    assert entry["license"] == "LFM Open License v1.0"
    assert entry["llama_git_ref"] == "d05706b4b"
    assert "--jinja" in entry["llama_flags"]
    assert "off" in entry["llama_flags"]


def test_resolves_recommended_quant_and_mmproj(monkeypatch):
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: list(REPO_FILES))
    model_file, mmproj_file = catalog.resolve_gguf_files(_entry("lfm3_omni_2b_abliter8"))
    assert model_file == "LFM3-Omni-2B-Abliter8-Q6_K.gguf"
    assert mmproj_file == "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf"


def test_q8_preference_is_honoured(monkeypatch):
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: list(REPO_FILES))
    entry = dict(_entry("lfm3_omni_2b_abliter8"), prefer_quant="Q8_0")
    model_file, _ = catalog.resolve_gguf_files(entry)
    assert model_file == "LFM3-Omni-2B-Abliter8-Q8_0.gguf"


def test_mmproj_is_never_chosen_as_the_model(monkeypatch):
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: list(REPO_FILES))
    model_file, _ = catalog.resolve_gguf_files(_entry("lfm3_omni_2b_abliter8"))
    assert not Path(model_file).name.lower().startswith("mmproj")


def test_unreachable_repo_resolves_to_empty(monkeypatch):
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: [])
    model_file, mmproj_file = catalog.resolve_gguf_files(_entry("lfm3_omni_2b_abliter8"))
    assert model_file == ""
    assert mmproj_file == ""


def test_explicit_entry_makes_no_lookup(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(catalog, "_hf_repo_filenames", lambda repo_id: calls.append(repo_id) or [])
    model_file, mmproj_file = catalog.resolve_gguf_files(_entry("phi3_mini_4k_q4"))
    assert model_file == "Phi-3-mini-4k-instruct-q4.gguf"
    assert mmproj_file == ""
    assert calls == [], "entries with a fixed filename must not query the network"
