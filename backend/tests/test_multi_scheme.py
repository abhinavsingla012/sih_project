"""
Samanvay Multi-Scheme + Officer Scoping + Seeded History regression tests.
Covers iteration 9 review request items 1, 4 (backend), 6, 8, 9 (backend part), 10 (auth suite is run separately).
"""
import os
import time
import uuid
import pytest
import httpx

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://txn-orchestrate.preview.emergentagent.com").rstrip("/")
ORIGIN = BASE
PWD = "Demo@2026!"

OPERATOR = "operator@demo.in"
CITIZEN = "citizen@demo.in"
SKILL_OFF = "official@demo.in"
SJSA_OFF = "sjsa@demo.in"
AGRI_OFF = "agri@demo.in"

SCHEMES = ["MH_SKILL_BENEFIT", "MH_POST_MATRIC_SCHOLARSHIP", "MH_DRIP_IRRIGATION_SUBSIDY"]
AMOUNTS = {"MH_SKILL_BENEFIT": 15000, "MH_POST_MATRIC_SCHOLARSHIP": 25000, "MH_DRIP_IRRIGATION_SUBSIDY": 40000}


def _login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD},
               headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    csrf = c.cookies.get("samanvay_csrf")
    c.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    return c


def _idem():
    return f"itest-{uuid.uuid4().hex}"


def _digilocker_grant(cit, docs, application_id=None):
    """Simulated OAuth 2.0 authorization-code flow: authorize -> allow -> requester callback -> grant id."""
    state = uuid.uuid4().hex; scope = ",".join(docs)
    r = cit.get("/api/mock/digilocker/oauth2/1/authorize", params={"client_id": "sampark", "scope": scope, "state": state})
    assert r.status_code == 200, r.text
    d = cit.post("/api/mock/digilocker/oauth2/1/authorize/decision", json={"state": state, "scope": scope, "decision": "allow"}).json()
    body = {"code": d["code"], "state": state}
    if application_id: body["application_id"] = application_id
    r = cit.post("/api/digilocker/callback", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _wait(client, txn, statuses, timeout=25):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        r = client.get(f"/api/transactions/{txn}")
        if r.status_code == 200:
            last = r.json()
            if last["status"] in statuses:
                return last
        time.sleep(1.5)
    raise AssertionError(f"txn {txn} did not reach {statuses}; last={last and last.get('status')}")


@pytest.fixture(scope="module")
def op():
    c = _login(OPERATOR); yield c; c.close()


@pytest.fixture(scope="module")
def cit():
    c = _login(CITIZEN); yield c; c.close()


@pytest.fixture(scope="module")
def sjsa():
    c = _login(SJSA_OFF); yield c; c.close()


@pytest.fixture(scope="module")
def agri():
    c = _login(AGRI_OFF); yield c; c.close()


@pytest.fixture(scope="module")
def skill():
    c = _login(SKILL_OFF); yield c; c.close()


# ---------- Catalogue ----------

def test_services_returns_three_schemes(cit):
    r = cit.get("/api/services")
    assert r.status_code == 200
    items = r.json()["items"] if isinstance(r.json(), dict) and "items" in r.json() else r.json()
    codes = [s["code"] for s in items]
    for c in SCHEMES:
        assert c in codes, f"scheme {c} missing"
    for s in items:
        if s["code"] in AMOUNTS:
            assert s["amount"] == AMOUNTS[s["code"]]
            assert "districts" in s and "Pune" in s["districts"]
            assert len(s["districts"]) == 18
            assert "options" in s and isinstance(s["options"], list) and len(s["options"]) >= 3
            for o in s["options"]:
                assert "code" in o and "label" in o
            stages = s["stages"]
            stage_by_id = {st["id"]: st for st in stages}
            assert stage_by_id["identity"]["system"] == "State Resident Registry"
            assert stage_by_id["treasury"]["system"] == "State Treasury"
            assert stage_by_id["eligibility"]["system"] == s["system"]
            assert stage_by_id["approval"]["system"] == s["system"]


# ---------- Officer scoping ----------

def _pending_ids(client):
    r = client.get("/api/reviews?state=pending")
    assert r.status_code == 200
    return r.json()["items"]


def test_officer_scoping_sjsa_sees_only_scholarship(sjsa):
    items = _pending_ids(sjsa)
    assert len(items) >= 1
    for it in items:
        assert it.get("service_code") == "MH_POST_MATRIC_SCHOLARSHIP" or \
               "Post-matric" in (it.get("service_name") or "")


def test_officer_scoping_agri_sees_only_drip(agri):
    items = _pending_ids(agri)
    assert len(items) >= 1
    for it in items:
        assert it.get("service_code") == "MH_DRIP_IRRIGATION_SUBSIDY" or \
               "Drip" in (it.get("service_name") or "")


def test_officer_scoping_skill_sees_only_skill(skill):
    items = _pending_ids(skill)
    assert len(items) >= 1
    for it in items:
        assert it.get("service_code") == "MH_SKILL_BENEFIT" or \
               "Skill" in (it.get("service_name") or "")


def test_skill_officer_gets_404_on_scholarship_txn(skill, sjsa):
    # Find a scholarship txn from sjsa pending
    items = _pending_ids(sjsa)
    assert items, "no scholarship pending"
    txn = items[0]["transaction_id"]
    r = skill.get(f"/api/transactions/{txn}")
    assert r.status_code == 404
    r2 = skill.post(f"/api/reviews/{txn}/decision",
                    json={"decision": "SANCTION", "remarks": "cross-department attempt", "version": 1})
    assert r2.status_code == 404


# ---------- Full citizen->officer flow for scholarship (25000) ----------

def test_scholarship_end_to_end(cit, sjsa, op):
    # Create scholarship application as citizen
    payload = {
        "service_code": "MH_POST_MATRIC_SCHOLARSHIP",
        "option_code": "UG",
        "district": "Nagpur",
        "digilocker_grant": _digilocker_grant(cit, ["ADHAR", "CRCER", "INCER"])["grant_id"],
        "eligibility_consent": True,
        "payment_consent": True,
    }
    r = cit.post("/api/applications", json=payload, headers={"Idempotency-Key": _idem()})
    assert r.status_code in (200, 201), r.text
    app = r.json()
    txn = app["transaction_id"]

    view = _wait(op, txn, {"UNDER_REVIEW"}, timeout=30)
    approval = next(s for s in view["stages"] if s["id"] == "approval")
    assert approval["state"] == "AWAITING_REVIEW"

    # sjsa sanctions
    ov = sjsa.get(f"/api/transactions/{txn}").json()
    dec = sjsa.post(f"/api/reviews/{txn}/decision", json={
        "decision": "SANCTION",
        "remarks": "Scholarship documents verified, sanctioning as per scheme guidelines.",
        "version": ov["version"],
    })
    assert dec.status_code == 200, dec.text

    completed = _wait(op, txn, {"COMPLETED"}, timeout=40)
    ev = op.get(f"/api/transactions/{txn}/payment-evidence").json()
    assert ev["disbursement_count"] == 1
    # Amount check
    canonical = completed.get("canonical", {})
    benefit_amt = canonical.get("benefit", {}).get("amount") or canonical.get("payment", {}).get("amount")
    assert benefit_amt == 25000, f"amount was {benefit_amt}"


# ---------- Submit without consent -> validation ----------

def test_application_without_consent_rejected(cit):
    r = cit.post("/api/applications", json={
        "service_code": "MH_DRIP_IRRIGATION_SUBSIDY",
        "option_code": "COTTON",
        "district": "Pune",
        "eligibility_consent": False,
        "payment_consent": True,
    }, headers={"Idempotency-Key": _idem()})
    assert r.status_code in (400, 422), r.text


# ---------- Seeded history sanity ----------

def test_monitoring_overview_has_three_schemes(op):
    r = op.get("/api/monitoring/overview")
    assert r.status_code == 200
    data = r.json()
    assert data.get("total", 0) >= 30  # ~36 seeded ± test creations
    by_scheme = data.get("by_scheme") or []
    codes = [b.get("code") for b in by_scheme]
    for c in SCHEMES:
        assert c in codes, f"missing {c} in by_scheme"


def test_applications_by_status_seeded(op):
    for status in ["COMPLETED", "UNDER_REVIEW", "REJECTED", "RETRY_SCHEDULED",
                   "RECONCILING", "HUMAN_INTERVENTION_REQUIRED", "BLOCKED"]:
        r = op.get(f"/api/applications?status={status}&limit=100")
        assert r.status_code == 200, f"{status}: {r.status_code}"
        items = r.json().get("items", [])
        assert len(items) >= 1, f"no seeded {status}"


def test_seeded_completed_has_full_evidence(op):
    r = op.get("/api/applications?status=COMPLETED&limit=100")
    items = r.json()["items"]
    # find one not owned by Aditi/Rohan
    target = None
    for a in items:
        owner = (a.get("owner_name") or "").lower()
        if "aditi" not in owner and "rohan" not in owner:
            target = a
            break
    assert target, "no non-Aditi/Rohan COMPLETED seed"
    txn = target["transaction_id"]
    view = op.get(f"/api/transactions/{txn}").json()
    stages = view["stages"]
    assert len(stages) == 5
    for st in stages:
        assert st["state"] == "COMPLETED", f"stage {st['id']} state={st['state']}"
        assert st.get("evidence"), f"stage {st['id']} missing evidence"
        ev = st["evidence"]
        assert "mapping_version" in ev
        assert "canonical_output" in ev
        assert "lineage" in ev
        assert st.get("attempts"), f"stage {st['id']} missing attempts"
        for at in st["attempts"]:
            assert "duration_ms" in at
    events = view.get("events", [])
    assert len(events) >= 14
    seqs = [e["sequence"] for e in events]
    assert seqs == sorted(seqs), "events not ordered"
    assert any(e.get("kind") == "REVIEW_DECIDED" or "REVIEW_DECIDED" in str(e) for e in events)
    mappings = view.get("mappings", [])
    assert len(mappings) == 5
    ev = op.get(f"/api/transactions/{txn}/payment-evidence").json()
    assert ev["disbursement_count"] == 1


def test_seeded_rejected_has_decision(op):
    r = op.get("/api/applications?status=REJECTED&limit=50")
    items = r.json()["items"]
    assert items
    txn = items[0]["transaction_id"]
    v = op.get(f"/api/transactions/{txn}").json()
    approval = next(s for s in v["stages"] if s["id"] == "approval")
    assert approval.get("review", {}).get("decision") == "REJECTED"
    assert approval["review"].get("remarks")


# ---------- Demo journey with scheme ----------

def test_demo_journey_with_drip_success(op):
    r = op.post("/api/demo/journeys", json={
        "scenario": "success", "service_code": "MH_DRIP_IRRIGATION_SUBSIDY",
        "option_code": "COTTON", "review": "auto"
    }, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 201, r.text
    txn = r.json()["transaction_id"]
    v = _wait(op, txn, {"COMPLETED"}, timeout=30)
    ev = op.get(f"/api/transactions/{txn}/payment-evidence").json()
    assert ev["disbursement_count"] == 1
    canonical = v.get("canonical", {})
    amt = canonical.get("benefit", {}).get("amount") or canonical.get("payment", {}).get("amount")
    assert amt == 40000


def test_demo_journey_treasury_unavailable_scholarship(op):
    r = op.post("/api/demo/journeys", json={
        "scenario": "treasury_unavailable", "service_code": "MH_POST_MATRIC_SCHOLARSHIP",
        "option_code": "UG", "review": "auto"
    }, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 201, r.text
    txn = r.json()["transaction_id"]
    v = _wait(op, txn, {"RETRY_SCHEDULED", "RECONCILING", "HUMAN_INTERVENTION_REQUIRED"}, timeout=40)
    assert v["status"] in {"RETRY_SCHEDULED", "RECONCILING", "HUMAN_INTERVENTION_REQUIRED"}


# ---------- Policy probe purpose ----------

def test_policy_rule_uses_benefit_eligibility(op):
    r = op.get("/api/policy/rules")
    if r.status_code == 404:
        pytest.skip("no policy rules endpoint")
    assert r.status_code == 200
    rules = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    found = False
    for rl in rules:
        if "eligibility" in (rl.get("id") or "").lower() or "eligibility" in (rl.get("name") or "").lower():
            found = True
            # purpose should relate to BENEFIT_ELIGIBILITY
            purpose = rl.get("purpose") or ""
            assert "ELIGIBILITY" in purpose.upper() or "Benefit Eligibility" in purpose, f"purpose={purpose}"
    assert found, "no eligibility rule found"


# ---------- Reset demo dataset auth ----------

def test_reset_demo_forbidden_for_citizen(cit):
    r = cit.post("/api/demo/dataset/reset", json={}, headers={"Idempotency-Key": _idem()})
    assert r.status_code == 403
