"""PC Sensors skill — CPU, RAM, GPU, disk, network, temperature, uptime."""
from __future__ import annotations

import json
import shutil
import subprocess
import time

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sensors_cpu",
            "description": "Get CPU usage percentage (per-core and overall) and frequency.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_memory",
            "description": "Get RAM and swap usage.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_disk",
            "description": "Get disk usage for all mounted partitions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Specific mount point to check (optional, default all)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_temperature",
            "description": "Get hardware temperatures (CPU, GPU, NVMe, etc.) via lm-sensors.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_gpu",
            "description": "Get NVIDIA GPU stats (usage, VRAM, temperature) via nvidia-smi.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_network",
            "description": "Get network interface stats (bytes sent/received, current speed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface": {"type": "string", "description": "Interface name, e.g. 'eth0' (optional, default all)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_uptime",
            "description": "Get system uptime and load averages.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sensors_top_processes",
            "description": "List the top N processes by CPU or memory usage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "by": {"type": "string", "description": "'cpu' or 'memory' (default 'cpu')."},
                    "limit": {"type": "integer", "description": "Number of processes (default 8)."},
                },
                "required": [],
            },
        },
    },
]


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def dispatch(name: str, args: dict) -> str:
    try:
        import psutil
    except ImportError:
        psutil = None  # type: ignore[assignment]

    if name == "sensors_cpu":
        if psutil is None:
            return "[sensors] psutil not installed. Run: pip install psutil"
        overall = psutil.cpu_percent(interval=0.5)
        per_core = psutil.cpu_percent(interval=0, percpu=True)
        freq = psutil.cpu_freq()
        freq_str = f"{freq.current:.0f} MHz (max {freq.max:.0f} MHz)" if freq else "unknown"
        cores_str = "  ".join(f"C{i}:{p:.0f}%" for i, p in enumerate(per_core))
        return f"CPU: {overall:.1f}% overall\nFrequency: {freq_str}\nPer-core: {cores_str}"

    if name == "sensors_memory":
        if psutil is None:
            return "[sensors] psutil not installed."
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return (
            f"RAM: {_fmt_bytes(vm.used)} / {_fmt_bytes(vm.total)} ({vm.percent:.1f}% used)\n"
            f"Swap: {_fmt_bytes(sw.used)} / {_fmt_bytes(sw.total)} ({sw.percent:.1f}% used)"
        )

    if name == "sensors_disk":
        if psutil is None:
            return "[sensors] psutil not installed."
        path_filter = str(args.get("path") or "").strip()
        parts = psutil.disk_partitions(all=False)
        lines = []
        for p in parts:
            if path_filter and p.mountpoint != path_filter:
                continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
                lines.append(
                    f"{p.mountpoint} ({p.fstype}): "
                    f"{_fmt_bytes(usage.used)} / {_fmt_bytes(usage.total)} "
                    f"({usage.percent:.1f}% used)"
                )
            except PermissionError:
                continue
        return "\n".join(lines) or "No disk info available."

    if name == "sensors_temperature":
        # Try lm-sensors first
        if shutil.which("sensors"):
            result = subprocess.run(
                ["sensors", "-j"], capture_output=True, text=True, timeout=5, check=False
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    lines = []
                    for chip, readings in data.items():
                        for sensor, values in readings.items():
                            if isinstance(values, dict):
                                for key, val in values.items():
                                    if "input" in key and isinstance(val, (int, float)):
                                        lines.append(f"{chip} / {sensor}: {val:.1f}°C")
                    return "\n".join(lines) or "No temperature sensors found."
                except Exception:
                    return result.stdout.strip()
        # Fallback: psutil
        if psutil is not None and hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                lines = []
                for chip, entries in temps.items():
                    for e in entries:
                        lines.append(f"{chip} / {e.label or 'temp'}: {e.current:.1f}°C")
                return "\n".join(lines)
        return "[sensors] Install lm-sensors (sensors command) for temperature data."

    if name == "sensors_gpu":
        if not shutil.which("nvidia-smi"):
            return "[sensors] nvidia-smi not found. NVIDIA GPU required."
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if result.returncode != 0:
            return f"[sensors] nvidia-smi error: {result.stderr.strip()}"
        lines = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 7:
                name_gpu, gpu_util, mem_util, mem_used, mem_total, temp, power = parts[:7]
                lines.append(
                    f"{name_gpu}: GPU {gpu_util}%  VRAM {mem_used}/{mem_total} MiB ({mem_util}%)  "
                    f"Temp {temp}°C  Power {power}W"
                )
        return "\n".join(lines) or "No GPU info."

    if name == "sensors_network":
        if psutil is None:
            return "[sensors] psutil not installed."
        iface_filter = str(args.get("interface") or "").strip()
        # Sample twice for speed
        before = psutil.net_io_counters(pernic=True)
        time.sleep(0.5)
        after = psutil.net_io_counters(pernic=True)
        lines = []
        for iface, stats in after.items():
            if iface_filter and iface != iface_filter:
                continue
            if iface.startswith("lo"):
                continue
            b = before.get(iface)
            rx_speed = (stats.bytes_recv - b.bytes_recv) * 2 if b else 0
            tx_speed = (stats.bytes_sent - b.bytes_sent) * 2 if b else 0
            lines.append(
                f"{iface}: ↓{_fmt_bytes(rx_speed)}/s ↑{_fmt_bytes(tx_speed)}/s  "
                f"(total ↓{_fmt_bytes(stats.bytes_recv)} ↑{_fmt_bytes(stats.bytes_sent)})"
            )
        return "\n".join(lines) or "No network interfaces found."

    if name == "sensors_uptime":
        if psutil is not None:
            boot = psutil.boot_time()
            uptime_secs = int(time.time() - boot)
            h, rem = divmod(uptime_secs, 3600)
            m, s = divmod(rem, 60)
            uptime_str = f"{h}h {m}m {s}s"
        else:
            result = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=3)
            uptime_str = result.stdout.strip()
        try:
            with open("/proc/loadavg") as f:
                load = f.read().strip().split()[:3]
            load_str = f"Load: {' '.join(load)} (1/5/15 min)"
        except Exception:
            load_str = ""
        return f"Uptime: {uptime_str}\n{load_str}".strip()

    if name == "sensors_top_processes":
        if psutil is None:
            return "[sensors] psutil not installed."
        by = str(args.get("by") or "cpu").strip().lower()
        limit = int(args.get("limit") or 8)
        attr = "cpu_percent" if by == "cpu" else "memory_percent"
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                continue
        # cpu_percent needs a second sample
        if by == "cpu":
            time.sleep(0.3)
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(p.info)
                except Exception:
                    continue
        procs.sort(key=lambda x: float(x.get(attr) or 0), reverse=True)
        lines = [f"{'PID':>7}  {'CPU%':>6}  {'MEM%':>6}  NAME"]
        for p in procs[:limit]:
            lines.append(
                f"{p.get('pid', '?'):>7}  "
                f"{p.get('cpu_percent', 0):>6.1f}  "
                f"{p.get('memory_percent', 0):>6.1f}  "
                f"{p.get('name', '?')}"
            )
        return "\n".join(lines)

    return f"[sensors] unknown tool: {name}"
