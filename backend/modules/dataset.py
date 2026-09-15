"""Synthetic demo history. Every document mirrors what the live workflow writes and is marked seeded=True."""
import hashlib, random
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from core.config import DEMO
from core.database import db, uid
from modules.definitions import SCHEMES, DISTRICTS, stage_templates
from modules.policy import FIELD_RULES
from modules.seed import ACCOUNTS, OFFICERS
from modules.connectors import evidence

FIRST = ['Aarav', 'Vivaan', 'Aditya', 'Sai', 'Arjun', 'Omkar', 'Pranav', 'Siddharth', 'Tejas', 'Yash', 'Nikhil', 'Akshay', 'Sagar', 'Ganesh', 'Aniket', 'Rahul', 'Suresh', 'Mahesh', 'Vikas', 'Sneha', 'Pooja', 'Priya', 'Aishwarya', 'Shruti', 'Neha', 'Pallavi', 'Manasi', 'Rutuja', 'Sakshi', 'Vaishnavi', 'Anjali', 'Kavita', 'Manisha', 'Archana', 'Savita', 'Madhuri', 'Swati', 'Tejaswini', 'Balasaheb', 'Dnyaneshwar']
LAST = ['Patil', 'Deshmukh', 'Jadhav', 'Pawar', 'Shinde', 'More', 'Kulkarni', 'Joshi', 'Chavan', 'Gaikwad', 'Bhosale', 'Kadam', 'Sawant', 'Mane', 'Salunkhe', 'Thorat', 'Wagh', 'Ingle', 'Kale', 'Nikam', 'Raut', 'Sonawane', 'Waghmare', 'Kamble', 'Shaikh', 'Pathan', 'Gawande', 'Bhagat', 'Lokhande', 'Mahajan']
REMARKS = {
    'skill': ['Enrolment confirmed with the training partner; sanctioned under scheme guidelines.', 'Identity and age verified; candidate meets the 18–35 criterion. Sanctioned.', 'Programme allocation verified against the approved list. Sanctioned.'],
    'social_justice': ['Institution recognition and admission verified; scholarship sanctioned for the academic year.', 'Income certificate and bonafide certificate on record; sanctioned.', 'Admission verified with the institute portal. Sanctioned.'],
    'agriculture': ['7/12 extract and micro-irrigation quotation verified by the taluka office; subsidy sanctioned.', 'Field inspection report satisfactory; sanctioned under the micro-irrigation component.', 'Landholding and crop pattern verified; sanctioned.'],
}
REJECT_REMARKS = {'skill': 'Training partner could not confirm enrolment for the selected programme.', 'social_justice': 'Institution is not on the recognised list for the current academic year.', 'agriculture': 'Land record shows the survey number is not held in the applicant’s name.'}
FAILURES = {'CONNECTION_FAILED': 'Could not reach the department.', 'DOWNSTREAM_UNAVAILABLE': 'Department returned HTTP 503.', 'TIMEOUT': 'Department response timed out. Outcome will be reconciled.'}
MIX = [('completed', 68), ('under_review', 12), ('ineligible', 6), ('officer_rejected', 5), ('retry_scheduled', 4), ('reconciling', 3), ('human_intervention', 3), ('blocked', 3)]
iso = lambda dt: dt.isoformat()

class Builder:
    def __init__(self, rng, person, scheme, option, district, created, officer):
        self.rng, self.scheme, self.officer, self.t = rng, scheme, officer, created
        stages = [{**{k: d[k] for k in ('id', 'name', 'system', 'connector')}, 'state': 'PENDING', 'operation_id': uid('OP'), 'attempts': [], 'external_id': None, 'evidence': None, 'policy': None, 'review': None} for d in stage_templates(scheme)]
        tx = uid('TXN'); expiry = iso(created + timedelta(days=30))
        consents = [{'id': uid('CNS'), 'recipient': dept, 'purpose': purpose, 'fields': sorted(fields), 'state': 'ACTIVE', 'granted_at': iso(created), 'expires_at': expiry, 'subject': person['id'], 'transaction_id': tx, 'policy_version': 'field-policy-v1', 'actor': person['id']} for dept in ('eligibility', 'treasury') for purpose, fields in FIELD_RULES[dept].items()]
        self.app = {'id': uid(f'APP-MH-{created.year}'), 'transaction_id': tx, 'owner_id': person['id'], 'owner_name': person['name'], 'subject': person['subject'], 'person_reference': person['person_reference'], 'service_code': scheme['code'], 'option_code': option, 'unit': scheme['unit'], 'district': district, 'amount': scheme['amount'], 'status': 'SUBMITTED', 'created_at': iso(created), 'updated_at': iso(created), 'version': 0, 'workflow_version': 'benefit-v1', 'canonical_version': '1', 'idempotency_key': f'seed-{tx}', 'fingerprint': hashlib.sha256(tx.encode()).hexdigest(), 'departments': ['registry', 'eligibility', 'treasury'], 'stages': stages, 'events': [], 'audit': [], 'consents': consents, 'mappings': [], 'canonical': {}, 'scenario': 'success', 'review_mode': 'manual', 'next_retry_at': None, 'is_demo': True, 'seeded': True}
        self.mocks = {'mock_registry': [], 'mock_eligibility': [], 'mock_payments': []}
        self.person = person
        self.emit('APPLICATION_CREATED', person['id'], None, {'result': 'ACCEPTED', 'consent_ids': [c['id'] for c in consents]})

    def tick(self, seconds=None, **kw):
        self.t += timedelta(seconds=seconds if seconds is not None else self.rng.uniform(0.4, 2.5), **kw); return self.t

    def emit(self, type_, actor, stage_id, payload, causation=None):
        app = self.app; stamp = iso(self.t); sequence = len(app['events']) + 1
        event = {'id': uid('EVT'), 'type': type_, 'schema_version': '1', 'transaction_id': app['transaction_id'], 'application_id': app['id'], 'sequence': sequence, 'timestamp': stamp, 'producer': actor, 'stage_id': stage_id, 'payload': payload, 'causation_id': causation, 'published': True, 'stream_id': None}
        app['events'].append(event)
        app['audit'].append({'id': uid('AUD'), 'sequence': sequence, 'timestamp': stamp, 'actor': actor, 'action': type_, 'stage_id': stage_id, 'source': actor, 'destination': 'interoperability-fabric', 'result': payload.get('result', 'RECORDED'), 'metadata': payload})
        app['updated_at'] = stamp; app['version'] += 1
        return event

    def decision(self, stage, fields, purpose, allow=True):
        dept = 'eligibility' if stage['connector'] == 'approval' else stage['connector']
        consent = next((c for c in self.app['consents'] if c['recipient'] == dept and c['purpose'] == purpose), None)
        d = {'id': uid('DEC'), 'decision': 'ALLOW' if allow else 'DENY', 'actor': f'service:{dept}', 'department': dept, 'fields': fields, 'purpose': purpose, 'policy_version': 'field-policy-v1', 'consent_id': consent['id'] if consent and allow else None, 'reason': 'Purpose and field scope permitted' if allow else 'Field scope or active consent does not permit this exchange', 'timestamp': iso(self.t)}
        stage['policy'] = d; return d

    def attempt(self, stage, outcome, error=None, seconds=None):
        a = {'id': uid('ATT'), 'number': len(stage['attempts']) + 1, 'started_at': iso(self.t), 'outcome': 'PROCESSING', 'operation_id': stage['operation_id']}
        stage['attempts'].append(a); stage['state'] = 'RUNNING'; stage['started_at'] = stage.get('started_at') or iso(self.t); stage['lease_until'] = None
        self.emit('PAYMENT_INITIATED' if stage['id'] == 'treasury' else 'INTEGRATION_STARTED', f'connector:{stage["connector"]}', stage['id'], {'attempt_id': a['id'], 'operation_id': stage['operation_id'], 'policy_decision': stage['policy']})
        ms = self.tick(seconds) and int(self.rng.uniform(280, 1400) if outcome not in ('TIMEOUT',) else 8000)
        a.update(completed_at=iso(self.t), duration_ms=ms, outcome=outcome)
        if error: a['error'] = error; stage['error'] = error
        return a

    def complete(self, stage, index, result_status, external_id, entity_type, canonical, ev, event_type):
        a = stage['attempts'][-1]; app = self.app
        stage.update(state='COMPLETED', completed_at=iso(self.t), external_id=external_id, evidence=ev, error=None)
        app['canonical'].update(canonical)
        app['mappings'].append({'system': stage['connector'] if stage['connector'] != 'approval' else 'eligibility', 'entity_type': entity_type, 'external_id': external_id, 'internal_reference': app['person_reference'] if entity_type == 'person' else app['transaction_id'], 'operation_id': stage['operation_id'], 'stage_id': stage['id']})
        app['status'] = 'REJECTED' if result_status == 'INELIGIBLE' else 'COMPLETED' if index == 3 else 'PROCESSING'
        self.emit(event_type, f'connector:{stage["connector"]}', stage['id'], {'result': result_status, 'external_id': external_id, 'mapping_version': ev['mapping_version'], 'reconciled': False, 'policy_decision_id': stage['policy']['id'], 'attempt_id': a['id']})

    def request_stage(self, stage, actor='workflow', causation=None):
        stage['state'] = 'READY'; self.app['status'] = 'PROCESSING'
        return self.emit('STAGE_REQUESTED', actor, stage['id'], {'operation_id': stage['operation_id']}, causation)

    def build(self, outcome):
        app, s, p, rng = self.app, self.app['stages'], self.person, self.rng
        # 1. Identity
        self.tick(); self.request_stage(s[0]); self.decision(s[0], ['identity.subjectReference'], 'IDENTITY_VERIFICATION'); self.attempt(s[0], 'SUCCESS')
        canonical = {'identity': {'verificationStatus': 'VERIFIED', 'externalReference': p['citizen_id']}, 'person': {'globalReference': p['person_reference']}}
        self.complete(s[0], 0, 'VERIFIED', p['citizen_id'], 'person', canonical, evidence('registry-v1', {'citizenId': p['citizen_id'], 'status': 'VERIFIED'}, canonical, [{'source': 'citizenId', 'target': 'identity.externalReference', 'transform': 'reference'}, {'source': 'dob', 'target': 'person.dateOfBirth', 'transform': 'ISO validation; not retained'}, {'source': 'status', 'target': 'identity.verificationStatus', 'transform': 'enum'}]), 'IDENTITY_VERIFIED')
        self.mocks['mock_registry'].append({'operation_id': s[0]['operation_id'], 'response': {'citizenId': p['citizen_id'], 'dob': p['date_of_birth'], 'status': 'VERIFIED'}, 'subject': p['subject'], 'created_at': iso(self.t), 'seeded': True})
        # 2. Eligibility
        self.tick(); self.request_stage(s[1]); self.decision(s[1], ['person.dateOfBirth', 'identity.verificationStatus', 'person.globalReference', 'scheme.optionCode'], 'BENEFIT_ELIGIBILITY'); self.attempt(s[1], 'SUCCESS')
        ben = uid('BEN'); verification = 'INELIGIBLE' if outcome == 'ineligible' else 'SUCCESS'; status = 'INELIGIBLE' if verification == 'INELIGIBLE' else 'ELIGIBLE'
        canonical = {'eligibility': {'status': status, 'beneficiaryReference': ben}, 'scheme': {'code': app['service_code'], 'optionCode': app['option_code']}}
        self.complete(s[1], 1, status, ben, 'beneficiary', canonical, evidence('eligibility-v1', {'beneficiary_id': ben, 'verification': verification}, canonical, [{'source': 'verification', 'target': 'eligibility.status', 'transform': 'SUCCESS → ELIGIBLE'}, {'source': 'beneficiary_id', 'target': 'eligibility.beneficiaryReference', 'transform': 'reference'}, {'source': 'person.dateOfBirth', 'target': 'birth_date', 'transform': 'ISO → DD/MM/YYYY; transient'}, {'source': 'scheme_code + option_code', 'target': 'scheme.optionCode', 'transform': 'catalogue lookup'}]), 'ELIGIBILITY_CHECKED')
        self.mocks['mock_eligibility'].append({'operation_id': s[1]['operation_id'], 'response': {'beneficiary_id': ben, 'verification': verification}, 'uid': p['person_reference'], 'scheme_code': app['service_code'], 'created_at': iso(self.t), 'seeded': True})
        if outcome == 'ineligible':
            s[2]['error'] = None; return self
        # 3. Officer sanction
        self.tick(); s[2]['state'] = 'AWAITING_REVIEW'; app['status'] = 'UNDER_REVIEW'; s[2]['review'] = {'requested_at': iso(self.t), 'mode': 'manual'}
        requested = self.emit('REVIEW_REQUESTED', 'workflow', 'approval', {'result': 'AWAITING_OFFICER', 'department': s[2]['system']})
        if outcome == 'under_review': return self
        self.tick(minutes=rng.uniform(25, 60 * 52)); o = self.officer
        decided_outcome = 'REJECTED' if outcome == 'officer_rejected' else 'SANCTIONED'
        remarks = REJECT_REMARKS[self.scheme['unit']] if decided_outcome == 'REJECTED' else rng.choice(REMARKS[self.scheme['unit']])
        s[2]['review'].update(decision=decided_outcome, remarks=remarks, officer_id=o['id'], officer_name=o['name'], designation=o['designation'], decided_at=iso(self.t))
        decided = self.emit('REVIEW_DECIDED', o['id'], 'approval', {'result': decided_outcome, 'remarks': remarks, 'officer': o['name']}, requested['id'])
        if decided_outcome == 'REJECTED':
            s[2]['state'] = 'REJECTED'; s[2]['error'] = f'Rejected by the department: {remarks}'; app['status'] = 'REJECTED'
            self.emit('APPLICATION_REJECTED', o['id'], 'approval', {'result': 'REJECTED', 'remarks': remarks}, decided['id']); return self
        self.request_stage(s[2], 'review', decided['id']); self.decision(s[2], ['eligibility.status'], 'BENEFIT_ELIGIBILITY'); self.attempt(s[2], 'SUCCESS')
        apr = uid('APR'); canonical = {'benefit': {'approvalReference': apr, 'payeeReference': ben, 'amount': app['amount'], 'sanctionedBy': o['name']}}
        self.complete(s[2], 2, 'APPROVED', apr, 'approval', canonical, evidence('approval-v1', {'approval_ref': apr, 'decision': 'SANCTIONED', 'sanctioned_by': o['name']}, canonical, [{'source': 'decision', 'target': 'benefit.approvalReference', 'transform': 'SANCTIONED → approved reference'}, {'source': 'officer decision', 'target': 'benefit.sanctionedBy', 'transform': 'officer of record'}]), 'APPLICATION_APPROVED')
        self.mocks['mock_eligibility'].append({'operation_id': s[2]['operation_id'], 'response': {'approval_ref': apr, 'decision': 'SANCTIONED'}, 'sanctioned_by': o['id'], 'remarks': remarks, 'created_at': iso(self.t), 'seeded': True})
        # 4. Treasury
        self.tick()
        if outcome == 'blocked':
            consent = next(c for c in app['consents'] if c['recipient'] == 'treasury'); consent.update(state='REVOKED', revoked_at=iso(self.t))
            self.emit('CONSENT_REVOKED', p['id'], None, {'consent_id': consent['id'], 'reason': 'Applicant withdrew consent for disbursement pending a bank account correction.', 'result': 'REVOKED'})
            self.tick(); self.request_stage(s[3]); d = self.decision(s[3], ['benefit.approvalReference', 'benefit.payeeReference', 'benefit.amount'], 'BENEFIT_DISBURSEMENT', allow=False)
            s[3]['state'] = 'BLOCKED'; s[3]['error'] = d['reason']; app['status'] = 'BLOCKED'
            self.emit('POLICY_DENIED', d['actor'], 'treasury', d); return self
        self.request_stage(s[3]); self.decision(s[3], ['benefit.approvalReference', 'benefit.payeeReference', 'benefit.amount'], 'BENEFIT_DISBURSEMENT')
        body = urlencode({'operation_id': s[3]['operation_id'], 'approval_ref': apr, 'payee_ref': ben, 'amount': str(app['amount']), 'transaction_id': app['transaction_id']}).encode()
        payment = {'operation_id': s[3]['operation_id'], 'approval_ref': apr, 'payee_ref': ben, 'amount': str(app['amount']), 'transaction_id': app['transaction_id'], 'fingerprint': hashlib.sha256(body).hexdigest(), 'payment_ref': uid('PAY'), 'created_at': iso(self.t), 'seeded': True}
        failures = {'retry_scheduled': [rng.choice(['CONNECTION_FAILED', 'DOWNSTREAM_UNAVAILABLE']) for _ in range(rng.randint(1, 2))], 'reconciling': ['TIMEOUT'], 'human_intervention': ['DOWNSTREAM_UNAVAILABLE', 'DOWNSTREAM_UNAVAILABLE', 'CONNECTION_FAILED', 'DOWNSTREAM_UNAVAILABLE']}.get(outcome, [])
        for n, code in enumerate(failures):
            a = self.attempt(s[3], code, FAILURES[code])
            state = 'HUMAN_INTERVENTION_REQUIRED' if n == 3 else 'RECONCILING' if code == 'TIMEOUT' else 'RETRY_SCHEDULED'
            s[3]['state'] = state; app['status'] = state
            app['next_retry_at'] = None if state == 'HUMAN_INTERVENTION_REQUIRED' else iso(datetime.now(timezone.utc) + timedelta(hours=rng.uniform(1, 14)))
            self.emit('INTEGRATION_FAILED', 'connector:treasury', 'treasury', {'result': code, 'attempt_id': a['id'], 'retryable': True})
            self.emit('HUMAN_INTERVENTION_REQUIRED' if state == 'HUMAN_INTERVENTION_REQUIRED' else 'RETRY_SCHEDULED', 'recovery', 'treasury', {'result': state, 'next_retry_at': app['next_retry_at']})
            if n < len(failures) - 1:
                self.tick(minutes=15 * (2 ** n)); e = self.emit('RETRY_STARTED', 'service:recovery', 'treasury', {'reason': 'Scheduled recovery dispatch', 'operation_id': s[3]['operation_id'], 'idempotency_key': None}); self.request_stage(s[3], 'recovery', e['id']); app['status'] = 'RETRYING'
        if outcome == 'reconciling': self.mocks['mock_payments'].append(payment)
        if failures: return self
        self.attempt(s[3], 'SUCCESS'); canonical = {'payment': {'reference': payment['payment_ref'], 'status': 'COMPLETED'}}
        self.complete(s[3], 3, 'COMPLETED', payment['payment_ref'], 'payment', canonical, evidence('treasury-v1', {'payment_ref': payment['payment_ref'], 'state': 'DISBURSED', 'format': 'XML'}, canonical, [{'source': '/payment/payment_ref', 'target': 'payment.reference', 'transform': 'safe XML extraction'}, {'source': '/payment/state', 'target': 'payment.status', 'transform': 'DISBURSED → COMPLETED'}]), 'PAYMENT_COMPLETED')
        self.mocks['mock_payments'].append(payment); app['next_retry_at'] = None
        self.emit('APPLICATION_COMPLETED', 'workflow', None, {'result': 'COMPLETED'})
        return self

def make_people(rng, count, min_age, max_age, start):
    people = []
    for i in range(count):
        n = start + i; first, last = rng.choice(FIRST), rng.choice(LAST)
        dob = datetime.now(timezone.utc).date() - timedelta(days=int(rng.uniform(min_age, max_age) * 365.25 + rng.randint(0, 300)))
        people.append({'id': f'USR-SYN-{n:03d}', 'email': f'{first.lower()}.{last.lower()}{n}@synthetic.demo.in', 'name': f'{first} {last}', 'role': 'citizen', 'department': None, 'subject': f'SYN-CITIZEN-{n:03d}', 'person_reference': f'PERSON-SYN-{n:03d}', 'active': False, 'password_hash': '!', 'synthetic': True, 'citizen_id': f'CID-{7000 + n}', 'date_of_birth': dob.isoformat()})
    return people

async def seed_dataset(reset=False, seed=26129):
    if not DEMO: return {'seeded': 0}
    if reset:
        for c in ('applications', 'mock_registry', 'mock_eligibility', 'mock_payments', 'demo_scenarios', 'notification_reads'): await db[c].delete_many({})
        await db.users.delete_many({'synthetic': True}); await db.mock_people.delete_many({'synthetic': True})
    elif await db.applications.find_one({'seeded': True}, {'_id': 0, 'id': 1}): return {'seeded': 0, 'skipped': True}
    rng = random.Random(seed); now = datetime.now(timezone.utc)
    young, farmers, outliers = make_people(rng, 36, 18, 29, 1), make_people(rng, 24, 31, 62, 101), make_people(rng, 6, 37, 52, 201)
    for person in young + farmers + outliers:
        await db.users.update_one({'id': person['id']}, {'$set': {k: v for k, v in person.items() if k not in ('citizen_id', 'date_of_birth')}}, upsert=True)
        await db.mock_people.update_one({'subject': person['subject']}, {'$set': {'subject': person['subject'], 'citizen_id': person['citizen_id'], 'date_of_birth': person['date_of_birth'], 'status': 'VERIFIED', 'created_at': now.isoformat(), 'synthetic': True}}, upsert=True)
    officers = {OFFICERS[i]['unit']: {'id': i, 'name': name, 'designation': OFFICERS[i]['designation']} for i, _, name, role, *_ in ACCOUNTS if role == 'official'}
    outcomes = [o for o, n in MIX for _ in range(n)]; rng.shuffle(outcomes); schemes = list(SCHEMES.values())
    pending = {u: 0 for u in officers}; docs, mocks = [], {'mock_registry': [], 'mock_eligibility': [], 'mock_payments': []}
    def keep(b):
        docs.append(b.app)
        for k, v in b.mocks.items(): mocks[k].extend(v)
    # The two sign-in demo citizens get a small personal history so their portal is not empty.
    for user_id, cid, dob, journeys in (('USR-CITIZEN', 'CID-9281', '2004-08-19', [('completed', 0, 38), ('completed', 1, 21), ('under_review', 2, 1.2)]), ('USR-CITIZEN-2', 'CID-9282', '2002-03-11', [('completed', 0, 30), ('officer_rejected', 1, 9)])):
        u = await db.users.find_one({'id': user_id}, {'_id': 0})
        if not u: continue
        for outcome, index, days in journeys:
            scheme = schemes[index]; created = now - timedelta(days=days)
            if outcome == 'under_review': pending[scheme['unit']] += 1
            keep(Builder(rng, {**u, 'citizen_id': cid, 'date_of_birth': dob}, scheme, rng.choice(list(scheme['options'])), 'Pune', created, officers[scheme['unit']]).build(outcome))
    for outcome in outcomes:
        if outcome == 'under_review':
            unit = min(pending, key=lambda u: (pending[u], rng.random())); scheme = next(s for s in schemes if s['unit'] == unit); pending[unit] += 1
        elif outcome == 'ineligible': scheme = rng.choice(schemes[:2])
        else: scheme = rng.choice(schemes)
        pool = outliers if outcome == 'ineligible' else farmers if scheme['unit'] == 'agriculture' and rng.random() < 0.8 else young
        person = rng.choice(pool)
        days = rng.uniform(0.02, 5) if outcome == 'under_review' else rng.uniform(0.5, 12) if outcome in ('retry_scheduled', 'reconciling', 'human_intervention', 'blocked') else rng.uniform(1, 60)
        created = now - timedelta(days=days)
        b = Builder(rng, person, scheme, rng.choice(list(scheme['options'])), rng.choice(DISTRICTS), created, officers[scheme['unit']]).build(outcome)
        keep(b)
    if docs: await db.applications.insert_many(docs)
    for k, v in mocks.items():
        if v: await db[k].insert_many(v)
    return {'seeded': len(docs), 'people': len(young) + len(farmers) + len(outliers)}
