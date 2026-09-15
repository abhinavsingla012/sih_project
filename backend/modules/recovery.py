from core.database import db,now
from core.errors import fail
from modules.repository import load,save,emit
from modules.events import publish_pending

async def retry(app,version,reason,actor,idempotency_key=None):
    if app['version']!=version: fail(409,'VERSION_CONFLICT','The transaction changed. Refresh and try again.')
    s=next((s for s in app['stages'] if s['state'] in ('RECONCILING','RETRY_SCHEDULED','HUMAN_INTERVENTION_REQUIRED')),None)
    if not s: fail(409,'NOT_RETRYABLE','There is no recoverable stage in this application.')
    if len(s['attempts'])>=4: fail(409,'RETRY_LIMIT','Retry budget exhausted. This case requires investigation; completion cannot be forced.')
    s['state']='READY';app['status']='RETRYING';app['next_retry_at']=None
    e=emit(app,'RETRY_STARTED',actor,s['id'],{'reason':reason,'operation_id':s['operation_id'],'idempotency_key':idempotency_key})
    emit(app,'STAGE_REQUESTED','recovery',s['id'],{'operation_id':s['operation_id']},e['id'])
    await save(app,version);await publish_pending(app['id']);return app

async def maintenance():
    await publish_pending()
    async for app in db.applications.find({'next_retry_at':{'$ne':None,'$lte':now()},'status':{'$in':['RECONCILING','RETRY_SCHEDULED']}},{'_id':0}).limit(100):
        try: await retry(app,app['version'],'Scheduled recovery dispatch','service:recovery')
        except Exception: continue