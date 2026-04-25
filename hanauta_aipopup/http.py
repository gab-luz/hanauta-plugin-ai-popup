# HTTP utilities
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib import request, error
from urllib.parse import urlparse

from .runtime import AI_STATE_DIR, KOBOLDCPP_RELEASE_STATE_FILE


def _normalize_host_url(host: str) -> str:
    v = host.strip().rstrip("/")
    if not v.startswith(("http://", "https://")):
        v = f"http://{v}"
    return v


def _api_url_from_host(host: str) -> str:
    clean = host.strip().rstrip("/")
    if not clean:
        return ""
    if clean.startswith(("http://", "https://")):
        return clean
    if clean in {"api.openai.com", "www.api.openai.com"} or clean.endswith(".openai.com"):
        return f"https://{clean}"
    return f"http://{clean}"


def _friendly_http_target(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return url
    path = p.path or "/"
    if p.query:
        path = f"{path}?{p.query}"
    return f"{p.scheme}://{p.netloc}{path}"


def _friendly_network_error(action: str, url: str, exc: Exception) -> RuntimeError:
    target = _friendly_http_target(url)
    if isinstance(exc, error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ConnectionRefusedError):
            return RuntimeError(f"{action} failed because {target} refused the connection.")
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            return RuntimeError(f"{action} timed out while waiting for {target}.")
        return RuntimeError(f"{action} failed at {target}: {reason}.")
    return RuntimeError(f"{action} failed at {target}: {exc}.")


def _wait_for_http_ready(url: str, timeout: float = 8.0, poll: float = 0.25) -> bool:
    deadline = time.time() + max(0.2, timeout)
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=min(1.2, max(0.3, poll * 2.0))) as resp:
                return int(getattr(resp, "status", 200) or 200) < 500
        except error.HTTPError as e:
            if int(getattr(e, "code", 0) or 0) < 500:
                return True
        except Exception:
            pass
        time.sleep(max(0.05, poll))
    return False


def _http_json(url: str, timeout: float = 10.0, headers: dict | None = None) -> dict | list:
    merged = {"User-Agent": "Hanauta AI/1.0"}
    if headers:
        merged.update(headers)
    req = request.Request(url, headers=merged)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError:
        raise
    except Exception as exc:
        raise _friendly_network_error("Request", url, exc) from exc


def _http_post_json(url: str, payload: dict, timeout: float = 180.0, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    merged = {"User-Agent": "Hanauta AI/1.0", "Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = request.Request(url, data=body, headers=merged, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError:
        raise
    except Exception as exc:
        raise _friendly_network_error("Request", url, exc) from exc


def _http_post_bytes(url: str, payload: dict, timeout: float = 240.0, headers: dict | None = None) -> tuple[bytes, str]:
    body = json.dumps(payload).encode("utf-8")
    merged = {"User-Agent": "Hanauta AI/1.0", "Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = request.Request(url, data=body, headers=merged, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), str(resp.headers.get("Content-Type", ""))
    except error.HTTPError:
        raise
    except Exception as exc:
        raise _friendly_network_error("Request", url, exc) from exc


def _http_post_multipart(url: str, fields: dict, files: dict, timeout: float = 240.0) -> dict:
    boundary = f"----Hanauta{int(time.time() * 1000)}{os.getpid()}"
    parts = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(str(value).encode())
        parts.append(b"\r\n")
    for name, (filename, data, ctype) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
        parts.append(data)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    merged = {"User-Agent": "Hanauta AI/1.0", "Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))}
    req = request.Request(url, data=body, headers=merged, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError:
        raise
    except Exception as exc:
        raise _friendly_network_error("Upload", url, exc) from exc


def _openai_compat_alive(host: str) -> bool:
    try:
        with request.urlopen(f"{_normalize_host_url(host)}/v1/models", timeout=1.2):
            return True
    except Exception:
        return False


def _looks_like_gemma4_model_name(text: str) -> bool:
    return "gemma-4" in text.lower() or "gemma4" in text.lower()


def _looks_like_gemma4_audio_variant(text: str) -> bool:
    lowered = text.lower()
    return _looks_like_gemma4_model_name(lowered) and ("e4b" in lowered or "e2b" in lowered)


def _hf_resolve_url(repo_id: str, rel_path: str) -> str:
    return f"https://huggingface.co/{repo_id.strip('/')}/resolve/main/{rel_path.lstrip('/')}?download=true"


def _download_file(url: str, dest: Path, timeout: float = 300.0):
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 5):
        try:
            req = request.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
            with request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as f:
                while chunk := resp.read(1024 * 1024):
                    f.write(chunk)
            return
        except Exception:
            if attempt >= 4:
                raise
            time.sleep(min(4.0, 0.8 * attempt))


def _download_hf_files(repo_id: str, files: list, dest_root: Path):
    for fp in files:
        dest = dest_root / fp
        if dest.exists() and dest.stat().st_size > 0:
            continue
        _download_file(_hf_resolve_url(repo_id, fp), dest)


def _download_and_extract_zip_bundle(url: str, dest_root: Path):
    dest_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hanauta-") as tmp:
        archive = Path(tmp) / "bundle.zip"
        _download_file(url, archive, timeout=600.0)
        with zipfile.ZipFile(archive, "r") as z:
            z.extractall(dest_root)


def _load_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_json_file(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_notify_koboldcpp_release():
    import logging
    LOGGER = logging.getLogger("hanauta.ai_popup")
    now = time.time()
    state = _load_json_file(KOBOLDCPP_RELEASE_STATE_FILE)
    if now - float(state.get("last_checked", 0)) < 20 * 60 * 60:
        return
    latest_tag, latest_url = "", ""
    try:
        req = request.Request(
            "https://api.github.com/repos/LostRuins/koboldcpp/releases/latest",
            headers={"User-Agent": "Hanauta AI/1.0", "Accept": "application/vnd.github+json"},
        )
        with request.urlopen(req, timeout=5.0) as resp:
            p = json.loads(resp.read().decode("utf-8"))
        latest_tag = str(p.get("tag_name", "")).strip()
        latest_url = str(p.get("html_url", "")).strip()
    except Exception as exc:
        LOGGER.warning("KoboldCpp release check: %s", exc)
    prev = str(state.get("last_seen_tag", "")).strip()
    _save_json_file(KOBOLDCPP_RELEASE_STATE_FILE, {
        "last_checked": now,
        "last_seen_tag": latest_tag or prev,
        "last_url": latest_url or str(state.get("last_url", "")),
    })
    if latest_tag and prev and latest_tag != prev:
        send_desktop_notification("KoboldCpp update", f"New KoboldCpp release: {latest_tag}\n{latest_url}")


def send_desktop_notification(title: str, body: str, icon_path: str = ""):
    import logging
    LOGGER = logging.getLogger("hanauta.ai_popup")
    try:
        cmd = ["notify-send", "-a", "Hanauta AI"]
        if icon_path:
            ico = Path(icon_path).expanduser()
            if ico.exists():
                cmd.extend(["-i", str(ico)])
        cmd.extend([title, body])
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        LOGGER.exception("notify-send")


def send_desktop_notification_with_action(title: str, body: str, action_key: str, action_label: str, callback=None, icon_path: str = ""):
    import logging
    import threading
    LOGGER = logging.getLogger("hanauta.ai_popup")
    try:
        cmd = ["notify-send", "-a", "Hanauta AI", "--wait", "--action", f"{action_key}={action_label}"]
        if icon_path:
            ico = Path(icon_path).expanduser()
            if ico.exists():
                cmd.extend(["-i", str(ico)])
        cmd.extend([title, body])
        
        def run():
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if result.stdout.strip() == action_key and callback:
                    callback()
            except Exception:
                LOGGER.exception("notify-send action")
                send_desktop_notification(title, body, icon_path)
        
        threading.Thread(target=run, daemon=True).start()
    except Exception:
        LOGGER.exception("notify-send action setup")
        send_desktop_notification(title, body, icon_path)


def _sd_auth_headers(profile_key: str, payload: dict) -> dict:
    from base64 import b64encode
    from .storage import secure_load_secret
    username = payload.get("sd_auth_user", "").strip()
    password = secure_load_secret(f"{profile_key}:sd_auth_pass").strip()
    if not username or not password:
        return {}
    return {"Authorization": f"Basic {b64encode(f'{username}:{password}'.encode()).decode()}"}


def _sdapi_not_found_message(host: str) -> str:
    return f"SD API 404. Start WebUI/Forge with --api and use base host ({_normalize_host_url(host)})."


def _looks_like_gemma4_model_name(text: str) -> bool:
    return "gemma-4" in text.lower() or "gemma4" in text.lower()


def _looks_like_gemma4_audio_variant(text: str) -> bool:
    lowered = text.lower()
    return _looks_like_gemma4_model_name(lowered) and ("e4b" in lowered or "e2b" in lowered)


def _probe_openai_style_audio_input_support(host: str, model: str, api_key: str = "") -> bool:
    import io
    import struct
    import wave
    from base64 import b64encode
    try:
        sample_rate = 16000
        frames = int(sample_rate * 0.15)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack("<" + "h" * frames, *([0] * frames)))
        audio_b64 = b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return False
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model or "koboldcpp",
        "messages": [
            {"role": "system", "content": "You are a speech-to-text transcriber."},
            {"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                {"type": "text", "text": "Say OK."}
            ]},
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    try:
        resp = _http_post_json(f"{_api_url_from_host(host)}/v1/chat/completions", payload, timeout=30.0, headers=headers)
        choices = resp.get("choices", [])
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message", {})
                if isinstance(msg, dict) and msg.get("content", "").strip():
                    return True
                if first.get("text", "").strip():
                    return True
    except Exception:
        pass
    return False


def load_backend_settings() -> dict:
    from .runtime import BACKEND_SETTINGS_FILE
    try:
        return json.loads(BACKEND_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_backend_settings(settings: dict):
    from .runtime import AI_STATE_DIR, BACKEND_SETTINGS_FILE
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


__all__ = [
    "_normalize_host_url",
    "_api_url_from_host",
    "_friendly_network_error",
    "_wait_for_http_ready",
    "_http_json",
    "_http_post_json",
    "_http_post_bytes",
    "_http_post_multipart",
    "_openai_compat_alive",
    "_looks_like_gemma4_model_name",
    "_looks_like_gemma4_audio_variant",
    "_probe_openai_style_audio_input_support",
    "_hf_resolve_url",
    "_download_file",
    "_download_hf_files",
    "_download_and_extract_zip_bundle",
    "_load_json_file",
    "_save_json_file",
    "_sd_auth_headers",
    "_sdapi_not_found_message",
    "maybe_notify_koboldcpp_release",
    "send_desktop_notification",
    "send_desktop_notification_with_action",
    "load_backend_settings",
    "save_backend_settings",
]