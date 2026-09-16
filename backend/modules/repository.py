"""Single-document state, evidence and event intent form the atomic durability boundary."""
import copy, json, hashlib
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
from core.database import db, now, uid
from core.errors import fail
from modules.policy import visibility, authorize, FIELD_RULES
from modules.models import ApplicationView
from modules.definitions import STAGES, SCHEMES, DISTRICTS, stage_templates

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

def catalogue_entry(body):
    scheme=SCHEMES.get(body.service_code)
    if not scheme: fail(422,'UNKNOWN_SERVICE','This service is not in the scheme catalogue.')
    if body.option_code not in scheme['options']: fail(422,'INVALID_OPTION',f'Choose a valid {scheme["option_label"].lower()} for this scheme.')
    if body.district not in DISTRICTS: fail(422,'INVALID_DISTRICT','Choose a Maharashtra district from the list.')
    return scheme

def document_attachment(grant):
    return {'grant_id':grant['id'],'connected_at':now(),'scope':grant['scope'],'shared':[{k:d.get(k) for k in ('doctype','name','uri','issuer','issuer_name','issued_on')} for d in grant['documents']]}

def document_consent(app,user_id,actor,stamp=None):
    stamp=stamp or now()
    return {'id':uid('CNS'),'recipient':'digilocker','purpose':'DOCUMENT_VERIFICATION','fields':sorted(FIELD_RULES['digilocker']['DOCUMENT_VERIFICATION']),'state':'ACTIVE','granted_at':stamp,'expires_at':(datetime.fromisoformat(stamp)+timedelta(days=30)).isoformat(),'subject':user_id,'transaction_id':app['transaction_id'],'policy_version':'field-policy-v1','actor':actor}

async def grant_for(user_id,grant_id):
    grant=await db.digilocker_grants.find_one({'id':grant_id,'user_id':user_id},{'_id':0})
    if not grant or grant['expires_at']<=now(): fail(422,'INVALID_DOCUMENT_GRANT','The DigiLocker consent is missing or has expired. Share your documents again.')
    return grant

async def auto_grant(user, scheme, stamp=None):
    """Server-side stand-in for a citizen who already completed the DigiLocker consent (demo journeys, seeded history)."""
    from mock_departments.digilocker import issue_token
    scope=','.join(scheme['documents']); stamp=stamp or now()
    docs=await db.mock_locker_documents.find({'subject':user['subject'],'doctype':{'$in':scheme['documents']}},{'_id':0}).to_list(20)
    grant={'id':uid('DLG'),'user_id':user['id'],'subject':user['subject'],'scope':scope,'access_token':issue_token(user['subject'],scope),'expires_at':(datetime.fromisoformat(stamp)+timedelta(days=30)).isoformat(),'documents':[{'doctype':d['doctype'],'name':d['name'],'uri':d['uri'],'issuer':d['issuer'],'issuer_name':d['issuer_name'],'issued_on':d['issued_on']} for d in docs],'created_at':stamp,'state':'server-side'}
    await db.digilocker_grants.insert_one(grant); grant.pop('_id',None)
    return grant

async def create(user, body, key, scenario='success', actor=None, review_mode='manual'):
    scheme=catalogue_entry(body)
    grant=await grant_for(user['id'],body.digilocker_grant) if body.digilocker_grant else None
    fingerprint=hashlib.sha256(json.dumps({'body':body.model_dump(),'scenario':scenario,'review_mode':review_mode},sort_keys=True).encode()).hexdigest()
    old=await db.applications.find_one({'owner_id':user['id'],'idempotency_key':key},{'_id':0})
    if old:
        if old['fingerprint']!=fingerprint: fail(409,'IDEMPOTENCY_CONFLICT','This submission key belongs to different application data.')
        return old
    stamp=now(); tx=uid('TXN'); app_id=uid(f'APP-MH-{datetime.now(timezone.utc).year}')
    expiry=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    consents=[{'id':uid('CNS'),'recipient':dept,'purpose':purpose,'fields':sorted(fields),'state':'ACTIVE','granted_at':stamp,'expires_at':expiry,'subject':user['id'],'transaction_id':tx,'policy_version':'field-policy-v1','actor':actor or user['id']} for dept in ('eligibility','treasury') for purpose,fields in FIELD_RULES[dept].items()]
    app={'id':app_id,'transaction_id':tx,'owner_id':user['id'],'owner_name':user['name'],'subject':user['subject'],'person_reference':user['person_reference'],'service_code':body.service_code,'option_code':body.option_code,'unit':scheme['unit'],'district':body.district,'amount':scheme['amount'],'status':'SUBMITTED','created_at':stamp,'updated_at':stamp,'version':0,'workflow_version':'benefit-v2','canonical_version':'1','idempotency_key':key,'fingerprint':fingerprint,'departments':['registry','digilocker','eligibility','treasury'],'stages':[{**{k:d[k] for k in ('id','name','system','connector')},'state':'PENDING','operation_id':uid('OP'),'attempts':[],'external_id':None,'evidence':None,'policy':None,'review':None} for d in stage_templates(scheme)],'events':[],'audit':[],'consents':consents,'mappings':[],'canonical':{},'scenario':scenario,'review_mode':review_mode,'next_retry_at':None,'is_demo':True,'documents':document_attachment(grant) if grant else None}
    if grant: app['consents'].append(document_consent(app,user['id'],f'digilocker:{grant["id"]}',stamp))
    emit(app,'APPLICATION_CREATED',actor or user['id'],payload={'result':'ACCEPTED','consent_ids':[c['id'] for c in app['consents']],'documents_shared':[d['doctype'] for d in (app['documents'] or {}).get('shared',[])]})
    try: await db.applications.insert_one(copy.deepcopy(app))
    except DuplicateKeyError:
        return await create(user,body,key,scenario,actor,review_mode)
    return app

def project(app,user,full=True):
    safe=copy.deepcopy(app)
    scheme=SCHEMES.get(safe.get('service_code'),{})
    option=safe.get('option_code') or safe.get('course_code') or ''
    safe.update(option_code=option,service_name=scheme.get('name',safe.get('service_code','')),option_label=scheme.get('options',{}).get(option,option.replace('_',' ').title()),department=scheme.get('department',''),unit=safe.get('unit') or scheme.get('unit',''))
    if user.role=='citizen':
        safe.update(events=[],audit=[],mappings=[],canonical={},scenario=None,review_mode=None)
        for stage in safe['stages']:
            review=stage.get('review')
            stage.update(evidence=None,policy=None,attempts=[],operation_id='',external_id=None,review={k:v for k,v in review.items() if k!='officer_id'} if review else None)
    elif user.role=='official':
        safe['canonical']={k:v for k,v in safe['canonical'].items() if k in ('eligibility','documents')}
        safe['events']=[e for e in safe['events'] if e.get('stage_id') in ('documents','eligibility','approval')]
        safe['audit']=[e for e in safe['audit'] if e.get('stage_id') in ('documents','eligibility','approval')]
        safe['mappings']=[m for m in safe['mappings'] if m['system']==user.department]
        safe['consents']=[c for c in safe['consents'] if c['recipient']==user.department]
        for stage in safe['stages']:
            if stage['id'] not in ('documents','eligibility','approval'): stage.update(evidence=None,policy=None,attempts=[],operation_id='',external_id=None)
    safe.setdefault('documents',None)
    if not full:
        safe.update(events=[],audit=[],mappings=[],canonical={},consents=[])
        for stage in safe['stages']: stage.update(evidence=None,policy=None,attempts=[])
    return ApplicationView(**safe)