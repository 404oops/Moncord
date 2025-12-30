from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import Iterable, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from .collectors import capture_snapshot
from .config import Config, load_config
from .notifier import DiscordNotifier


def _configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _parse_cron_entries(raw_value: str) -> List[str]:
    if not raw_value:
        return ["0 * * * *"]
    fragments: List[str] = []
    for token in raw_value.replace(";", "\n").splitlines():
        stripped = token.strip()
        if stripped:
            fragments.append(stripped)
    return fragments or ["0 * * * *"]


def _register_jobs(scheduler: BackgroundScheduler, config: Config, notifier: DiscordNotifier) -> None:
    cron_entries = _parse_cron_entries(config.cron_expression)
    for cron_expression in cron_entries:
        try:
            trigger = CronTrigger.from_crontab(cron_expression)
        except ValueError as exc:
            logging.error("Invalid cron expression '%s': %s", cron_expression, exc)
            continue

        def _job_wrapper(trigger_expression: str) -> None:
            snapshot = capture_snapshot(config)
            logging.debug("Dispatching heartbeat for cron '%s'", trigger_expression)
            notifier.send("heartbeat", snapshot)

        scheduler.add_job(
            func=_job_wrapper,
            trigger=trigger,
            kwargs={"trigger_expression": cron_expression},
            name=f"heartbeat@{cron_expression}",
            misfire_grace_time=60,
            coalesce=True,
        )


def main() -> None:
    load_dotenv()
    _configure_logging()

    try:
        config = load_config()
    except ValueError as exc:
        logging.error("Configuration error: %s", exc)
        sys.exit(1)

    notifier = DiscordNotifier(config)
    scheduler = BackgroundScheduler(timezone="UTC")
    _register_jobs(scheduler, config, notifier)

    if not scheduler.get_jobs():
        logging.error("No valid cron expressions registered; exiting")
        notifier.close()
        sys.exit(1)

    stop_event = threading.Event()

    def _handle_signal(signum: int, _: object) -> None:
        logging.info("Received signal %s; shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    startup_snapshot = capture_snapshot(config)
    notifier.send("startup", startup_snapshot)

    scheduler.start()
    logging.info("Scheduler started with %d job(s)", len(scheduler.get_jobs()))

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        scheduler.shutdown(wait=False)
        shutdown_snapshot = capture_snapshot(config)
        notifier.send("shutdown", shutdown_snapshot)
        notifier.close()
        logging.info("Moncord stopped")


if __name__ == "__main__":
    main()
