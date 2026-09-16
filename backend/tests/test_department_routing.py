"""Iteration 10 regression: department routing sanity — a scholarship
application must appear in sjsa@ pending inbox and NOT in official@ or agri@."""
import os
import time
import uuid
import httpx
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ORIGIN = BASE
PWD = "Demo@2026!"


def _login(email):
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"email": email, "password": PWD},
               headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    csrf = c.cookies.get("samanvay_csrf")
    c.headers.update({"Origin": ORIGIN, "X-CSRF-Token": csrf})
    return c


def test_scholarship_routes_to_sjsa_only():
    citizen = _login("citizen@demo.in")
    payload = {
        "service_code": "MH_POST_MATRIC_SCHOLARSHIP",
        "option_code": "UG",
        "district": "Pune",
        "eligibility_consent": True,
        "payment_consent": True,
    }
    r = citizen.post("/api/applications", json=payload,
                     headers={"Idempotency-Key": f"itest-{uuid.uuid4().hex}"})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    txn = body.get("transaction_id") or body.get("id")
    assert txn, body

    # Wait for it to reach UNDER_REVIEW
    end = time.time() + 25
    while time.time() < end:
        d = citizen.get(f"/api/transactions/{txn}")
        if d.status_code == 200 and d.json().get("status") == "UNDER_REVIEW":
            break
        time.sleep(1.5)

    def _ids(client):
        r = client.get("/api/reviews", params={"state": "pending"})
        assert r.status_code == 200, r.text
        return [i["transaction_id"] for i in r.json()["items"]]

    sjsa = _login("sjsa@demo.in"); ids_sjsa = _ids(sjsa)
    skill = _login("official@demo.in"); ids_skill = _ids(skill)
    agri = _login("agri@demo.in"); ids_agri = _ids(agri)

    print(f"txn={txn} sjsa[{len(ids_sjsa)}] skill[{len(ids_skill)}] agri[{len(ids_agri)}]")
    assert txn in ids_sjsa, f"scholarship should be visible to sjsa officer; got {ids_sjsa[:5]}"
    assert txn not in ids_skill, "scholarship must NOT be in skill inbox"
    assert txn not in ids_agri, "scholarship must NOT be in agri inbox"

    citizen.close(); sjsa.close(); skill.close(); agri.close()
