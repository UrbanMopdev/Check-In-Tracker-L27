"""Send changed booking records to the Kustomer form hook."""
import logging

import requests

log = logging.getLogger(__name__)

TIMEOUT = 30


def send_record(url, record):
    """POST one record. Returns True on a 2xx response."""
    try:
        response = requests.post(url, json=record, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.error('Kustomer send failed for booking %s: %s', record.get('ID'), exc)
        return False
    if 200 <= response.status_code < 300:
        log.info('Sent booking %s to Kustomer (%s): %s', record.get('ID'), response.status_code,
                 record.get('event_type') or record.get('Warning Type'))
        return True
    log.error('Kustomer rejected booking %s: %s %s', record.get('ID'), response.status_code, response.text[:300])
    return False
