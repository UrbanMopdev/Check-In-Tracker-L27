# Ideas: using the booking data strategically

Parked for later (2026-10-30). Nothing here is built yet.

## Available data

The Launch27 bookings API returns, per booking: team, scheduled time and arrival
window, en-route start/end, check-in/check-out, estimated duration, travel distance,
price, revenue, tip, discount, frequency, new vs. returning customer, referral code,
"How did you hear about us?", and location.

**The tracker does not keep any history.** Each poll overwrites the last one, and only
today's four tracked times are stored. The API accepts any date, so past data can be
pulled in later.

## Ideas, most valuable first

1. **Late-arrival alerts:** flag a cleaner who hasn't set off in time or has missed the
   arrival window, and tell Kustomer before the customer complains. This is the closest
   to what the tracker already does.
2. **Actual vs. estimated job time:** check-out minus check-in vs. estimated duration, by
   service, team and home. Shows underpriced jobs, teams that run long, and quoting errors.
3. **Revenue per labour hour:** by team, service, area and frequency, to see which work
   to pursue and where to stop discounting.
4. **Marketing attribution and retention:** acquisition channel and referral code vs.
   whether customers become recurring.
5. **Travel and routing:** distance and drive time per job, for scheduling and possible
   zone-based pricing.

## Suggested first step

Save each day's bookings to a small Postgres database on Railway (about $1–2/month),
pull in a few months of history from the API, then build a dashboard on top. Ideas 2–5
all come from that data. Idea 1 is a separate change to the tracker's logic.

## Caution

The data includes customer names, addresses, emails and phone numbers. Keep anything
built from it internal, and store only the fields the analysis needs.
