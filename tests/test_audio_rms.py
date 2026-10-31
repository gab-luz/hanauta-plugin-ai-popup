"""RMS must not depend on ``audioop`` (removed in Python 3.13).

The old implementation imported it, swallowed the ImportError and returned 0.0,
so every recording measured as silence: voice mode looped "Listening" forever
and dictation failed with "captured only silence" even on a working mic.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import tts, voice  # noqa: E402


def _write_wav(tmp_path: Path, samples: bytes, width: int = 2) -> Path:
    path = tmp_path / f"probe_{width}.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(width)
        handle.setframerate(16000)
        handle.writeframes(samples)
    return path


def _tone(seconds: float = 0.25, amplitude: int = 12000) -> bytes:
    rate = 16000
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(int(rate * seconds))
    )


def test_a_real_tone_is_not_mistaken_for_silence(tmp_path):
    path = _write_wav(tmp_path, _tone())
    for module in (voice, tts):
        rms = module._voice_recording_rms(path)
        assert rms > voice.SILENT_RMS * 100, f"{module.__name__} reported {rms}"
        assert 0.15 < rms < 0.35


def test_digital_silence_still_reads_as_silence(tmp_path):
    path = _write_wav(tmp_path, b"\0\0" * 4000)
    assert voice._voice_recording_rms(path) == 0.0
    assert tts._voice_recording_rms(path) == 0.0


def test_32_bit_and_empty_inputs_do_not_raise():
    assert voice._pcm_rms(b"", 2) == 0.0
    assert voice._pcm_rms(b"\x01", 2) == 0.0  # half a sample
    assert voice._pcm_rms(b"\0" * 64, 4) == 0.0


def test_both_copies_agree():
    frames = _tone(0.1)
    assert voice._pcm_rms(frames, 2) == tts._pcm_rms(frames, 2)
