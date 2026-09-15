"""Approved separate Redis consumer. Not an in-web-process workflow timer."""
import asyncio,json,logging,os
from fastapi import HTTPException
from redis.exceptions import RedisError
from core.database import bus,db,now
from modules.events import STREAM,GROUP,ensure_group,publish_pending
from modules.workflow import handle
CONSUMER=f'workflow-{os.getpid()}'

async def process(message_id,fields):
    try:
        event=json.loads(fields['event'])
        if await handle(event):
            await bus.xack(STREAM,GROUP,message_id)
            await db.worker_health.update_one({'id':'event-consumer'},{'$set':{'last_event_at':now(),'consumer':CONSUMER}},upsert=True)
    except HTTPException as e:
        if e.status_code==409: return
        logging.warning('Event handling requires recovery: HTTP %s',e.status_code)
    except (ValueError,KeyError,TypeError):
        await bus.xadd(STREAM+'.dead-letter',{'original_stream_id':message_id,'reason':'INVALID_EVENT_CONTRACT','recorded_at':now()})
        await bus.xack(STREAM,GROUP,message_id)
    except Exception:
        logging.exception('Consumer failure; event retained in pending entries')

async def main():
    await ensure_group();await publish_pending()
    while True:
        try:
            await bus.set('samanvay:consumer:heartbeat',now(),ex=20)
            claimed=await bus.xautoclaim(STREAM,GROUP,CONSUMER,min_idle_time=60000,start_id='0-0',count=20)
            for mid,fields in claimed[1]: await process(mid,fields)
            rows=await bus.xreadgroup(GROUP,CONSUMER,{STREAM:'>'},count=10,block=3000)
            for _,messages in rows:
                for mid,fields in messages: await process(mid,fields)
        except RedisError:
            logging.warning('Redis unavailable; consumer reconnecting')
            await asyncio.sleep(2)
            try: await ensure_group();await publish_pending()
            except RedisError: pass

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())