"""Flatten a Launch27 booking into the record sent to Kustomer.

Field names match what the original script sent (after its cleaning step removed
periods from column names), so the Kustomer form hook mapping keeps working.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

TRACKED_FIELDS = ('Enroute_Start', 'Enroute_End', 'Checked_In', 'Checked_Out')

NA = 'N/A'


def to_local(utc_str, tz):
    """'2024-09-05T13:14:42.23152Z' -> '2024-09-05 09:14 AM' in `tz`; 'N/A' if missing/unparseable."""
    if not utc_str or utc_str == NA:
        return NA
    for fmt in ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ'):
        try:
            parsed = datetime.strptime(utc_str, fmt).replace(tzinfo=timezone.utc)
            return parsed.astimezone(tz).strftime('%Y-%m-%d %I:%M %p')
        except ValueError:
            continue
    log.warning('Could not parse UTC time: %s', utc_str)
    return NA


def _obj(value):
    return value if isinstance(value, dict) else {}


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return None if value == NA else value
    return value


def parse_booking(booking, tz):
    user = _obj(booking.get('user'))
    summary = _obj(booking.get('summary'))
    tax = _obj(summary.get('tax'))
    actions = _obj(booking.get('actions'))
    payment = _obj(booking.get('payment_method_info'))
    teams = booking.get('teams') or []
    services = booking.get('services') or []
    first_service = _obj(services[0]) if services else {}
    tracking = [_obj(t) for t in (booking.get('time_tracking') or [{}])]
    charged = _obj(booking.get('charges')).get('charged') or [{}]
    first_charge = _obj(charged[0])
    distance = tracking[0].get('distance')

    record = {
        'ID': booking.get('id', NA),
        'Date': to_local(booking.get('service_date'), tz),
        'Location': _obj(booking.get('location')).get('name', NA),
        'Customer': user.get('name', NA),
        'Customer_Email': user.get('email', NA),
        'is_new_customer': user.get('is_new_customer', NA),
        'referral_code': user.get('referral_code', NA),
        'is_stripe_card': user.get('is_stripe_card', NA),
        'Arrival_Window': booking.get('arrival_window', NA),
        'Full_Address': _obj(booking.get('address')).get('full_address', NA),
        'Phone_Number': booking.get('phone', NA),
        'Frequency': _obj(booking.get('frequency')).get('name', NA),
        'Payment_Code': payment.get('code', NA),
        'Payment_Text': payment.get('text', NA),
        'Team_id': ', '.join(str(_obj(t).get('id', NA)) for t in teams),
        'Team_Name': ', '.join(_obj(t).get('title') or NA for t in teams),
        'Duration': booking.get('duration', NA),
        'Booking': first_service.get('name', NA),
        'Price': first_service.get('price', NA),
        'Created_at': to_local(booking.get('created_at'), tz),
        'Created_by': _obj(booking.get('created_by')).get('name', NA),
        'Revenue': summary.get('revenue', NA),
        'Discount': summary.get('discount', NA),
        'Tax_Before_Tax': tax.get('before_tax', NA),
        'Tax_Percent': tax.get('tax_percent', NA),
        'Tax_Amount': tax.get('tax_amount', NA),
        'Tax_After_Tax': tax.get('after_tax', NA),
        'Tip': summary.get('tip', NA),
        'Total': summary.get('total', NA),
        'Action_Edit': actions.get('edit', NA),
        'Action_Cancel': actions.get('cancel', NA),
        'Action_Late_Cancel': actions.get('late_cancel', NA),
        'Action_Recurring_Cancel': actions.get('recurring_cancel', NA),
        'Action_Edit_Tip': actions.get('edit_tip', NA),
        'Action_Complete': actions.get('complete', NA),
        'Est Duration': booking.get('blocked_duration', NA),
        'Distance': f'{distance} km' if distance is not None else NA,
        'Enroute_Start': to_local(tracking[0].get('enroute_started_at'), tz),
        'Enroute_End': to_local(tracking[0].get('enroute_finished_at'), tz),
        'Checked_In': ', '.join(to_local(t.get('checkin_at'), tz) for t in tracking),
        'Checked_Out': ', '.join(to_local(t.get('checkout_at'), tz) for t in tracking),
        'Time_Reported': ', '.join(to_local(t.get('enroute_finished_at'), tz) for t in tracking),
        'Status': ', '.join(str(t.get('state') or NA) for t in tracking),
        'Description': first_charge.get('description', NA),
        'Charge_Status': first_charge.get('status', NA),
        'Charged_Date': first_charge.get('charged_date', NA),
    }

    # Custom fields become columns named after their (period-free) title, e.g. 'Any Pets?'.
    for field in booking.get('custom_fields') or []:
        values = _obj(field).get('values')
        if values:
            title = (field.get('title') or '').strip().replace('.', '')
            first = _obj(values[0])
            record[title] = first.get('label', first.get('value', NA))

    return {key: _clean(value) for key, value in record.items()}


def parse_bookings(bookings, tz_name):
    tz = ZoneInfo(tz_name)
    records = []
    for booking in bookings:
        try:
            records.append(parse_booking(booking, tz))
        except Exception:
            log.exception('Skipping booking %s: could not parse it', _obj(booking).get('id'))
    return records
