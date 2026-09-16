"""
Simulated DigiLocker document verification: pause on missing documents, citizen consent round trip, resume, masked officer preview.
Run: cd /app/backend && python -m pytest tests/test_digilocker.py -v
"""
import os
import time
import uuid
import pytest
import httpx

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://txn-orchestrate.preview.emergentagent.com").rstrip("/")
PWD = "Demo@2026!"
SCHOLARSHIP_DOCS = ["ADHAR", "CRCER", "INCER"]


def _login(email):
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD}, headers={"Origin": BASE, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    c.headers.update({"Origin": BASE, "X-CSRF-Token": c.cookies.get("samanvay_csrf")})
    return c


def _idem():
    return f"dl-{uuid.uuid4().hex}"


def _wait(client, path, statuses, timeout=30):
    end = time.time() + timeout; last = None
    while time.time() < end:
        r = client.get(path)
        if r.status_code == 200:
            last = r.json()
            if last["status"] in statuses: return last
        time.sleep(1.5)
    raise AssertionError(f"{path} did not reach {statuses}; last={last and last.get('status')}")


def _authorize(cit, docs, state=None):
    state = state or uuid.uuid4().hex; scope = ",".join(docs)
    r = cit.get("/api/mock/digilocker/oauth2/1/authorize", params={"client_id": "sampark", "scope": scope, "state": state})
    assert r.status_code == 200, r.text
    return r.json(), state, scope


def _grant(cit, docs, application_id=None):
    _, state, scope = _authorize(cit, docs)
    d = cit.post("/api/mock/digilocker/oauth2/1/authorize/decision", json={"state": state, "scope": scope, "decision": "allow"}).json()
    assert d.get("code"), d
    body = {"code": d["code"], "state": state}
    if application_id: body["application_id"] = application_id
    r = cit.post("/api/digilocker/callback", json=body)
    assert r.status_code == 200, r.text
    return r.json(), d["code"], state


@pytest.fixture(scope="module")
def op():
    c = _login("operator@demo.in"); yield c
    # Leave the jury demo pristine: Rohan's income certificate is re-removed and his paused scholarship is re-seeded.
    c.post("/api/demo/dataset/reset"); c.close()


@pytest.fixture(scope="module")
def aditi():
    c = _login("citizen@demo.in"); yield c; c.close()


@pytest.fixture(scope="module")
def rohan():
    c = _login("rohan@demo.in"); yield c; c.close()


@pytest.fixture(scope="module")
def sjsa():
    c = _login("sjsa@demo.in"); yield c; c.close()


@pytest.fixture(scope="module")
def skill():
    c = _login("official@demo.in"); yield c; c.close()


def test_services_expose_document_requirements(aditi):
    items = aditi.get("/api/services").json()["items"]
    by_code = {s["code"]: s for s in items}
    assert [d["code"] for d in by_code["MH_POST_MATRIC_SCHOLARSHIP"]["documents"]] == SCHOLARSHIP_DOCS
    assert [d["code"] for d in by_code["MH_SKILL_BENEFIT"]["documents"]] == ["ADHAR", "SSCER"]
    assert [d["code"] for d in by_code["MH_DRIP_IRRIGATION_SUBSIDY"]["documents"]] == ["ADHAR", "LNRCD"]
    assert [s["id"] for s in by_code["MH_SKILL_BENEFIT"]["stages"]] == ["identity", "documents", "eligibility", "approval", "treasury"]


def test_authorize_lists_locker_contents(aditi, rohan):
    a, _, _ = _authorize(aditi, SCHOLARSHIP_DOCS)
    assert a["requester"]["client_id"] == "sampark" and a["holder"]["name"] == "Aditi Patil"
    assert all(d["available"] for d in a["documents"])
    r, _, _ = _authorize(rohan, SCHOLARSHIP_DOCS)
    avail = {d["doctype"]: d["available"] for d in r["documents"]}
    assert avail == {"ADHAR": True, "CRCER": True, "INCER": False}


def test_authorize_requires_locker_owner(op):
    r = op.get("/api/mock/digilocker/oauth2/1/authorize", params={"client_id": "sampark", "scope": "ADHAR", "state": uuid.uuid4().hex})
    assert r.status_code == 403


def test_deny_returns_access_denied_without_code(aditi):
    _, state, scope = _authorize(aditi, ["ADHAR"])
    d = aditi.post("/api/mock/digilocker/oauth2/1/authorize/decision", json={"state": state, "scope": scope, "decision": "deny"}).json()
    assert d == {"error": "access_denied", "state": state}


def test_callback_rejects_replayed_code_and_state_mismatch(aditi):
    summary, code, state = _grant(aditi, ["ADHAR"])
    assert summary["grant_id"].startswith("DLG-") and summary["missing"] == []
    replay = aditi.post("/api/digilocker/callback", json={"code": code, "state": state})
    assert replay.status_code == 400 and replay.json()["error"]["code"] == "DIGILOCKER_EXCHANGE_FAILED"
    _, state2, scope2 = _authorize(aditi, ["ADHAR"])
    d = aditi.post("/api/mock/digilocker/oauth2/1/authorize/decision", json={"state": state2, "scope": scope2, "decision": "allow"}).json()
    bad = aditi.post("/api/digilocker/callback", json={"code": d["code"], "state": "x" * 32})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "STATE_MISMATCH"


def test_token_endpoint_rejects_wrong_client_secret(aditi):
    r = aditi.post("/api/mock/digilocker/oauth2/1/token", json={"grant_type": "authorization_code", "code": "nope", "client_id": "sampark", "client_secret": "wrong"})
    assert r.status_code == 401


def test_pull_requires_bearer(aditi):
    r = aditi.get("/api/mock/digilocker/oauth2/1/xml/in.gov.uidai-ADHAR-DEADBEEF00")
    assert r.status_code == 401


def test_submission_without_grant_pauses_for_all_documents(aditi, op):
    r = aditi.post("/api/applications", json={"service_code": "MH_SKILL_BENEFIT", "option_code": "WEB_DEVELOPMENT", "district": "Pune", "eligibility_consent": True, "payment_consent": True}, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 201, r.text
    app = r.json()
    view = _wait(op, f"/api/transactions/{app['transaction_id']}", {"AWAITING_DOCUMENTS"})
    docs = next(s for s in view["stages"] if s["id"] == "documents")
    assert docs["state"] == "AWAITING_DOCUMENTS" and docs["hold"]["missing"] == ["ADHAR", "SSCER"]
    assert next(s for s in view["stages"] if s["id"] == "identity")["state"] == "COMPLETED"
    # citizen later shares from the application page -> resumes
    _grant(aditi, ["ADHAR", "SSCER"], application_id=app["id"])
    resumed = _wait(op, f"/api/transactions/{app['transaction_id']}", {"UNDER_REVIEW"})
    docs = next(s for s in resumed["stages"] if s["id"] == "documents")
    assert docs["state"] == "COMPLETED" and docs["evidence"]["mapping_version"] == "digilocker-v1"
    assert resumed["canonical"]["documents"]["status"] == "VERIFIED"
    assert any(e["type"] == "DOCUMENTS_SHARED" for e in resumed["events"]) and any(e["type"] == "DOCUMENTS_VERIFIED" for e in resumed["events"])


def test_complete_grant_verifies_and_reaches_officer(aditi, sjsa, op):
    summary, _, _ = _grant(aditi, SCHOLARSHIP_DOCS)
    r = aditi.post("/api/applications", json={"service_code": "MH_POST_MATRIC_SCHOLARSHIP", "option_code": "UG", "district": "Pune", "digilocker_grant": summary["grant_id"], "eligibility_consent": True, "payment_consent": True}, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 201, r.text
    app = r.json()
    assert app["documents"]["grant_id"] == summary["grant_id"] and len(app["documents"]["shared"]) == 3
    assert any(c["recipient"] == "digilocker" for c in app["consents"])
    view = _wait(op, f"/api/transactions/{app['transaction_id']}", {"UNDER_REVIEW"})
    docs = next(s for s in view["stages"] if s["id"] == "documents")
    results = docs["evidence"]["source_summary"]["documents"]
    assert len(results) == 3 and all(d["signature"] == "VALID" and d["holder_match"] == "MATCH" for d in results)
    assert any(m["system"] == "digilocker" and m["entity_type"] == "document_grant" for m in view["mappings"])
    # officer sees documents + masked preview
    case = sjsa.get(f"/api/transactions/{app['transaction_id']}")
    assert case.status_code == 200 and case.json()["documents"]["grant_id"] == summary["grant_id"]
    uri = app["documents"]["shared"][0]["uri"]
    pv = sjsa.get(f"/api/applications/{app['id']}/documents/{uri}")
    assert pv.status_code == 200, pv.text
    body = pv.json()
    assert body["signature"] == "VALID" and body["verification"]["verified"] is True
    assert body["document"]["holder"]["dob"].startswith("XXXX-XX-") and body["document"]["holder"]["masked_id"].startswith("XXXX XXXX ")
    assert "note" in body


def test_auditor_preview_uses_the_case_grant_not_an_older_one(aditi):
    """Aditi's Aadhaar URI is identical across all her applications; the preview must use THIS case's grant, not an expired seeded one."""
    auditor = _login("auditor@demo.in")
    fresh = next(a for a in aditi.get("/api/applications").json()["items"] if a.get("documents") and a["status"] in ("UNDER_REVIEW", "PROCESSING", "COMPLETED") and a["created_at"] > time.strftime("%Y-%m-%dT00:00"))
    detail = aditi.get(f"/api/applications/{fresh['id']}").json()
    uri = next(d for d in detail["documents"]["shared"] if d["doctype"] == "ADHAR")["uri"]
    r = auditor.get(f"/api/applications/{fresh['id']}/documents/{uri}")
    assert r.status_code == 200, r.text
    assert r.json()["signature"] == "VALID"
    auditor.close()


def test_preview_scoped_to_department_and_never_for_unknown(skill, aditi):
    apps = aditi.get("/api/applications?service_code=MH_POST_MATRIC_SCHOLARSHIP").json()["items"]
    target = next(a for a in apps if a.get("documents"))
    detail = aditi.get(f"/api/applications/{target['id']}").json()
    uri = next(d for d in detail["documents"]["shared"] if d["doctype"] == "CRCER")["uri"]  # never part of a Skill Development case
    assert skill.get(f"/api/applications/{target['id']}/documents/{uri}").status_code == 404  # skill officer cannot open a social-justice case
    sk_apps = skill.get("/api/applications").json()["items"]
    assert skill.get(f"/api/applications/{sk_apps[0]['id']}/documents/in.gov.uidai-ADHAR-NOPE000000").status_code == 404  # unknown uri on own case


def test_rohan_missing_income_certificate_pauses_then_resumes(rohan, sjsa, op):
    apps = rohan.get("/api/applications").json()["items"]
    paused = next(a for a in apps if a["status"] == "AWAITING_DOCUMENTS")
    detail = rohan.get(f"/api/applications/{paused['id']}").json()
    docs = next(s for s in detail["stages"] if s["id"] == "documents")
    assert docs["hold"]["missing"] == ["INCER"] and len(detail["documents"]["shared"]) == 2
    # Officer / operator see the hold, but nobody can decide yet
    assert op.get(f"/api/transactions/{paused['transaction_id']}").json()["status"] == "AWAITING_DOCUMENTS"
    # Issue the certificate into the locker (simulated Revenue Department push) and re-share
    issued = rohan.post("/api/mock/digilocker/issue", json={"doctype": "INCER"})
    assert issued.status_code == 200 and issued.json()["uri"].startswith("in.gov.maharashtra.revenue-INCER-")
    a, _, _ = _authorize(rohan, SCHOLARSHIP_DOCS)
    assert all(d["available"] for d in a["documents"])
    summary, _, _ = _grant(rohan, SCHOLARSHIP_DOCS, application_id=paused["id"])
    assert summary["missing"] == [] and summary["application"]["status"] in ("PROCESSING", "UNDER_REVIEW")
    view = _wait(op, f"/api/transactions/{paused['transaction_id']}", {"UNDER_REVIEW"})
    docs = next(s for s in view["stages"] if s["id"] == "documents")
    assert docs["state"] == "COMPLETED" and "hold" not in docs or docs.get("hold") is None
    assert len(docs["attempts"]) == 2 and docs["attempts"][0]["outcome"] == "INCOMPLETE" and docs["attempts"][1]["outcome"] == "SUCCESS"
    # Officer sanctions -> completes with exactly one payment
    inbox = sjsa.get("/api/reviews?state=pending").json()["items"]
    assert any(i["id"] == paused["id"] for i in inbox)
    case = sjsa.get(f"/api/transactions/{paused['transaction_id']}").json()
    incer = next(d for d in case["documents"]["shared"] if d["doctype"] == "INCER")
    pv = sjsa.get(f"/api/applications/{paused['id']}/documents/{incer['uri']}").json()
    assert pv["signature"] == "VALID" and pv["document"]["holder"]["name"] == "Rohan Shah" and "annual_income" in pv["document"]["fields"]
    dec = sjsa.post(f"/api/reviews/{paused['transaction_id']}/decision", json={"decision": "SANCTION", "remarks": "Income certificate verified via DigiLocker; sanctioned.", "version": case["version"]})
    assert dec.status_code == 200, dec.text
    done = _wait(op, f"/api/transactions/{paused['transaction_id']}", {"COMPLETED"}, timeout=40)
    assert op.get(f"/api/transactions/{paused['transaction_id']}/payment-evidence").json()["disbursement_count"] == 1
    assert done["status"] == "COMPLETED"


def test_callback_on_non_waiting_application_conflicts(aditi):
    apps = aditi.get("/api/applications?status=COMPLETED").json()["items"]
    target = apps[0]
    _, state, scope = _authorize(aditi, ["ADHAR"])
    d = aditi.post("/api/mock/digilocker/oauth2/1/authorize/decision", json={"state": state, "scope": scope, "decision": "allow"}).json()
    r = aditi.post("/api/digilocker/callback", json={"code": d["code"], "state": state, "application_id": target["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_AWAITING_DOCUMENTS"


def test_demo_journey_auto_grant_completes(op):
    r = op.post("/api/demo/journeys", json={"scenario": "success", "service_code": "MH_SKILL_BENEFIT", "review": "auto"}, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 201, r.text
    app = r.json()
    assert app["documents"] and len(app["documents"]["shared"]) == 2
    done = _wait(op, f"/api/transactions/{app['transaction_id']}", {"COMPLETED"}, timeout=40)
    assert [s["state"] for s in done["stages"]] == ["COMPLETED"] * 5


def test_notifications_include_document_events(rohan):
    types = {n["type"] for n in rohan.get("/api/notifications").json()["items"]}
    assert "DOCUMENTS_REQUIRED" in types or "DOCUMENTS_SHARED" in types or "DOCUMENTS_VERIFIED" in types
