from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class SeedVCBackend:
    """
    Backend externo para Seed-VC V2.

    Mantém o Seed-VC isolado do ambiente do KokoClone.
    Espera encontrar:
      - SEEDVC_DIR: diretório do repo seed-vc
      - SEEDVC_PYTHON: python do ambiente/venv/conda do seed-vc
    """

    def __init__(
        self,
        seedvc_dir: str | None = None,
        python_bin: str | None = None,
        diffusion_steps: int = 50,
        length_adjust: float = 1.0,
        intelligibility_cfg_rate: float = 0.80,
        similarity_cfg_rate: float = 0.60,
        convert_style: bool = True,
        anonymization_only: bool = False,
        top_p: float = 0.9,
        temperature: float = 1.0,
        repetition_penalty: float = 1.05,
        compile_model: bool = False,
        cfm_checkpoint_path: str | None = None,
        ar_checkpoint_path: str | None = None,
    ) -> None:
        self.seedvc_dir = Path(
            seedvc_dir or os.environ.get("SEEDVC_DIR", "")
        ).expanduser()

        if not self.seedvc_dir.is_dir():
            raise RuntimeError(
                "Seed-VC não encontrado. Defina SEEDVC_DIR apontando para o diretório do repo seed-vc."
            )

        self.inference_script = self.seedvc_dir / "inference_v2.py"

        if not self.inference_script.is_file():
            raise RuntimeError(
                f"inference_v2.py não encontrado em: {self.inference_script}"
            )

        self.python_bin = python_bin or os.environ.get("SEEDVC_PYTHON", "python")

        self.diffusion_steps = diffusion_steps
        self.length_adjust = length_adjust
        self.intelligibility_cfg_rate = intelligibility_cfg_rate
        self.similarity_cfg_rate = similarity_cfg_rate
        self.convert_style = convert_style
        self.anonymization_only = anonymization_only
        self.top_p = top_p
        self.temperature = temperature
        self.repetition_penalty = repetition_penalty
        self.compile_model = compile_model
        self.cfm_checkpoint_path = cfm_checkpoint_path
        self.ar_checkpoint_path = ar_checkpoint_path

    @staticmethod
    def _bool_arg(value: bool) -> str:
        return "true" if value else "false"

    def convert(
        self,
        source_audio: str | os.PathLike,
        reference_audio: str | os.PathLike,
        output_path: str | os.PathLike,
    ) -> str:
        source_audio = Path(source_audio).resolve()
        reference_audio = Path(reference_audio).resolve()
        output_path = Path(output_path).resolve()

        if not source_audio.is_file():
            raise FileNotFoundError(f"Áudio fonte não encontrado: {source_audio}")

        if not reference_audio.is_file():
            raise FileNotFoundError(f"Áudio de referência não encontrado: {reference_audio}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="kokoclone_seedvc_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            cmd = [
                self.python_bin,
                str(self.inference_script),
                "--source",
                str(source_audio),
                "--target",
                str(reference_audio),
                "--output",
                str(tmpdir_path),
                "--diffusion-steps",
                str(self.diffusion_steps),
                "--length-adjust",
                str(self.length_adjust),
                "--intelligibility-cfg-rate",
                str(self.intelligibility_cfg_rate),
                "--similarity-cfg-rate",
                str(self.similarity_cfg_rate),
                "--convert-style",
                self._bool_arg(self.convert_style),
                "--anonymization-only",
                self._bool_arg(self.anonymization_only),
                "--top-p",
                str(self.top_p),
                "--temperature",
                str(self.temperature),
                "--repetition-penalty",
                str(self.repetition_penalty),
                "--compile",
                self._bool_arg(self.compile_model),
            ]

            if self.cfm_checkpoint_path:
                cmd.extend(["--cfm-checkpoint-path", self.cfm_checkpoint_path])

            if self.ar_checkpoint_path:
                cmd.extend(["--ar-checkpoint-path", self.ar_checkpoint_path])

            subprocess.run(
                cmd,
                cwd=str(self.seedvc_dir),
                check=True,
            )

            wavs = sorted(
                tmpdir_path.glob("*.wav"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )

            if not wavs:
                raise RuntimeError("Seed-VC terminou, mas não gerou nenhum arquivo WAV.")

            shutil.copy2(wavs[0], output_path)

        return str(output_path)