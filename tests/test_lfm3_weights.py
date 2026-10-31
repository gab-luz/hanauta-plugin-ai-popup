"""Weight resolution for llama.cpp backends.

A configured path that no longer exists must not read as "no model": the files
are usually already in the download cache, and when they genuinely are missing
LFM3 can fetch its published GGUF repo on its own.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import backends  # noqa: E402


def _cache_with(tmp_path: Path, model: str = "LFM3-Omni-2B-Abliter8-Q6_K.gguf", mmproj: str = "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf") -> Path:
    repo_dir = tmp_path / backends.LFM3_HF_REPO.replace("/", "--")
    repo_dir.mkdir(parents=True, exist_ok=True)
    for name in (model, mmproj):
        (repo_dir / name).write_bytes(b"gguf")
    return repo_dir


def _payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "gguf_path": "/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf",
        "mmproj_path": "/models/mmproj-BF16.gguf",
        "llama_runtime_flavor": "lfm3",
        "llama_hf_cache_dir": str(tmp_path),
    }
    payload.update(overrides)
    return payload


def test_placeholder_paths_are_replaced_by_cached_weights(tmp_path, monkeypatch):
    # This is the reported bug: /models/... does not exist, the downloaded files do.
    repo_dir = _cache_with(tmp_path)
    monkeypatch.setattr(backends, "_download_hf_file", lambda *a, **k: pytest.fail("network used"))

    model, mmproj, note = backends.resolve_llama_weights(_payload(tmp_path), download=False)

    assert model == repo_dir / "LFM3-Omni-2B-Abliter8-Q6_K.gguf"
    assert mmproj == repo_dir / "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf"
    assert "cached" in note.lower()


def test_configured_paths_are_never_overwritten(tmp_path, monkeypatch):
    real = tmp_path / "mine.gguf"
    real.write_bytes(b"gguf")
    _cache_with(tmp_path)
    monkeypatch.setattr(backends, "_download_hf_file", lambda *a, **k: pytest.fail("network used"))

    model, _mmproj, _note = backends.resolve_llama_weights(
        _payload(tmp_path, gguf_path=str(real)), download=False
    )

    assert model == real


def test_missing_weights_are_downloaded_from_the_lfm3_repo(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_download(
        repo: str, filename: str, dest: Path, timeout: float = 1800.0, progress=None
    ) -> Path:
        calls.append((repo, filename))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"gguf")
        if progress is not None:
            progress(dest.name, 4, 4)
        return dest

    monkeypatch.setattr(backends, "_download_hf_file", fake_download)

    model, mmproj, note = backends.resolve_llama_weights(_payload(tmp_path, llama_hf_cache_dir=str(tmp_path)))

    assert model is not None and model.exists()
    assert mmproj is not None and mmproj.exists()
    assert (backends.LFM3_HF_REPO, backends.LFM3_MODEL_FILE) in calls
    assert (backends.LFM3_HF_REPO, backends.LFM3_MMPROJ_FILE) in calls
    assert "Downloaded" in note


def test_download_progress_is_forwarded_to_the_caller(tmp_path, monkeypatch):
    seen: list[tuple] = []

    def fake_download(repo, filename, dest, timeout=1800.0, progress=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * 10)
        if progress is not None:
            progress(dest.name, 10, 10)
        return dest

    monkeypatch.setattr(backends, "_download_hf_file", fake_download)

    def report(name: str, done: int, total: int) -> None:
        seen.append((name, done, total))

    backends.resolve_llama_weights(_payload(tmp_path), progress=report)

    assert seen and seen[0][1] == 10


def test_auto_download_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_download_hf_file", lambda *a, **k: pytest.fail("network used"))

    model, mmproj, _note = backends.resolve_llama_weights(
        _payload(tmp_path, llama_auto_download=False)
    )

    assert model is None and mmproj is None


def test_a_failed_projector_download_still_leaves_text_usable(tmp_path, monkeypatch):
    def fake_download(
        repo: str, filename: str, dest: Path, timeout: float = 1800.0, progress=None
    ) -> Path:
        if filename.startswith("mmproj"):
            raise RuntimeError("404")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"gguf")
        return dest

    monkeypatch.setattr(backends, "_download_hf_file", fake_download)

    model, mmproj, note = backends.resolve_llama_weights(_payload(tmp_path))

    assert model is not None and mmproj is None
    assert "images/audio stay off" in note


def test_non_lfm3_payloads_do_not_fetch_lfm3_weights(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_download_hf_file", lambda *a, **k: pytest.fail("network used"))

    model, _mmproj, _note = backends.resolve_llama_weights(
        {"gguf_path": "/nope.gguf", "llama_hf_cache_dir": str(tmp_path)}
    )

    assert model is None


def test_panel_persists_adopted_weights(tmp_path, monkeypatch):
    # Startup must rewrite the stale placeholder paths once, so the popup stops
    # reporting missing weights that are actually downloaded.
    from hanauta_aipopup import ui_panel

    repo_dir = _cache_with(tmp_path)
    saved: list[dict] = []
    monkeypatch.setattr(ui_panel, "save_backend_settings", lambda settings: saved.append(dict(settings)))

    class _Panel:
        backend_settings = {
            "lfm3": {
                "gguf_path": "/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf",
                "mmproj_path": "/models/mmproj-BF16.gguf",
                "llama_runtime_flavor": "lfm3",
                "llama_hf_cache_dir": str(tmp_path),
            }
        }
        _backend_settings_file_mtime = staticmethod(lambda: 0.0)

    _Panel._adopt_cached_llama_weights = ui_panel.SidebarPanel._adopt_cached_llama_weights
    panel = _Panel()
    panel._adopt_cached_llama_weights()

    assert panel.backend_settings["lfm3"]["gguf_path"] == str(repo_dir / "LFM3-Omni-2B-Abliter8-Q6_K.gguf")
    assert panel.backend_settings["lfm3"]["mmproj_path"] == str(
        repo_dir / "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf"
    )
    assert len(saved) == 1

    # A second pass must not rewrite the file again.
    panel._adopt_cached_llama_weights()
    assert len(saved) == 1
