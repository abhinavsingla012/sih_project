from datetime import datetime, timezone
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from core.config import setting
client = AsyncIOMotorClient(setting('MONGO_URL'))
db = client[setting('DB_NAME')]
bus = redis.from_url(setting('REDIS_URL'), decode_responses=True, socket_connect_timeout=2, socket_timeout=5)
def now():
    return datetime.now(timezone.utc).isoformat()
def uid(prefix):
    return f'{prefix}-{uuid4().hex[:12].upper()}'
async def indexes():
    await db.users.create_index('id', unique=True)
    await db.users.create_index('email', unique=True)
    await db.sessions.create_index('id', unique=True)
    await db.applications.create_index('id', unique=True)
    await db.applications.create_index('transaction_id', unique=True)
    await db.applications.create_index([('owner_id', 1), ('idempotency_key', 1)], unique=True)
    await db.applications.create_index([('owner_id', 1), ('created_at', -1)])
    await db.applications.create_index([('status', 1), ('next_retry_at', 1)])
    for collection in ('mock_registry', 'mock_eligibility', 'mock_payments'):
        await db[collection].create_index('operation_id', unique=True)
    await db.mock_people.create_index('subject', unique=True)
    await db.identifier_mappings.create_index([('system', 1), ('entity_type', 1), ('external_id', 1)], unique=True)
    await db.maintenance_receipts.create_index('id', unique=True)