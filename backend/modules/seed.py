import bcrypt
from core.config import setting, DEMO
from core.database import db, now
ACCOUNTS = [
    ('USR-OPERATOR', 'operator@demo.in', 'Ananya Deshmukh', 'operator', None, None),
    ('USR-CITIZEN', 'citizen@demo.in', 'Aditi Patil', 'citizen', None, 'DEMO-CITIZEN-001'),
    ('USR-CITIZEN-2', 'rohan@demo.in', 'Rohan Shah', 'citizen', None, 'DEMO-CITIZEN-002'),
    ('USR-AUDITOR', 'auditor@demo.in', 'Vikram Joshi', 'auditor', None, None),
    ('USR-OFFICIAL', 'official@demo.in', 'Meera Kulkarni', 'official', 'eligibility', None),
]
async def seed():
    if not DEMO: return
    password_hash = bcrypt.hashpw(setting('DEMO_PASSWORD').encode(), bcrypt.gensalt()).decode()
    for id_, email, name, role, department, subject in ACCOUNTS:
        await db.users.update_one({'id': id_}, {'$setOnInsert': {'id': id_, 'email': email, 'name': name, 'role': role, 'department': department, 'subject': subject, 'person_reference': f'PERSON-{id_.replace("USR-", "")}', 'active': True, 'password_hash': password_hash}}, upsert=True)
    for subject, cid, dob in [('DEMO-CITIZEN-001', 'CID-9281', '2004-08-19'), ('DEMO-CITIZEN-002', 'CID-9282', '2002-03-11')]:
        await db.mock_people.update_one({'subject': subject}, {'$setOnInsert': {'subject': subject, 'citizen_id': cid, 'date_of_birth': dob, 'status': 'VERIFIED', 'created_at': now()}}, upsert=True)