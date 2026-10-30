"""Settings, read from environment variables (optionally via a .env file)."""
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Minimal .env loader so cron/systemd don't need extra tooling. Real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _active_hours(raw):
    start, end = (int(part) for part in raw.split('-'))
    return start, end


@dataclass(frozen=True)
class Settings:
    l27_base_url: str
    l27_email: str
    l27_password: str
    kustomer_webhook_url: str
    timezone: str
    state_dir: Path
    active_hours: tuple
    poll_seconds: int
    dry_run: bool
    kustomer_late_webhook_url: str = ''
    late_dry_run: bool = True

    @property
    def token_file(self):
        return self.state_dir / 'bearer_token.txt'

    @property
    def snapshot_file(self):
        return self.state_dir / 'last_snapshot.json'

    @property
    def late_sent_file(self):
        return self.state_dir / 'late_warnings_sent.json'


def load_settings():
    _load_dotenv(PROJECT_DIR / '.env')

    missing = [name for name in ('L27_EMAIL', 'L27_PASSWORD', 'KUSTOMER_WEBHOOK_URL') if not os.environ.get(name)]
    dry_run = os.environ.get('DRY_RUN', '').lower() in ('1', 'true', 'yes')
    if dry_run and 'KUSTOMER_WEBHOOK_URL' in missing:
        missing.remove('KUSTOMER_WEBHOOK_URL')
    if missing:
        raise SystemExit(f"Missing required settings: {', '.join(missing)} (see .env.example)")

    state_dir = Path(os.environ.get('STATE_DIR', PROJECT_DIR / 'state'))
    state_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        l27_base_url=os.environ.get('L27_BASE_URL', 'https://urbanmop.launch27.com').rstrip('/'),
        l27_email=os.environ['L27_EMAIL'],
        l27_password=os.environ['L27_PASSWORD'],
        kustomer_webhook_url=os.environ.get('KUSTOMER_WEBHOOK_URL', ''),
        timezone=os.environ.get('TIMEZONE', 'America/New_York'),
        state_dir=state_dir,
        active_hours=_active_hours(os.environ.get('ACTIVE_HOURS', '7-23')),
        poll_seconds=int(os.environ.get('POLL_SECONDS', '60')),
        dry_run=dry_run,
        kustomer_late_webhook_url=os.environ.get('KUSTOMER_LATE_WEBHOOK_URL', ''),
        late_dry_run=os.environ.get('LATE_WARNINGS_DRY_RUN', 'true').lower() in ('1', 'true', 'yes'),
    )
