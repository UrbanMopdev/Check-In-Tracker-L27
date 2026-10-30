"""Compare the latest bookings with the previous snapshot and push changes to Kustomer."""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from checkin_tracker import kustomer
from checkin_tracker.late import send_late_warnings
from checkin_tracker.launch27 import Launch27Client
from checkin_tracker.parse import TRACKED_FIELDS, parse_bookings

log = logging.getLogger(__name__)


def _tracked(record):
    return {field: record.get(field) or '' for field in TRACKED_FIELDS}


def load_snapshot(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def save_snapshot(path, snapshot):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(snapshot, indent=2))
    tmp.replace(path)


def find_changes(records, previous):
    """Return records whose tracked fields differ from `previous`, each with an 'event_type'.

    Bookings not in the previous snapshot are skipped (same as the original script):
    the first time a booking is seen only establishes its baseline.
    """
    changed = []
    for record in records:
        before = previous.get(str(record['ID']))
        if before is None:
            continue
        now = _tracked(record)
        fields = [field for field in TRACKED_FIELDS if now[field] != before.get(field, '')]
        if fields:
            changed.append({**record, 'event_type': ', '.join(fields)})
    return changed


def _client(settings):
    return Launch27Client(settings.l27_base_url, settings.l27_email, settings.l27_password, settings.token_file)


def _today(settings):
    return datetime.now(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d')


def resend(settings, booking_id, event_type, client=None, send=kustomer.send_record):
    """Manually send one of today's bookings to Kustomer as `event_type`. Leaves the snapshot alone."""
    client = client or _client(settings)
    records = parse_bookings(client.get_bookings(_today(settings)), settings.timezone)
    matches = [r for r in records if str(r['ID']) == str(booking_id)]
    if not matches:
        log.error('Booking %s is not in today\'s bookings', booking_id)
        return False
    return send(settings.kustomer_webhook_url, {**matches[0], 'event_type': event_type})


def run_once(settings, client=None, send=kustomer.send_record):
    """One poll: fetch today's bookings, detect changes, send them, save the new snapshot."""
    client = client or _client(settings)
    today = _today(settings)
    bookings = client.get_bookings(today)
    records = parse_bookings(bookings, settings.timezone)

    if settings.kustomer_late_webhook_url:
        try:
            send_late_warnings(settings, bookings, records, today, send)
        except Exception:
            log.exception('Late check-in warnings failed')

    previous = load_snapshot(settings.snapshot_file)
    snapshot = {str(r['ID']): _tracked(r) for r in records}

    if previous is None:
        log.info('No previous snapshot; saved baseline of %d bookings for %s', len(records), today)
        save_snapshot(settings.snapshot_file, snapshot)
        return []

    changes = find_changes(records, previous)
    for record in changes:
        if settings.dry_run:
            log.info('[dry run] Would send booking %s: %s', record['ID'], record['event_type'])
        elif not send(settings.kustomer_webhook_url, record):
            # Keep the old values so this change is detected and retried on the next poll.
            snapshot[str(record['ID'])] = previous[str(record['ID'])]

    if not changes:
        log.info('No changes across %d bookings for %s', len(records), today)
    save_snapshot(settings.snapshot_file, snapshot)
    return changes
