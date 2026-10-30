"""Entry point.

    python -m checkin_tracker          # one poll (for cron)
    python -m checkin_tracker --loop   # poll every POLL_SECONDS during ACTIVE_HOURS (for a worker/service)
    python -m checkin_tracker --resend 129026 --event Checked_In   # manually send one of today's bookings
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from checkin_tracker.config import load_settings
from checkin_tracker.tracker import resend, run_once

log = logging.getLogger('checkin_tracker')


def in_active_hours(settings):
    start, end = settings.active_hours
    return start <= datetime.now(ZoneInfo(settings.timezone)).hour <= end


def main(argv=None):
    parser = argparse.ArgumentParser(prog='checkin_tracker')
    parser.add_argument('--loop', action='store_true', help='keep polling instead of running once')
    parser.add_argument('--resend', metavar='BOOKING_ID', help="send one of today's bookings to Kustomer now")
    parser.add_argument('--event', default='Checked_In', help='event_type for --resend (default: Checked_In)')
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout,
    )
    settings = load_settings()

    if args.resend:
        return 0 if resend(settings, args.resend, args.event) else 1

    if not args.loop:
        try:
            run_once(settings)
        except Exception:
            log.exception('Poll failed')
            return 1
        return 0

    log.info('Polling every %ss between %s:00 and %s:59 %s',
             settings.poll_seconds, *settings.active_hours, settings.timezone)
    while True:
        started = time.monotonic()
        if in_active_hours(settings):
            try:
                run_once(settings)
            except Exception:
                log.exception('Poll failed')
        time.sleep(max(0, settings.poll_seconds - (time.monotonic() - started)))


if __name__ == '__main__':
    sys.exit(main())
