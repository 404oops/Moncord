from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List
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
    host_root_path = Path(os.environ.get("HOST_ROOT_PATH", "/hostfs").strip() or "/hostfs")

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
