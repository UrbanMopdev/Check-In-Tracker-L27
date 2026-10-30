from checkin_tracker.launch27 import PAGE_SIZE, Launch27Client


class Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        self.text = str(body)

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, pages, valid_token='fresh'):
        self.pages = pages
        self.valid_token = valid_token
        self.logins = 0
        self.offsets = []

    def post(self, url, json, timeout):
        self.logins += 1
        return Response(200, {'bearer': self.valid_token})

    def get(self, url, headers, params, timeout):
        if headers['Authorization'] != f'Bearer {self.valid_token}':
            return Response(401, {'error': 'unauthorized'})
        self.offsets.append(params['offset'])
        return Response(200, self.pages[params['offset'] // PAGE_SIZE])


def make_client(tmp_path, session, cached_token=None):
    token_file = tmp_path / 'bearer_token.txt'
    if cached_token:
        token_file.write_text(cached_token)
    client = Launch27Client('https://example.invalid', 'e', 'p', token_file)
    client.session = session
    return client, token_file


def test_paginates_until_short_page(tmp_path):
    session = FakeSession([[{'id': i} for i in range(PAGE_SIZE)], [{'id': 'last'}]])
    client, _ = make_client(tmp_path, session, cached_token='fresh')
    assert len(client.get_bookings('2024-08-25')) == PAGE_SIZE + 1
    assert session.offsets == [0, PAGE_SIZE]
    assert session.logins == 0


def test_expired_token_triggers_one_relogin_and_is_cached(tmp_path):
    session = FakeSession([[{'id': 1}]])
    client, token_file = make_client(tmp_path, session, cached_token='stale')
    assert client.get_bookings('2024-08-25') == [{'id': 1}]
    assert session.logins == 1
    assert token_file.read_text() == 'fresh'
