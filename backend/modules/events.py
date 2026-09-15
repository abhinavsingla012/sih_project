import json, logging
from redis.exceptions import ResponseError, RedisError
from core.config import setting
from core.database import db, bus

STREAM=setting('STREAM_NAME'); GROUP=setting('STREAM_GROUP')
async def ensure_group():
    try: await bus.xgroup_create(STREAM,GROUP,id='0-0',mkstream=True)
    except ResponseError as e:
        if 'BUSYGROUP' not in str(e): raise

async def publish_pending(application_id=None):
    query={'events':{'$elemMatch':{'published':False}}}
    if application_id: query['id']=application_id
    async for app in db.applications.find(query,{'_id':0,'id':1,'events':1}).limit(200):
        for event in app['events']:
            if event['published']: continue
            try:
                stream_id=await bus.xadd(STREAM,{'event':json.dumps(event)})
                await db.applications.update_one({'id':app['id'],'events.id':event['id']},{'$set':{'events.$.published':True,'events.$.stream_id':stream_id}})
            except RedisError:
                logging.warning('Event transport unavailable; durable outbox retained')
                return False
    return True