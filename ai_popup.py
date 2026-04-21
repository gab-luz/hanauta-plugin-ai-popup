#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os

# Qt WebEngine can crash on some Linux/GBM GPU stacks. Use conservative flags only.
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
_extra_flags = [
    "--disable-gpu",
    "--disable-features=UseSkiaRenderer,Vulkan",
]
for _flag in _extra_flags:
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags

from hanauta_aipopup.full import main


if __name__ == "__main__":
    raise SystemExit(main())
