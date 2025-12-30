from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List
import logging
import os

import requests

from .config import Config

DEFAULT_EMBED_TEMPLATES = {
    "startup": {
        "title": "Moncord Online",
        "description": "Monitoring online for **{hostname}** at {timestamp_local}",
        "color": 0x2ecc71,
    },
    "heartbeat": {
        "title": "Moncord Heartbeat",
        "description": "System report for **{hostname}** at {timestamp_local}",
        "color": 0x5865F2,
    },
    "shutdown": {
        "title": "Moncord Offline",
        "description": "Monitoring offline for **{hostname}** at {timestamp_local}",
        "color": 0xe74c3c,
    },
}


class DiscordNotifier:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = requests.Session()
        self._templates = {key: value.copy() for key, value in DEFAULT_EMBED_TEMPLATES.items()}
        self._load_template_overrides()

    def _load_template_overrides(self) -> None:
        for event_key in self._templates.keys():
            base = event_key.upper()
            description_override = os.environ.get(f"TEMPLATE_{base}")
            title_override = os.environ.get(f"TEMPLATE_{base}_TITLE")
            color_override = os.environ.get(f"TEMPLATE_{base}_COLOR")

            if description_override:
                self._templates[event_key]["description"] = description_override
            if title_override:
                self._templates[event_key]["title"] = title_override
            if color_override:
                parsed = self._parse_color(color_override)
                if parsed is not None:
                    self._templates[event_key]["color"] = parsed

    @staticmethod
    def _parse_color(raw_value: str | None) -> int | None:
        if not raw_value:
            return None
        cleaned = raw_value.strip().lower().replace("#", "")
        if cleaned.startswith("0x"):
            cleaned = cleaned[2:]
        try:
            value = int(cleaned, 16)
        except ValueError:
            logging.warning("Invalid embed color value '%s'", raw_value)
            return None
        return max(0, min(value, 0xFFFFFF))

    @staticmethod
    def _chunk_text(text: str, size: int = 1000) -> Iterable[str]:
        if len(text) <= size:
            yield text
            return
        start = 0
        while start < len(text):
            yield text[start : start + size]
            start += size

    def _build_disks_block(self, snapshot: Dict[str, object]) -> List[str]:
        disks = snapshot.get("disks", [])
        if not disks:
            return ["No eligible disks"]

        lines = []
        for disk in disks:
            lines.append(
                f"{disk['mount_point']} ({disk['filesystem']})"
                f": {disk['used_percent']}% used ({disk['used_gb']}/{disk['total_gb']} GiB)"
            )

        text = "\n".join(lines)
        return list(self._chunk_text(text))

    def _build_context(self, event: str, snapshot: Dict[str, object]) -> Dict[str, object]:
        timestamp_iso = snapshot.get("timestamp_iso")
        timestamp = datetime.fromisoformat(timestamp_iso) if timestamp_iso else datetime.now()
        timestamp_local = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

        cpu = snapshot.get("cpu", {})
        memory = snapshot.get("memory", {})
        uptime = snapshot.get("uptime", {})

        cron_display = ", ".join(
            entry.strip()
            for entry in self._config.cron_expression.replace(";", "\n").splitlines()
            if entry.strip()
        ) or self._config.cron_expression

        context = {
            "hostname": snapshot.get("hostname", "unknown"),
            "timestamp_iso": timestamp_iso,
            "timestamp_local": timestamp_local,
            "cron_expression": self._config.cron_expression,
            "cron_display": cron_display,
            "cpu_percent": cpu.get("cpu_percent", 0),
            "load_1": cpu.get("load_1", 0),
            "load_5": cpu.get("load_5", 0),
            "load_15": cpu.get("load_15", 0),
            "memory_percent": memory.get("memory_percent", 0),
            "memory_used_gb": memory.get("memory_used_gb", 0),
            "memory_total_gb": memory.get("memory_total_gb", 0),
            "uptime_human": uptime.get("uptime_human", "n/a"),
            "disks_chunks": self._build_disks_block(snapshot),
        }
        context["disks_block"] = "\n".join(context["disks_chunks"]) if context["disks_chunks"] else ""
        return context

    def send(self, event: str, snapshot: Dict[str, object]) -> None:
        template = self._templates.get(event)
        if not template:
            logging.warning("No template configured for event %s", event)
            return

        context = self._build_context(event, snapshot)
        embed = self._build_embed(event, template, context)

        payload = {
            "username": self._config.username,
            "embeds": [embed],
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

    def _build_embed(self, event: str, template: Dict[str, object], context: Dict[str, object]) -> Dict[str, object]:
        title = template.get("title", "Moncord").format(**context)
        description = template.get("description", "").format(**context)
        color = template.get("color")

        fields: List[Dict[str, object]] = []

        fields.append(
            {
                "name": "CPU",
                "value": (
                    f"Usage: {context['cpu_percent']}%\n"
                    f"Load: {context['load_1']}/{context['load_5']}/{context['load_15']}"
                ),
                "inline": True,
            }
        )
        fields.append(
            {
                "name": "Memory",
                "value": (
                    f"Usage: {context['memory_percent']}%\n"
                    f"{context['memory_used_gb']}/{context['memory_total_gb']} GiB"
                ),
                "inline": True,
            }
        )
        fields.append(
            {
                "name": "Uptime",
                "value": context["uptime_human"],
                "inline": True,
            }
        )

        fields.append(
            {
                "name": "Cron",
                "value": f"`{context['cron_display']}`",
                "inline": False,
            }
        )

        disk_chunks = context.get("disks_chunks", []) or ["No eligible disks"]
        for index, chunk in enumerate(disk_chunks, start=1):
            name = "Disks" if index == 1 else f"Disks ({index})"
            fields.append(
                {
                    "name": name,
                    "value": chunk,
                    "inline": False,
                }
            )

        embed: Dict[str, object] = {
            "title": title,
            "description": description,
            "fields": fields,
        }

        timestamp_iso = context.get("timestamp_iso")
        if timestamp_iso:
            embed["timestamp"] = timestamp_iso

        if isinstance(color, int):
            embed["color"] = color

        embed["footer"] = {"text": context.get("hostname", "Moncord")}

        return embed
