"""Idempotent demo bootstrap; preserves protected settings and never prints secrets."""
from pathlib import Path
import os
import secrets
from dotenv import dotenv_values, set_key, unset_key
root = Path(__file__).parent
local = root / '.env.local'
shared = root / '.env'
values = dotenv_values(local)
# Runtime addresses are supplied by the environment on first setup, never
# guessed in application code or written over protected .env configuration.
protected = dotenv_values(shared)
# The platform cron dispatcher reads the schedule credential from .env only,
# so that single secret lives there; every other secret stays in .env.local.
if not protected.get('WEBHOOK_CRON_SECRET'):
    set_key(str(shared), 'WEBHOOK_CRON_SECRET', values.get('WEBHOOK_CRON_SECRET') or secrets.token_urlsafe(48))
if values.get('WEBHOOK_CRON_SECRET'):
    unset_key(str(local), 'WEBHOOK_CRON_SECRET')
defaults = {
    'DEMO_MODE': 'true',
    'STREAM_NAME': 'samanvay:events',
    'STREAM_GROUP': 'samanvay-workflows',
    'CONNECTOR_TIMEOUT': '3',
    'SESSION_HOURS': '12',
}
for key in ('REDIS_URL', 'MOCK_BASE_URL'):
    if not values.get(key) and not protected.get(key) and not os.environ.get(key):
        raise SystemExit(f'Supply {key} in the environment for first-time setup.')
for key in (*defaults, 'REDIS_URL', 'MOCK_BASE_URL'):
    if not values.get(key) and not protected.get(key):
        set_key(str(local), key, os.environ.get(key) or defaults.get(key))
for key in ('JWT_SECRET', 'REGISTRY_KEY', 'ELIGIBILITY_SECRET', 'TREASURY_SECRET'):
    if not values.get(key):
        set_key(str(local), key, secrets.token_urlsafe(48))
set_key(str(local), 'APP_ORIGIN', dotenv_values(root.parent / 'frontend/.env')['REACT_APP_BACKEND_URL'])
if not values.get('DEMO_PASSWORD'):
    set_key(str(local), 'DEMO_PASSWORD', 'Demo@2026!')
local.chmod(0o600)
print('Local configuration initialized; secrets not printed.')