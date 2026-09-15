import os
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / '.env.local', override=True)
def setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f'Missing required configuration: {name}')
    return value
DEMO = setting('DEMO_MODE') == 'true'


def trusted_origins() -> tuple[str, ...]:
    """Exact configured browser/proxy origins, never inferred from a request."""
    origins = [setting('APP_ORIGIN'), *os.environ.get('TRUSTED_ORIGINS', '').split(',')]
    allowed = []
    for value in origins:
        origin = value.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or '*' in origin):
            raise RuntimeError('Trusted origins must be explicit HTTP(S) origins without paths or wildcards.')
        # Validate malformed ports at startup rather than silently trusting them.
        _ = parsed.port
        if origin not in allowed:
            allowed.append(origin)
    return tuple(allowed)


TRUSTED_ORIGINS = trusted_origins()
