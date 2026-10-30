# Check-In Tracker (Launch27 → Kustomer)

Polls today's Launch27 bookings every minute, watches four time-tracking fields:
**Enroute_Start, Enroute_End, Checked_In, Checked_Out**. When any of them change on a booking,
the full booking record is POSTed to the Kustomer form hook. An `event_type` field lists which
fields changed (e.g. `"Checked_In"` or `"Enroute_End, Checked_In"`).

This is a rebuild of the original `api-tracking` project. Behaviour and the payload field names
are the same, so the existing Kustomer workflow keeps working.

## How it works

1. Reuse the cached Launch27 bearer token, or log in if it is missing or rejected (401/403).
2. Fetch all of today's bookings (today in `TIMEZONE`, default America/New_York), 100 per page.
3. Flatten each booking. Timestamps are converted to `YYYY-MM-DD HH:MM AM/PM` in `TIMEZONE`.
4. Compare the tracked fields with the previous poll's snapshot (`state/last_snapshot.json`).
5. Send each changed booking to Kustomer. If a send fails, the booking keeps its old snapshot,
   so the change is sent again on the next poll.

**Late check-in warnings.** If `KUSTOMER_LATE_WEBHOOK_URL` is set, each poll also looks for
bookings whose cleaner has neither started driving nor checked in as the arrival window runs out.
It sends the booking to that hook with a `Warning Type` field, which the Kustomer
"vps-lack-of-check-in-warning" workflow branches on:

| Warning Type | Sent when | What the Kustomer workflow does |
| --- | --- | --- |
| `Half Arrival Window/ 30 Minutes` | 30 min before the arrival window ends | SMS to the cleaner (if their profile allows SMS) |
| `15 Minutes` | 15 min before the arrival window ends | Task on the cleaner's profile for the operations team |

Each warning goes out at most once per booking per day. Nothing is sent once the window has
ended, and cancelled or unassigned bookings are skipped.

A booking seen for the first time only sets its baseline and is not sent, the same as the
original. The very first run only saves a baseline.

## Setup

Requires Python 3.9+.

```bash
git clone https://github.com/UrbanMopdev/Check-In-Tracker-L27.git ~/checkin-tracker
cd ~/checkin-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # then fill in L27_EMAIL, L27_PASSWORD, KUSTOMER_WEBHOOK_URL
chmod 600 .env
```

Test without sending anything to Kustomer:

```bash
DRY_RUN=true .venv/bin/python -m checkin_tracker   # run twice: first run saves the baseline
```

## Running it

You can run it in either of two ways.

### Option A: a long-running service (recommended)

`python -m checkin_tracker --loop` polls every `POLL_SECONDS` during `ACTIVE_HOURS`.
`ACTIVE_HOURS` is evaluated in `TIMEZONE`, not in the server's clock. A systemd unit:

```ini
# /etc/systemd/system/checkin-tracker.service
[Unit]
Description=Launch27 check-in tracker
After=network-online.target

[Service]
WorkingDirectory=/root/checkin-tracker
ExecStart=/root/checkin-tracker/.venv/bin/python -m checkin_tracker --loop
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now checkin-tracker
journalctl -u checkin-tracker -f
```

The included `Procfile` (`worker: python -m checkin_tracker --loop`) runs the same thing on a
platform such as Railway or Heroku. Set the variables from `.env.example` in the platform.
Point `STATE_DIR` at a persistent volume, or the snapshot resets on each deploy.

### Option B: cron (the original setup)

`python -m checkin_tracker` with no flag does a single poll. Cron uses the server's time zone.
Set `CRON_TZ` so the hours mean Eastern time. `flock` stops a slow run from overlapping the next one:

```cron
CRON_TZ=America/New_York
* 7-23 * * * cd /root/checkin-tracker && flock -n state/.lock .venv/bin/python -m checkin_tracker >> checkin-tracker.log 2>&1
```

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `L27_EMAIL` / `L27_PASSWORD` | yes | | Launch27 staff login |
| `KUSTOMER_WEBHOOK_URL` | yes (unless `DRY_RUN`) | | Kustomer form hook URL |
| `L27_BASE_URL` | | `https://urbanmop.launch27.com` | |
| `TIMEZONE` | | `America/New_York` | Sets which day counts as "today" and how timestamps are formatted |
| `ACTIVE_HOURS` | | `7-23` | `--loop` only; inclusive hours in `TIMEZONE` |
| `POLL_SECONDS` | | `60` | `--loop` only |
| `STATE_DIR` | | `./state` | Cached token and last snapshot |
| `DRY_RUN` | | `false` | Log changes without sending |
| `KUSTOMER_LATE_WEBHOOK_URL` | | | Hook for late check-in warnings; empty = off |
| `LATE_WARNINGS_DRY_RUN` | | `true` | Log late warnings without sending |

Settings come from the environment. A `.env` file in the project root is also read.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Changes from the original project

- Credentials and the Kustomer hook URL now come from environment variables. They are no longer hardcoded in source.
- Token check: the old code fetched a fixed past date's bookings on every run to test the token. Now the token is renewed only when Launch27 rejects it.
- Network calls now time out. A failed fetch no longer crashes the run or overwrites the snapshot.
- A failed Kustomer send is retried on the next poll. The old code dropped it.
- State files sit in `STATE_DIR`, not in whatever directory cron happened to start in.
- Active hours are in Eastern time. The old cron entry used the VPS clock, which is usually UTC.
- Dependencies are down to `requests` and `tzdata`. pandas, numpy, openpyxl and pytz are gone.
- `Distance` is `null` when Launch27 has no distance. The old code sent the string `"N/A km"`.
