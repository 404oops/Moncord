from __future__ import annotations

from datetime import datetime
from typing import Dict
import logging
import os

import requests

from .config import Config

DEFAULT_TEMPLATES = {
    "startup": (
        ":white_check_mark: Monitoring online for **{hostname}** at {timestamp_local}"
        "\nCron schedule: `{cron_expression}`\nUptime: {uptime_human}"
    ),
    "heartbeat": (
        ":satellite: Hourly report for **{hostname}** at {timestamp_local}"
        "\nCPU {cpu_percent}% | Load {load_1}/{load_5}/{load_15}"
        "\nRAM {memory_used_gb}/{memory_total_gb} GiB ({memory_percent}%)"
        "\nUptime: {uptime_human}"
        "\nDisks:\n{disks_block}"
    ),
    "shutdown": (
        ":octagonal_sign: Monitoring offline for **{hostname}** at {timestamp_local}"
        "\nLast uptime reading: {uptime_human}"
    ),
}


class DiscordNotifier:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = requests.Session()
        self._templates = DEFAULT_TEMPLATES.copy()
        self._load_template_overrides()

    def _load_template_overrides(self) -> None:
        overrides = {
            "startup": os.environ.get("TEMPLATE_STARTUP"),
            "heartbeat": os.environ.get("TEMPLATE_HEARTBEAT"),
            "shutdown": os.environ.get("TEMPLATE_SHUTDOWN"),
        }
        for key, value in overrides.items():
            if value:
                self._templates[key] = value

    def _build_disks_block(self, snapshot: Dict[str, object]) -> str:
        disks = snapshot.get("disks", [])
        if not disks:
            return "- No eligible disks"

        lines = []
        for disk in disks:
            lines.append(
                f"- {disk['mount_point']} ({disk['filesystem']})"
                f": {disk['used_percent']}% used ({disk['used_gb']}/{disk['total_gb']} GiB)"
            )
        return "\n".join(lines)

    def _build_context(self, event: str, snapshot: Dict[str, object]) -> Dict[str, object]:
        timestamp_iso = snapshot.get("timestamp_iso")
        timestamp = datetime.fromisoformat(timestamp_iso) if timestamp_iso else datetime.now()
        timestamp_local = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

        cpu = snapshot.get("cpu", {})
        memory = snapshot.get("memory", {})
        uptime = snapshot.get("uptime", {})

        context = {
            "hostname": snapshot.get("hostname", "unknown"),
            "timestamp_iso": timestamp_iso,
            "timestamp_local": timestamp_local,
            "cron_expression": self._config.cron_expression,
            "cpu_percent": cpu.get("cpu_percent", 0),
            "load_1": cpu.get("load_1", 0),
            "load_5": cpu.get("load_5", 0),
            "load_15": cpu.get("load_15", 0),
            "memory_percent": memory.get("memory_percent", 0),
            "memory_used_gb": memory.get("memory_used_gb", 0),
            "memory_total_gb": memory.get("memory_total_gb", 0),
            "uptime_human": uptime.get("uptime_human", "n/a"),
            "disks_block": self._build_disks_block(snapshot),
        }
        return context

    def send(self, event: str, snapshot: Dict[str, object]) -> None:
        template = self._templates.get(event)
        if not template:
            logging.warning("No template configured for event %s", event)
            return

        context = self._build_context(event, snapshot)
        message = template.format(**context)

        payload = {
            "content": message,
            "username": self._config.username,
        }
        if self._config.avatar_url:
            payload["avatar_url"] = self._config.avatar_url

        try:
            response = self._session.post(self._config.webhook_url, json=payload, timeout=10)
        except requests.RequestException as exc:
            logging.error("Failed to send Discord webhook: %s", exc)
            return

        if response.status_code >= 400:
            logging.error("Discord webhook rejected message with status %s: %s", response.status_code, response.text)

    def close(self) -> None:
        self._session.close()
