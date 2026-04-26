from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    pass

KOBOLDCPP_PROFILE_KEY = "koboldcpp"


def _existing_path(value: object) -> Path | None:
    text = _path_text(value)
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.exists() else None


def _path_text(value: object) -> str:
    return str(value).strip()


def _normalize_host_url(host: str) -> str:
    value = host.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


def _openai_compat_alive(host: str) -> bool:
    try:
        import request
        with request.urlopen(f"{_normalize_host_url(host)}/v1/models", timeout=1.2) as response:
            return response.status < 400
    except Exception:
        return False


def _koboldcpp_model_loaded(host: str) -> tuple[bool, str]:
    """
    Returns (loaded, model_name).
    Uses /api/v1/model which only returns a real name once the model is fully loaded.
    Falls back to /api/extra/version to confirm the process is at least running.
    """
    from urllib import request as _req
    base = _normalize_host_url(host)
    try:
        with _req.urlopen(f"{base}/api/v1/model", timeout=3.0) as resp:
            import json as _json
            data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            model = str(data.get("result", "")).strip()
            # KoboldCpp returns "koboldcpp" (no slash) when no model is loaded yet
            if model and "/" in model:
                return True, model.split("/", 1)[-1]
            return False, model
    except Exception:
        return False, ""


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_pgid_alive(pgid: int) -> bool:
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except OSError:
        return False


def koboldcpp_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host and _openai_compat_alive(host):
        return True, f"Server active at {host}"
    pid = int(payload.get("koboldcpp_pid", 0) or 0)
    pgid = int(payload.get("koboldcpp_pgid", 0) or 0)
    if _is_pid_alive(pid) or _is_pgid_alive(pgid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def start_koboldcpp(payload: dict[str, object]) -> tuple[bool, str]:
    binary_path = _existing_path(payload.get("binary_path"))
    gguf_path = _existing_path(payload.get("gguf_path"))
    if binary_path is None or gguf_path is None:
        return False, "Configure both the KoboldCpp binary path and GGUF model first."
    command = [str(binary_path), "--model", str(gguf_path)]
    mmproj_path = _existing_path(payload.get("mmproj_path"))
    if mmproj_path is not None:
        command.extend(["--mmproj", str(mmproj_path)])
    host = str(payload.get("host", "")).strip()
    if host:
        parsed = urlparse(_normalize_host_url(host))
        if parsed.port:
            command.extend(["--port", str(parsed.port)])
        if parsed.hostname and parsed.hostname not in {"", "127.0.0.1", "localhost"}:
            command.extend(["--host", parsed.hostname])
    if str(payload.get("device", "cpu")).lower() == "gpu":
        command.append("--usecublas")
    if bool(payload.get("jinja", False)):
        command.append("--jinja")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Unable to start KoboldCpp: {exc}"
    payload["koboldcpp_pid"] = int(process.pid or 0)
    try:
        payload["koboldcpp_pgid"] = int(os.getpgid(int(process.pid or 0))) if int(process.pid or 0) else 0
    except Exception:
        payload["koboldcpp_pgid"] = int(payload.get("koboldcpp_pgid", 0) or 0)
    return True, f"KoboldCpp started with {gguf_path.name}."


def stop_koboldcpp(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("koboldcpp_pid", 0) or 0)
    pgid = int(payload.get("koboldcpp_pgid", 0) or 0)
    if not _is_pid_alive(pid) and not _is_pgid_alive(pgid):
        payload["koboldcpp_pid"] = 0
        payload["koboldcpp_pgid"] = 0
        return False, "No tracked KoboldCpp process is running."
    try:
        if _is_pgid_alive(pgid):
            os.killpg(pgid, signal.SIGTERM)
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except Exception:
                os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"Unable to stop KoboldCpp: {exc}"
    payload["koboldcpp_pid"] = 0
    payload["koboldcpp_pgid"] = 0
    return True, f"Stopped KoboldCpp process {pid}."