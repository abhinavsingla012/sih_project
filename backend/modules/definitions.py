"""Pinned, inspectable demo contracts. No executable mapping expressions."""
STAGES = [
    {'id': 'identity', 'name': 'Identity verification', 'system': 'Citizen Registry', 'connector': 'registry', 'event': 'IDENTITY_VERIFIED', 'purpose': 'IDENTITY_VERIFICATION', 'fields': ['identity.subjectReference']},
    {'id': 'eligibility', 'name': 'Eligibility check', 'system': 'Skill Development', 'connector': 'eligibility', 'event': 'ELIGIBILITY_CHECKED', 'purpose': 'SKILL_BENEFIT_ELIGIBILITY', 'fields': ['person.dateOfBirth', 'identity.verificationStatus', 'person.globalReference', 'course.code']},
    {'id': 'approval', 'name': 'Department approval', 'system': 'Skill Development', 'connector': 'approval', 'event': 'APPLICATION_APPROVED', 'purpose': 'SKILL_BENEFIT_ELIGIBILITY', 'fields': ['eligibility.status'], 'review': True},
    {'id': 'treasury', 'name': 'Benefit disbursement', 'system': 'State Treasury', 'connector': 'treasury', 'event': 'PAYMENT_COMPLETED', 'purpose': 'BENEFIT_DISBURSEMENT', 'fields': ['benefit.approvalReference', 'benefit.payeeReference', 'benefit.amount']},
]
CONNECTORS = [
    {'id':'registry','name':'Citizen Registry','department':'Department A','description':'Citizen identity verification','protocol':'REST / JSON','auth':'API key','schema_version':'registry-v1','identifier':'citizenId','status_field':'status','status_value':'VERIFIED','canonical_status':'VERIFIED','color':'teal','endpoint':'/api/mock/registry/verify'},
    {'id':'eligibility','name':'Skill Development','department':'Department B','description':'Eligibility and benefit approval','protocol':'REST / JSON','auth':'Scoped bearer token','schema_version':'eligibility-v1','identifier':'beneficiary_id','status_field':'verification','status_value':'SUCCESS','canonical_status':'ELIGIBLE','color':'blue','endpoint':'/api/mock/eligibility/check'},
    {'id':'treasury','name':'State Treasury','department':'Department C','description':'Idempotent benefit disbursement','protocol':'Form / XML','auth':'HMAC signature','schema_version':'treasury-v1','identifier':'payment_ref','status_field':'state','status_value':'DISBURSED','canonical_status':'COMPLETED','color':'amber','endpoint':'/api/mock/treasury/disburse'},
]
MAPPINGS = [
    {'id':'registry-v1','connector':'registry','source':'Citizen Registry','target':'Canonical v1','rows':[
        {'source':'citizenId','target':'identity.externalReference','transform':'reference','example_in':'CID-9281','example_out':'CID-9281'},
        {'source':'dob','target':'person.dateOfBirth','transform':'ISO date validation · transient','example_in':'2004-08-19','example_out':'2004-08-19'},
        {'source':'status','target':'identity.verificationStatus','transform':'enum: VERIFIED → VERIFIED','example_in':'VERIFIED','example_out':'VERIFIED'}]},
    {'id':'eligibility-v1','connector':'eligibility','source':'Skill Development','target':'Canonical v1','rows':[
        {'source':'beneficiary_id','target':'eligibility.beneficiaryReference','transform':'reference','example_in':'BEN-2201','example_out':'BEN-2201'},
        {'source':'verification','target':'eligibility.status','transform':'enum: SUCCESS → ELIGIBLE','example_in':'SUCCESS','example_out':'ELIGIBLE'},
        {'source':'birth_date','target':'person.dateOfBirth','transform':'DD/MM/YYYY ↔ ISO · transient','example_in':'19/08/2004','example_out':'2004-08-19'}]},
    {'id':'treasury-v1','connector':'treasury','source':'State Treasury','target':'Canonical v1','rows':[
        {'source':'/payment/payment_ref','target':'payment.reference','transform':'safe XML extraction','example_in':'PAY-7219','example_out':'PAY-7219'},
        {'source':'/payment/state','target':'payment.status','transform':'enum: DISBURSED → COMPLETED','example_in':'DISBURSED','example_out':'COMPLETED'}]},
]