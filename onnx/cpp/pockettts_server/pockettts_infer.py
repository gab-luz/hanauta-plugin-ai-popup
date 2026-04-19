#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
import wave
from pathlib import Path


def _load_engine(model_dir: Path):
    script_path = model_dir / "pocket_tts_onnx.py"
    if not script_path.exists():
        raise RuntimeError(f"PocketTTS ONNX script not found: {script_path}")
    spec = importlib.util.spec_from_file_location("pockettts_onnx", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load PocketTTS ONNX module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "PocketTTSOnnx"):
        raise RuntimeError("PocketTTSOnnx class not found in pocket_tts_onnx.py")
    return module.PocketTTSOnnx(
        models_dir=str(model_dir / "onnx"),
        tokenizer_path=str(model_dir / "tokenizer.model"),
        precision="int8",
        device="auto",
    )


def _write_wav_float32_mono(path: Path, samples, sample_rate: int) -> None:
    try:
        import numpy as np
    except Exception as exc:
        raise RuntimeError(f"numpy is required: {exc}")

    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        raise RuntimeError("No audio samples produced.")
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice-reference", default="")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args(argv)

    model_dir = Path(args.model_dir).expanduser()
    out_path = Path(args.output).expanduser()
    if not model_dir.exists():
        raise RuntimeError(f"Model dir does not exist: {model_dir}")

    engine = _load_engine(model_dir)
    reference = (
        Path(args.voice_reference).expanduser()
        if args.voice_reference.strip()
        else (model_dir / "reference_sample.wav")
    )
    if not reference.exists():
        raise RuntimeError(f"Voice reference WAV not found: {reference}")

    text = str(args.text or "").strip()
    if not text:
        raise RuntimeError("Empty input text.")

    lang = str(args.language or "").strip() or "auto"
    audio = None
    try:
        audio = engine.generate(text, voice=str(reference), language=lang)
    except TypeError:
        audio = engine.generate(text, voice=str(reference))

    _write_wav_float32_mono(out_path, audio, 24000)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
