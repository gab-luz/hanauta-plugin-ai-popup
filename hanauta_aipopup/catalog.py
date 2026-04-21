# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path

from .runtime import MODEL_CATALOG_FILE


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

