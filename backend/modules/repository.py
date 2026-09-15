"""Single-document state, evidence and event intent form the atomic durability boundary."""
import copy, json, hashlib
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
from core.database import db, now, uid
from core.errors import fail
from modules.policy import visibility, authorize, FIELD_RULES
from modules.models import ApplicationView
from modules.definitions import STAGES

async def load(key, user=None):
    query={'$or':[{'id':key},{'transaction_id':key}]}
    if user: query={'$and':[query, visibility(user)]}
    app=await db.applications.find_one(query,{'_id':0})
    if not app: fail(404,'NOT_FOUND','Application not found.')
    return app

def emit(app, event_type, actor='workflow', stage_id=None, payload=None, causation_id=None):
    stamp=now(); sequence=len(app['events'])+1
    if sequence>180: fail(409,'HISTORY_LIMIT','This bounded prototype transaction reached its event limit.')
    event={'id':uid('EVT'),'type':event_type,'schema_version':'1','transaction_id':app['transaction_id'],'application_id':app['id'],'sequence':sequence,'timestamp':stamp,'producer':actor,'stage_id':stage_id,'payload':payload or {},'causation_id':causation_id,'published':False,'stream_id':None}
    app['events'].append(event)
    app['audit'].append({'id':uid('AUD'),'sequence':sequence,'timestamp':stamp,'actor':actor,'action':event_type,'stage_id':stage_id,'source':actor,'destination':'interoperability-fabric','result':(payload or {}).get('result','RECORDED'),'metadata':payload or {}})
    return event

async def save(app, expected_version):
    app['version']=expected_version+1; app['updated_at']=now()
    result=await db.applications.replace_one({'id':app['id'],'version':expected_version},copy.deepcopy(app))
    if result.modified_count!=1: fail(409,'VERSION_CONFLICT','The transaction changed. Refresh and try again.')
    return app

async def create(user, body, key, scenario='success', actor=None):
    fingerprint=hashlib.sha256(json.dumps({'body':body.model_dump(),'scenario':scenario},sort_keys=True).encode()).hexdigest()
    old=await db.applications.find_one({'owner_id':user['id'],'idempotency_key':key},{'_id':0})
    if old:
        if old['fingerprint']!=fingerprint: fail(409,'IDEMPOTENCY_CONFLICT','This submission key belongs to different application data.')
        return old
    stamp=now(); tx=uid('TXN'); app_id=uid(f'APP-MH-{datetime.now(timezone.utc).year}')
    expiry=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    consents=[{'id':uid('CNS'),'recipient':dept,'purpose':purpose,'fields':sorted(fields),'state':'ACTIVE','granted_at':stamp,'expires_at':expiry,'subject':user['id'],'transaction_id':tx,'policy_version':'field-policy-v1','actor':actor or user['id']} for dept in ('eligibility','treasury') for purpose,fields in FIELD_RULES[dept].items()]
    app={'id':app_id,'transaction_id':tx,'owner_id':user['id'],'owner_name':user['name'],'subject':user['subject'],'person_reference':user['person_reference'],'service_code':body.service_code,'course_code':body.course_code,'district':body.district,'amount':15000,'status':'SUBMITTED','created_at':stamp,'updated_at':stamp,'version':0,'workflow_version':'skill-benefit-v1','canonical_version':'1','idempotency_key':key,'fingerprint':fingerprint,'departments':['registry','eligibility','treasury'],'stages':[{**{k:d[k] for k in ('id','name','system','connector')},'state':'PENDING','operation_id':uid('OP'),'attempts':[],'external_id':None,'evidence':None,'policy':None} for d in STAGES],'events':[],'audit':[],'consents':consents,'mappings':[],'canonical':{},'scenario':scenario,'next_retry_at':None,'is_demo':True}
    emit(app,'APPLICATION_CREATED',actor or user['id'],payload={'result':'ACCEPTED','consent_ids':[c['id'] for c in consents]})
    try: await db.applications.insert_one(copy.deepcopy(app))
    except DuplicateKeyError:
        return await create(user,body,key,scenario,actor)
    return app

def project(app,user,full=True):
    safe=copy.deepcopy(app)
    if user.role=='citizen':
        safe.update(events=[],audit=[],mappings=[],canonical={},scenario=None)
        for stage in safe['stages']:
            stage.update(evidence=None,policy=None,attempts=[],operation_id='',external_id=None)
    elif user.role=='official':
        safe['canonical']={k:v for k,v in safe['canonical'].items() if k=='eligibility'}
        safe['events']=[e for e in safe['events'] if e.get('stage_id') in ('eligibility','approval')]
        safe['audit']=[e for e in safe['audit'] if e.get('stage_id') in ('eligibility','approval')]
        safe['mappings']=[m for m in safe['mappings'] if m['system']==user.department]
        safe['consents']=[c for c in safe['consents'] if c['recipient']==user.department]
        for stage in safe['stages']:
            if stage['id'] not in ('eligibility','approval'): stage.update(evidence=None,policy=None,attempts=[],operation_id='',external_id=None)
    if not full:
        safe.update(events=[],audit=[],mappings=[],canonical={},consents=[])
        for stage in safe['stages']: stage.update(evidence=None,policy=None,attempts=[])
    return ApplicationView(**safe)