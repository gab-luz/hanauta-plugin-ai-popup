#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher for the Hanauta AI popup.

The popup itself now lives in ``ai-popup.py`` (the Nest-based rewrite). This
entry point stays because the hyphenated name is not importable, and the plugin
and desktop file use this path. Run the legacy UI with
``python3 -m hanauta_aipopup.app`` while the remaining modules are ported.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_main():
    name = "hanauta_popup_main"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "ai-popup.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def main() -> int:
    return int(load_main().main())


if __name__ == "__main__":
    raise SystemExit(main())
