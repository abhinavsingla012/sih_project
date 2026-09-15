"""Pinned, inspectable demo contracts. No executable mapping expressions."""
DISTRICTS = ['Pune', 'Mumbai City', 'Mumbai Suburban', 'Thane', 'Nagpur', 'Nashik', 'Chhatrapati Sambhajinagar', 'Solapur', 'Kolhapur', 'Amravati', 'Satara', 'Sangli', 'Jalgaon', 'Ahmednagar', 'Latur', 'Nanded', 'Ratnagiri', 'Wardha']
SCHEMES = {
    'MH_SKILL_BENEFIT': {'code': 'MH_SKILL_BENEFIT', 'name': 'Skill development training benefit', 'unit': 'skill', 'department': 'Skill Development & Entrepreneurship', 'system': 'Skill Development', 'amount': 15000, 'description': 'Training support for citizens enrolling in an approved skilling programme.', 'eligibility': 'Age 18–35 · verified identity · approved training programme', 'min_age': 18, 'max_age': 35, 'option_label': 'Training programme', 'options': {'DATA_ANALYTICS': 'Data analytics', 'ELECTRIC_VEHICLES': 'Electric vehicle maintenance', 'WEB_DEVELOPMENT': 'Web development', 'SOLAR_TECHNICIAN': 'Solar technician'}, 'icon': 'graduation'},
    'MH_POST_MATRIC_SCHOLARSHIP': {'code': 'MH_POST_MATRIC_SCHOLARSHIP', 'name': 'Post-matric scholarship', 'unit': 'social_justice', 'department': 'Social Justice & Special Assistance', 'system': 'Social Justice', 'amount': 25000, 'description': 'Maintenance and fee support for students continuing education after Class 10.', 'eligibility': 'Age 16–30 · enrolled at a recognised institution', 'min_age': 16, 'max_age': 30, 'option_label': 'Course level', 'options': {'HSC': 'Higher secondary (Class 11–12)', 'DIPLOMA': 'Diploma', 'UG': 'Undergraduate degree', 'PG': 'Postgraduate degree'}, 'icon': 'book'},
    'MH_DRIP_IRRIGATION_SUBSIDY': {'code': 'MH_DRIP_IRRIGATION_SUBSIDY', 'name': 'Drip irrigation subsidy', 'unit': 'agriculture', 'department': 'Agriculture', 'system': 'Agriculture', 'amount': 40000, 'description': 'Capital subsidy for installing micro-irrigation on cultivated farmland.', 'eligibility': 'Age 18–70 · registered landholder · crop under micro-irrigation', 'min_age': 18, 'max_age': 70, 'option_label': 'Crop', 'options': {'SUGARCANE': 'Sugarcane', 'COTTON': 'Cotton', 'GRAPES': 'Grapes', 'POMEGRANATE': 'Pomegranate', 'SOYBEAN': 'Soybean'}, 'icon': 'sprout'},
}
UNITS = {s['unit']: s['department'] for s in SCHEMES.values()}
STAGES = [
    {'id': 'identity', 'name': 'Identity verification', 'system': 'State Resident Registry', 'connector': 'registry', 'event': 'IDENTITY_VERIFIED', 'purpose': 'IDENTITY_VERIFICATION', 'fields': ['identity.subjectReference']},
    {'id': 'eligibility', 'name': 'Eligibility check', 'system': 'Line department', 'connector': 'eligibility', 'event': 'ELIGIBILITY_CHECKED', 'purpose': 'BENEFIT_ELIGIBILITY', 'fields': ['person.dateOfBirth', 'identity.verificationStatus', 'person.globalReference', 'scheme.optionCode']},
    {'id': 'approval', 'name': 'Department sanction', 'system': 'Line department', 'connector': 'approval', 'event': 'APPLICATION_APPROVED', 'purpose': 'BENEFIT_ELIGIBILITY', 'fields': ['eligibility.status'], 'review': True},
    {'id': 'treasury', 'name': 'Benefit disbursement', 'system': 'State Treasury', 'connector': 'treasury', 'event': 'PAYMENT_COMPLETED', 'purpose': 'BENEFIT_DISBURSEMENT', 'fields': ['benefit.approvalReference', 'benefit.payeeReference', 'benefit.amount']},
]
CONNECTORS = [
    {'id':'registry','name':'State Resident Registry','department':'Identity authority','description':'Citizen identity verification','protocol':'REST / JSON','auth':'API key','schema_version':'registry-v1','identifier':'citizenId','status_field':'status','status_value':'VERIFIED','canonical_status':'VERIFIED','color':'teal','endpoint':'/api/mock/registry/verify'},
    {'id':'eligibility','name':'Line department systems','department':'Skill Development · Social Justice · Agriculture','description':'Scheme eligibility and officer sanction','protocol':'REST / JSON','auth':'Scoped bearer token','schema_version':'eligibility-v1','identifier':'beneficiary_id','status_field':'verification','status_value':'SUCCESS','canonical_status':'ELIGIBLE','color':'blue','endpoint':'/api/mock/eligibility/check'},
    {'id':'treasury','name':'State Treasury (DBT)','department':'Finance department','description':'Idempotent direct benefit transfer','protocol':'Form / XML','auth':'HMAC signature','schema_version':'treasury-v1','identifier':'payment_ref','status_field':'state','status_value':'DISBURSED','canonical_status':'COMPLETED','color':'amber','endpoint':'/api/mock/treasury/disburse'},
]
MAPPINGS = [
    {'id':'registry-v1','connector':'registry','source':'State Resident Registry','target':'Canonical v1','rows':[
        {'source':'citizenId','target':'identity.externalReference','transform':'reference','example_in':'CID-9281','example_out':'CID-9281'},
        {'source':'dob','target':'person.dateOfBirth','transform':'ISO date validation · transient','example_in':'2004-08-19','example_out':'2004-08-19'},
        {'source':'status','target':'identity.verificationStatus','transform':'enum: VERIFIED → VERIFIED','example_in':'VERIFIED','example_out':'VERIFIED'}]},
    {'id':'eligibility-v1','connector':'eligibility','source':'Line department','target':'Canonical v1','rows':[
        {'source':'beneficiary_id','target':'eligibility.beneficiaryReference','transform':'reference','example_in':'BEN-2201','example_out':'BEN-2201'},
        {'source':'verification','target':'eligibility.status','transform':'enum: SUCCESS → ELIGIBLE','example_in':'SUCCESS','example_out':'ELIGIBLE'},
        {'source':'birth_date','target':'person.dateOfBirth','transform':'DD/MM/YYYY ↔ ISO · transient','example_in':'19/08/2004','example_out':'2004-08-19'},
        {'source':'scheme_code + option_code','target':'scheme.optionCode','transform':'scheme catalogue lookup','example_in':'MH_SKILL_BENEFIT / DATA_ANALYTICS','example_out':'DATA_ANALYTICS'}]},
    {'id':'treasury-v1','connector':'treasury','source':'State Treasury','target':'Canonical v1','rows':[
        {'source':'/payment/payment_ref','target':'payment.reference','transform':'safe XML extraction','example_in':'PAY-7219','example_out':'PAY-7219'},
        {'source':'/payment/state','target':'payment.status','transform':'enum: DISBURSED → COMPLETED','example_in':'DISBURSED','example_out':'COMPLETED'}]},
]
def stage_templates(scheme):
    return [{**s, 'system': scheme['system'] if s['connector'] in ('eligibility', 'approval') else s['system']} for s in STAGES]
