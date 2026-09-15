"""Idempotent demo bootstrap; preserves protected settings and never prints secrets."""
from pathlib import Path
import secrets
from dotenv import dotenv_values, set_key
root = Path(__file__).parent
local = root / '.env.local'
values = dotenv_values(local)
for key in ('JWT_SECRET', 'REGISTRY_KEY', 'ELIGIBILITY_SECRET', 'TREASURY_SECRET', 'WEBHOOK_CRON_SECRET'):
    if not values.get(key):
        set_key(str(local), key, secrets.token_urlsafe(48))
set_key(str(local), 'APP_ORIGIN', dotenv_values(root.parent / 'frontend/.env')['REACT_APP_BACKEND_URL'])
if not values.get('DEMO_PASSWORD'):
    set_key(str(local), 'DEMO_PASSWORD', 'Demo@2026!')
local.chmod(0o600)
print('Local configuration initialized; secrets not printed.')