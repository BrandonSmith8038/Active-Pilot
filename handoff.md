# ActivePilot - Developer Handoff

Last updated: 2026-10-30. Written so a new Claude conversation can continue development without the earlier chat. Statements are based on the current files unless marked **UNVERIFIED**.

## 1. What the app does

ActivePilot is a self-hosted dashboard for tracking activity requirements at virtual airlines (VAs): how many flights are needed per period to stay on the roster. There is one card per airline (UPS, Southwest, FedEx). Each card shows the last flight, the "fly by" deadline, a countdown, flights counted, the requirement and the grace period. A button logs a flight for today; settings let the user add a flight on a past date, edit requirements, and set a warning window. A background thread sends daily ntfy notifications at a set hour when a card is in its warning window or overdue.

Single user, LAN only, no authentication.

### How it works
- The browser loads `dashboard.html` (served at any unknown path, including `/`). The page calls `GET /api/state` every 60 seconds and after every action.
- The server computes every card's status in `compute()`; the page only displays what it receives.
- Actions are `POST` requests (log, delete, settings, warn, test). After each, the server saves to `/data/data.json`.

## 2. Language, frameworks, dependencies

- Python 3.12 (Docker image `python:3.12-slim`). **Standard library only** (`http.server`, `json`, `threading`, `urllib`, `zoneinfo`, `datetime`). The only pip install is `tzdata`, so `zoneinfo` can find timezones in the slim image.
- Frontend: one HTML file with inline CSS and vanilla JavaScript. No frameworks, no build step, no external CDN or font requests.
- Docker / docker-compose. Hosted on an Unraid server (appdata path `/mnt/user/appdata/vac-dashboard`).
- Notifications: public `ntfy.sh` over HTTPS.

## 3. Project structure

```
app.py               backend (server, API, deadline logic, notification loop, migrations)
dashboard.html       frontend (cards, settings dialog, all CSS and JS)
logo.png             header logo (transparent PNG, ~820x359)
icon.png             512x512 app icon (Unraid/Docker); served at /icon.png
favicon.ico          browser tab icon (16/32/48/64); served at /favicon.ico
Dockerfile           copies app.py dashboard.html logo.png icon.png favicon.ico into /app
docker-compose.yml   container vac-dashboard, port from HTTP_PORT, /data volume, Unraid icon label
.env.example         template for .env (git-ignored)
.gitignore           ignores .env and Python/OS junk
README.md            user-facing setup guide
handoff.md           this file
```

All eight runtime files must sit in one directory for the Docker build to succeed (the Dockerfile `COPY` line lists them by name; add new files there too).

## 4. How the components interact

- `app.py` `compute(a)` turns one airline record into a card: last flight, deadline, days left, status, flights in window, grace left. Both `GET /api/state` and the notification loop call it, so the screen and the notifications always agree.
- `notify_loop()` runs in a daemon thread, wakes every 30 seconds, and after `NOTIFY_HOUR` sends at most one notification per airline per day (tracked by the `notified` date saved in `data.json`). It shares a `threading.Lock` with the request handlers.
- `dashboard.html`: `renderCards()` builds the cards, `renderSets()` builds the tabbed settings dialog, `load()` fetches state and re-renders. `act()` posts an action, then reloads and re-renders everything including settings. While the dialog is open, the 60-second refresh redraws the cards only (so typed but unsaved settings are not wiped).
- Static files are served from the `STATIC` dict in `app.py` (`/logo.png`, `/icon.png`, `/favicon.ico`).

## 5. Data storage

Single JSON file `/data/data.json` (container path; host path `/mnt/user/appdata/vac-dashboard`). Written atomically (temp file then `os.replace`). Shape:

```json
{
  "warn_days": 5,
  "rules_v": 4,
  "airlines": [
    {
      "id": "swa", "name": "Southwest", "sub": "Southwest Virtual", "color": "#3b4f8f",
      "flights": 2, "period": 90, "unit": "days", "grace": 7,
      "period_end": "2026-12-01",
      "history": ["2026-10-27", "2026-07-17"],
      "notified": "2026-10-29"
    }
  ]
}
```

- `history`: ISO dates, one entry per flight (duplicates allowed so two flights on one day work).
- `period_end`: optional. If set (and `unit` is `days`), the airline uses fixed periods; empty string means rolling.
- `notified`: date of the last daily notification check for that airline.
- `color` in the file is ignored at runtime; real colors come from the `COLORS` dict in `app.py`.
- `rules_v` is a schema/rules version used by `migrate()` (see section 8).

API:

| Method and path | Body | Effect |
|---|---|---|
| GET `/api/state` | | Today's date, warn days, ntfy configured flag, computed airlines |
| POST `/api/log` | `{id, date?}` | Add a flight (default today; future dates rejected) |
| POST `/api/delete` | `{id, date}` | Remove one matching history date |
| POST `/api/settings` | `{id, flights, period, unit, grace, period_end}` | Save one airline's requirement |
| POST `/api/warn` | `{days}` | Set warning window (0-60) |
| POST `/api/test` | | Send a test ntfy message |

Environment: `HTTP_PORT` (8100), `TZ`, `NTFY_SERVER`, `NTFY_TOPIC`, `NOTIFY_HOUR` (16), `ICON_URL` (used only by the compose label).

## 6. Features implemented

"User-seen" means the user viewed it running (screenshots/feedback in the chat). "Sandbox-tested" means Claude ran the logic in a script, not in the live container.

| Feature | Status |
|---|---|
| Card per airline with last flight, fly-by, days left, requirement, flights in window, grace | User-seen |
| Log flight today, add past flight, flight history with delete | User-seen (history list and delete buttons shown) |
| Boarding-pass card styling (off-white ticket, color band, notches, barcode) | User-seen and approved |
| Header logo (far left, 112px tall) and gear icon (far right) | User-seen |
| Tabbed settings dialog with custom +/- steppers | User-seen and approved |
| Rolling deadline: Nth most recent flight + period | Sandbox-tested |
| Warning (<= warn_days) and overdue statuses, grace-period display | Sandbox-tested; overdue card seen in a screenshot |
| One-time data migration to the airline rules (rules_v 2) and Southwest 7-day grace (rules_v 4) | User-seen (settings screenshot showed 2/90/7 and 1/90/10) |
| Fixed-period mode with `period_end` | Sandbox-tested only |
| Daily ntfy notifications and test button | **UNVERIFIED** (user has not reported a received notification) |
| Favicon and Unraid icon appearing | **UNVERIFIED** |
| Docker build/run of the very latest file set | Likely (logo displayed), not explicitly confirmed |

## 7. Important technical decisions and requirements

- **Mirrors the user's Nascar Checkin container** (Python stdlib, single `app.py` + HTML, `/data` volume, `.env` file, Unraid icon label). Keep it dependency-free.
- **Rules are in days, not months** (calendar months were tried and rejected: UPS "every 30 days", SWA "2 flights in 90 days", FedEx "1 flight every 90 days + 10-day grace"). `unit: "months"` still works for rolling mode but is not used.
- **Rolling deadline** = date of the Nth most recent flight + period (N = flights required). With fewer than N flights logged, the earliest logged flight is used.
- **Southwest fixed periods**: the Southwest SOP (v7.4) says "rolling 90 days", but the airline's own site shows 1/2 and "due by Dec 1, 2026" while still Active. That date fits fixed back-to-back 90-day periods counted back from Dec 1 (Mar 6, Jun 4, Sep 2). So Southwest uses `period_end = 2026-12-01`. This is an inference **(UNVERIFIED)**; the plan is to compare after the user's next flight (see section 10). Fixed mode: current period is (end - period, end]; if the flight count is met, the deadline jumps to the end of the next period and the card shows "Period complete".
- **Grace period** is only displayed ("Grace period" / "Past grace" chip and countdown) and mentioned in notifications; it does not change `status`. Southwest grace = 7 days (SOP "warning status for 7 days"); FedEx = 10 days.
- **Deadhead flights do not count**, so they are never logged.
- **Port 8100**, LAN only, no login. Port 8100 is recorded in the user's home-server port list.
- **Notifications**: public ntfy.sh topic from `.env`; one message per airline per day after `NOTIFY_HOUR` (default 16:00 local), only when status is warning or overdue; no tap action wanted.
- **Colors** (muted, user-approved): UPS `#8c6a2b`, Southwest `#3b4f8f`, FedEx `#5a3f8a` (FedEx must stay purple). Kept in `COLORS` in `app.py`.
- **Flight logging is date only** (no flight number/route/notes).
- **The history feature is trial**: the user may remove it. The history block in `renderCards()` is marked with an HTML comment so it can be deleted cleanly.
- **Airlines are fixed** at three; no UI to add or remove airlines.
- **Branding**: renamed ActivePilot. Technical names (`vac-dashboard` container and `/mnt/user/appdata/vac-dashboard`) were deliberately kept to avoid moving saved data.

## 8. Known bugs, limitations, unfinished

- Fixed-period logic is based on an inference about the site's behavior (see above).
- `period_end` is ignored if `unit` is `months`.
- Notification text can say "Last flight: None." if an airline has no history but is overdue in fixed mode.
- Deleting a flight does not reset `notified`, so a card that was notified earlier today will not re-notify until tomorrow.
- A restart after the notify hour sends that day's notification late (by design).
- Any unknown GET path (including `/icon.png?x=1`) returns the dashboard page, because static files match exact paths only.
- The barcode on each card is decorative (derived from airline id and deadline); it encodes nothing.
- No authentication; do not expose the port.
- `migrate()` hardcodes Southwest `period_end = 2026-12-01` on first run of rules_v 3. On a brand-new install that date will be stale after Dec 2026 and should be edited in Settings.
- No automated tests. No Git history existed before this handoff.

Migration versions (`rules_v`): 2 = apply official rules (flights/period/unit/grace) to saved airlines; 3 = set Southwest `period_end`; 4 = set Southwest grace to 7. A fresh install starts at `rules_v: 2` so migrations 3 and 4 run on first start.

## 9. Instructions for modifying without breaking things

- Do not change the shape of `data.json` without adding a `migrate()` step (bump `rules_v`); the user's real flight history lives there.
- Keep `compute()` as the single source of truth for deadlines. Do not duplicate deadline math in the page.
- If you add a new file the page or app needs, add it to the `Dockerfile` `COPY` line and, if it is served, to `STATIC` in `app.py`.
- Keep element IDs used by settings code: `f-<id>`, `p-<id>`, `u-<id>`, `g-<id>`, `e-<id>`, `d-<id>`, `warn`, and the global functions `logFlight`, `delFlight`, `saveSet`, `addPast`, `saveWarn`, `testNtfy`, `setTab`, `bump` (they are called from inline `onclick` attributes).
- Keep `renderSets()` from running while the dialog is open unless an action just completed (it wipes unsaved typing).
- The card status classes (`ok`, `warning`, `overdue`, `none`) drive CSS variables such as `--s`; keep them in sync with `compute()`.
- Notification header values must be plain ASCII (ntfy headers); do not put emoji in titles (use the `Tags` header instead).
- The user cannot easily run a browser against Claude's sandbox: changes to the page are checked by syntax-checking the script with `node --check` only. Ask the user to test.

## 10. Next planned tasks

1. **Southwest check**: the user will fly another Southwest flight and log it. Compare the card's "Fly by" with the airline site's "Due by". If the site rolls to about Mar 1, 2027, fixed periods are right; otherwise work out the site's logic from the date it shows.
2. Offered, not decided: make the Southwest card show whichever deadline is sooner (strict rolling per the SOP vs the site's date).
3. Verify ntfy end to end: Settings > Alerts > test notification, then confirm the 4 pm reminder arrives.
4. Verify the favicon and the Unraid Docker-tab icon (`ICON_URL=http://SERVER-IP:8100/icon.png`).
5. Offered styling options: a light/cream page variant and striped ticket edges like a reference boarding pass.
6. Optional rename of container and data folder to `activepilot` (requires moving `/mnt/user/appdata/vac-dashboard`).
7. Optional cleanups from section 8.

## 11. How the user likes to work

- Before any **new project**, ask ten clarifying questions, one at a time.
- After a requested feature, prompt the user to test it and say if it is good; when they say it looks good or is good to go, give a commit message.
- Code changes: if fewer than 6 changes, give them in search-and-replace format; always add a brief plain-English explanation of what changed and how, so the user can learn.
- When asked for an updated `handoff.md`, update the current file with the sections above, based on the actual files, and mark anything unverifiable.
- The user pushes files to GitHub and rebuilds with `docker compose up -d --build` on Unraid.
