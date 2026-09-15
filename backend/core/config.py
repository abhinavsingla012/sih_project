import os
from pathlib import Path
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