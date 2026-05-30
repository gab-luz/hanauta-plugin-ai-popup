from __future__ import annotations

import os
import signal
import subprocess
import time
import shutil
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
            # KoboldCpp returns "koboldcpp" when no model is loaded yet. Depending on
            # version/config, a loaded model may be returned as either a repo-like
            # name or a plain GGUF filename.
            if model and model.lower() not in {"koboldcpp", "none", "null", "unknown"}:
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


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _find_pids_by_binary(binary_path: Path) -> list[int]:
    """Find running process ids whose /proc/<pid>/exe points to binary_path."""
    target = str(binary_path.expanduser().resolve())
    pids: list[int] = []
    proc_dir = Path("/proc")
    if not proc_dir.exists():
        return pids
    for entry in proc_dir.iterdir():
        name = entry.name
        if not name.isdigit():
            continue
        pid = int(name)
        exe_link = entry / "exe"
        try:
            resolved = str(exe_link.resolve())
        except Exception:
            continue
        if resolved == target:
            pids.append(pid)
    return pids


def _try_graceful_stop_pid(pid: int, timeout_s: float = 2.0) -> tuple[bool, str]:
    if pid <= 0:
        return False, "invalid pid"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, str(exc)
    deadline = time.time() + max(0.1, timeout_s)
    while time.time() < deadline:
        if not _is_pid_alive(pid):
            return True, "stopped"
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError as exc:
        return False, str(exc)
    return (not _is_pid_alive(pid)), "killed"


def _try_pkexec_kill(pid: int) -> tuple[bool, str]:
    """Attempt privileged kill via polkit prompt (desktop environments)."""
    if pid <= 0:
        return False, "invalid pid"
    pkexec = shutil.which("pkexec")
    if not pkexec:
        return False, "pkexec not available"
    # First try TERM, then KILL if still alive.
    for sig in ("-TERM", "-KILL"):
        try:
            res = subprocess.run(
                [pkexec, "/bin/kill", sig, str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except Exception as exc:
            return False, str(exc)
        if res.returncode == 0:
            time.sleep(0.08)
            if not _is_pid_alive(pid):
                return True, "stopped with pkexec"
        err = (res.stderr or "").strip()
        if "not authorized" in err.lower():
            return False, err or "not authorized"
    return (not _is_pid_alive(pid)), "pkexec attempted"


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
    binary_path = _existing_path(payload.get("binary_path"))

    # If tracked process handles are stale, try discovering by configured binary path.
    discovered_pids: list[int] = []
    if not _is_pid_alive(pid) and not _is_pgid_alive(pgid):
        if binary_path is not None:
            discovered_pids = _find_pids_by_binary(binary_path)
        if not discovered_pids:
            payload["koboldcpp_pid"] = 0
            payload["koboldcpp_pgid"] = 0
            return False, "No tracked KoboldCpp process is running."
    try:
        if _is_pgid_alive(pgid):
            os.killpg(pgid, signal.SIGTERM)
        else:
            if _is_pid_alive(pid):
                try:
                    os.killpg(pid, signal.SIGTERM)
                except Exception:
                    os.kill(pid, signal.SIGTERM)
            elif discovered_pids:
                stopped = 0
                errors: list[str] = []
                for found_pid in discovered_pids:
                    ok, detail = _try_graceful_stop_pid(found_pid)
                    if ok:
                        stopped += 1
                        continue
                    if "operation not permitted" in detail.lower() or "permission denied" in detail.lower():
                        pk_ok, pk_detail = _try_pkexec_kill(found_pid)
                        if pk_ok:
                            stopped += 1
                            continue
                        errors.append(f"pid {found_pid}: {pk_detail}")
                    else:
                        errors.append(f"pid {found_pid}: {detail}")
                if stopped <= 0:
                    raise OSError("; ".join(errors) if errors else "unable to stop discovered KoboldCpp process")
    except OSError as exc:
        return False, f"Unable to stop KoboldCpp: {exc}"
    payload["koboldcpp_pid"] = 0
    payload["koboldcpp_pgid"] = 0
    if discovered_pids and not _is_pid_alive(pid):
        return True, f"Stopped KoboldCpp process(es): {', '.join(str(p) for p in discovered_pids)}."
    return True, f"Stopped KoboldCpp process {pid}."
