import copy
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from checkin_tracker.config import Settings
from checkin_tracker.parse import parse_booking, to_local
from checkin_tracker.tracker import load_snapshot, resend, run_once

NY = ZoneInfo('America/New_York')

BOOKING = {
    'id': 101,
    'service_date': '2024-08-25T18:00:00Z',
    'location': {'name': 'Ottawa'},
    'user': {'name': 'Test Customer', 'email': 'test@example.com', 'is_new_customer': False},
    'teams': [{'id': 7, 'title': 'Team Seven'}],
    'services': [{'name': 'Standard Clean', 'price': 118.25}],
    'summary': {'total': 133.62, 'tax': {'tax_percent': 13}},
    'duration': 195,
    'blocked_duration': 195,
    'time_tracking': [{
        'state': 'draft',
        'distance': 12.58,
        'enroute_started_at': '2024-08-25T17:28:00Z',
        'enroute_finished_at': None,
        'checkin_at': None,
        'checkout_at': None,
    }],
    'custom_fields': [
        {'title': 'Any Pets?          ', 'values': [{'label': 'Yes - Dog'}]},
        {'title': 'Extra Time.', 'values': [{'value': '30'}]},
        {'title': 'Notes', 'value': 'not a column'},
    ],
}


def test_to_local_handles_both_formats_and_missing():
    assert to_local('2024-09-05T13:14:42.23152Z', NY) == '2024-09-05 09:14 AM'
    assert to_local('2024-09-05T13:14:42Z', NY) == '2024-09-05 09:14 AM'
    assert to_local(None, NY) == 'N/A'
    assert to_local('garbage', NY) == 'N/A'


def test_parse_booking_matches_original_field_names():
    record = parse_booking(BOOKING, NY)
    assert record['ID'] == 101
    assert record['Date'] == '2024-08-25 02:00 PM'
    assert record['Team_id'] == '7'
    assert record['Price'] == 118.25
    assert record['Est Duration'] == 195
    assert record['Distance'] == '12.58 km'
    assert record['Enroute_Start'] == '2024-08-25 01:28 PM'
    assert record['Enroute_End'] is None
    assert record['Checked_In'] is None
    assert record['Any Pets?'] == 'Yes - Dog'
    assert record['Extra Time'] == '30'
    assert 'Notes' not in record
    assert record['Customer_Email'] == 'test@example.com'


def test_parse_booking_tolerates_null_nested_objects():
    booking = {**BOOKING, 'location': None, 'user': None, 'time_tracking': None, 'charges': None}
    record = parse_booking(booking, NY)
    assert record['Location'] is None
    assert record['Customer'] is None
    assert record['Checked_In'] is None


class FakeClient:
    def __init__(self, bookings):
        self.bookings = bookings

    def get_bookings(self, date):
        return copy.deepcopy(self.bookings)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        l27_base_url='https://example.invalid', l27_email='x', l27_password='y',
        kustomer_webhook_url='https://hook.invalid', timezone='America/New_York',
        state_dir=Path(tmp_path), active_hours=(7, 23), poll_seconds=60, dry_run=False,
    )


def checked_in(booking, when):
    updated = copy.deepcopy(booking)
    updated['time_tracking'][0]['checkin_at'] = when
    return updated


def test_first_run_only_saves_baseline(settings):
    sent = []
    assert run_once(settings, FakeClient([BOOKING]), lambda url, r: sent.append(r) or True) == []
    assert sent == []
    assert load_snapshot(settings.snapshot_file)['101']['Enroute_Start'] == '2024-08-25 01:28 PM'


def test_change_in_tracked_field_is_sent_once(settings):
    sent = []
    send = lambda url, r: sent.append(r) or True
    run_once(settings, FakeClient([BOOKING]), send)

    client = FakeClient([checked_in(BOOKING, '2024-08-25T17:55:00Z')])
    run_once(settings, client, send)
    assert len(sent) == 1
    assert sent[0]['event_type'] == 'Checked_In'
    assert sent[0]['Checked_In'] == '2024-08-25 01:55 PM'

    run_once(settings, client, send)
    assert len(sent) == 1


def test_untracked_change_and_new_booking_are_not_sent(settings):
    sent = []
    send = lambda url, r: sent.append(r) or True
    run_once(settings, FakeClient([BOOKING]), send)

    repriced = {**copy.deepcopy(BOOKING), 'summary': {'total': 999}}
    newcomer = {**checked_in(BOOKING, '2024-08-25T17:55:00Z'), 'id': 202}
    run_once(settings, FakeClient([repriced, newcomer]), send)
    assert sent == []
    assert '202' in load_snapshot(settings.snapshot_file)


def test_failed_send_is_retried_next_poll(settings):
    run_once(settings, FakeClient([BOOKING]), lambda url, r: True)
    client = FakeClient([checked_in(BOOKING, '2024-08-25T17:55:00Z')])

    run_once(settings, client, lambda url, r: False)
    sent = []
    run_once(settings, client, lambda url, r: sent.append(r) or True)
    assert [r['event_type'] for r in sent] == ['Checked_In']


def test_dry_run_does_not_send(settings):
    run_once(settings, FakeClient([BOOKING]), lambda url, r: True)

    def boom(url, record):
        raise AssertionError('should not send in dry run')

    changes = run_once(replace(settings, dry_run=True), FakeClient([checked_in(BOOKING, '2024-08-25T17:55:00Z')]), boom)
    assert len(changes) == 1


def test_resend_sends_one_booking_without_touching_snapshot(settings):
    sent = []
    send = lambda url, r: sent.append(r) or True
    assert resend(settings, '101', 'Checked_In', FakeClient([BOOKING]), send)
    assert [(r['ID'], r['event_type']) for r in sent] == [(101, 'Checked_In')]
    assert load_snapshot(settings.snapshot_file) is None
    assert not resend(settings, '999', 'Checked_In', FakeClient([BOOKING]), send)
