from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
import shutil
import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from urllib import request as _req

if TYPE_CHECKING:
    pass

KOBOLDCPP_PROFILE_KEY = "koboldcpp"
LLAMACPP_PROFILE_KEY = "llamacpp"


def _runtime_root(payload: dict[str, object]) -> Path:
    configured = str(payload.get("runtime_dir", "")).strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "hanauta-ai-popup"


def _ensure_llamacpp_binary(payload: dict[str, object]) -> tuple[bool, str, Path | None]:
    mtp_enabled = bool(payload.get("llama_mtp_enabled", False))
    flash_enabled = bool(payload.get("llama_flash_attn", False))
    needs_atomic = mtp_enabled or flash_enabled
    repo_url = (
        "https://github.com/AtomicBot-ai/atomic-llama-cpp-turboquant.git"
        if needs_atomic
        else "https://github.com/ggerganov/llama.cpp.git"
    )
    runtime_root = _runtime_root(payload)
    install_root = runtime_root / "runtimes" / ("atomic-llama-cpp" if needs_atomic else "llama-cpp")
    src_dir = install_root / "src"
    build_dir = src_dir / "build"
    bin_dir = build_dir / "bin"
    candidates = [
        bin_dir / "llama-server",
        bin_dir / "server",
        src_dir / "llama-server",
        src_dir / "server",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
            try:
                candidate.chmod(0o755)
            except Exception:
                pass
            return True, f"Using managed {'atomic-llama' if needs_atomic else 'llama.cpp'} runtime.", candidate
    if shutil.which("git") is None:
        return False, "git is required to auto-install llama.cpp runtime.", None
    if shutil.which("cmake") is None:
        return False, "cmake is required to auto-install llama.cpp runtime.", None
    install_root.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(src_dir)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["git", "-C", str(src_dir), "pull", "--ff-only"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        ["cmake", "-S", str(src_dir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    jobs = str(max(1, int(multiprocessing.cpu_count() or 1) - 1))
    build_cmd = ["cmake", "--build", str(build_dir), "--config", "Release", "-j", jobs, "--target", "llama-server"]
    result = subprocess.run(build_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        fallback_cmd = ["cmake", "--build", str(build_dir), "--config", "Release", "-j", jobs, "--target", "server"]
        subprocess.run(fallback_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 0:
            try:
                candidate.chmod(0o755)
            except Exception:
                pass
            flavor = "atomic-llama (turboquant/MTP)" if needs_atomic else "llama.cpp"
            return True, f"Installed and compiled {flavor} runtime.", candidate
    return False, "llama.cpp build finished but server binary was not found.", None


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


def _llamacpp_model_loaded(host: str) -> tuple[bool, str]:
    """Return (loaded, model_name) for llama.cpp OpenAI server mode."""
    from urllib import request as _req
    base = _normalize_host_url(host)
    try:
        with _req.urlopen(f"{base}/v1/models", timeout=2.5) as resp:
            import json as _json
            data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            rows = data.get("data", [])
            if isinstance(rows, list) and rows:
                first = rows[0] if isinstance(rows[0], dict) else {}
                model = str(first.get("id", "") or first.get("name", "")).strip()
                if model:
                    return True, model.split("/", 1)[-1]
            return True, "llama.cpp"
    except Exception:
        return False, ""


def llamacpp_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host and _openai_compat_alive(host):
        return True, f"Server active at {host}"
    pid = int(payload.get("llamacpp_pid", 0) or 0)
    pgid = int(payload.get("llamacpp_pgid", 0) or 0)
    if _is_pid_alive(pid) or _is_pgid_alive(pgid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def start_llamacpp(payload: dict[str, object]) -> tuple[bool, str]:
    binary_path = _existing_path(payload.get("binary_path"))
    bootstrap_note = ""
    if binary_path is None:
        try:
            ok_boot, note_boot, managed_bin = _ensure_llamacpp_binary(payload)
        except Exception as exc:
            return False, f"Failed to install/compile llama.cpp runtime: {exc}"
        if not ok_boot or managed_bin is None:
            return False, note_boot
        payload["binary_path"] = str(managed_bin)
        binary_path = managed_bin
        bootstrap_note = note_boot
    gguf_path = _existing_path(payload.get("gguf_path"))
    if gguf_path is None:
        repo = str(payload.get("llama_hf_repo", "")).strip()
        filename = str(payload.get("llama_hf_file", "")).strip()
        if repo and filename:
            cache_root = Path(str(payload.get("llama_hf_cache_dir", Path.home() / ".cache" / "hanauta-ai-popup" / "llm-models"))).expanduser()
            safe_repo = repo.replace("/", "--")
            target_dir = cache_root / safe_repo
            target_dir.mkdir(parents=True, exist_ok=True)
            out = target_dir / Path(filename).name
            if not out.exists() or out.stat().st_size <= 0:
                url = f"https://huggingface.co/{repo}/resolve/main/{filename}?download=true"
                try:
                    req = _req.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
                    with _req.urlopen(req, timeout=1800) as resp, out.open("wb") as handle:
                        while True:
                            chunk = resp.read(1024 * 1024)
                            if not chunk:
                                break
                            handle.write(chunk)
                except Exception as exc:
                    return False, f"Failed to download llama.cpp target GGUF: {exc}"
            payload["gguf_path"] = str(out)
            gguf_path = out
    if binary_path is None or gguf_path is None:
        return False, "Configure both llama.cpp binary path and GGUF model first."
    command = [str(binary_path), "-m", str(gguf_path)]
    host = str(payload.get("host", "")).strip()
    if host:
        parsed = urlparse(_normalize_host_url(host))
        if parsed.hostname:
            command.extend(["--host", str(parsed.hostname)])
        if parsed.port:
            command.extend(["--port", str(parsed.port)])
    # Performance flags
    if bool(payload.get("llama_flash_attn", False)):
        command.append("--flash-attn")
    if bool(payload.get("llama_mtp_enabled", False)):
        draft = _existing_path(payload.get("llama_mtp_draft_model"))
        if draft is None:
            d_repo = str(payload.get("llama_hf_draft_repo", "")).strip()
            d_file = str(payload.get("llama_hf_draft_file", "")).strip()
            if d_repo and d_file:
                cache_root = Path(str(payload.get("llama_hf_cache_dir", Path.home() / ".cache" / "hanauta-ai-popup" / "llm-models"))).expanduser()
                safe_repo = d_repo.replace("/", "--")
                target_dir = cache_root / safe_repo
                target_dir.mkdir(parents=True, exist_ok=True)
                out = target_dir / Path(d_file).name
                if not out.exists() or out.stat().st_size <= 0:
                    url = f"https://huggingface.co/{d_repo}/resolve/main/{d_file}?download=true"
                    try:
                        req = _req.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
                        with _req.urlopen(req, timeout=1800) as resp, out.open("wb") as handle:
                            while True:
                                chunk = resp.read(1024 * 1024)
                                if not chunk:
                                    break
                                handle.write(chunk)
                    except Exception as exc:
                        return False, f"Failed to download llama.cpp MTP draft GGUF: {exc}"
                payload["llama_mtp_draft_model"] = str(out)
                draft = out
        if draft is not None:
            command.extend(["--draft-model", str(draft)])
        draft_n = str(payload.get("llama_mtp_draft_n", "")).strip()
        if draft_n:
            command.extend(["--draft-max", draft_n])
    n_batch = str(payload.get("llama_n_batch", "")).strip()
    if n_batch:
        command.extend(["--batch-size", n_batch])
    if str(payload.get("device", "cpu")).lower() == "gpu":
        command.append("--gpu-layers")
        command.append(str(payload.get("llama_gpu_layers", "99") or "99"))
    extra_args = str(payload.get("llama_extra_args", "")).strip()
    if extra_args:
        try:
            command.extend(shlex.split(extra_args))
        except Exception:
            return False, "Invalid llama.cpp extra args."
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Unable to start llama.cpp: {exc}"
    payload["llamacpp_pid"] = int(process.pid or 0)
    try:
        payload["llamacpp_pgid"] = int(os.getpgid(int(process.pid or 0))) if int(process.pid or 0) else 0
    except Exception:
        payload["llamacpp_pgid"] = int(payload.get("llamacpp_pgid", 0) or 0)
    suffix = f" {bootstrap_note}" if bootstrap_note else ""
    return True, f"llama.cpp started with {gguf_path.name}.{suffix}"


def stop_llamacpp(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("llamacpp_pid", 0) or 0)
    pgid = int(payload.get("llamacpp_pgid", 0) or 0)
    binary_path = _existing_path(payload.get("binary_path"))
    discovered_pids: list[int] = []
    if not _is_pid_alive(pid) and not _is_pgid_alive(pgid):
        if binary_path is not None:
            discovered_pids = _find_pids_by_binary(binary_path)
        if not discovered_pids:
            payload["llamacpp_pid"] = 0
            payload["llamacpp_pgid"] = 0
            return False, "No tracked llama.cpp process is running."
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
                for found_pid in discovered_pids:
                    _try_graceful_stop_pid(found_pid)
    except OSError as exc:
        return False, f"Unable to stop llama.cpp: {exc}"
    payload["llamacpp_pid"] = 0
    payload["llamacpp_pgid"] = 0
    return True, f"Stopped llama.cpp process {pid}."
