# ActivePilot

Self-hosted dashboard that tracks flight-activity requirements for three virtual airlines (UPS, Southwest, FedEx). Single user, LAN only, no auth. Do not suggest exposing the port.

## Hard constraints
- Stdlib-only Python plus `tzdata` (the only pip install, in the Dockerfile). The frontend is one HTML file with vanilla JS: no frameworks, no build step, no CDN or font requests. This mirrors the user's other container ("Nascar Checkin"); keep it dependency-free.
- `/data/data.json` holds the user's real flight history. Any change to its shape needs a new `migrate()` step that bumps `rules_v`. Fresh installs start at `rules_v: 2`, so every later migration also runs on first start.
- `compute()` is the single source of truth for deadlines and status. The API and the notification loop both use it. Never duplicate deadline math in the page.
- A new runtime file must go on the Dockerfile `COPY` line and, if it is served, into `STATIC` in `app.py`. Static paths match exactly, so any other GET (even `/icon.png?x=1`) returns the dashboard.
- Inline `onclick` handlers call global JS functions, and settings code reads element IDs (`f-/p-/u-/g-/e-/d-<id>`, `warn`). Keep those names.
- Card status classes (`ok`, `warning`, `overdue`, `none`) drive CSS; keep them in sync with `compute()`.
- ntfy header values must be plain ASCII. No emoji in titles; use the `Tags` header.
- Container name `vac-dashboard` and host path `/mnt/user/appdata/vac-dashboard` were deliberately kept after the rename to ActivePilot, so saved data didn't have to move. Renaming them means moving that folder.

## Domain decisions (don't re-litigate)
- Rules are in **days**, not calendar months. Months were tried and rejected. `unit: "months"` still works for rolling mode but isn't used, and `period_end` is ignored with months.
- Rolling deadline = the Nth most recent flight + period (N = flights required).
- Grace is display-only. It never changes `status`.
- Deadhead flights don't count and are never logged. Logging is date only (no flight number, route or notes).
- Airlines are fixed at three; there is no add/remove UI.
- Colors are muted and user-approved. FedEx must stay purple.
- The flight-history UI is a trial and may be removed. Its block in `renderCards()` is marked with an HTML comment.
- Notifications: at most one per airline per day, after `NOTIFY_HOUR`, only for warning or overdue status, with no tap action.

## Unverified / open
- **Southwest is strict rolling (verified Nov 2026).** With flights on Oct 27 and Oct 30, 2026, the site showed a deadline of Jan 25, 2027 (Oct 27 + 90). The fixed-period guess was wrong, and migration v5 removes `period_end`. The fixed-period code path still exists but no airline uses it. The earlier "due by Dec 1, 2026" was never explained.
- Not yet confirmed by the user: ntfy delivery end to end (test button and the 4 pm reminder), and whether the favicon and Unraid icon (`ICON_URL=http://SERVER-IP:8100/icon.png`) appear.
- Known small issues: the notification can say "Last flight: None." in fixed mode with no history, and deleting a flight doesn't reset `notified`.
- `requiremnts` (misspelled) is an empty, unused file.

## Testing
- No unit tests. To check a change, run `python .claude/skills/run-activepilot/driver.py smoke` (the `/run-activepilot` skill), look at its screenshot, then ask the user to test.
- The user builds and tests with `docker compose up -d --build` on Unraid, then commits and pushes once changes are confirmed (see the workflow in the global CLAUDE.md).

## Ideas offered, not requested
- A light/cream page variant, and striped ticket edges like a reference boarding pass.
