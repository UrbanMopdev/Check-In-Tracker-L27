import copy
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from checkin_tracker.late import due_warnings, send_late_warnings
from checkin_tracker.parse import parse_bookings
from tests.test_tracker import BOOKING, settings  # noqa: F401  (pytest fixture)

HALF, FIFTEEN = 'Half Arrival Window/ 30 Minutes', '15 Minutes'

# Service 18:00Z with a 60-minute window -> window ends 19:00Z (3:00 PM Eastern).
WAITING = {**copy.deepcopy(BOOKING), 'arrival_window': 60, 'active': True, 'completed': False,
           'time_tracking': []}


def at(hh, mm):
    return datetime(2024, 8, 25, hh, mm, tzinfo=timezone.utc)


def test_warnings_follow_the_arrival_window():
    assert due_warnings(WAITING, at(18, 29)) == []
    assert due_warnings(WAITING, at(18, 30)) == [HALF]
    assert due_warnings(WAITING, at(18, 45)) == [HALF, FIFTEEN]
    assert due_warnings(WAITING, at(19, 0)) == []


def test_no_warning_once_cleaner_is_on_the_way_or_booking_is_inactive():
    enroute = {**WAITING, 'time_tracking': [{'enroute_started_at': '2024-08-25T18:20:00Z'}]}
    checked_in = {**WAITING, 'time_tracking': [{'checkin_at': '2024-08-25T18:40:00Z'}]}
    cancelled = {**WAITING, 'active': False}
    unassigned = {**WAITING, 'teams': []}
    for booking in (enroute, checked_in, cancelled, unassigned):
        assert due_warnings(booking, at(18, 50)) == []


def test_zero_minute_window_warns_before_start_time():
    fixed = {**WAITING, 'arrival_window': 0}
    assert due_warnings(fixed, at(17, 30)) == [HALF]
    assert due_warnings(fixed, at(18, 0)) == []


def run(settings, now, send):
    records = parse_bookings([WAITING], 'America/New_York')
    return send_late_warnings(settings, [WAITING], records, '2024-08-25', send, now=now)


def test_each_warning_sent_once_with_warning_type(settings):
    live = replace(settings, kustomer_late_webhook_url='https://late.invalid', late_dry_run=False)
    sent = []
    send = lambda url, r: sent.append((url, r)) or True
    run(live, at(18, 31), send)
    run(live, at(18, 32), send)
    run(live, at(18, 46), send)
    assert [(url, r['ID'], r['Warning Type']) for url, r in sent] == [
        ('https://late.invalid', 101, HALF),
        ('https://late.invalid', 101, FIFTEEN),
    ]
    assert sent[0][1]['Customer_Email'] == 'test@example.com'


def test_failed_warning_is_retried(settings):
    live = replace(settings, kustomer_late_webhook_url='https://late.invalid', late_dry_run=False)
    run(live, at(18, 31), lambda url, r: False)
    sent = []
    run(live, at(18, 32), lambda url, r: sent.append(r) or True)
    assert [r['Warning Type'] for r in sent] == [HALF]


def test_dry_run_logs_but_does_not_send(settings):
    trial = replace(settings, kustomer_late_webhook_url='https://late.invalid', late_dry_run=True)

    def boom(url, record):
        raise AssertionError('should not send in dry run')

    assert run(trial, at(18, 46), boom) == [('101', HALF), ('101', FIFTEEN)]
