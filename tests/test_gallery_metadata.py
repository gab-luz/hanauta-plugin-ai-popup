"""Tests that gallery entries carry their pinned build metadata through a download."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from hanauta_aipopup import catalog, ui_backend_settings  # noqa: E402

PATCH_URL = "https://example.invalid/lfm3-serving-guide.patch"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _entry() -> dict:
    return {
        "id": "lfm3_omni_2b_abliter8",
        "repo_id": "abliter8-ai/lfm3-2b-omni-abliter8-gguf",
        "file": "auto",
        "mmproj": "auto",
        "llama_git_ref": "d05706b4b",
        "llama_patch_url": PATCH_URL,
    }


def test_manager_remembers_entry_metadata(app, monkeypatch):
    monkeypatch.setattr(
        catalog,
        "resolve_gguf_files",
        lambda entry: (
            "LFM3-Omni-2B-Abliter8-Q6_K.gguf",
            "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf",
        ),
    )
    # Never start a real download thread.
    monkeypatch.setattr(ui_backend_settings.GgufModelDownloadWorker, "start", lambda self: None)

    manager = ui_backend_settings.GgufDownloadManager()
    assert manager.start(_entry()) is True

    stored = manager.entry("lfm3_omni_2b_abliter8")
    assert stored["llama_git_ref"] == "d05706b4b"
    assert stored["llama_patch_url"] == PATCH_URL


def test_unknown_entry_returns_empty_dict(app):
    manager = ui_backend_settings.GgufDownloadManager()
    assert manager.entry("nope") == {}


def test_gallery_entry_exposes_patch_slot():
    entry = {item["id"]: item for item in catalog.MODEL_CATALOG["llm_gguf"]}["lfm3_omni_2b_abliter8"]
    assert "llama_patch_url" in entry, "the patch slot must exist for reproducible builds"
    assert entry["llama_git_ref"] == "d05706b4b"
