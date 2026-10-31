from __future__ import annotations

import os
import re
import shlex
import socket
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


# flavor -> (repo url, default git ref)
_LLAMA_REPO_DEFAULTS: dict[str, tuple[str, str]] = {
    "upstream": ("https://github.com/ggml-org/llama.cpp.git", "master"),
    "atomic": ("https://github.com/AtomicBot-ai/atomic-llama-cpp-turboquant.git", "feature/turboquant-kv-cache"),
    # LFM3-Omni (text + vision + audio): the model card pins llama.cpp at d05706b4b
    # "plus the documented server patch" from the Abliter8 LFM3 serving guide.
    # Override llama_git_url / llama_git_ref (or the script's LLAMA_REPO / LLAMA_REF)
    # and supply llama_patch_url (or PATCH_URL / PATCH_FILE) to pin your own build.
    "lfm3": ("https://github.com/ggml-org/llama.cpp.git", "d05706b4b"),
}
# The model card requires a server patch from the Abliter8 LFM3 serving guide on
# top of the pinned commit, so the build is only reproducible with both.
_LLAMA_PATCH_DEFAULTS: dict[str, str] = {
    "lfm3": (
        "https://raw.githubusercontent.com/abliter8-ai/lfm3-abliter8-serving/"
        "main/patches/llama.cpp-lfm3-server.patch"
    ),
}
_LLAMA_INSTALL_DIRS: dict[str, str] = {
    "upstream": "llama-cpp",
    "atomic": "atomic-llama-cpp",
    "lfm3": "lfm3-llama-cpp",
}
# Drop-in location for a maintainer-provided binary, so users never need a toolchain.
_VENDOR_LLAMA_DIR = Path(__file__).resolve().parents[2] / "vendor" / "llama-lfm3"
# GPU build, preferred when present so inference uses the graphics card.
_VENDOR_LLAMA_CUDA_DIR = Path(__file__).resolve().parents[2] / "vendor" / "llama-lfm3-cuda"


def _llama_flavor(payload: dict[str, object]) -> str:
    flavor = str(payload.get("llama_runtime_flavor", "auto")).strip().lower() or "auto"
    if flavor == "auto":
        needs_atomic = bool(payload.get("llama_mtp_enabled", False)) or bool(payload.get("llama_flash_attn", False))
        return "atomic" if needs_atomic else "upstream"
    return flavor if flavor in _LLAMA_REPO_DEFAULTS else "upstream"


def llama_build_plan(payload: dict[str, object]) -> dict[str, object]:
    """Resolve runtime flavor into repo/ref/install paths. Pure, no I/O."""
    flavor = _llama_flavor(payload)
    default_repo, default_ref = _LLAMA_REPO_DEFAULTS[flavor]
    repo_url = str(payload.get("llama_git_url", "")).strip() or default_repo
    git_ref = str(payload.get("llama_git_ref", "")).strip() or default_ref
    patch_url = str(payload.get("llama_patch_url", "")).strip() or _LLAMA_PATCH_DEFAULTS.get(flavor, "")
    install_root = _runtime_root(payload) / "runtimes" / _LLAMA_INSTALL_DIRS[flavor]
    source_dir = Path(str(payload.get("llama_source_dir", "")).strip() or (install_root / "src"))
    build_dir = Path(str(payload.get("llama_build_dir", "")).strip() or (source_dir / "build"))
    return {
        "flavor": flavor,
        "repo_url": repo_url,
        "git_ref": git_ref,
        "patch_url": patch_url,
        "install_root": install_root,
        "source_dir": source_dir,
        "build_dir": build_dir,
    }


def _prebuilt_llama_server(payload: dict[str, object]) -> Path | None:
    """Return an already-usable llama-server binary, so nothing needs compiling."""
    for key in ("llama_server_binary", "binary_path"):
        explicit = _existing_path(payload.get(key))
        if explicit is not None and explicit.is_file() and os.access(explicit, os.X_OK):
            return explicit
    plan = llama_build_plan(payload)
    install_root = Path(str(plan["install_root"]))
    backend = str(payload.get("llama_compute_backend", "cpu")).strip() or "cpu"
    roots = [
        install_root,
        install_root / "current",
        install_root / backend,
        install_root / "cpu",
        Path(str(plan["build_dir"])) / "bin",
        _VENDOR_LLAMA_CUDA_DIR,
        _VENDOR_LLAMA_DIR,
    ]
    for root in roots:
        for name in ("llama-server", "server"):
            candidate = root / name
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
            except OSError:
                continue
    return None


def lfm3_build_env(plan: dict[str, object], payload: dict[str, object]) -> dict[str, str]:
    """Environment overrides for scripts/build_llama_lfm3.sh (matrix + verify)."""
    env: dict[str, str] = {
        "LLAMA_REPO": str(plan["repo_url"]),
        "LLAMA_REF": str(plan["git_ref"]),
        "PREFIX": str(plan["install_root"]),
        "JOBS": str(max(1, (multiprocessing.cpu_count() or 2) - 1)),
        "BACKENDS": str(payload.get("llama_compute_backend", "cpu")).strip() or "cpu",
    }
    if str(payload.get("device", "cpu")).strip().lower() == "gpu":
        env["CMAKE_EXTRA"] = "-DGGML_CUDA=ON"
    # Payload override first, then the flavor's documented patch (see _LLAMA_PATCH_DEFAULTS).
    patch_url = str(payload.get("llama_patch_url", "")).strip() or str(plan.get("patch_url", "")).strip()
    if patch_url:
        env["PATCH_URL"] = patch_url
    if bool(payload.get("llama_verify_after_build", False)):
        # The script boots the server and waits for the model to load.
        model = str(payload.get("gguf_path", "")).strip()
        mmproj = str(payload.get("mmproj_path", "")).strip()
        if model:
            env["SMOKE_MODEL"] = model
        if mmproj:
            env["SMOKE_MMPROJ"] = mmproj
    return env


def _draft_model_args(binary: Path | None, draft: str) -> list[str]:
    """Draft-model argv. Newer llama.cpp renamed this to ``--spec-draft-model``."""
    if binary is not None and llama_supports_flag(binary, "--spec-draft-model"):
        return ["--spec-draft-model", draft]
    return ["--model-draft", draft]


def _draft_max_args(binary: Path | None, count: str) -> list[str]:
    """Draft length argv. ``--draft-max`` was removed outright in newer builds."""
    if binary is not None and llama_supports_flag(binary, "--spec-draft-n-max"):
        return ["--spec-draft-n-max", count]
    return ["--draft-max", count]


def _cpu_runtime_binary(payload: dict[str, object]) -> Path | None:
    """A CPU build to fall back to when the GPU runtime sees no device."""
    roots: list[Path] = [_VENDOR_LLAMA_DIR]
    try:
        roots.insert(0, Path(str(_runtime_root(payload))))
    except Exception:
        pass
    for root in roots:
        for name in ("cpu", "backend"):
            candidate = root / name / "llama-server"
            if candidate.is_file():
                return candidate
    return None


def _port_in_use_note(payload: dict[str, object]) -> str:
    """Refuse to start when another service already owns the port.

    llama.cpp exits immediately if it cannot bind, which used to look like a
    successful start; the Hanauta host server squatting on 8081 made every LFM3
    launch fail silently.
    """
    host = str(payload.get("host", "")).strip()
    if not host:
        return ""
    parsed = urlparse(_normalize_host_url(host))
    if not parsed.hostname or not parsed.port:
        return ""
    probe = "127.0.0.1" if parsed.hostname in {"0.0.0.0", "::", "localhost"} else parsed.hostname
    try:
        with socket.create_connection((probe, parsed.port), timeout=0.6):
            pass
    except OSError:
        return ""
    return (
        f"Port {parsed.port} is already in use by another service, so llama.cpp cannot bind it. "
        "Set a free host for this backend (for example 127.0.0.1:8082) or stop that service."
    )


def _pick_free_port(start_port: int, attempts: int = 25) -> int | None:
    """First port at or after ``start_port`` that nothing is listening on."""
    for port in range(start_port, min(start_port + attempts, 65536)):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                continue
        except OSError:
            return port
    return None


def _reassign_busy_port(payload: dict[str, object]) -> str:
    """Move the server to a free port instead of dying on a busy one.

    Returns a note for the start message; a leading ``!`` marks a hard failure
    so the caller can surface it as an error.
    """
    host = str(payload.get("host", "")).strip()
    if not host:
        return ""
    parsed = urlparse(_normalize_host_url(host))
    if not parsed.hostname or not parsed.port:
        return ""
    problem = _port_in_use_note(payload)
    if not problem:
        return ""
    free_port = _pick_free_port(parsed.port + 1)
    if free_port is None:
        return f"!{problem}"
    payload["host"] = f"{parsed.hostname}:{free_port}"
    return f"Port {parsed.port} was busy; using {free_port} instead."


def _missing_model_note(payload: dict[str, object]) -> str:
    """Actionable text in place of llama-server's bare "failed to load model"."""
    configured = str(payload.get("gguf_path", "")).strip()
    where = f" (configured path is missing: {configured})" if configured else ""
    if _llama_flavor(payload) == "lfm3" or "lfm3" in configured.lower():
        return (
            f"LFM3-Omni weights are not on disk{where}. Download "
            "abliter8-ai/lfm3-2b-omni-abliter8-gguf — LFM3-Omni-2B-Abliter8-Q6_K.gguf plus "
            "mmproj-LFM3-Omni-2B-Abliter8-BF16.gguf — with the 'Download LFM3 GGUF + mmproj' "
            "button in Settings → Backends, or point the model and mmproj fields at files you "
            "already have."
        )
    return (
        f"No GGUF model is configured{where}. Pick a local GGUF in Settings → Backends "
        "or download one from the gallery."
    )


def _flash_attn_args(binary: Path | None) -> list[str]:
    """``--flash-attn`` argv for this build.

    Newer llama.cpp (including the LFM3 pin) made the value mandatory
    (``--flash-attn [on|off|auto]``); passing the bare flag there aborts startup
    with "expected value for argument". Older builds only accept the bare flag.
    """
    if binary is not None and llama_supports_flag(binary, "--flash-attn [on|off|auto]"):
        return ["--flash-attn", "on"]
    return ["--flash-attn"]


def _help_text(binary: Path) -> str:
    """``--help`` output of this build (empty when it cannot be run)."""
    try:
        result = subprocess.run(
            [str(binary), "--help"], capture_output=True, text=True, timeout=15, check=False,
            env=_server_env(binary),
        )
    except Exception:
        return ""
    return f"{result.stdout or ''}{result.stderr or ''}"


def llama_supports_flag(binary: Path, flag: str) -> bool:
    """True when this llama-server build advertises ``flag`` in ``--help``."""
    return flag in _help_text(binary)


def _flag_is_usable(help_text: str, flag: str) -> bool:
    """False for unknown flags and for ones this build documents as removed."""
    lines = [line for line in help_text.splitlines() if flag in line]
    if not lines:
        return False
    return not all("removed" in line.lower() for line in lines)


_VALUE_CHECKED_FLAGS = ("-ctk", "--cache-type-k", "-ctv", "--cache-type-v")


def _value_is_allowed(help_text: str, flag: str, value: str) -> bool:
    """Check a flag value against its documented ``allowed values:`` line."""
    lines = help_text.splitlines()
    for index, line in enumerate(lines):
        if flag not in line:
            continue
        window = " ".join(lines[index : index + 4])
        if "allowed values:" not in window:
            return True
        allowed = set(re.findall(r"[a-z0-9][a-z0-9_-]*", window.split("allowed values:", 1)[1]))
        return value in allowed
    return True


def _spec_type_values_ok(help_text: str, value: str) -> bool:
    """Whether every named speculative-decoding type exists in this build."""
    line = next((item for item in help_text.splitlines() if "--spec-type" in item), "")
    tail = line.split("--spec-type", 1)[-1].strip().split()
    if not tail:
        return True
    allowed = set(re.findall(r"[a-z0-9][a-z0-9-]*", tail[0]))
    return all(part.strip() in allowed for part in value.split(",") if part.strip())


def _supported_extra_args(binary: Path | None, tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split extra args into those this build knows and those it would reject.

    llama.cpp exits on an unknown flag, so a default written for one fork (the
    shipped ``--spec-type nextn`` speed args) kills a differently pinned build
    before it can serve anything.
    """
    if binary is None:
        return tokens, []
    help_text = _help_text(binary)
    if not help_text.strip():
        return tokens, []
    kept: list[str] = []
    dropped: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("-"):
            name = token.split("=", 1)[0]
            has_value = index + 1 < len(tokens) and not tokens[index + 1].startswith("-")
            if not _flag_is_usable(help_text, name):
                dropped.append(name)
                index += 2 if has_value else 1
                continue
            # Some flags survive as documented no-ops ("the argument has been
            # removed"), and others reject unknown values such as a spec type.
            if name == "--spec-type" and has_value and not _spec_type_values_ok(help_text, tokens[index + 1]):
                dropped.append(f"{name} {tokens[index + 1]}")
                index += 2
                continue
            if name in _VALUE_CHECKED_FLAGS and has_value and not _value_is_allowed(
                help_text, name, tokens[index + 1]
            ):
                dropped.append(f"{name} {tokens[index + 1]}")
                index += 2
                continue
        kept.append(token)
        index += 1
    return kept, dropped


_GPU_DEVICE_MARKERS = ("cuda", "vulkan", "metal", "hip", "rocm", "sycl", "opencl")


def llama_gpu_devices(binary: Path) -> list[str]:
    """GPU backends this build can actually use (empty for a CPU-only build)."""
    try:
        result = subprocess.run(
            [str(binary), "--list-devices"], capture_output=True, text=True, timeout=15, check=False,
            # Without the runtime's own library path a CUDA build cannot load
            # libggml-cuda.so and misleadingly reports zero devices.
            env=_server_env(binary),
        )
    except Exception:
        return []
    devices: list[str] = []
    for line in f"{result.stdout or ''}{result.stderr or ''}".splitlines():
        lowered = line.lower()
        # llama.cpp prints "  CUDA0: NVIDIA ..." without the word "device" on the
        # line itself, so only the GPU marker identifies a usable backend.
        if "available" in lowered:
            continue
        if any(marker in lowered for marker in _GPU_DEVICE_MARKERS):
            devices.append(line.strip())
    return devices


def auto_tune_payload(payload: dict[str, object]) -> dict[str, object]:
    """Fill acceleration flags from detected hardware when the user has not chosen.

    Only flags that were never saved are touched, so an explicit off stays off.
    A flag is also dropped when the built server does not advertise it, which
    keeps a CPU-only build from failing to start.
    """
    from ..hardware import acceleration_defaults

    tuned = dict(payload)
    if not bool(tuned.get("llama_auto_accelerate", True)):
        return tuned
    defaults = acceleration_defaults(tuned)
    binary = _prebuilt_llama_server(tuned)
    notes = list(tuned.get("llama_autotune_notes") or [])  # type: ignore[arg-type]

    if binary is None:
        # Nothing built yet: stay conservative rather than guessing that the
        # build which appears later will be GPU-capable.
        if defaults["flash_attn"] or defaults["mtp"]:
            notes.append("acceleration left off: no llama.cpp binary resolved yet")
    else:
        devices = llama_gpu_devices(binary)
        if not devices:
            if defaults["flash_attn"]:
                notes.append("llama_flash_attn disabled: this llama.cpp build has no GPU backend")
        else:
            # The settings dialog always writes a device and checks these boxes,
            # so a stored "cpu"/false is its default rather than a decision. This
            # switch is the opt-out, which is why it is checked first.
            tuned["device"] = "gpu"
            if defaults["flash_attn"]:
                if llama_supports_flag(binary, "--flash-attn"):
                    tuned["llama_flash_attn"] = True
                else:
                    notes.append("llama_flash_attn disabled: this build lacks --flash-attn")
            if defaults["mtp"]:
                if llama_supports_flag(binary, "--spec-draft-model") or llama_supports_flag(
                    binary, "--model-draft"
                ):
                    tuned["llama_mtp_enabled"] = True
                else:
                    notes.append("llama_mtp_enabled disabled: this build has no draft-model flag")
    if notes:
        tuned["llama_autotune_notes"] = notes
    return tuned


def _server_env(binary: Path | None) -> dict[str, str]:
    """Environment for the server, exposing shared libraries next to the binary.

    A vendored runtime ships its ``.so`` files beside ``llama-server``, and the
    linker does not search there unless told to.
    """
    env = dict(os.environ)
    if binary is not None:
        lib_dir = str(binary.parent)
        existing = env.get("LD_LIBRARY_PATH", "").strip()
        env["LD_LIBRARY_PATH"] = f"{lib_dir}:{existing}" if existing else lib_dir
    return env


def _lfm3_build_script() -> Path | None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_llama_lfm3.sh"
    return script if script.is_file() else None


def _build_llamacpp_via_script(
    plan: dict[str, object], payload: dict[str, object]
) -> tuple[bool, str, Path | None]:
    """Compile the LFM3 runtime through scripts/build_llama_lfm3.sh.

    The card requires a pinned commit plus a patch, which the script handles;
    this keeps one canonical build recipe instead of a second copy in Python.
    """
    script = _lfm3_build_script()
    if script is None:
        return False, "scripts/build_llama_lfm3.sh not found; cannot build the LFM3 runtime.", None
    env = dict(os.environ)
    env.update(lfm3_build_env(plan, payload))
    try:
        result = subprocess.run(
            ["bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
        )
    except Exception as exc:
        return False, f"LFM3 runtime build failed to start: {exc}", None
    binary = _prebuilt_llama_server(payload)
    if result.returncode == 0 and binary is not None:
        try:
            binary.chmod(0o755)
        except Exception:
            pass
        return True, f"Compiled the LFM3 llama.cpp runtime ({plan['git_ref']}).", binary
    detail = (result.stderr or result.stdout or "").strip().splitlines()
    reason = detail[-1] if detail else f"exit code {result.returncode}"
    return False, f"LFM3 runtime build failed: {reason}", None


def _ensure_llamacpp_binary(payload: dict[str, object]) -> tuple[bool, str, Path | None]:
    prebuilt = _prebuilt_llama_server(payload)
    if prebuilt is not None:
        try:
            prebuilt.chmod(0o755)
        except Exception:
            pass
        return True, f"Using existing llama-server runtime ({prebuilt.name}).", prebuilt

    plan = llama_build_plan(payload)
    flavor = str(plan["flavor"])
    if flavor == "lfm3":
        # Pinned commit + patch: build through the documented shell recipe.
        return _build_llamacpp_via_script(plan, payload)
    needs_atomic = flavor == "atomic"
    repo_url = str(plan["repo_url"])
    git_ref = str(plan["git_ref"])
    install_root = Path(str(plan["install_root"]))
    src_dir = Path(str(plan["source_dir"]))
    build_dir = Path(str(plan["build_dir"]))
    bin_dir = build_dir / "bin"
    candidates = [
        bin_dir / "llama-server",
        bin_dir / "server",
        src_dir / "llama-server",
        src_dir / "server",
    ]
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
    # Pin the requested ref: LFM3 support lives on a specific branch/commit.
    subprocess.run(
        ["git", "-C", str(src_dir), "checkout", git_ref],
        check=False,
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
            flavor = "atomic-llama (turboquant/MTP)" if needs_atomic else f"llama.cpp ({flavor})"
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
        with _req.urlopen(f"{_normalize_host_url(host)}/v1/models", timeout=1.2) as response:
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
    # Hardware-derived defaults (Flash Attention / MTP) before anything reads them.
    payload = auto_tune_payload(payload)
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
    # A CUDA build with no usable device fails deep inside llama.cpp; use the CPU
    # runtime instead of refusing to start.
    if binary_path is not None and "cuda" in str(binary_path).lower() and not llama_gpu_devices(binary_path):
        cpu_binary = _cpu_runtime_binary(payload)
        if cpu_binary is not None:
            binary_path = cpu_binary
            payload["binary_path"] = str(cpu_binary)
            note = "GPU runtime reported no device; using the CPU build."
            bootstrap_note = f"{bootstrap_note} {note}".strip()
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
        return False, _missing_model_note(payload)
    command = [str(binary_path), "-m", str(gguf_path)]
    # Context window. Without an explicit -c llama-server uses the model's trained
    # context, which is far too small for a chat plus images/audio on some cards.
    ctx_raw = str(payload.get("llama_context", "")).strip()
    try:
        if ctx_raw and int(float(ctx_raw)) >= 256:
            command.extend(["-c", str(int(float(ctx_raw)))])
    except (TypeError, ValueError):
        pass
    host = str(payload.get("host", "")).strip()
    if host:
        parsed = urlparse(_normalize_host_url(host))
        if parsed.hostname:
            command.extend(["--host", str(parsed.hostname)])
        if parsed.port:
            command.extend(["--port", str(parsed.port)])
    # Vision projector. Required for image input (LFM3-Omni, VL models); without it
    # llama-server ignores image parts instead of failing loudly.
    mmproj_path = _existing_path(payload.get("mmproj_path"))
    if mmproj_path is not None:
        command.extend(["--mmproj", str(mmproj_path)])
    elif str(payload.get("mmproj_path", "")).strip():
        # Never hand llama-server a path that is not there: it logs a CLIP error
        # and silently drops image/audio input instead of failing clearly.
        note = "The configured mmproj is missing, so image and audio input are disabled."
        bootstrap_note = f"{bootstrap_note} {note}".strip()
    # Chat template + reasoning mode. The LFM3-Omni card serves the model with
    # `--jinja --reasoning off` (it is a non-reasoning architecture).
    if bool(payload.get("llama_jinja", True)):
        command.append("--jinja")
    is_lfm3 = "lfm3" in gguf_path.name.lower()
    if bool(payload.get("llama_reasoning_off", is_lfm3)):
        command.extend(["--reasoning", "off"])
    extra_flags = payload.get("llama_extra_flags", [])
    if isinstance(extra_flags, list):
        command.extend(str(flag) for flag in extra_flags if str(flag).strip())
    # Performance flags
    if bool(payload.get("llama_flash_attn", False)):
        command.extend(_flash_attn_args(binary_path))
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
            command.extend(_draft_model_args(binary_path, str(draft)))
        draft_n = str(payload.get("llama_mtp_draft_n", "")).strip()
        if draft_n:
            command.extend(_draft_max_args(binary_path, draft_n))
    n_batch = str(payload.get("llama_n_batch", "")).strip()
    if n_batch:
        command.extend(["--batch-size", n_batch])
    if str(payload.get("device", "cpu")).lower() == "gpu":
        command.append("--gpu-layers")
        command.append(str(payload.get("llama_gpu_layers", "99") or "99"))
    extra_args = str(payload.get("llama_extra_args", "")).strip()
    if extra_args:
        try:
            extra_tokens = shlex.split(extra_args)
        except Exception:
            return False, "Invalid llama.cpp extra args."
        extra_tokens, dropped = _supported_extra_args(binary_path, extra_tokens)
        if dropped:
            note = f"Ignored flags this llama.cpp build does not support: {', '.join(dropped)}."
            bootstrap_note = f"{bootstrap_note} {note}".strip()
        command.extend(extra_tokens)
    port_note = _reassign_busy_port(payload)
    if port_note.startswith("!"):
        return False, port_note[1:]
    if port_note:
        bootstrap_note = f"{bootstrap_note} {port_note}".strip()
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_server_env(binary_path),
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
