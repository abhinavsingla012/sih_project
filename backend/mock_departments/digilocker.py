"""Simulated DigiLocker requester boundary: OAuth 2.0 authorization code → bearer token → issued-document pull.
Mirrors the public DigiLocker requester API shape so a real adapter can replace this module."""
import hashlib, hmac, json, secrets
from datetime import datetime, timezone, timedelta
from typing import Literal
import jwt
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from core.config import setting, DEMO
from core.database import db, uid, now
from core.errors import fail
from modules.auth import StrictModel, Principal, principal
from modules.definitions import DOCUMENT_TYPES

router = APIRouter(prefix='/api/mock/digilocker', tags=['Simulated DigiLocker'])
async def demo_only():
    if not DEMO: fail(404, 'NOT_FOUND', 'Not found.')
router.dependencies.append(Depends(demo_only))
CLIENT_ID = 'sampark'
REQUESTER = {'client_id': CLIENT_ID, 'name': 'Sampark — Government of Maharashtra', 'purpose': 'Verify documents for a government benefit application'}

class Holder(BaseModel):
    name: str
    dob: str
    masked_id: str
class DocumentEnvelope(BaseModel):
    uri: str
    doctype: str
    name: str
    issuer: str
    issuer_name: str
    issued_on: str
    holder: Holder
    fields: dict
    hash: str
    signature: str
    signed_at: str
class TokenRequest(StrictModel):
    grant_type: Literal['authorization_code']
    code: str = Field(max_length=120)
    client_id: Literal['sampark']
    client_secret: str
class Decision(StrictModel):
    state: str = Field(min_length=8, max_length=120)
    scope: str = Field(max_length=200)
    decision: Literal['allow', 'deny']
class IssueRequest(StrictModel):
    doctype: str = Field(max_length=10)

def canonical_payload(doc):
    return json.dumps({k: doc[k] for k in ('uri', 'doctype', 'issuer', 'issued_on', 'holder', 'fields')}, sort_keys=True, separators=(',', ':')).encode()
def sign_document(doc):
    return hmac.new(setting('DIGILOCKER_ISSUER_SECRET').encode(), canonical_payload(doc), hashlib.sha256).hexdigest()
def envelope(doc):
    payload = canonical_payload(doc)
    return DocumentEnvelope(**{k: doc[k] for k in ('uri', 'doctype', 'name', 'issuer', 'issuer_name', 'issued_on', 'holder', 'fields')}, hash=hashlib.sha256(payload).hexdigest(), signature=sign_document(doc), signed_at=doc.get('signed_at') or doc['issued_on'])

def document_fields(doctype, person, rng_seed):
    h = int(hashlib.sha256(f'{rng_seed}:{doctype}'.encode()).hexdigest()[:8], 16)
    year = datetime.now(timezone.utc).year
    return {
        'ADHAR': {'aadhaar_number': f'XXXX XXXX {h % 9000 + 1000}', 'gender': 'F' if h % 2 else 'M', 'address': f'{person.get("district", "Pune")}, Maharashtra', 'ekyc': 'Offline XML'},
        'SSCER': {'seat_number': f'M{h % 900000 + 100000}', 'passing_year': str(year - 6 - h % 8), 'percentage': f'{62 + h % 33}.{h % 10}%', 'result': 'PASS'},
        'CRCER': {'certificate_number': f'CC-{h % 90000 + 10000}', 'category': ('OBC', 'SC', 'ST', 'VJNT')[h % 4], 'issuing_office': 'Sub-Divisional Officer', 'valid_until': f'{year + 3}-03-31'},
        'INCER': {'certificate_number': f'IC-{h % 90000 + 10000}', 'annual_income': f'₹{(1 + h % 6) * 40000:,}', 'financial_year': f'{year - 1}-{str(year)[2:]}', 'issuing_office': 'Tahsildar office'},
        'LNRCD': {'survey_number': f'{h % 400 + 1}/{h % 9 + 1}', 'village': ('Shirur', 'Baramati', 'Karad', 'Malegaon', 'Akola')[h % 5], 'area_hectares': f'{1 + h % 5}.{h % 90:02d}', 'holder_type': 'Owner (Kabjedar)'},
    }[doctype]

def make_document(person, doctype, issued_days_ago=400):
    meta = DOCUMENT_TYPES[doctype]; h = hashlib.sha256(f'{person["subject"]}:{doctype}'.encode()).hexdigest()[:10].upper()
    issued = (datetime.now(timezone.utc) - timedelta(days=issued_days_ago)).date().isoformat()
    doc = {'uri': f'{meta["issuer"]}-{doctype}-{h}', 'subject': person['subject'], 'doctype': doctype, 'name': meta['name'], 'issuer': meta['issuer'], 'issuer_name': meta['issuer_name'], 'issued_on': issued, 'holder': {'name': person['name'], 'dob': person['date_of_birth'], 'masked_id': f'XXXX XXXX {int(h[:4], 16) % 9000 + 1000}'}, 'fields': document_fields(doctype, person, person['subject']), 'created_at': now()}
    return doc

async def seed_locker(person, doctypes, reset=False):
    if reset: await db.mock_locker_documents.delete_many({'subject': person['subject']})
    for doctype in doctypes:
        doc = make_document(person, doctype)
        await db.mock_locker_documents.update_one({'subject': person['subject'], 'doctype': doctype}, {'$setOnInsert': doc}, upsert=True)

async def locker_owner(user: Principal = Depends(principal)):
    if user.role != 'citizen' or not user.subject: fail(403, 'FORBIDDEN', 'Only a signed-in locker owner can authorize access.')
    return user

def issue_token(subject, scope):
    return jwt.encode({'sub': subject, 'scope': scope, 'aud': CLIENT_ID, 'iss': 'mock-digilocker', 'exp': datetime.now(timezone.utc) + timedelta(days=30)}, setting('DIGILOCKER_CLIENT_SECRET'), algorithm='HS256')

async def bearer(authorization: str = Header('')):
    try:
        claims = jwt.decode(authorization.removeprefix('Bearer '), setting('DIGILOCKER_CLIENT_SECRET'), algorithms=['HS256'], audience=CLIENT_ID, issuer='mock-digilocker')
    except jwt.PyJWTError: fail(401, 'INVALID_TOKEN', 'Invalid or expired DigiLocker access token.')
    return claims

@router.get('/oauth2/1/authorize')
async def authorize(scope: str = Query(max_length=200), state: str = Query(min_length=8, max_length=120), client_id: str = Query('sampark', max_length=40), user: Principal = Depends(locker_owner)):
    if client_id != CLIENT_ID: fail(400, 'UNKNOWN_CLIENT', 'Unknown requester.')
    requested = [d for d in scope.split(',') if d in DOCUMENT_TYPES]
    if not requested: fail(400, 'INVALID_SCOPE', 'No recognised document types requested.')
    owned = {d['doctype']: d for d in await db.mock_locker_documents.find({'subject': user.subject}, {'_id': 0}).to_list(50)}
    return {'requester': REQUESTER, 'state': state, 'holder': {'name': user.name, 'mobile': 'XXXXXX' + hashlib.sha256(user.subject.encode()).hexdigest()[:4].translate(str.maketrans('abcdef', '123456'))},
            'documents': [{'doctype': d, 'name': DOCUMENT_TYPES[d]['name'], 'issuer': DOCUMENT_TYPES[d]['issuer'], 'issuer_name': DOCUMENT_TYPES[d]['issuer_name'], 'available': d in owned, 'uri': owned[d]['uri'] if d in owned else None, 'issued_on': owned[d]['issued_on'] if d in owned else None} for d in requested]}

@router.post('/oauth2/1/authorize/decision')
async def decide(body: Decision, user: Principal = Depends(locker_owner)):
    if body.decision == 'deny': return {'error': 'access_denied', 'state': body.state}
    requested = [d for d in body.scope.split(',') if d in DOCUMENT_TYPES]
    code = secrets.token_urlsafe(32)
    await db.mock_locker_codes.insert_one({'code': code, 'subject': user.subject, 'user_id': user.id, 'scope': ','.join(requested), 'state': body.state, 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), 'used': False, 'created_at': now()})
    return {'code': code, 'state': body.state}

@router.post('/issue')
async def issue_from_issuer(body: IssueRequest, user: Principal = Depends(locker_owner)):
    """Simulates the issuing department pushing a freshly issued document into the citizen's locker."""
    if body.doctype not in DOCUMENT_TYPES: fail(422, 'UNKNOWN_DOCTYPE', 'Unknown document type.')
    person = await db.mock_people.find_one({'subject': user.subject}, {'_id': 0})
    if not person: fail(404, 'NOT_FOUND', 'No registry record for this locker owner.')
    doc = make_document({'subject': user.subject, 'name': user.name, 'date_of_birth': person['date_of_birth']}, body.doctype, issued_days_ago=0)
    await db.mock_locker_documents.update_one({'subject': user.subject, 'doctype': body.doctype}, {'$setOnInsert': doc}, upsert=True)
    stored = await db.mock_locker_documents.find_one({'subject': user.subject, 'doctype': body.doctype}, {'_id': 0})
    return {'doctype': body.doctype, 'name': stored['name'], 'issuer_name': stored['issuer_name'], 'uri': stored['uri'], 'issued_on': stored['issued_on']}

@router.post('/oauth2/1/token')
async def token(body: TokenRequest):
    if not hmac.compare_digest(body.client_secret, setting('DIGILOCKER_CLIENT_SECRET')): fail(401, 'INVALID_CLIENT', 'Invalid client credentials.')
    grant = await db.mock_locker_codes.find_one_and_update({'code': body.code, 'used': False, 'expires_at': {'$gt': now()}}, {'$set': {'used': True, 'used_at': now()}})
    if not grant: fail(400, 'INVALID_GRANT', 'Authorization code is invalid, expired or already used.')
    return {'access_token': issue_token(grant['subject'], grant['scope']), 'token_type': 'Bearer', 'expires_in': 30 * 86400, 'scope': grant['scope'], 'digilockerid': hashlib.sha256(grant['subject'].encode()).hexdigest()[:16], 'state': grant['state']}

@router.get('/oauth2/2/files/issued')
async def issued_files(claims: dict = Depends(bearer)):
    scope = claims['scope'].split(',')
    docs = await db.mock_locker_documents.find({'subject': claims['sub'], 'doctype': {'$in': scope}}, {'_id': 0}).to_list(50)
    return {'items': [{'uri': d['uri'], 'doctype': d['doctype'], 'name': d['name'], 'issuer': d['issuer'], 'issuerid': d['issuer'], 'issuer_name': d['issuer_name'], 'date': d['issued_on'], 'mime': 'application/xml'} for d in docs]}

@router.get('/oauth2/1/xml/{uri}', response_model=DocumentEnvelope)
async def pull_document(uri: str, claims: dict = Depends(bearer)):
    doc = await db.mock_locker_documents.find_one({'uri': uri, 'subject': claims['sub'], 'doctype': {'$in': claims['scope'].split(',')}}, {'_id': 0})
    if not doc: fail(404, 'NOT_FOUND', 'Document not found in this locker or outside the granted scope.')
    return envelope(doc)
