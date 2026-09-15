from core.errors import fail
from core.database import now, uid
DEPARTMENTS = {'registry', 'eligibility', 'treasury'}
FIELD_RULES = {
    'registry': {'IDENTITY_VERIFICATION': {'identity.subjectReference'}},
    'eligibility': {'SKILL_BENEFIT_ELIGIBILITY': {'person.dateOfBirth', 'identity.verificationStatus', 'person.globalReference', 'course.code', 'eligibility.status'}},
    'treasury': {'BENEFIT_DISBURSEMENT': {'benefit.approvalReference', 'benefit.payeeReference', 'benefit.amount'}},
}
def visibility(user):
    if user.role == 'citizen': return {'owner_id': user.id}
    if user.role in ('operator', 'auditor'): return {}
    if user.role in ('official', 'service') and user.department in DEPARTMENTS:
        return {'departments': user.department}
    return {'owner_id': '__denied__'}
def authorize(user, action, app=None):
    permissions = {'create': {'citizen'}, 'operate': {'operator'}, 'inspect': {'operator', 'auditor', 'official'}, 'read': {'citizen', 'operator', 'auditor', 'official', 'service'}, 'data_access': {'service'}, 'revoke': {'citizen'}, 'review': {'official'}}
    if user.role not in permissions.get(action, set()): fail(403, 'FORBIDDEN', 'Your role cannot perform this action.')
    if app and user.role == 'citizen' and app['owner_id'] != user.id: fail(404, 'NOT_FOUND', 'Application not found.')
def exchange_decision(app, department, fields, purpose):
    allowed_fields = FIELD_RULES.get(department, {}).get(purpose, set())
    consent = next((c for c in app['consents'] if c['recipient'] == department and c['purpose'] == purpose and c['state'] == 'ACTIVE' and c['expires_at'] > now()), None)
    consent_ok = department == 'registry' or bool(consent and set(fields).issubset(set(consent['fields'])))
    allowed = set(fields).issubset(allowed_fields) and consent_ok
    return {'id': uid('DEC'), 'decision': 'ALLOW' if allowed else 'DENY', 'actor': f'service:{department}', 'department': department, 'fields': fields, 'purpose': purpose, 'policy_version': 'field-policy-v1', 'consent_id': consent['id'] if consent else None, 'reason': 'Purpose and field scope permitted' if allowed else 'Field scope or active consent does not permit this exchange', 'timestamp': now()}