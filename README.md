# Moncord

> Warning: This project is vibecoded, but all code was screened, and the screening established that there's nothing harmful about this program, as it's pragmatically impossible for it to screw with your system. If you, for some reason, experience any faults, like missing disks or feature requests, drop an issue. This is nothing more than a quick project made for my server.

Moncord is a containerized system monitor that gathers host CPU, memory, uptime, and disk statistics before sending templated updates to a Discord webhook. Ships with hourly heartbeats, startup/shutdown alerts, and cron-configurable scheduling.

## Features

- Docker/compose deployment with host filesystem mounts for disk telemetry.
- Discord webhook embeds with editable titles, descriptions, colors, and optional avatar/username overrides.
- Cron-style scheduling via environment variables (supports multiple expressions).
- Graceful startup and shutdown hooks with signal handling.
- Disk include/exclude filters to limit noisy mounts.

## Quick Start with Docker Compose

```yaml
services:
  moncord:
    image: ghcr.io/404oops/moncord:latest
    container_name: moncord
    hostname: Homelab # This should be the name of the machine you'll be monitorint.
    restart: unless-stopped
    environment:
      DISCORD_WEBHOOK_URL: https://discord.com/api/webhooks/replace-me
      DISCORD_USERNAME: Moncord
      DISCORD_AVATAR_URL: ""
      MONITOR_CRON: "0 * * * *"
      HOST_LABEL: ""
      HOST_ROOT_PATH: /hostfs
      DISK_INCLUDE: ""
      DISK_EXCLUDE: ""
    volumes:
      - /:/hostfs:ro
      - /proc:/hostfs/proc:ro
    pid: host
    stop_signal: SIGTERM
```

## Environment Variables

| Variable                   | Description                                                             | Default                          |
| -------------------------- | ----------------------------------------------------------------------- | -------------------------------- |
| `DISCORD_WEBHOOK_URL`      | Discord webhook destination (required).                                 | —                                |
| `DISCORD_USERNAME`         | Username shown in Discord messages.                                     | `Moncord`                        |
| `DISCORD_AVATAR_URL`       | Avatar image URL used for the webhook sender.                           | empty                            |
| `MONITOR_CRON`             | One or more cron expressions (newline or `;` separated).                | `0 * * * *`                      |
| `HOST_LABEL`               | Friendly name for the monitored host. Falls back to container hostname. | container hostname               |
| `HOST_ROOT_PATH`           | Path inside the container mapped to host root.                          | `/hostfs`                        |
| `DISK_INCLUDE`             | Comma-separated mountpoint prefixes to include (e.g. `/`, `/data`).     | include all                      |
| `DISK_EXCLUDE`             | Comma-separated mountpoint prefixes to ignore.                          | exclude none                     |
| `TEMPLATE_STARTUP`         | Optional override for the startup embed description.                    | code default                     |
| `TEMPLATE_HEARTBEAT`       | Optional override for the heartbeat embed description.                  | code default                     |
| `TEMPLATE_SHUTDOWN`        | Optional override for the shutdown embed description.                   | code default                     |
| `TEMPLATE_STARTUP_TITLE`   | Optional override for the startup embed title.                          | code default                     |
| `TEMPLATE_HEARTBEAT_TITLE` | Optional override for the heartbeat embed title.                        | code default                     |
| `TEMPLATE_SHUTDOWN_TITLE`  | Optional override for the shutdown embed title.                         | code default                     |
| `TEMPLATE_STARTUP_COLOR`   | Override embed color (hex or decimal) for startup events.               | code default                     |
| `TEMPLATE_HEARTBEAT_COLOR` | Override embed color (hex or decimal) for heartbeat events.             | code default                     |
| `TEMPLATE_SHUTDOWN_COLOR`  | Override embed color (hex or decimal) for shutdown events.              | code default                     |
| `LOG_LEVEL`                | Python logging level (`INFO`, `DEBUG`, ...).                            | `INFO`                           |
| `MONCORD_IMAGE`            | Fully qualified image reference used by compose deployments.            | `ghcr.io/404oops/moncord:latest` |
| `MONCORD_VERSION`          | Optional override for the image version tag during local builds.        | `dev`                            |
| `MONCORD_VCS_REF`          | Git reference injected into image labels during local builds.           | `dev`                            |
| `MONCORD_BUILD_DATE`       | ISO date string embedded in image labels during local builds.           | `unknown`                        |

### Cron Options

- Multiple expressions are supported; separate with a newline or `;` (e.g. `0 * * * *;30 * * * *`).
- Cron syntax is parsed and transformed into APScheduler triggers internally, so standard five-field formats apply.
- If native cron is preferred, convert the Docker service into a one-shot container and drive execution via host cron using `docker run`. The bundled scheduler remains available as a fallback.

## Message Templates

Defaults live in `monitor/src/notifier.py` within `DEFAULT_EMBED_TEMPLATES`. Titles, descriptions, and colors are formatted with Python `str.format` placeholders sourced from captured metrics. Override at runtime via environment variables or edit the template constants directly.

Embed colors accept common formats such as `#5865F2`, `0x5865F2`, or plain decimal integers. Values are clamped to Discord's 24-bit range automatically.

### Available Placeholders

- `hostname`, `timestamp_local`, `timestamp_iso`
- `cron_expression`, `cron_display`, `uptime_human`
- `cpu_percent`, `load_1`, `load_5`, `load_15`
- `memory_percent`, `memory_used_gb`, `memory_total_gb`
- `disks_block` (single string) and `disks_chunks` (array) for mount summaries

## Disk Metrics

The compose file binds the host root to `/hostfs` and parses host mount tables (falling back to `/proc/1/mountinfo` when needed) to evaluate disk usage from the host perspective. Adjust volume mappings, the `HOST_ROOT_PATH` value, or the include/exclude filters if you need alternate storage visibility.

## Shutdown Notifications

The container traps `SIGTERM`/`SIGINT`, emits a final snapshot, and closes the Discord session before exit. Compose will send `SIGTERM` by default during `docker-compose down` or `docker stop`.
