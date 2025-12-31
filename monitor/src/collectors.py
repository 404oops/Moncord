from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
import logging
import os
import socket

import psutil

from .config import Config

_PSEUDO_FS_TYPES = {
    "proc",
    "sysfs",
    "devtmpfs",
    "tmpfs",
    "devpts",
    "overlay",
    "squashfs",
    "mqueue",
    "hugetlbfs",
    "cgroup",
    "cgroup2",
    "autofs",
    "fusectl",
    "tracefs",
    "binfmt_misc",
    "efivarfs",
    "bpf",
    "pstore",
    "configfs",
    "debugfs",
    "securityfs",
}


@dataclass(frozen=True)
class DiskSnapshot:
    device: str
    mount_point: str
    filesystem: str
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float


def _format_bytes(bytes_total: int) -> float:
    return round(bytes_total / (1024 ** 3), 2)


def _should_include(mount_point: str, include: Sequence[str], exclude: Sequence[str]) -> bool:
    if any(mount_point.startswith(prefix) for prefix in exclude):
        return False
    if not include:
        return True
    return any(mount_point.startswith(prefix) for prefix in include)


def _resolve_host_path(root: Path, mount_point: str) -> Path:
    root_str = str(root)
    # If mount_point already starts with the host root path, use it directly
    if mount_point.startswith(root_str):
        return Path(mount_point)
    if mount_point == "/":
        return root
    return root / mount_point.lstrip("/")


def _decode_mount_field(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t")


def _parse_mounts_table(handle: Iterable[str]) -> List[Tuple[str, str, str]]:
    entries: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw_line in handle:
        parts = raw_line.split()
        if len(parts) < 3:
            continue
        device, mount_point, fs_type = parts[:3]
        key = f"{device}:{mount_point}"
        if key in seen:
            continue
        seen.add(key)
        if fs_type in _PSEUDO_FS_TYPES:
            continue
        entries.append((device, mount_point, fs_type))
    return entries


def _parse_mountinfo_table(handle: Iterable[str]) -> List[Tuple[str, str, str]]:
    entries: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw_line in handle:
        parts = raw_line.split()
        if len(parts) < 10:
            continue
        mount_point = _decode_mount_field(parts[4])
        fs_type = parts[-3]
        source = parts[-2]
        key = f"{source}:{mount_point}"
        if key in seen:
            continue
        seen.add(key)
        if fs_type in _PSEUDO_FS_TYPES:
            continue
        entries.append((source, mount_point, fs_type))
    return entries


def _load_mount_entries(config: Config) -> List[Tuple[str, str, str]]:
    candidates: List[Tuple[str, Path, str]] = []
    host_mounts = config.host_root_path / "proc" / "mounts"
    candidates.append(("host_root", host_mounts, "mounts"))

    candidates.append(("proc1", Path("/proc/1/mountinfo"), "mountinfo"))
    candidates.append(("container", Path("/proc/mounts"), "mounts"))

    for label, path, table_type in candidates:
        if table_type == "mounts":
            parser = _parse_mounts_table
        else:
            parser = _parse_mountinfo_table

        try:
            with path.open("r", encoding="utf-8") as handle:
                entries = parser(handle)
        except FileNotFoundError:
            continue
        except PermissionError:
            logging.warning("Insufficient permission to read mount table %s", path)
            continue

        if entries:
            if label != "host_root":
                logging.debug("Using mount table %s for disk metrics", path)
            return entries

    logging.warning("No accessible mount tables found; disk metrics will be empty")
    return []


def _display_mount_point(mount_point: str, host_root: Path) -> str:
    """Strip host root prefix from mount point for cleaner display."""
    root_str = str(host_root)
    if mount_point.startswith(root_str) and mount_point != root_str:
        stripped = mount_point[len(root_str):]
        return stripped if stripped.startswith("/") else "/" + stripped
    if mount_point == root_str:
        return "/"
    return mount_point


def capture_disk_usage(config: Config) -> List[DiskSnapshot]:
    snapshots: List[DiskSnapshot] = []
    has_hostfs_root = False
    entries = list(_load_mount_entries(config))

    # Check if we have a hostfs root mount
    root_str = str(config.host_root_path)
    for _, mount_point, _ in entries:
        if mount_point == root_str or mount_point.startswith(root_str + "/"):
            has_hostfs_root = True
            break

    for device, mount_point, fs_type in entries:
        # Skip bare root if hostfs root is present (avoids duplicate)
        if mount_point == "/" and has_hostfs_root:
            logging.debug("Skipping root mount / because hostfs root is present")
            continue
        if not _should_include(mount_point, config.disk_include, config.disk_exclude):
            logging.debug("Skipping mount %s due to include/exclude filters", mount_point)
            continue

        host_path = _resolve_host_path(config.host_root_path, mount_point)
        if not host_path.exists():
            logging.debug("Skipping mount %s because %s does not exist", mount_point, host_path)
            continue

        if not host_path.is_dir():
            logging.debug("Skipping mount %s because %s is not a directory", mount_point, host_path)
            continue

        try:
            usage = psutil.disk_usage(str(host_path))
        except PermissionError:
            logging.debug("Skipping mount %s due to permission error", mount_point)
            continue
        except FileNotFoundError:
            logging.debug("Skipping mount %s because path disappeared", mount_point)
            continue

        snapshots.append(
            DiskSnapshot(
                device=device,
                mount_point=_display_mount_point(mount_point, config.host_root_path),
                filesystem=fs_type,
                total_gb=_format_bytes(usage.total),
                used_gb=_format_bytes(usage.used),
                free_gb=_format_bytes(usage.free),
                used_percent=round(usage.percent, 2),
            )
        )

    snapshots.sort(key=lambda snap: snap.mount_point)
    return snapshots


def capture_cpu_stats() -> Dict[str, float]:
    # First call with interval=None returns a meaningful instantaneous value without blocking longer than needed.
    cpu_percent = psutil.cpu_percent(interval=0.25)
    load1, load5, load15 = os.getloadavg()
    return {
        "cpu_percent": round(cpu_percent, 2),
        "load_1": round(load1, 2),
        "load_5": round(load5, 2),
        "load_15": round(load15, 2),
    }


def capture_memory_stats() -> Dict[str, float]:
    mem = psutil.virtual_memory()
    # buffers + cached = disk cache; available on Linux, fallback to 0 elsewhere
    buffers = getattr(mem, "buffers", 0)
    cached = getattr(mem, "cached", 0)
    cache_total = buffers + cached
    return {
        "memory_percent": round(mem.percent, 2),
        "memory_used_gb": _format_bytes(mem.used),
        "memory_total_gb": _format_bytes(mem.total),
        "memory_available_gb": _format_bytes(mem.available),
        "memory_buffers_gb": _format_bytes(buffers),
        "memory_cached_gb": _format_bytes(cached),
        "memory_cache_gb": _format_bytes(cache_total),
    }


def capture_uptime_stats() -> Dict[str, str | float]:
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    uptime_seconds = (now - boot_time).total_seconds()

    days, remainder = divmod(int(uptime_seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_human = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"

    return {
        "boot_time_iso": boot_time.isoformat(),
        "uptime_seconds": uptime_seconds,
        "uptime_human": uptime_human,
    }


def resolve_hostname(config: Config) -> str:
    if config.host_label:
        return config.host_label
    return socket.gethostname()


def capture_snapshot(config: Config) -> Dict[str, object]:
    snapshot = {
        "cpu": capture_cpu_stats(),
        "memory": capture_memory_stats(),
        "uptime": capture_uptime_stats(),
        "hostname": resolve_hostname(config),
        "timestamp_iso": datetime.now(tz=timezone.utc).isoformat(),
    }
    snapshot["disks"] = [disk.__dict__ for disk in capture_disk_usage(config)]
    return snapshot
