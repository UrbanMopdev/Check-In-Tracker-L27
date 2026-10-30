"""Late check-in warnings for the Kustomer "vps-lack-of-check-in-warning" workflow.

A booking is late when its cleaner has neither started driving nor checked in as the
arrival window runs out. The workflow branches on the 'Warning Type' field:
  'Half Arrival Window/ 30 Minutes' -> SMS to the cleaner
  '15 Minutes'                      -> task for the operations team
Each warning is sent at most once per booking per day.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# (Warning Type sent to Kustomer, minutes before the arrival window ends)
WARNINGS = (
    ('Half Arrival Window/ 30 Minutes', 30),
    ('15 Minutes', 15),
)


def _utc(value):
    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def due_warnings(booking, now):
    """Warning types that are due for `booking` at `now` (UTC), most urgent last."""
    if booking.get('active') is False or booking.get('completed') or not booking.get('teams'):
        return []
    tracking = [t for t in booking.get('time_tracking') or [] if isinstance(t, dict)]
    if any(t.get('enroute_started_at') or t.get('checkin_at') for t in tracking):
        return []
    start = _utc(booking.get('service_date'))
    if start is None:
        return []
    window_end = start + timedelta(minutes=booking.get('arrival_window') or 0)
    # Once the window has ended, stop warning (also avoids a burst of stale alerts after a restart).
    if now >= window_end:
        return []
    return [label for label, minutes in WARNINGS if now >= window_end - timedelta(minutes=minutes)]


def _load_sent(path, today):
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    return data.get('sent', {}) if data.get('date') == today else {}


def _save_sent(path, today, sent):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'date': today, 'sent': sent}, indent=2))
    tmp.replace(path)


def send_late_warnings(settings, bookings, records, today, send, now=None):
    """Send any due, not-yet-sent warnings. Returns the (booking ID, warning type) pairs handled."""
    now = now or datetime.now(timezone.utc)
    by_id = {str(r['ID']): r for r in records}
    sent = _load_sent(settings.late_sent_file, today)
    handled = []

    for booking in bookings:
        booking_id = str(booking.get('id'))
        record = by_id.get(booking_id)
        if record is None:
            continue
        for warning in due_warnings(booking, now):
            if warning in sent.get(booking_id, []):
                continue
            payload = {**record, 'Warning Type': warning}
            if settings.late_dry_run:
                log.info('[late dry run] Would warn booking %s (%s, team %s): %s',
                         booking_id, record.get('Date'), record.get('Team_Name'), warning)
            elif not send(settings.kustomer_late_webhook_url, payload):
                continue  # not recorded, so it is retried on the next poll
            sent.setdefault(booking_id, []).append(warning)
            handled.append((booking_id, warning))

    _save_sent(settings.late_sent_file, today, sent)
    return handled
