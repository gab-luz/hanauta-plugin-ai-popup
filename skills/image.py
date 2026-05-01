"""Stable Diffusion WebUI skill — generate images via SD WebUI API.

Settings in skills_settings.json under "sdwebui":
    {
        "sdwebui": {
            "enabled": true,
            "url": "http://127.0.0.1:7860",
            "default_prompt": "",
            "default_negative_prompt": "",
            "default_steps": 20,
            "default_cfg_scale": 7.0,
            "default_width": 512,
            "default_height": 512,
            "default_sampler": "Euler a",
            "default_model": ""
        }
    }

SD WebUI must be started with --api flag (e.g., in webui-user.sh: COMMANDLINE_ARGS=--api)
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from urllib import error, request

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

_OUTPUT_DIR = Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "sd-images"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sd_txt2img",
            "description": (
                "Generate an image from a text prompt using Stable Diffusion WebUI. "
                "Returns the path to the generated image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Positive prompt describing what to generate."},
                    "negative_prompt": {"type": "string", "description": "Negative prompt (things to avoid)."},
                    "steps": {"type": "integer", "description": "Sampling steps (default from settings, typically 20)."},
                    "cfg_scale": {"type": "number", "description": "CFG scale (default from settings, typically 7.0)."},
                    "width": {"type": "integer", "description": "Image width (default from settings, typically 512)."},
                    "height": {"type": "integer", "description": "Image height (default from settings, typically 512)."},
                    "sampler": {"type": "string", "description": "Sampler name (default from settings, e.g., 'Euler a')."},
                    "seed": {"type": "integer", "description": "Random seed (-1 for random, default -1)."},
                    "batch_size": {"type": "integer", "description": "Number of images to generate (default 1)."},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sd_img2img",
            "description": (
                "Generate an image from an existing image using Stable Diffusion WebUI. "
                "Returns the path to the generated image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Positive prompt describing the target."},
                    "negative_prompt": {"type": "string", "description": "Negative prompt (things to avoid)."},
                    "image_path": {"type": "string", "description": "Path to the input image."},
                    "denoise_strength": {"type": "number", "description": "Denoising strength 0-1 (default 0.75)."},
                    "steps": {"type": "integer", "description": "Sampling steps (default from settings)."},
                    "cfg_scale": {"type": "number", "description": "CFG scale (default from settings)."},
                    "width": {"type": "integer", "description": "Image width (default from settings)."},
                    "height": {"type": "integer", "description": "Image height (default from settings)."},
                    "seed": {"type": "integer", "description": "Random seed (-1 for random, default -1)."},
                },
                "required": ["prompt", "image_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sd_models",
            "description": "List available Stable Diffusion models/checkpoints.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sd_samplers",
            "description": "List available samplers.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sd_options",
            "description": "Get or set SD WebUI options (model, samplers, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sd_model_checkpoint": {"type": "string", "description": "Model name to switch to."},
                    "sd_sampler_name": {"type": "string", "description": "Sampler name to set as default."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sd_interrupt",
            "description": "Interrupt the current generation.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _load_cfg() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("sdwebui", {})
    except Exception:
        return {}


def _api_url(cfg: dict, path: str) -> str:
    url = str(cfg.get("url", "http://127.0.0.1:7860")).rstrip("/")
    return f"{url}{path}"


def _sd_post(cfg: dict, endpoint: str, payload: dict) -> dict:
    import urllib.request

    url = _api_url(cfg, endpoint)
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode()
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"SD WebUI API error {exc.code}: {exc.read().decode()[:200]}")
    except Exception as exc:
        raise RuntimeError(f"SD WebUI connection failed: {exc}")


def _save_image(base64_data: str, prompt: str, cfg: dict) -> str:
    from PIL import Image, PngImagePlugin
    import uuid

    image_data = base64_data.split(",", 1)[-1]
    image = Image.open(io.BytesIO(base64.b64decode(image_data)))

    info = f"Prompt: {prompt}"
    if cfg.get("default_negative_prompt"):
        info += f"\nNegative: {cfg.get('default_negative_prompt')}"
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("parameters", info)

    filename = f"sd_{uuid.uuid4().hex[:8]}.png"
    filepath = _OUTPUT_DIR / filename
    image.save(filepath, pnginfo=pnginfo)
    return str(filepath)


def dispatch(name: str, args: dict) -> str:
    cfg = _load_cfg()
    if not bool(cfg.get("enabled", True)):
        return "[sdwebui] Skill is disabled in settings."

    try:
        if name == "sd_txt2img":
            prompt = str(args.get("prompt", "")).strip()
            if not prompt:
                return "Prompt is required."

            negative_prompt = str(args.get("negative_prompt") or cfg.get("default_negative_prompt") or "")
            steps = int(args.get("steps") or cfg.get("default_steps", 20))
            cfg_scale = float(args.get("cfg_scale") or cfg.get("default_cfg_scale", 7.0))
            width = int(args.get("width") or cfg.get("default_width", 512))
            height = int(args.get("height") or cfg.get("default_height", 512))
            sampler = str(args.get("sampler") or cfg.get("default_sampler", "Euler a"))
            seed = int(args.get("seed", -1))
            batch_size = int(args.get("batch_size", 1))

            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "width": width,
                "height": height,
                "sampler_name": sampler,
                "seed": seed,
                "batch_size": batch_size,
            }

            result = _sd_post(cfg, "/sdapi/v1/txt2img", payload)
            images = result.get("images", [])
            if not images:
                return "Generation failed - no images returned."

            saved_paths = []
            for img_b64 in images:
                path = _save_image(img_b64, prompt, cfg)
                saved_paths.append(path)

            if len(saved_paths) == 1:
                return f"Generated: {saved_paths[0]}"
            return "Generated:\n" + "\n".join(saved_paths)

        if name == "sd_img2img":
            prompt = str(args.get("prompt", "")).strip()
            image_path = str(args.get("image_path", "")).strip()
            if not prompt or not image_path:
                return "Prompt and image_path are required."

            input_path = Path(image_path)
            if not input_path.exists():
                return f"Input image not found: {image_path}"

            from PIL import Image

            input_image = Image.open(input_path)
            buffered = io.BytesIO()
            input_image.save(buffered, format="PNG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            denoise_strength = float(args.get("denoise_strength", 0.75))
            negative_prompt = str(args.get("negative_prompt") or cfg.get("default_negative_prompt") or "")
            steps = int(args.get("steps") or cfg.get("default_steps", 20))
            cfg_scale = float(args.get("cfg_scale") or cfg.get("default_cfg_scale", 7.0))
            width = int(args.get("width") or cfg.get("default_width", 512))
            height = int(args.get("height") or cfg.get("default_height", 512))
            seed = int(args.get("seed", -1))

            payload = {
                "init_images": [img_b64],
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "width": width,
                "height": height,
                "denoise_strength": denoise_strength,
                "seed": seed,
            }

            result = _sd_post(cfg, "/sdapi/v1/img2img", payload)
            images = result.get("images", [])
            if not images:
                return "Generation failed - no images returned."

            path = _save_image(images[0], prompt, cfg)
            return f"Generated: {path}"

        if name == "sd_models":
            result = _sd_post(cfg, "/sdapi/v1/sd-models", {})
            if not result:
                return "No models found or SD WebUI not running."
            models = result if isinstance(result, list) else result.get("models", [])
            if not models:
                return "No models found."
            lines = ["Available models:"]
            for m in models:
                title = m.get("title", m.get("model_name", "?"))
                hash_ = m.get("hash", "")[:8]
                lines.append(f"  {title} [{hash_}]")
            return "\n".join(lines)

        if name == "sd_samplers":
            result = _sd_post(cfg, "/sdapi/v1/samplers", {})
            if not result:
                return "No samplers found."
            samplers = result if isinstance(result, list) else []
            if not samplers:
                return "No samplers found."
            lines = ["Available samplers:"]
            for s in samplers:
                name_ = s.get("name", "?")
                aliases = s.get("aliases", "")
                lines.append(f"  {name_}" + (f" ({aliases})" if aliases else ""))
            return "\n".join(lines)

        if name == "sd_options":
            sd_model = str(args.get("sd_model_checkpoint", "")).strip()
            sd_sampler = str(args.get("sd_sampler_name", "")).strip()

            if not sd_model and not sd_sampler:
                result = _sd_post(cfg, "/sdapi/v1/options", {})
                if not result:
                    return "Could not fetch options."
                current_model = result.get("sd_model_checkpoint", "?")
                current_sampler = result.get("sd_sampler_name", "?")
                return f"Current model: {current_model}\nCurrent sampler: {current_sampler}"

            payload = {}
            if sd_model:
                payload["sd_model_checkpoint"] = sd_model
            if sd_sampler:
                payload["sd_sampler_name"] = sd_sampler

            _sd_post(cfg, "/sdapi/v1/options", payload)
            changes = []
            if sd_model:
                changes.append(f"model -> {sd_model}")
            if sd_sampler:
                changes.append(f"sampler -> {sd_sampler}")
            return f"Updated: {', '.join(changes)}"

        if name == "sd_interrupt":
            _sd_post(cfg, "/sdapi/v1/interrupt", {})
            return "Generation interrupted."

    except Exception as exc:
        return f"[sdwebui] {exc}"

    return f"[sdwebui] unknown tool: {name}"