# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path

from .runtime import MODEL_CATALOG_FILE

_HF_MODEL_API = "https://huggingface.co/api/models/{repo_id}"


def _format_bytes(value: int) -> str:
    size = float(max(0, int(value)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size >= 1024.0 and idx < (len(units) - 1):
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _dir_size_bytes(root: Path) -> int:
    try:
        total = 0
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    total += int(path.stat().st_size)
            except Exception:
                continue
        return total
    except Exception:
        return 0


def _load_model_catalog() -> dict[str, list[dict[str, object]]]:
    try:
        raw = json.loads(MODEL_CATALOG_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            out: dict[str, list[dict[str, object]]] = {}
            for key, value in raw.items():
                if isinstance(value, list):
                    cleaned: list[dict[str, object]] = []
                    for entry in value:
                        if isinstance(entry, dict):
                            cleaned.append(dict(entry))
                    out[str(key)] = cleaned
            return out
    except Exception:
        pass
    return {"llm_gguf": []}


MODEL_CATALOG = _load_model_catalog()


def find_entry(entry_id: str, category: str = "llm_gguf") -> dict[str, object] | None:
    """Look up a gallery entry by id (used by the auto-download/auto-configure UI)."""
    for entry in MODEL_CATALOG.get(category, []):
        if str(entry.get("id", "")).strip() == entry_id:
            return dict(entry)
    return None


def _hf_repo_filenames(repo_id: str) -> list[str]:
    """List the file paths in a HuggingFace repo. Returns [] when unreachable."""
    clean = str(repo_id or "").strip().strip("/")
    if not clean:
        return []
    from .http import _http_json

    try:
        payload = _http_json(_HF_MODEL_API.format(repo_id=clean), timeout=20.0)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    siblings = payload.get("siblings", [])
    if not isinstance(siblings, list):
        return []
    names: list[str] = []
    for item in siblings:
        if isinstance(item, dict):
            name = str(item.get("rfilename", "")).strip()
            if name:
                names.append(name)
    return names


def _pick_gguf(candidates: list[str], prefer: str) -> str:
    if not candidates:
        return ""
    token = str(prefer or "").strip().upper()
    if token:
        for name in candidates:
            if token in name.upper():
                return name
    return candidates[0]


def resolve_gguf_files(entry: dict[str, object]) -> tuple[str, str]:
    """Resolve a gallery entry to ``(model_file, mmproj_file)``.

    An entry may leave ``file`` / ``mmproj`` as ``"auto"`` (or empty) and let the
    repo listing decide. That keeps the gallery working when a publisher renames
    quant files or ships the vision projector under a different name.
    """
    explicit_file = str(entry.get("file", "") or "").strip()
    explicit_mmproj = str(entry.get("mmproj", "") or "").strip()

    def _needs_lookup(value: str) -> bool:
        return value.strip().lower() == "auto"

    if not _needs_lookup(explicit_file) and not _needs_lookup(explicit_mmproj):
        # Empty mmproj means "this entry has no vision projector".
        return explicit_file, ("" if explicit_mmproj.lower() in {"", "none"} else explicit_mmproj)

    repo_id = str(entry.get("repo_id", "") or "").strip()
    prefer = str(entry.get("prefer_quant", "") or "").strip()
    files = [name for name in _hf_repo_filenames(repo_id) if name.lower().endswith(".gguf")]
    mmprojs = [name for name in files if Path(name).name.lower().startswith("mmproj")]
    models = [name for name in files if name not in mmprojs]

    model_file = explicit_file if not _needs_lookup(explicit_file) else _pick_gguf(models, prefer)
    if _needs_lookup(explicit_mmproj):
        mmproj_file = _pick_gguf(mmprojs, "bf16") or _pick_gguf(mmprojs, "")
    else:
        mmproj_file = "" if explicit_mmproj.lower() == "none" else explicit_mmproj
    return model_file, mmproj_file


__all__ = [
    "MODEL_CATALOG",
    "_format_bytes",
    "_dir_size_bytes",
    "find_entry",
    "_hf_repo_filenames",
    "_pick_gguf",
    "resolve_gguf_files",
]
