import copy
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import HTTPException
from core.database import db, now, uid
from modules.repository import load, save, emit
from modules.definitions import STAGES, SCHEMES
from modules.connectors import REGISTRY
from modules.policy import exchange_decision
from modules.events import publish_pending

TERMINAL={'COMPLETED','REJECTED','BLOCKED'}
async def prepare(app,index,event):
    if app['status'] in TERMINAL: return
    stage=app['stages'][index]
    if stage['state']!='PENDING': return
    if any(s['state']!='COMPLETED' for s in app['stages'][:index]): return
    version=app['version']
    if STAGES[index].get('review') and not (stage.get('review') or {}).get('decision'):
        if app.get('review_mode','manual')=='auto':
            stage['review']={'requested_at':now(),'mode':'auto','decision':'SANCTIONED','remarks':'Automatic sanction for a demonstration drill; no officer review.','officer_name':'Demonstration auto-sanction','designation':'Simulated department rule','decided_at':now()}
            emit(app,'REVIEW_DECIDED','service:demo-auto-sanction',stage['id'],{'result':'SANCTIONED','mode':'auto'},event['id'])
        else:
            stage['state']='AWAITING_REVIEW'; app['status']='UNDER_REVIEW'
            stage['review']={'requested_at':now(),'mode':'manual'}
            emit(app,'REVIEW_REQUESTED','workflow',stage['id'],{'result':'AWAITING_OFFICER','department':stage['system']},event['id'])
            await save(app,version); await publish_pending(app['id']); return
    stage['state']='READY'; app['status']='PROCESSING'
    emit(app,'STAGE_REQUESTED','workflow',stage['id'],{'operation_id':stage['operation_id']},event['id'])
    await save(app,version); await publish_pending(app['id'])

async def hold_for_documents(app,stage,event,missing,evidence=None):
    version=app['version']
    stage['state']='AWAITING_DOCUMENTS'; app['status']='AWAITING_DOCUMENTS'; stage['lease_until']=None; stage['error']=None
    if evidence is not None: stage['evidence']=evidence
    stage['hold']={'missing':missing,'requested_at':now()}
    emit(app,'DOCUMENTS_REQUIRED','workflow',stage['id'],{'result':'AWAITING_DOCUMENTS','missing':missing},event['id'])
    await save(app,version); await publish_pending(app['id'])

async def execute_stage(app,index,event):
    stage=app['stages'][index]; config=STAGES[index]; adapter=REGISTRY[config['connector']]
    if stage['state'] not in ('READY','RUNNING'): return True
    if stage['state']=='RUNNING' and stage.get('lease_until','')>now(): return False
    if any(s['state']!='COMPLETED' for s in app['stages'][:index]): return False
    if config.get('requires') and not app.get(config['requires']):
        await hold_for_documents(app,stage,event,list(SCHEMES[app['service_code']]['documents'])); return True
    if len(stage['attempts'])>=4:
        version=app['version'];stage['state']='HUMAN_INTERVENTION_REQUIRED';app['status']='HUMAN_INTERVENTION_REQUIRED'
        emit(app,'HUMAN_INTERVENTION_REQUIRED','recovery',stage['id'],{'result':'RETRY_LIMIT'})
        await save(app,version);await publish_pending(app['id']);return True
    decision=exchange_decision(app,adapter.department,config['fields'],config['purpose'])
    version=app['version'];stage['policy']=decision
    if decision['decision']=='DENY':
        stage['state']='BLOCKED'; app['status']='BLOCKED';stage['error']=decision['reason']
        emit(app,'POLICY_DENIED',decision['actor'],stage['id'],decision,event['id'])
        await save(app,version);await publish_pending(app['id']);return True
    attempt={'id':uid('ATT'),'number':len(stage['attempts'])+1,'started_at':now(),'outcome':'PROCESSING','operation_id':stage['operation_id']}
    stage['attempts'].append(attempt);stage['state']='RUNNING';stage['started_at']=stage.get('started_at') or now();stage['lease_until']=(datetime.now(timezone.utc)+timedelta(seconds=45)).isoformat()
    emit(app,'PAYMENT_INITIATED' if stage['id']=='treasury' else 'INTEGRATION_STARTED',f'connector:{config["connector"]}',stage['id'],{'attempt_id':attempt['id'],'operation_id':stage['operation_id'],'policy_decision':decision},event['id'])
    await save(app,version);await publish_pending(app['id'])
    start=datetime.now(timezone.utc)
    result=None; error=None; recovered=False
    try:
        if attempt['number']>1:
            result=await adapter.reconcile(app,stage);recovered=bool(result)
        if not result: result=await adapter.execute(app,stage)
    except httpx.TimeoutException: error=('TIMEOUT','Department response timed out. Outcome will be reconciled.',True)
    except httpx.HTTPStatusError as exc:
        error=('DOWNSTREAM_UNAVAILABLE' if exc.response.status_code>=500 else 'DOWNSTREAM_REJECTED',f'Department returned HTTP {exc.response.status_code}.',exc.response.status_code>=500 or exc.response.status_code==429)
    except httpx.RequestError: error=('CONNECTION_FAILED','Could not reach the department.',True)
    except (ValueError,KeyError,TypeError): error=('SCHEMA_ERROR','Department response failed the pinned schema contract.',False)
    # Reload after the HTTP boundary: consent/revocation/audit can change concurrently.
    for _ in range(8):
        current=await load(app['id']); v=current['version']; s=current['stages'][index]
        if s['state']=='COMPLETED': return True
        if not s['attempts'] or s['attempts'][-1]['id']!=attempt['id']: return False
        latest=s['attempts'][-1]; latest['completed_at']=now();latest['duration_ms']=round((datetime.now(timezone.utc)-start).total_seconds()*1000)
        s['lease_until']=None
        if error:
            code,message,retryable=error;latest.update(outcome=code,error=message);s['error']=message
            state=('RECONCILING' if s['id']=='treasury' and code=='TIMEOUT' else 'RETRY_SCHEDULED') if retryable and len(s['attempts'])<4 else 'HUMAN_INTERVENTION_REQUIRED'
            s['state']=state;current['status']=state;current['next_retry_at']=(datetime.now(timezone.utc)+timedelta(minutes=15*(2**(len(s['attempts'])-1)))).isoformat() if state!='HUMAN_INTERVENTION_REQUIRED' else None
            emit(current,'INTEGRATION_FAILED',f'connector:{config["connector"]}',s['id'],{'result':code,'attempt_id':latest['id'],'retryable':retryable},event['id'])
            emit(current,'HUMAN_INTERVENTION_REQUIRED' if state=='HUMAN_INTERVENTION_REQUIRED' else 'RETRY_SCHEDULED','recovery',s['id'],{'result':state,'next_retry_at':current['next_retry_at']})
        elif result.status=='DOCUMENTS_REQUIRED':
            missing=result.canonical['documents']['missing']
            latest.update(outcome='INCOMPLETE');s.update(state='AWAITING_DOCUMENTS',evidence=result.evidence,error=None);s['hold']={'missing':missing,'requested_at':now()};current['status']='AWAITING_DOCUMENTS'
            emit(current,'DOCUMENTS_REQUIRED','workflow',s['id'],{'result':'AWAITING_DOCUMENTS','missing':missing},event['id'])
        else:
            latest.update(outcome='RECONCILED' if recovered else 'SUCCESS');s.update(state='COMPLETED',completed_at=now(),external_id=result.external_id,evidence=result.evidence,error=None);s.pop('hold',None)
            current['canonical'].update(result.canonical);current['next_retry_at']=None
            mapping={'system':adapter.department,'entity_type':result.entity_type,'external_id':result.external_id,'internal_reference':current['person_reference'] if result.entity_type=='person' else current['transaction_id'],'operation_id':s['operation_id'],'stage_id':s['id']}
            if not any(m['external_id']==mapping['external_id'] for m in current['mappings']): current['mappings'].append(mapping)
            current['status']='REJECTED' if result.status in ('INELIGIBLE','DOCUMENT_MISMATCH') else 'COMPLETED' if index==len(STAGES)-1 else 'PROCESSING'
            if result.status=='DOCUMENT_MISMATCH': s['error']='A shared document failed issuer-signature or holder verification.'
            emit(current,config['event'],f'connector:{config["connector"]}',s['id'],{'result':result.status,'external_id':result.external_id,'mapping_version':result.evidence['mapping_version'],'reconciled':recovered,'policy_decision_id':s['policy']['id']},event['id'])
            if current['status']=='COMPLETED': emit(current,'APPLICATION_COMPLETED','workflow',payload={'result':'COMPLETED'})
        try:
            await save(current,v);await publish_pending(current['id']);return True
        except HTTPException as exc:
            if exc.status_code!=409: raise
    return False

async def handle(event):
    if event.get('type')=='MAINTENANCE_REQUESTED':
        from modules.recovery import maintenance
        await maintenance();return True
    app=await load(event['application_id'])
    if event['type']=='APPLICATION_CREATED': await prepare(app,0,event)
    elif event['type']=='STAGE_REQUESTED':
        index=next((i for i,s in enumerate(STAGES) if s['id']==event.get('stage_id')),None)
        if index is None: raise ValueError('Invalid stage contract')
        return await execute_stage(app,index,event)
    else:
        index=next((i for i,s in enumerate(STAGES) if s['event']==event['type']),None)
        if index is not None and index+1<len(STAGES) and app['stages'][index]['state']=='COMPLETED': await prepare(app,index+1,event)
    return True