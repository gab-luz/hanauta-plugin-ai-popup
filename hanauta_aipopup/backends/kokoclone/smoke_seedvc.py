from __future__ import annotations

import argparse
from pathlib import Path

from .seedvc_backend import SeedVCBackend


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed-VC V2 smoke test (external repo + venv).")
    parser.add_argument("--source", required=True, help="Path to source WAV to convert.")
    parser.add_argument("--reference", required=True, help="Path to reference WAV.")
    parser.add_argument("--output", required=True, help="Output WAV path.")
    args = parser.parse_args()

    out = SeedVCBackend().convert(
        source_audio=Path(args.source).expanduser(),
        reference_audio=Path(args.reference).expanduser(),
        output_path=Path(args.output).expanduser(),
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

