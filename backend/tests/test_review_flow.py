"""
Samanvay Officer Review Inbox - backend regression tests.
Covers: pending inbox, sanction happy path, reject path, authorization,
version conflict, remarks validation, auto-mode regression.
"""
import os
import time
import uuid
import pytest
import httpx

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://txn-orchestrate.preview.emergentagent.com").rstrip("/")
ORIGIN = BASE
PWD = "Demo@2026!"
OFFICIAL = "official@demo.in"
OPERATOR = "operator@demo.in"
CITIZEN = "citizen@demo.in"


def _login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post(
        "/api/auth/login",
        json={"email": email, "password": PWD},
        headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    csrf = c.cookies.get("samanvay_csrf")
    assert csrf, "no csrf cookie set"
    c.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    return c


def _idem() -> str:
    return f"itest-{uuid.uuid4().hex}"


def _wait_status(client: httpx.Client, txn: str, statuses, timeout=25):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        r = client.get(f"/api/transactions/{txn}")
        if r.status_code == 200:
            last = r.json()
            if last["status"] in statuses:
                return last
        time.sleep(1.5)
    raise AssertionError(f"txn {txn} did not reach {statuses}; last status={last and last.get('status')}")


@pytest.fixture(scope="module")
def op():
    c = _login(OPERATOR)
    yield c
    c.close()


@pytest.fixture(scope="module")
def off():
    c = _login(OFFICIAL)
    yield c
    c.close()


@pytest.fixture(scope="module")
def cit():
    c = _login(CITIZEN)
    yield c
    c.close()


def _create_manual_journey(op_client: httpx.Client):
    r = op_client.post(
        "/api/demo/journeys",
        json={"scenario": "success", "review": "manual"},
        headers={"Idempotency-Key": _idem()},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- Pending pause ---------------------------------------------------------

def test_manual_journey_pauses_under_review(op):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    # poll until UNDER_REVIEW (worker moves stages 1 & 2 to COMPLETED then pauses)
    end = time.time() + 25
    seen = None
    while time.time() < end:
        r = op.get(f"/api/transactions/{txn}")
        seen = r.json()
        if seen["status"] == "UNDER_REVIEW":
            break
        time.sleep(1.5)
    assert seen["status"] == "UNDER_REVIEW", f"got {seen['status']}"
    approval = next(s for s in seen["stages"] if s["id"] == "approval")
    assert approval["state"] == "AWAITING_REVIEW"
    assert approval.get("review", {}).get("mode") == "manual"
    treasury = next(s for s in seen["stages"] if s["id"] == "treasury")
    assert treasury["state"] == "PENDING"


# --- Reviews list ----------------------------------------------------------

def test_reviews_pending_lists_case(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    r = off.get("/api/reviews?state=pending")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [i["transaction_id"] for i in items]
    assert txn in ids, f"pending inbox missing {txn}: {ids}"


def test_reviews_forbidden_for_citizen(cit):
    r = cit.get("/api/reviews?state=pending")
    assert r.status_code == 403
    assert r.json().get("detail", {}).get("code") in ("FORBIDDEN", None) or "FORBIDDEN" in r.text


# --- Sanction happy path ---------------------------------------------------

def test_sanction_flow(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    initial = _wait_status(op, txn, {"UNDER_REVIEW"})

    # fetch as official for correct version
    r = off.get(f"/api/transactions/{txn}")
    assert r.status_code == 200
    version = r.json()["version"]

    dec = off.post(
        f"/api/reviews/{txn}/decision",
        json={
            "decision": "SANCTION",
            "remarks": "Eligibility and enrolment verified; sanctioned under scheme guidelines.",
            "version": version,
        },
    )
    assert dec.status_code == 200, dec.text
    body = dec.json()
    approval = next(s for s in body["stages"] if s["id"] == "approval")
    assert approval["review"]["decision"] == "SANCTIONED"
    assert approval["review"]["officer_name"] == "Meera Kulkarni"

    # wait for treasury completion
    completed = _wait_status(op, txn, {"COMPLETED"}, timeout=30)
    assert completed["status"] == "COMPLETED"
    canonical = completed.get("canonical", {})
    assert canonical.get("benefit", {}).get("sanctionedBy") == "Meera Kulkarni"

    # payment evidence
    ev = op.get(f"/api/transactions/{txn}/payment-evidence")
    assert ev.status_code == 200
    assert ev.json()["disbursement_count"] == 1


# --- Reject flow -----------------------------------------------------------

def test_reject_flow(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    r = off.get(f"/api/transactions/{txn}")
    version = r.json()["version"]
    dec = off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "REJECT", "remarks": "Documents insufficient for scheme.", "version": version},
    )
    assert dec.status_code == 200, dec.text
    body = dec.json()
    assert body["status"] == "REJECTED"
    approval = next(s for s in body["stages"] if s["id"] == "approval")
    assert approval["review"]["decision"] == "REJECTED"
    treasury = next(s for s in body["stages"] if s["id"] == "treasury")
    assert treasury["state"] == "PENDING"
    # payment evidence zero
    time.sleep(1)
    ev = op.get(f"/api/transactions/{txn}/payment-evidence")
    assert ev.status_code == 200
    assert ev.json()["disbursement_count"] == 0


# --- Authorization & validation --------------------------------------------

def test_decision_forbidden_for_operator(op):
    # create a case, try as operator to sanction
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    st = _wait_status(op, txn, {"UNDER_REVIEW"})
    version = st["version"]
    r = op.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "operator try sanction", "version": version},
    )
    assert r.status_code == 403


def test_decision_forbidden_for_citizen(cit, op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    r = cit.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "citizen sanction attempt", "version": 1},
    )
    assert r.status_code == 403
    # clean up: officer sanctions it so worker doesn't retain
    off_view = off.get(f"/api/transactions/{txn}").json()
    off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "REJECT", "remarks": "cleanup after auth test.", "version": off_view["version"]},
    )


def test_decision_remarks_too_short(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    ov = off.get(f"/api/transactions/{txn}").json()
    r = off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "hi", "version": ov["version"]},
    )
    assert r.status_code == 422
    # cleanup
    off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "REJECT", "remarks": "cleanup short-remarks test.", "version": ov["version"]},
    )


def test_decision_stale_version_conflict(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    r = off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "stale version attempt for tests.", "version": 0},
    )
    assert r.status_code == 409
    # cleanup
    ov = off.get(f"/api/transactions/{txn}").json()
    off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "REJECT", "remarks": "cleanup stale-version test.", "version": ov["version"]},
    )


def test_decision_not_reviewable_after_decision(op, off):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    ov = off.get(f"/api/transactions/{txn}").json()
    r = off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "REJECT", "remarks": "first rejection makes it not reviewable.", "version": ov["version"]},
    )
    assert r.status_code == 200
    ov2 = off.get(f"/api/transactions/{txn}").json()
    r2 = off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "trying second decision on decided case.", "version": ov2["version"]},
    )
    assert r2.status_code == 409


# --- Auto mode -------------------------------------------------------------

def test_auto_mode_completes_without_officer(op, off):
    r = op.post(
        "/api/demo/journeys",
        json={"scenario": "success", "review": "auto"},
        headers={"Idempotency-Key": _idem()},
    )
    assert r.status_code == 201
    txn = r.json()["transaction_id"]
    completed = _wait_status(op, txn, {"COMPLETED"}, timeout=45)
    assert completed["status"] == "COMPLETED"
    approval = next(s for s in completed["stages"] if s["id"] == "approval")
    assert approval["review"]["mode"] == "auto"
    assert approval["review"]["officer_name"] == "Demonstration auto-sanction"

    # not in official's decided list (manual filter)
    dec = off.get("/api/reviews?state=decided")
    assert dec.status_code == 200
    txns = [i["transaction_id"] for i in dec.json()["items"]]
    assert txn not in txns


# --- Citizen projection ----------------------------------------------------

def test_citizen_projection_hides_officer_id(op, off, cit):
    app = _create_manual_journey(op)
    txn = app["transaction_id"]
    _wait_status(op, txn, {"UNDER_REVIEW"})
    ov = off.get(f"/api/transactions/{txn}").json()
    off.post(
        f"/api/reviews/{txn}/decision",
        json={"decision": "SANCTION", "remarks": "sanctioned for projection test.", "version": ov["version"]},
    )
    _wait_status(op, txn, {"COMPLETED"}, timeout=30)
    # find app id via applications listing for citizen
    apps = cit.get("/api/applications").json()["items"]
    match = next((a for a in apps if a["transaction_id"] == txn), None)
    assert match, "citizen cannot see own txn"
    detail = cit.get(f"/api/applications/{match['id']}").json()
    approval = next(s for s in detail["stages"] if s["id"] == "approval")
    review = approval.get("review", {})
    assert review.get("officer_name") == "Meera Kulkarni"
    assert "officer_id" not in review, "citizen should not see officer_id"
