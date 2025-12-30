from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List
import logging
import os


@dataclass(frozen=True)
class Config:
    webhook_url: str
    username: str
    avatar_url: str | None
    cron_expression: str
    host_label: str | None
    host_root_path: Path
    disk_include: List[str]
    disk_exclude: List[str]


def _split_csv(env_value: str | None) -> List[str]:
    if not env_value:
        return []
    return [entry.strip() for entry in env_value.split(",") if entry.strip()]


def load_config() -> Config:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL environment variable is required")

    username = os.environ.get("DISCORD_USERNAME", "Moncord").strip() or "Moncord"
    avatar_url = os.environ.get("DISCORD_AVATAR_URL", "").strip() or None
    cron_expression = os.environ.get("MONITOR_CRON", "0 * * * *").strip() or "0 * * * *"

    host_label = os.environ.get("HOST_LABEL", "").strip() or None
    raw_host_root = os.environ.get("HOST_ROOT_PATH", "/hostfs").strip() or "/hostfs"
    host_root_candidates = []

    explicit_path = Path(raw_host_root)
    host_root_candidates.append(explicit_path)

    if explicit_path != Path("/proc/1/root"):
        host_root_candidates.append(Path("/proc/1/root"))
    if explicit_path != Path("/"):
        host_root_candidates.append(Path("/"))

    host_root_path = explicit_path
    for candidate in host_root_candidates:
        if candidate.exists():
            if candidate != explicit_path:
                logging.info(
                    "Host root %s not accessible; falling back to %s", explicit_path, candidate
                )
            host_root_path = candidate
            break
    else:
        logging.warning("Could not resolve a valid host root path; using %s", explicit_path)

    disk_include = _split_csv(os.environ.get("DISK_INCLUDE"))
    disk_exclude = _split_csv(os.environ.get("DISK_EXCLUDE"))

    return Config(
        webhook_url=webhook_url,
        username=username,
        avatar_url=avatar_url,
        cron_expression=cron_expression,
        host_label=host_label,
        host_root_path=host_root_path,
        disk_include=disk_include,
        disk_exclude=disk_exclude,
    )
