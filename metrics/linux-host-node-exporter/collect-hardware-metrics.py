#!/usr/bin/python3
"""Export NVIDIA and SMART data in Prometheus textfile format."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path


def label(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def number(value: object) -> float | None:
    try:
        result = float(str(value).strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def sample(name: str, value: object, labels: dict[str, object] | None = None) -> str | None:
    numeric = number(value)
    if numeric is None:
        return None
    suffix = ""
    if labels:
        suffix = "{" + ",".join(f'{key}="{label(item)}"' for key, item in sorted(labels.items())) + "}"
    return f"{name}{suffix} {numeric:g}"


def metric(lines: list[str], name: str, help_text: str, metric_type: str = "gauge") -> None:
    lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} {metric_type}"))


def gpu_metrics() -> list[str]:
    fields = [
        "index", "name", "uuid", "temperature.gpu", "utilization.gpu",
        "utilization.memory", "memory.total", "memory.used", "memory.free",
        "power.draw", "power.limit", "fan.speed", "clocks.current.graphics",
        "clocks.current.memory",
    ]
    completed = subprocess.run(
        ["/usr/bin/nvidia-smi", f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"],
        check=False, capture_output=True, text=True, timeout=20,
    )
    lines: list[str] = []
    definitions = {
        "linux_host_gpu_info": ("Static NVIDIA GPU information.", "gauge"),
        "linux_host_gpu_temperature_celsius": ("NVIDIA GPU temperature in Celsius.", "gauge"),
        "linux_host_gpu_utilization_percent": ("NVIDIA GPU utilization percentage.", "gauge"),
        "linux_host_gpu_memory_utilization_percent": ("NVIDIA memory-controller utilization percentage.", "gauge"),
        "linux_host_gpu_memory_total_bytes": ("NVIDIA GPU memory capacity in bytes.", "gauge"),
        "linux_host_gpu_memory_used_bytes": ("NVIDIA GPU memory used in bytes.", "gauge"),
        "linux_host_gpu_memory_free_bytes": ("NVIDIA GPU memory free in bytes.", "gauge"),
        "linux_host_gpu_power_watts": ("NVIDIA GPU power draw in watts.", "gauge"),
        "linux_host_gpu_power_limit_watts": ("NVIDIA GPU power limit in watts.", "gauge"),
        "linux_host_gpu_fan_percent": ("NVIDIA GPU fan speed percentage.", "gauge"),
        "linux_host_gpu_graphics_clock_hertz": ("NVIDIA GPU graphics clock in hertz.", "gauge"),
        "linux_host_gpu_memory_clock_hertz": ("NVIDIA GPU memory clock in hertz.", "gauge"),
        "linux_host_hardware_collector_success": ("Whether a hardware textfile collector completed successfully.", "gauge"),
    }
    for name, (help_text, kind) in definitions.items():
        metric(lines, name, help_text, kind)
    if completed.returncode != 0:
        lines.append('linux_host_hardware_collector_success{collector="gpu"} 0')
        return lines

    for row in csv.reader(completed.stdout.splitlines(), skipinitialspace=True):
        if len(row) != len(fields):
            continue
        values = dict(zip(fields, row))
        labels = {"gpu": values["index"], "name": values["name"], "uuid": values["uuid"]}
        lines.append(sample("linux_host_gpu_info", 1, labels) or "")
        mappings = {
            "temperature.gpu": ("linux_host_gpu_temperature_celsius", 1),
            "utilization.gpu": ("linux_host_gpu_utilization_percent", 1),
            "utilization.memory": ("linux_host_gpu_memory_utilization_percent", 1),
            "memory.total": ("linux_host_gpu_memory_total_bytes", 1024 * 1024),
            "memory.used": ("linux_host_gpu_memory_used_bytes", 1024 * 1024),
            "memory.free": ("linux_host_gpu_memory_free_bytes", 1024 * 1024),
            "power.draw": ("linux_host_gpu_power_watts", 1),
            "power.limit": ("linux_host_gpu_power_limit_watts", 1),
            "fan.speed": ("linux_host_gpu_fan_percent", 1),
            "clocks.current.graphics": ("linux_host_gpu_graphics_clock_hertz", 1_000_000),
            "clocks.current.memory": ("linux_host_gpu_memory_clock_hertz", 1_000_000),
        }
        for field, (name, multiplier) in mappings.items():
            value = number(values[field])
            rendered = sample(name, value * multiplier if value is not None else None, labels)
            if rendered:
                lines.append(rendered)
    lines.append('linux_host_hardware_collector_success{collector="gpu"} 1')
    return [line for line in lines if line]


def smart_devices() -> list[Path]:
    devices: set[Path] = set()
    for block in Path("/sys/block").iterdir():
        name = block.name
        if re.fullmatch(r"sd[a-z]+", name):
            devices.add(Path("/dev") / name)
        elif match := re.fullmatch(r"(nvme\d+)n\d+", name):
            devices.add(Path("/dev") / match.group(1))
    return sorted(devices)


def smart_metrics() -> list[str]:
    lines: list[str] = []
    definitions = {
        "linux_host_smart_scrape_success": "Whether SMART data was available for the device.",
        "linux_host_smart_device_info": "Static SMART device information.",
        "linux_host_smart_health_passed": "Whether the SMART overall health assessment passed.",
        "linux_host_smart_temperature_celsius": "SMART device temperature in Celsius.",
        "linux_host_smart_power_on_hours": "SMART device power-on hours.",
        "linux_host_smart_reallocated_sectors": "ATA reallocated sector count.",
        "linux_host_smart_pending_sectors": "ATA current pending sector count.",
        "linux_host_smart_offline_uncorrectable_sectors": "ATA offline uncorrectable sector count.",
        "linux_host_smart_nvme_percentage_used": "NVMe estimated endurance used percentage.",
        "linux_host_smart_nvme_available_spare_percent": "NVMe available spare percentage.",
        "linux_host_smart_nvme_critical_warning": "NVMe critical warning bitmask.",
        "linux_host_smart_nvme_media_errors_total": "NVMe media and data-integrity errors.",
        "linux_host_smart_nvme_error_log_entries_total": "NVMe error information log entries.",
        "linux_host_smart_nvme_unsafe_shutdowns_total": "NVMe unsafe shutdown count.",
        "linux_host_hardware_collector_success": "Whether a hardware textfile collector completed successfully.",
    }
    for name, help_text in definitions.items():
        metric(lines, name, help_text)

    successful = 0
    for device in smart_devices():
        completed = subprocess.run(
            ["/usr/bin/smartctl", "-a", "-j", str(device)],
            check=False, capture_output=True, text=True, timeout=45,
        )
        try:
            data = json.loads(completed.stdout)
        except json.JSONDecodeError:
            lines.append(sample("linux_host_smart_scrape_success", 0, {"device": device.name}) or "")
            continue
        model = data.get("model_name") or data.get("model_family") or "unknown"
        serial = data.get("serial_number") or "unknown"
        protocol = data.get("device", {}).get("protocol") or "unknown"
        labels = {"device": device.name, "model": model, "protocol": protocol, "serial": serial}
        health = data.get("smart_status", {}).get("passed")
        available = health is not None
        lines.append(sample("linux_host_smart_scrape_success", int(available), labels) or "")
        if not available:
            continue
        successful += 1
        lines.append(sample("linux_host_smart_device_info", 1, labels) or "")
        lines.append(sample("linux_host_smart_health_passed", int(bool(health)), labels) or "")
        for name, value in (
            ("linux_host_smart_temperature_celsius", data.get("temperature", {}).get("current")),
            ("linux_host_smart_power_on_hours", data.get("power_on_time", {}).get("hours")),
        ):
            rendered = sample(name, value, labels)
            if rendered:
                lines.append(rendered)

        attributes = {item.get("name"): item.get("raw", {}).get("value") for item in data.get("ata_smart_attributes", {}).get("table", [])}
        for attribute, name in (
            ("Reallocated_Sector_Ct", "linux_host_smart_reallocated_sectors"),
            ("Current_Pending_Sector", "linux_host_smart_pending_sectors"),
            ("Offline_Uncorrectable", "linux_host_smart_offline_uncorrectable_sectors"),
        ):
            rendered = sample(name, attributes.get(attribute), labels)
            if rendered:
                lines.append(rendered)

        nvme = data.get("nvme_smart_health_information_log") or {}
        for source, name in (
            ("percentage_used", "linux_host_smart_nvme_percentage_used"),
            ("available_spare", "linux_host_smart_nvme_available_spare_percent"),
            ("critical_warning", "linux_host_smart_nvme_critical_warning"),
            ("media_errors", "linux_host_smart_nvme_media_errors_total"),
            ("num_err_log_entries", "linux_host_smart_nvme_error_log_entries_total"),
            ("unsafe_shutdowns", "linux_host_smart_nvme_unsafe_shutdowns_total"),
        ):
            rendered = sample(name, nvme.get(source), labels)
            if rendered:
                lines.append(rendered)
    lines.append(sample("linux_host_hardware_collector_success", int(successful > 0), {"collector": "smart"}) or "")
    return [line for line in lines if line]


def write_atomic(output: Path, lines: list[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=output.parent, prefix=f".{output.name}.", delete=False) as temporary:
        temporary.write("\n".join(lines) + "\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("collector", choices=("gpu", "smart"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_atomic(args.output, gpu_metrics() if args.collector == "gpu" else smart_metrics())


if __name__ == "__main__":
    main()
