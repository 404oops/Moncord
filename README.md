# Moncord

Moncord is a containerized system monitor that gathers host CPU, memory, uptime, and disk statistics before sending templated updates to a Discord webhook. Ships with hourly heartbeats, startup/shutdown alerts, and cron-configurable scheduling.

## Features

- Docker/compose deployment with host filesystem mounts for disk telemetry.
- Discord webhook notifications with editable templates and optional avatar/username overrides.
- Cron-style scheduling via environment variables (supports multiple expressions).
- Graceful startup and shutdown hooks with signal handling.
- Disk include/exclude filters to limit noisy mounts.

## Quick Start with Docker Compose

```yaml
services:
  moncord:
    image: ghcr.io/404oops/moncord:latest
    container_name: moncord
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

## Container Images

- GitHub Actions workflow [`.github/workflows/publish.yml`](.github/workflows/publish.yml) builds multi-architecture images (amd64/arm64) and pushes them to GitHub Container Registry on every push to `main` and on `v*` tags.
- Images are published under `ghcr.io/<owner>/moncord`. Override the target with `MONCORD_IMAGE` in your `.env` file.
- Make sure the repository has `packages: write` permission for the default `GITHUB_TOKEN` (automatic for public repos).

## Environment Variables

| Variable              | Description                                                             | Default                          |
| --------------------- | ----------------------------------------------------------------------- | -------------------------------- |
| `DISCORD_WEBHOOK_URL` | Discord webhook destination (required).                                 | —                                |
| `DISCORD_USERNAME`    | Username shown in Discord messages.                                     | `Moncord`                        |
| `DISCORD_AVATAR_URL`  | Avatar image URL used for the webhook sender.                           | empty                            |
| `MONITOR_CRON`        | One or more cron expressions (newline or `;` separated).                | `0 * * * *`                      |
| `HOST_LABEL`          | Friendly name for the monitored host. Falls back to container hostname. | container hostname               |
| `HOST_ROOT_PATH`      | Path inside the container mapped to host root.                          | `/hostfs`                        |
| `DISK_INCLUDE`        | Comma-separated mountpoint prefixes to include (e.g. `/`, `/data`).     | include all                      |
| `DISK_EXCLUDE`        | Comma-separated mountpoint prefixes to ignore.                          | exclude none                     |
| `TEMPLATE_STARTUP`    | Optional override for the startup message template.                     | code default                     |
| `TEMPLATE_HEARTBEAT`  | Optional override for the heartbeat message template.                   | code default                     |
| `TEMPLATE_SHUTDOWN`   | Optional override for the shutdown message template.                    | code default                     |
| `LOG_LEVEL`           | Python logging level (`INFO`, `DEBUG`, ...).                            | `INFO`                           |
| `MONCORD_IMAGE`       | Fully qualified image reference used by compose deployments.            | `ghcr.io/404oops/moncord:latest` |
| `MONCORD_VERSION`     | Optional override for the image version tag during local builds.        | `dev`                            |
| `MONCORD_VCS_REF`     | Git reference injected into image labels during local builds.           | `dev`                            |
| `MONCORD_BUILD_DATE`  | ISO date string embedded in image labels during local builds.           | `unknown`                        |

### Cron Options

- Multiple expressions are supported; separate with a newline or `;` (e.g. `0 * * * *;30 * * * *`).
- Cron syntax is parsed and transformed into APScheduler triggers internally, so standard five-field formats apply.
- If native cron is preferred, convert the Docker service into a one-shot container and drive execution via host cron using `docker run`. The bundled scheduler remains available as a fallback.

## Message Templates

Defaults live in `monitor/src/notifier.py` within `DEFAULT_TEMPLATES`. Each template uses Python `str.format` placeholders sourced from captured metrics. Override at runtime via environment variables or edit the template constants directly.

### Available Placeholders

- `hostname`, `timestamp_local`, `timestamp_iso`
- `cron_expression`, `uptime_human`
- `cpu_percent`, `load_1`, `load_5`, `load_15`
- `memory_percent`, `memory_used_gb`, `memory_total_gb`
- `disks_block` with preformatted mount summaries

## Disk Metrics

The compose file binds the host root to `/hostfs` and parses `/proc/mounts` to evaluate disk usage from the host perspective. Adjust volume mappings or the include/exclude filters if you need alternate storage visibility.

## Shutdown Notifications

The container traps `SIGTERM`/`SIGINT`, emits a final snapshot, and closes the Discord session before exit. Compose will send `SIGTERM` by default during `docker-compose down` or `docker stop`.
