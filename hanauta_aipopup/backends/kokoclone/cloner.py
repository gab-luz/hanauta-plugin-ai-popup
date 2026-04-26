from __future__ import annotations

import os
import tempfile

import numpy as np
import soundfile as sf
import torch
from kokoro import KPipeline

from core.seedvc_backend import SeedVCBackend


class KokoClone:
    def __init__(
        self,
        kokoro_repo: str = "hexgrad/Kokoro-82M",
        seedvc_dir: str | None = None,
        seedvc_python: str | None = None,
    ) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Initializing KokoClone on: {self.device.type.upper()}")

        self.kokoro_repo = kokoro_repo
        self.kokoro_pipeline_cache: dict[str, KPipeline] = {}

        print("Loading Seed-VC V2 backend...")
        self.seedvc = SeedVCBackend(
            seedvc_dir=seedvc_dir,
            python_bin=seedvc_python,

            # Bons defaults para pt-BR TTS → voz feminina de referência
            diffusion_steps=50,
            length_adjust=1.0,
            intelligibility_cfg_rate=0.80,
            similarity_cfg_rate=0.60,
            convert_style=True,
            anonymization_only=False,
            top_p=0.9,
            temperature=1.0,
            repetition_penalty=1.05,
            compile_model=False,
        )

    def _get_config(self, lang: str) -> tuple[str, str]:
        """
        Map public language codes to official Kokoro pipeline codes and default voices.
        """
        config = {
            "en": ("a", "af_bella"),
            "hi": ("h", "hf_alpha"),
            "fr": ("f", "ff_siwis"),
            "it": ("i", "im_nicola"),
            "es": ("e", "ef_dora"),
            "pt": ("p", "pf_dora"),
            "ja": ("j", "jf_alpha"),
            "zh": ("z", "zf_001"),
        }

        try:
            return config[lang]
        except KeyError as exc:
            raise ValueError(f"Language '{lang}' not supported.") from exc

    def _get_official_kokoro_pipeline(self, lang: str) -> KPipeline:
        """
        Return a cached official Kokoro pipeline for the requested language.
        """
        lang_code, _ = self._get_config(lang)

        if lang_code not in self.kokoro_pipeline_cache:
            self.kokoro_pipeline_cache[lang_code] = KPipeline(
                lang_code=lang_code,
                repo_id=self.kokoro_repo,
                device=self.device.type,
            )

        return self.kokoro_pipeline_cache[lang_code]

    def _synthesize_with_official_kokoro(
        self,
        pipeline: KPipeline,
        text: str,
        voice: str,
    ) -> tuple[np.ndarray, int]:
        """
        Use the upstream Kokoro pipeline for speech synthesis before Seed-VC conversion.
        """
        chunks: list[np.ndarray] = []

        for _, _, audio in pipeline(
            text,
            voice=voice,
            speed=1.0,
            split_pattern=r"\n+",
        ):
            chunks.append(np.asarray(audio, dtype=np.float32))

        if not chunks:
            raise RuntimeError("Official Kokoro pipeline produced no audio chunks.")

        return np.concatenate(chunks), 24000

    def generate(
        self,
        text: str,
        lang: str,
        reference_audio: str,
        output_path: str = "output.wav",
    ) -> None:
        """
        Text → Kokoro pt-BR/native TTS → Seed-VC V2 reference voice conversion.
        """
        _, voice = self._get_config(lang)

        official_pipeline = self._get_official_kokoro_pipeline(lang)

        print(f"Synthesizing text ({lang.upper()}) with official Kokoro pipeline...")
        samples, sr = self._synthesize_with_official_kokoro(
            official_pipeline,
            text,
            voice,
        )

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_path = temp_audio.name

            sf.write(temp_path, samples, sr)

            print("Applying Seed-VC V2 voice/accent conversion...")
            self.seedvc.convert(
                source_audio=temp_path,
                reference_audio=reference_audio,
                output_path=output_path,
            )

            print(f"Success! Saved: {output_path}")

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def convert(
        self,
        source_audio: str,
        reference_audio: str,
        output_path: str = "output.wav",
    ) -> None:
        """
        Audio → Seed-VC V2 reference voice conversion.
        """
        print("Applying Seed-VC V2 voice/accent conversion...")

        self.seedvc.convert(
            source_audio=source_audio,
            reference_audio=reference_audio,
            output_path=output_path,
        )

        print(f"Success! Saved: {output_path}")