import copy,json,hashlib,hmac
from datetime import datetime,timezone
import httpx
from fastapi import APIRouter, Depends, Header, Query, Request, Response, HTTPException
from pydantic import BaseModel,Field
from pymongo.errors import DuplicateKeyError
from core.config import setting,DEMO
from core.database import db,bus,now,uid
from core.errors import fail
from modules.auth import principal,Principal
from modules.models import CreateApplication,DemoJourney,ApplicationView,ApplicationList,RetryRequest,RevokeRequest,ScenarioRequest,DataAccessRequest,ReviewDecision
from modules.repository import load,save,create,project,emit
from modules.policy import authorize,visibility,exchange_decision,FIELD_RULES
from modules.events import publish_pending,STREAM,GROUP
from modules.definitions import CONNECTORS,MAPPINGS,STAGES
from modules.recovery import retry
from modules.connectors import eligibility_token,REGISTRY
from mock_departments.router import service_principal

router=APIRouter(prefix='/api',tags=['Interoperability'])
class Payload(BaseModel):
    data: dict

def idempotency(key):
    if not key or not 8<=len(key)<=120: fail(422,'IDEMPOTENCY_REQUIRED','Provide an Idempotency-Key between 8 and 120 characters.')
    return key

@router.get('/services')
async def services(user:Principal=Depends(principal)):
    return {'items':[{'code':'MH_SKILL_BENEFIT','version':'1','name':'Skill development benefit','amount':15000,'currency':'INR','description':'Hypothetical training benefit for eligible citizens aged 18–35.','courses':['DATA_ANALYTICS','ELECTRIC_VEHICLES','WEB_DEVELOPMENT'],'districts':['Pune','Mumbai','Nagpur','Nashik','Thane'],'is_demo':True}]}

@router.post('/applications',response_model=ApplicationView,status_code=201)
async def new_application(body:CreateApplication,user:Principal=Depends(principal),key:str=Header('',alias='Idempotency-Key')):
    authorize(user,'create')
    stored=await db.users.find_one({'id':user.id},{'_id':0})
    app=await create(stored,body,idempotency(key))
    await publish_pending(app['id'])
    return project(await load(app['id'],user),user)

@router.get('/applications',response_model=ApplicationList)
async def applications(user:Principal=Depends(principal),status:str|None=None,search:str=Query('',max_length=100),cursor:str|None=None,limit:int=Query(20,ge=1,le=100),attention:bool=False):
    authorize(user,'read');q=visibility(user)
    if status:q={'$and':[q,{'status':status}]}
    if attention:q={'$and':[q,{'status':{'$in':['RECONCILING','RETRY_SCHEDULED','HUMAN_INTERVENTION_REQUIRED','BLOCKED']}}]}
    if search:
        import re
        q={'$and':[q,{'$or':[{field:{'$regex':re.escape(search),'$options':'i'}} for field in ('id','transaction_id','owner_name')]}]}
    total=await db.applications.count_documents(q)
    if cursor:q={'$and':[q,{'created_at':{'$lt':cursor}}]}
    docs=await db.applications.find(q,{'_id':0}).sort('created_at',-1).limit(limit+1).to_list(limit+1)
    return ApplicationList(items=[project(d,user,False) for d in docs[:limit]],total=total,next_cursor=docs[limit-1]['created_at'] if len(docs)>limit else None)

@router.get('/applications/{key}',response_model=ApplicationView)
async def application(key:str,user:Principal=Depends(principal)):
    authorize(user,'read');return project(await load(key,user),user)

@router.get('/transactions/{key}',response_model=ApplicationView)
async def transaction(key:str,user:Principal=Depends(principal)):
    authorize(user,'inspect');return project(await load(key,user),user)

@router.post('/transactions/{key}/stages/{stage_id}/retry',response_model=ApplicationView,status_code=202)
async def retry_stage(key:str,stage_id:str,body:RetryRequest,user:Principal=Depends(principal),idem:str=Header('',alias='Idempotency-Key')):
    authorize(user,'operate');idempotency(idem);app=await load(key,user)
    # Retry requests are serialized by the transaction revision and stage state.
    stage=next((s for s in app['stages'] if s['id']==stage_id),None)
    if not stage:fail(404,'NOT_FOUND','Stage not found.')
    if any(e['type']=='RETRY_STARTED' and e['payload'].get('idempotency_key')==idem for e in app['events']):return project(app,user)
    if stage['state'] not in ('RECONCILING','RETRY_SCHEDULED','HUMAN_INTERVENTION_REQUIRED'):fail(409,'NOT_RETRYABLE','This stage is not waiting for recovery.')
    app=await retry(app,body.version,body.reason,user.id,idem)
    return project(app,user)

@router.get('/reviews',response_model=ApplicationList)
async def reviews(user:Principal=Depends(principal),state:str=Query('pending',pattern='^(pending|decided)$'),limit:int=Query(50,ge=1,le=100)):
    authorize(user,'inspect')
    match={'id':'approval','state':'AWAITING_REVIEW'} if state=='pending' else {'id':'approval','review.decided_at':{'$exists':True},'review.mode':'manual'}
    q={'$and':[visibility(user),{'stages':{'$elemMatch':match}}]}
    sort_key='stages.2.review.requested_at' if state=='pending' else 'updated_at'
    docs=await db.applications.find(q,{'_id':0}).sort(sort_key,1 if state=='pending' else -1).limit(limit).to_list(limit)
    return ApplicationList(items=[project(d,user,False) for d in docs],total=await db.applications.count_documents(q))

@router.post('/reviews/{key}/decision',response_model=ApplicationView)
async def decide_review(key:str,body:ReviewDecision,user:Principal=Depends(principal)):
    authorize(user,'review');app=await load(key,user)
    stage=next(s for s in app['stages'] if s['id']=='approval')
    if user.department!=REGISTRY['approval'].department:fail(403,'FORBIDDEN','Only the approving department can decide this case.')
    if stage['state']!='AWAITING_REVIEW':fail(409,'NOT_REVIEWABLE','This application is not awaiting a department decision.')
    if app['version']!=body.version:fail(409,'VERSION_CONFLICT','The case changed. Refresh and try again.')
    v=app['version'];outcome='SANCTIONED' if body.decision=='SANCTION' else 'REJECTED'
    stage['review'].update(decision=outcome,remarks=body.remarks.strip(),officer_id=user.id,officer_name=user.name,designation=user.designation,decided_at=now())
    decided=emit(app,'REVIEW_DECIDED',user.id,stage['id'],{'result':outcome,'remarks':stage['review']['remarks'],'officer':user.name})
    if outcome=='SANCTIONED':
        stage['state']='READY';app['status']='PROCESSING'
        emit(app,'STAGE_REQUESTED','review',stage['id'],{'operation_id':stage['operation_id']},decided['id'])
    else:
        stage['state']='REJECTED';stage['error']=f'Rejected by the department: {stage["review"]["remarks"]}';app['status']='REJECTED'
        emit(app,'APPLICATION_REJECTED',user.id,stage['id'],{'result':'REJECTED','remarks':stage['review']['remarks']},decided['id'])
    await save(app,v);await publish_pending(app['id']);return project(app,user)

@router.post('/applications/{key}/consents/{consent_id}/revoke',response_model=ApplicationView)
async def revoke(key:str,consent_id:str,body:RevokeRequest,user:Principal=Depends(principal)):
    app=await load(key,user);authorize(user,'revoke',app);v=app['version']
    consent=next((c for c in app['consents'] if c['id']==consent_id),None)
    if not consent:fail(404,'NOT_FOUND','Consent not found.')
    if consent['state']=='REVOKED':return project(app,user)
    consent.update(state='REVOKED',revoked_at=now())
    emit(app,'CONSENT_REVOKED',user.id,payload={'consent_id':consent_id,'reason':body.reason,'result':'REVOKED'})
    await save(app,v);await publish_pending(app['id']);return project(app,user)

@router.post('/demo/journeys',response_model=ApplicationView,status_code=201)
async def demo_journey(body:DemoJourney,user:Principal=Depends(principal),key:str=Header('',alias='Idempotency-Key')):
    authorize(user,'operate')
    if not DEMO:fail(404,'NOT_FOUND','Demo controls are disabled.')
    citizen=await db.users.find_one({'id':'USR-CITIZEN'},{'_id':0})
    app=await create(citizen,CreateApplication(course_code=body.course_code,district='Pune',eligibility_consent=True,payment_consent=True),idempotency(key),body.scenario,f'demo-operator:{user.id}',body.review)
    await db.demo_scenarios.update_one({'transaction_id':app['transaction_id']},{'$setOnInsert':{'transaction_id':app['transaction_id'],'scenario':body.scenario}},upsert=True)
    await publish_pending(app['id']);return project(app,user)

@router.post('/demo/transactions/{key}/scenario',response_model=ApplicationView)
async def scenario(key:str,body:ScenarioRequest,user:Principal=Depends(principal)):
    authorize(user,'operate');app=await load(key,user)
    if not DEMO or not app['is_demo']:fail(403,'DEMO_ONLY','Scenario controls are limited to synthetic transactions.')
    if any(s['state']=='RUNNING' for s in app['stages']):fail(409,'IN_FLIGHT','Wait for the current attempt to finish before changing its scenario.')
    if app['status']=='COMPLETED':fail(409,'TERMINAL','A completed transaction cannot change scenario.')
    v=app['version'];app['scenario']=body.scenario
    emit(app,'DEMO_SCENARIO_CHANGED',user.id,payload={'scenario':body.scenario,'result':'UPDATED'})
    await save(app,v)
    await db.demo_scenarios.update_one({'transaction_id':app['transaction_id']},{'$set':{'scenario':body.scenario}},upsert=True)
    await publish_pending(app['id']);return project(app,user)

@router.post('/transactions/{key}/data-access')
async def data_access(key:str,body:DataAccessRequest,user:Principal=Depends(service_principal)):
    authorize(user,'data_access');app=await load(key,user)
    decision=exchange_decision(app,user.department,body.fields,body.purpose)
    for _ in range(8):
        app=await load(key,user);decision=exchange_decision(app,user.department,body.fields,body.purpose);v=app['version']
        emit(app,'POLICY_ALLOWED' if decision['decision']=='ALLOW' else 'POLICY_DENIED',decision['actor'],'eligibility',decision)
        try:await save(app,v);break
        except HTTPException as e:
            if e.status_code!=409:raise
    else:fail(503,'AUDIT_UNAVAILABLE','The decision could not be durably recorded; access denied.')
    await publish_pending(app['id'])
    if decision['decision']=='DENY':fail(403,'POLICY_DENIED',decision['reason'],decision=decision)
    values={'eligibility.status':app['canonical'].get('eligibility',{}).get('status'),'person.globalReference':app['person_reference'],'identity.verificationStatus':app['canonical'].get('identity',{}).get('verificationStatus'),'course.code':app['course_code']}
    # DOB is not retained by the fabric; retrieve only after successful authorization.
    if 'person.dateOfBirth' in body.fields:
        from modules.connectors import registry_source
        values['person.dateOfBirth']=(await registry_source(app)).dob
    return {'data':{f:values.get(f) for f in body.fields},'decision':decision}

@router.post('/demo/transactions/{key}/policy-probe')
async def probe(key:str,user:Principal=Depends(principal)):
    authorize(user,'operate');app=await load(key,user)
    if not DEMO:fail(404,'NOT_FOUND','Demo controls are disabled.')
    async with httpx.AsyncClient(base_url=setting('MOCK_BASE_URL'),timeout=10) as client:
        r=await client.post(f'/api/transactions/{app["transaction_id"]}/data-access',headers={'Authorization':f'Bearer {await eligibility_token()}'},json={'fields':['citizen.bankAccount'],'purpose':'SKILL_BENEFIT_ELIGIBILITY'})
    return {'http_status':r.status_code,'response':r.json(),'requested_field':'citizen.bankAccount','requesting_department':'eligibility'}

@router.get('/connectors')
async def connectors(user:Principal=Depends(principal)):
    authorize(user,'inspect');return {'items':CONNECTORS,'canonical_version':'1','workflow_version':'skill-benefit-v1'}

@router.get('/mappings')
async def mappings(user:Principal=Depends(principal)):
    authorize(user,'inspect');return {'items':MAPPINGS}

@router.get('/policies')
async def policies(user:Principal=Depends(principal)):
    authorize(user,'inspect');return {'version':'field-policy-v1','rules':[{'department':d,'purpose':p,'fields':sorted(fields),'decision':'ALLOW','consent_required':d!='registry'} for d,purposes in FIELD_RULES.items() for p,fields in purposes.items()],'default_decision':'DENY'}

@router.get('/audit')
async def audit(user:Principal=Depends(principal),search:str=Query('',max_length=100),limit:int=Query(80,ge=1,le=200)):
    authorize(user,'inspect');q=visibility(user)
    if search:
        import re
        q={'$and':[q,{'transaction_id':{'$regex':re.escape(search),'$options':'i'}}]}
    records=[]
    async for app in db.applications.find(q,{'_id':0}).sort('updated_at',-1).limit(100):
        for entry in project(app,user).audit:records.append({**entry,'transaction_id':app['transaction_id'],'application_id':app['id']})
    records.sort(key=lambda e:e['timestamp'],reverse=True)
    return {'items':records[:limit]}

@router.get('/monitoring/overview')
async def overview(user:Principal=Depends(principal)):
    authorize(user,'inspect');q=visibility(user)
    docs=await db.applications.find(q,{'_id':0}).sort('created_at',-1).limit(1000).to_list(1000)
    attempts=[a for d in docs for s in d['stages'] for a in s['attempts'] if a.get('completed_at')]
    attention=[d for d in docs if d['status'] in ('RECONCILING','RETRY_SCHEDULED','HUMAN_INTERVENTION_REQUIRED','BLOCKED')]
    successful=sum(a['outcome'] in ('SUCCESS','RECONCILED') for a in attempts)
    components=[]
    for c in CONNECTORS:
        stages=[s for d in docs for s in d['stages'] if s['connector']==c['id'] or (c['id']=='eligibility' and s['connector']=='approval')]
        ca=[a for s in stages for a in s['attempts'] if a.get('completed_at')]
        latest=max(ca,key=lambda a:a['completed_at']) if ca else None
        components.append({**c,'health':'UNKNOWN' if not latest else 'HEALTHY' if latest['outcome'] in ('SUCCESS','RECONCILED') else 'DEGRADED','requests':len(ca),'latency_ms':round(sum(a['duration_ms'] for a in ca)/len(ca)) if ca else None,'failures':sum(a['outcome'] not in ('SUCCESS','RECONCILED') for a in ca),'last_checked':latest['completed_at'] if latest else None})
    try: redis_ok=await bus.ping();heartbeat=await bus.get('samanvay:consumer:heartbeat');pending=await bus.xpending(STREAM,GROUP);stream_length=await bus.xlen(STREAM)
    except Exception:redis_ok=False;heartbeat=None;pending={'pending':None};stream_length=None
    completed=sum(d['status']=='COMPLETED' for d in docs)
    awaiting_review=sum(d['status']=='UNDER_REVIEW' for d in docs)
    return {'total':len(docs),'completed':completed,'active':sum(d['status'] in ('PROCESSING','SUBMITTED','RETRYING','UNDER_REVIEW') for d in docs),'awaiting_review':awaiting_review,'attention':len(attention),'success_rate':round(successful/len(attempts)*100,1) if attempts else None,'average_latency_ms':round(sum(a['duration_ms'] for a in attempts)/len(attempts)) if attempts else None,'events':sum(len(d['events']) for d in docs),'policy_denials':sum(e['type']=='POLICY_DENIED' for d in docs for e in d['events']),'components':components,'infrastructure':{'mongodb':'HEALTHY','redis':'HEALTHY' if redis_ok else 'UNAVAILABLE','consumer':'HEALTHY' if heartbeat else 'UNAVAILABLE','pending_messages':pending['pending'],'stream_length':stream_length,'last_heartbeat':heartbeat},'scope':'Latest 1,000 visible applications','recent':[project(d,user,False).model_dump() for d in docs[:5]]}

@router.get('/notifications')
async def notifications(user:Principal=Depends(principal)):
    q=visibility(user);docs=await db.applications.find(q,{'_id':0,'id':1,'events':1}).sort('updated_at',-1).limit(50).to_list(50)
    receipt=await db.notification_reads.find_one({'user_id':user.id},{'_id':0}) or {'ids':[]}
    items=[{'id':e['id'],'application_id':a['id'],'type':e['type'],'timestamp':e['timestamp'],'read':e['id'] in receipt['ids']} for a in docs for e in a['events'] if e['type'] in ('APPLICATION_CREATED','APPLICATION_COMPLETED','INTEGRATION_FAILED','CONSENT_REVOKED','REVIEW_REQUESTED','REVIEW_DECIDED','APPLICATION_REJECTED')]
    return {'items':sorted(items,key=lambda x:x['timestamp'],reverse=True)[:80]}

@router.patch('/notifications/{notification_id}')
async def mark_read(notification_id:str,user:Principal=Depends(principal)):
    app=await db.applications.find_one({'$and':[visibility(user),{'events.id':notification_id}]},{'_id':0,'id':1})
    if not app:fail(404,'NOT_FOUND','Notification not found.')
    await db.notification_reads.update_one({'user_id':user.id},{'$addToSet':{'ids':notification_id}},upsert=True)
    return {'id':notification_id,'read':True}

@router.get('/transactions/{key}/payment-evidence')
async def payment_evidence(key:str,user:Principal=Depends(principal)):
    authorize(user,'operate');app=await load(key,user)
    op=app['stages'][-1]['operation_id']
    doc=await db.mock_payments.find_one({'operation_id':op},{'_id':0,'payment_ref':1,'created_at':1})
    return {'operation_id':op,'disbursement_count':await db.mock_payments.count_documents({'operation_id':op}),'payment_reference':doc.get('payment_ref') if doc else None,'source':'Simulated treasury authoritative ledger'}

@router.post('/internal/maintenance/recover',status_code=202)
async def recover(request:Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    if not hmac.compare_digest(request.headers.get('authorization',''),f'Bearer {setting("WEBHOOK_CRON_SECRET")}'):fail(401,'INVALID_CRON_CREDENTIAL','Invalid maintenance credentials.')
    try:body=await request.json()
    except Exception:fail(400,'INVALID_ENVELOPE','Invalid schedule envelope.')
    if not isinstance(body,dict) or body.get('event')!='schedule.triggered' or not body.get('run_id'):fail(400,'INVALID_ENVELOPE','Invalid schedule envelope.')
    rid=body['run_id']
    existing=await db.maintenance_receipts.find_one({'id':rid},{'_id':0})
    if existing and existing.get('queued'):return {'accepted':True,'duplicate':True}
    await db.maintenance_receipts.update_one({'id':rid},{'$setOnInsert':{'id':rid,'created_at':now(),'queued':False}},upsert=True)
    try:await bus.xadd(STREAM,{'event':json.dumps({'type':'MAINTENANCE_REQUESTED','id':rid})})
    except Exception:fail(503,'QUEUE_UNAVAILABLE','Maintenance could not be queued.')
    await db.maintenance_receipts.update_one({'id':rid},{'$set':{'queued':True}})
    return {'accepted':True}