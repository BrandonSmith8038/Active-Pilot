# ActivePilot

A small self-hosted dashboard that keeps track of the activity requirements for the virtual airlines (VAs) I fly with. Each airline gets a boarding-pass style card showing when I last flew, when I need to fly by, and how many days are left. A button on each card logs a flight, and a daily ntfy notification reminds me before a deadline slips.

Built to run in Docker on an Unraid server, on the local network only.

## Features

- One card per airline: last flight, fly-by date, countdown, flights counted, requirement, grace period
- "Log flight today" button, plus an "Add a past flight" date picker for logging a flight late
- Per-airline flight history with delete buttons
- Card turns amber inside the warning window (default 5 days before the deadline) and red when overdue
- Optional grace period per airline (days after the deadline before the pilot is deactivated)
- Two ways to count a deadline: rolling (from your most recent flights) or fixed back-to-back periods (matched to a date from the airline's own site)
- Daily ntfy notifications at a set hour (default 4 pm) while a card is in its warning window or overdue
- Tabbed settings window: requirements per airline, warning window, test notification

## Airlines and rules (as configured)

| Airline | Requirement | Grace | Counting |
|---|---|---|---|
| UPS | 1 flight every 30 days | none | rolling |
| Southwest | 2 flights every 90 days | 7 days | fixed periods (current period ends 2026-12-01) |
| FedEx | 1 flight every 90 days | 10 days | rolling |

Deadhead flights do not count. Requirements can be edited from the Settings tab for each airline.

## Quick start

1. Put all files from this folder in one directory (the Dockerfile copies the app, page and images in).
2. Copy `.env.example` to `.env` and fill it in (see below).
3. Build and start:

   ```
   docker compose up -d --build
   ```

4. Open `http://YOUR-SERVER-IP:8100`.

Keep the port LAN-only. There is no login, so do not forward it on your router.

## Settings (.env)

| Variable | Default | Purpose |
|---|---|---|
| `HTTP_PORT` | `8100` | Port the dashboard listens on |
| `TZ` | `UTC` | Your timezone (IANA name, e.g. `America/Phoenix`); decides what "today" is and when the daily reminder fires |
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy server |
| `NTFY_TOPIC` | empty | ntfy topic to publish to; leave empty to turn notifications off |
| `NOTIFY_HOUR` | `16` | Hour (0-23, local time) the daily reminder is sent |
| `ICON_URL` | empty | Icon for the Unraid Docker tab, e.g. `http://YOUR-SERVER-IP:8100/icon.png` |

`.env` is git-ignored so a `git pull` never overwrites it.

## Data

Flight history and settings are stored in one JSON file, `/data/data.json` inside the container. The compose file maps `/data` to `/mnt/user/appdata/vac-dashboard` on the server, outside the git clone, so rebuilding or updating never touches your history.

## Files

| File | Purpose |
|---|---|
| `app.py` | The whole backend: web server, JSON API, deadline logic, notification loop |
| `dashboard.html` | The whole frontend: cards, settings window, styling |
| `logo.png` | Logo shown in the page header |
| `icon.png` | 512 px app icon (Unraid/Docker) |
| `favicon.ico` | Browser tab icon |
| `Dockerfile` | Python 3.12-slim image; copies in the files above |
| `docker-compose.yml` | Container, port, data volume and Unraid icon label |
| `.env.example` | Template for `.env` |
| `handoff.md` | Detailed notes for continuing development |

## Updating

```
git pull
docker compose up -d --build
```

Your `.env` and `/data` folder are not part of the repo, so they are kept.
