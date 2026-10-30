"""Launch27 API client: login, cached bearer token, paginated bookings fetch."""
import logging

import requests

log = logging.getLogger(__name__)

PAGE_SIZE = 100
TIMEOUT = 30


class Launch27Error(Exception):
    pass


class Launch27Client:
    def __init__(self, base_url, email, password, token_file):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.token_file = token_file
        self.session = requests.Session()

    def _read_token(self):
        try:
            return self.token_file.read_text().strip() or None
        except FileNotFoundError:
            return None

    def login(self):
        log.info('Logging in to Launch27 for a new bearer token')
        response = self.session.post(
            f'{self.base_url}/latest/login',
            json={'email': self.email, 'password': self.password},
            timeout=TIMEOUT,
        )
        if response.status_code >= 400:
            raise Launch27Error(f'Login failed: {response.status_code} {response.text[:300]}')
        token = response.json().get('bearer')
        if not token:
            raise Launch27Error('Login failed: no bearer token in response')
        self.token_file.write_text(token)
        return token

    def _get_page(self, token, date, offset):
        return self.session.get(
            f'{self.base_url}/v1/staff/bookings',
            headers={'Authorization': f'Bearer {token}'},
            params={'from': date, 'to': date, 'limit': PAGE_SIZE, 'offset': offset},
            timeout=TIMEOUT,
        )

    def get_bookings(self, date):
        """Return every booking for `date` (YYYY-MM-DD). Re-logs in once if the cached token is rejected."""
        token = self._read_token() or self.login()
        bookings = []
        offset = 0
        retried = False
        while True:
            response = self._get_page(token, date, offset)
            if response.status_code in (401, 403) and not retried:
                retried = True
                token = self.login()
                continue
            if response.status_code != 200:
                raise Launch27Error(f'Bookings fetch failed: {response.status_code} {response.text[:300]}')

            page = response.json()
            if not isinstance(page, list):
                raise Launch27Error(f'Unexpected bookings response: {str(page)[:300]}')
            bookings.extend(page)
            if len(page) < PAGE_SIZE:
                return bookings
            offset += PAGE_SIZE
