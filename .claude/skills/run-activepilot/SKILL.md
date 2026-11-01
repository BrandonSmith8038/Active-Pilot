---
name: run-activepilot
description: Run, start, launch, smoke-test, or screenshot the ActivePilot flight-activity dashboard locally (outside Docker) against throwaway data. Use to confirm a change to app.py or dashboard.html works in the real running app - deadlines, logging/deleting flights, static files, page rendering.
---

# Run ActivePilot

ActivePilot is a stdlib Python HTTP server (`app.py`) serving one HTML page plus a JSON API. The agent path is
`driver.py`: it copies the shipped files to a temp work dir, rewrites the hardcoded `/data` path so real flight
history is never touched, launches the server with ntfy disabled, drives it over HTTP, and screenshots the page
with headless Chrome.

Paths below are relative to the repo root. Verified on Windows 11 (Git Bash, repo on the `\\reddirtserver` share),
Python 3.11, Node 24, Chrome.

## Prerequisites

- Python 3.9+ on PATH. `tzdata` is installed automatically by the driver into `<workdir>/deps` (not system Python).
- Optional: `node` (page JS syntax check) and Chrome/Edge (screenshot). Each step is skipped with a note if missing.

## Run (agent path)

```bash
python .claude/skills/run-activepilot/driver.py smoke
```

About 5 seconds. It prints `PASS`/`FAIL` per check, ends with `ALL PASSED`, and exits 1 if anything failed. Checks:
the page loads, the static files and their content types, the query-string fallback to the dashboard, the fresh state (ups/swa/fdx, `none`,
ntfy off), the Southwest fixture (flights 2026-10-27 + 2026-10-30 → deadline `2027-01-25`), rejection of a future date, delete,
and `node --check` on the page script. It then saves a screenshot to
`%TEMP%\activepilot-run\dashboard.png` (path printed). **Open the screenshot and look at it.** It should show three
ticket cards, with Southwest at OCT 30 → JAN 25, "ON TRACK".

To keep it running for manual poking (e.g. with `curl`), run it in the background:

```bash
python .claude/skills/run-activepilot/driver.py serve --port 8766     # run_in_background
curl -s -X POST http://127.0.0.1:8766/api/warn -d '{"days":9}'
curl -s http://127.0.0.1:8766/api/state
```

`serve` wipes data on start unless you pass `--keep-data`. Stopping the background task also stops the server.
Other flags: `--port` (default 8765), `--tz` (default `America/Phoenix`, as in `.env.example`), and `--workdir`.

API surface for ad-hoc requests: `GET /api/state`, `POST /api/log {id,date}`, `/api/delete {id,date}`,
`/api/settings {id,flights,period,unit,grace,period_end}`, `/api/warn {days}`, `/api/test`. Airline ids are
`ups`, `swa` and `fdx`.

When a change adds behavior, add a `check(...)` line to `smoke()` in `driver.py`.

## Run (human path)

The real deploy is `docker compose up -d --build` on Unraid. It isn't runnable here (no Docker on this machine), and it uses
the real `.env` and `/mnt/user/appdata/vac-dashboard` data. Don't use it for testing.

## Gotchas

- **`app.py` hardcodes `/data/data.json`** (and `os.makedirs("/data")`). Run straight from the repo on Windows,
  that resolves to `/data` at the root of the current drive or share. The driver rewrites exactly those two strings in
  its copy and exits loudly if it doesn't find exactly two, so update `stage()` if the data path code changes.
- **The file list comes from the Dockerfile `COPY` line.** A new runtime file that isn't on that line is missing
  here too, just like in the container. That is intentional.
- **Static paths match exactly.** `/icon.png?x=1` returns the dashboard HTML, not the icon (the smoke test asserts this).
- **Fixture dates are fixed, "today" isn't.** The SWA deadline (`2027-01-25`) never changes, but `days_left` and
  `status` depend on the real date and `--tz`. Assert on `deadline`, not on status, unless you control the date.
- **Notifications are always off** (`NTFY_TOPIC=""` is forced), so nothing reaches the user's phone. The notify
  loop still runs and stamps `notified` in the throwaway data.
- **Screenshots** use `--virtual-time-budget=5000` so the page's `/api/state` fetch renders before capture, and a temp
  `--user-data-dir` so headless Chrome doesn't attach to the user's open Chrome.
- The repo lives on a network share. In Git Bash, `cd //reddirtserver/appdata/flight-reminders-src` works.

## Troubleshooting

- `ZoneInfoNotFoundError: 'No time zone found with key America/Chicago'`: Windows Python has no tz database, so
  `tzdata` is missing. The driver installs it into `<workdir>/deps` and sets `PYTHONPATH`. If you launch `app.py` by hand,
  do the same: `pip install --target <dir> tzdata`, then `PYTHONPATH=<dir>`.
