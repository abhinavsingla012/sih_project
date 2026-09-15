"""Real HTTP adapters. Department transport details never enter the orchestrator."""
import hashlib, hmac, time
from datetime import datetime
from urllib.parse import urlencode
from typing import Literal
import httpx
from pydantic import BaseModel
from defusedxml.ElementTree import fromstring
from core.config import setting
from mock_departments.router import RegistryResponse, EligibilityResponse, ApprovalResponse

class CanonicalResult(BaseModel):
    external_id: str
    entity_type: str
    status: str
    canonical: dict
    evidence: dict

class ConnectorAdapter:
    department: str
    async def execute(self, app, stage): raise NotImplementedError
    async def reconcile(self, app, stage): return None

async def request(method, path, **kwargs):
    async with httpx.AsyncClient(base_url=setting('MOCK_BASE_URL'), timeout=float(setting('CONNECTOR_TIMEOUT')), follow_redirects=False) as client:
        r=await client.request(method,path,**kwargs)
        r.raise_for_status()
        if len(r.content)>65536: raise ValueError('Downstream response too large')
        return r

async def registry_source(app):
    return RegistryResponse.model_validate((await request('POST','/api/mock/registry/verify',headers={'X-API-Key':setting('REGISTRY_KEY')},json={'operation_id':app['stages'][0]['operation_id'],'subject':app['subject'],'transaction_id':app['transaction_id']})).json())

def evidence(version, source, target, rows):
    return {'mapping_version':version, 'canonical_version':'1','source_summary':source,'canonical_output':target,'lineage':rows}

class RegistryAdapter(ConnectorAdapter):
    department='registry'
    async def execute(self, app, stage):
        native=await registry_source(app)
        datetime.strptime(native.dob,'%Y-%m-%d')
        canonical={'identity':{'verificationStatus':native.status,'externalReference':native.citizenId},'person':{'globalReference':app['person_reference']}}
        return CanonicalResult(external_id=native.citizenId,entity_type='person',status='VERIFIED',canonical=canonical,evidence=evidence('registry-v1',{'citizenId':native.citizenId,'status':native.status},canonical,[{'source':'citizenId','target':'identity.externalReference','transform':'reference'},{'source':'dob','target':'person.dateOfBirth','transform':'ISO validation; not retained'},{'source':'status','target':'identity.verificationStatus','transform':'enum'}]))

async def eligibility_token():
    return (await request('POST','/api/mock/eligibility/oauth/token',json={'client_id':'eligibility','client_secret':setting('ELIGIBILITY_SECRET')})).json()['access_token']

class EligibilityAdapter(ConnectorAdapter):
    department='eligibility'
    async def execute(self,app,stage):
        source=await registry_source(app)
        native=EligibilityResponse.model_validate((await request('POST','/api/mock/eligibility/check',headers={'Authorization':f'Bearer {await eligibility_token()}'},json={'operation_id':stage['operation_id'],'uid':app['person_reference'],'birth_date':datetime.strptime(source.dob,'%Y-%m-%d').strftime('%d/%m/%Y'),'verification':source.status,'scheme_code':app['service_code'],'option_code':app['option_code']})).json())
        status={'SUCCESS':'ELIGIBLE','INELIGIBLE':'INELIGIBLE'}[native.verification]
        canonical={'eligibility':{'status':status,'beneficiaryReference':native.beneficiary_id},'scheme':{'code':app['service_code'],'optionCode':app['option_code']}}
        return CanonicalResult(external_id=native.beneficiary_id,entity_type='beneficiary',status=status,canonical=canonical,evidence=evidence('eligibility-v1',native.model_dump(),canonical,[{'source':'verification','target':'eligibility.status','transform':'SUCCESS → ELIGIBLE'},{'source':'beneficiary_id','target':'eligibility.beneficiaryReference','transform':'reference'},{'source':'person.dateOfBirth','target':'birth_date','transform':'ISO → DD/MM/YYYY; transient'},{'source':'scheme_code + option_code','target':'scheme.optionCode','transform':'catalogue lookup'}]))

class ApprovalAdapter(ConnectorAdapter):
    department='eligibility'
    async def execute(self,app,stage):
        review=stage.get('review') or {}
        native=ApprovalResponse.model_validate((await request('POST','/api/mock/eligibility/approve',headers={'Authorization':f'Bearer {await eligibility_token()}'},json={'operation_id':stage['operation_id'],'beneficiary_id':app['canonical']['eligibility']['beneficiaryReference'],'officer_reference':review.get('officer_id'),'remarks':review.get('remarks')})).json())
        canonical={'benefit':{'approvalReference':native.approval_ref,'payeeReference':app['canonical']['eligibility']['beneficiaryReference'],'amount':app['amount'],'sanctionedBy':review.get('officer_name')}}
        return CanonicalResult(external_id=native.approval_ref,entity_type='approval',status='APPROVED',canonical=canonical,evidence=evidence('approval-v1',{**native.model_dump(),'sanctioned_by':review.get('officer_name')},canonical,[{'source':'decision','target':'benefit.approvalReference','transform':'SANCTIONED → approved reference'},{'source':'officer decision','target':'benefit.sanctionedBy','transform':'officer of record'}]))

def treasury_headers(method,path,body=b''):
    stamp=str(time.time()); content=stamp.encode()+b'.'+method.encode()+b'.'+path.encode()+b'.'+body
    return {'X-Timestamp':stamp,'X-Signature':hmac.new(setting('TREASURY_SECRET').encode(),content,hashlib.sha256).hexdigest(),'Content-Type':'application/x-www-form-urlencoded'}

class TreasuryAdapter(ConnectorAdapter):
    department='treasury'
    def normalize(self,response):
        root=fromstring(response.content)
        if root.findtext('state')!='DISBURSED' or not (root.findtext('payment_ref') or '').startswith('PAY-'): raise ValueError('Unrecognized treasury schema')
        ref=root.findtext('payment_ref'); canonical={'payment':{'reference':ref,'status':'COMPLETED'}}
        return CanonicalResult(external_id=ref,entity_type='payment',status='COMPLETED',canonical=canonical,evidence=evidence('treasury-v1',{'payment_ref':ref,'state':'DISBURSED','format':'XML'},canonical,[{'source':'/payment/payment_ref','target':'payment.reference','transform':'safe XML extraction'},{'source':'/payment/state','target':'payment.status','transform':'DISBURSED → COMPLETED'}]))
    async def execute(self,app,stage):
        b=app['canonical']['benefit']; path='/api/mock/treasury/disburse'
        body=urlencode({'operation_id':stage['operation_id'],'approval_ref':b['approvalReference'],'payee_ref':b['payeeReference'],'amount':str(b['amount']),'transaction_id':app['transaction_id']}).encode()
        return self.normalize(await request('POST',path,content=body,headers=treasury_headers('POST',path,body)))
    async def reconcile(self,app,stage):
        path=f'/api/mock/treasury/disbursements/by-operation/{stage["operation_id"]}'
        try: return self.normalize(await request('GET',path,headers=treasury_headers('GET',path)))
        except httpx.HTTPStatusError as e:
            if e.response.status_code==404: return None
            raise

REGISTRY={'registry':RegistryAdapter(),'eligibility':EligibilityAdapter(),'approval':ApprovalAdapter(),'treasury':TreasuryAdapter()}