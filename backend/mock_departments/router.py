import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timezone, timedelta
from typing import Literal
from urllib.parse import parse_qs
import jwt
from fastapi import APIRouter, Header, Request, Response, Depends
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from core.config import setting, DEMO
from core.database import db, uid, now
from core.errors import fail
from modules.auth import StrictModel, Principal
from modules.definitions import SCHEMES
BENEFIT_AMOUNTS = {str(s['amount']) for s in SCHEMES.values()}

router = APIRouter(prefix='/api/mock', tags=['Simulated department boundaries'])
async def demo_only():
    if not DEMO: fail(404, 'NOT_FOUND', 'Not found.')
router.dependencies.append(Depends(demo_only))

class RegistryRequest(StrictModel):
    operation_id: str = Field(max_length=100)
    subject: str = Field(max_length=100)
    transaction_id: str = Field(max_length=100)
class RegistryResponse(BaseModel):
    citizenId: str
    dob: str
    status: Literal['VERIFIED']
class ClientCredentials(StrictModel):
    client_id: Literal['eligibility']
    client_secret: str
class EligibilityRequest(StrictModel):
    operation_id: str = Field(max_length=100)
    uid: str = Field(max_length=100)
    birth_date: str = Field(max_length=10)
    verification: Literal['VERIFIED']
    scheme_code: str = Field(max_length=60)
    option_code: str = Field(max_length=40)
class EligibilityResponse(BaseModel):
    beneficiary_id: str
    verification: Literal['SUCCESS', 'INELIGIBLE']
class ApprovalRequest(StrictModel):
    operation_id: str = Field(max_length=100)
    beneficiary_id: str = Field(max_length=100)
    officer_reference: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=500)
class ApprovalResponse(BaseModel):
    approval_ref: str
    decision: Literal['SANCTIONED']

async def service_principal(authorization: str = Header('')):
    try:
        token = authorization.removeprefix('Bearer ')
        claims = jwt.decode(token, setting('ELIGIBILITY_SECRET'), algorithms=['HS256'], audience='samanvay-service', issuer='mock-eligibility')
        if claims.get('sub') != 'eligibility' or claims.get('scope') != 'eligibility:exchange': raise ValueError()
    except (jwt.PyJWTError, ValueError):
        fail(401, 'INVALID_SERVICE_TOKEN', 'Invalid service credentials.')
    return Principal(id='SERVICE-ELIGIBILITY', name='Eligibility service', email='service@demo.in', role='service', department='eligibility')

@router.post('/registry/verify', response_model=RegistryResponse)
async def verify(body: RegistryRequest, x_api_key: str = Header('')):
    if not hmac.compare_digest(x_api_key, setting('REGISTRY_KEY')): fail(401, 'INVALID_API_KEY', 'Invalid registry credentials.')
    person = await db.mock_people.find_one({'subject': body.subject}, {'_id': 0})
    if not person: fail(404, 'SUBJECT_NOT_FOUND', 'Citizen reference is not known to this registry.')
    response = {'citizenId':person['citizen_id'], 'dob':person['date_of_birth'], 'status':person['status']}
    await db.mock_registry.update_one({'operation_id':body.operation_id}, {'$setOnInsert':{'operation_id':body.operation_id,'response':response,'subject':body.subject,'created_at':now()}}, upsert=True)
    return RegistryResponse(**response)

@router.post('/eligibility/oauth/token')
async def token(body: ClientCredentials):
    if not hmac.compare_digest(body.client_secret, setting('ELIGIBILITY_SECRET')): fail(401, 'INVALID_CLIENT', 'Invalid client credentials.')
    token = jwt.encode({'sub':'eligibility','scope':'eligibility:exchange','aud':'samanvay-service','iss':'mock-eligibility','exp':datetime.now(timezone.utc)+timedelta(minutes=5)}, setting('ELIGIBILITY_SECRET'), algorithm='HS256')
    return {'access_token':token,'token_type':'Bearer','expires_in':300}

@router.post('/eligibility/check', response_model=EligibilityResponse)
async def check(body: EligibilityRequest, service=Depends(service_principal)):
    try: dob = datetime.strptime(body.birth_date, '%d/%m/%Y')
    except ValueError: fail(422, 'INVALID_DATE', 'Expected DD/MM/YYYY.')
    scheme = SCHEMES.get(body.scheme_code)
    if not scheme or body.option_code not in scheme['options']: fail(422, 'UNKNOWN_SCHEME', 'Scheme or option is not administered by this department.')
    existing = await db.mock_eligibility.find_one({'operation_id':body.operation_id}, {'_id':0})
    if existing: return EligibilityResponse(**existing['response'])
    age = (datetime.now(timezone.utc).date() - dob.date()).days / 365.2425
    response = {'beneficiary_id':uid('BEN'), 'verification':'SUCCESS' if scheme['min_age'] <= age <= scheme['max_age'] else 'INELIGIBLE'}
    await db.mock_eligibility.update_one({'operation_id':body.operation_id}, {'$setOnInsert':{'operation_id':body.operation_id,'response':response,'uid':body.uid,'scheme_code':body.scheme_code,'created_at':now()}}, upsert=True)
    saved = await db.mock_eligibility.find_one({'operation_id':body.operation_id}, {'_id':0})
    return EligibilityResponse(**saved['response'])

@router.post('/eligibility/approve', response_model=ApprovalResponse)
async def approve(body: ApprovalRequest, service=Depends(service_principal)):
    eligible = await db.mock_eligibility.find_one({'response.beneficiary_id':body.beneficiary_id,'response.verification':'SUCCESS'}, {'_id':0})
    if not eligible: fail(409, 'NOT_ELIGIBLE', 'An eligible department decision is required.')
    await db.mock_eligibility.update_one({'operation_id':body.operation_id},{'$setOnInsert':{'operation_id':body.operation_id,'response':{'approval_ref':uid('APR'),'decision':'SANCTIONED'},'sanctioned_by':body.officer_reference,'remarks':body.remarks,'created_at':now()}}, upsert=True)
    doc = await db.mock_eligibility.find_one({'operation_id':body.operation_id}, {'_id':0})
    return ApprovalResponse(**doc['response'])

async def treasury_auth(request: Request):
    body = await request.body()
    stamp = request.headers.get('x-timestamp','')
    try:
        if abs(time.time()-float(stamp)) > 60: raise ValueError()
    except ValueError: fail(401, 'STALE_SIGNATURE', 'Invalid signature timestamp.')
    canonical = stamp.encode()+b'.'+request.method.encode()+b'.'+request.url.path.encode()+b'.'+body
    signature=hmac.new(setting('TREASURY_SECRET').encode(),canonical,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,request.headers.get('x-signature','')): fail(401, 'INVALID_SIGNATURE', 'Invalid treasury signature.')
    return body

def payment_xml(doc):
    return Response(f'<payment><payment_ref>{doc["payment_ref"]}</payment_ref><state>DISBURSED</state><amount>{doc["amount"]}</amount></payment>', media_type='application/xml')

@router.post('/treasury/disburse')
async def disburse(request: Request, body: bytes = Depends(treasury_auth)):
    values = {k:v[0] for k,v in parse_qs(body.decode()).items()}
    if set(values) != {'operation_id','approval_ref','payee_ref','amount','transaction_id'}: fail(422,'INVALID_FORM','Invalid treasury form.')
    if values['amount'] not in BENEFIT_AMOUNTS or not values['approval_ref'].startswith('APR-'): fail(422,'INVALID_BENEFIT','Invalid approved benefit.')
    fingerprint=hashlib.sha256(body).hexdigest()
    existing=await db.mock_payments.find_one({'operation_id':values['operation_id']},{'_id':0})
    if existing:
        if existing['fingerprint'] != fingerprint: fail(409,'IDEMPOTENCY_CONFLICT','Operation payload changed.')
        return payment_xml(existing)
    scenario=await db.demo_scenarios.find_one({'transaction_id':values['transaction_id']},{'_id':0})
    mode=scenario['scenario'] if scenario else 'success'
    if mode=='treasury_unavailable': fail(503,'TREASURY_UNAVAILABLE','Simulated treasury unavailability.')
    doc={**values,'fingerprint':fingerprint,'payment_ref':uid('PAY'),'created_at':now()}
    try: await db.mock_payments.insert_one(doc.copy())
    except DuplicateKeyError:
        doc=await db.mock_payments.find_one({'operation_id':values['operation_id']},{'_id':0})
        if doc['fingerprint']!=fingerprint: fail(409,'IDEMPOTENCY_CONFLICT','Operation payload changed.')
    if mode=='timeout_after_commit': await asyncio.sleep(float(setting('CONNECTOR_TIMEOUT'))+1)
    return payment_xml(doc)

@router.get('/treasury/disbursements/by-operation/{operation_id}')
async def reconcile(operation_id: str, request: Request, auth=Depends(treasury_auth)):
    doc=await db.mock_payments.find_one({'operation_id':operation_id},{'_id':0})
    if not doc: fail(404,'PAYMENT_NOT_FOUND','No disbursement for this operation.')
    return payment_xml(doc)