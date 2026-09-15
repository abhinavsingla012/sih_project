#!/usr/bin/env python3
"""Iteration 5 focused tests: infra resilience, dispatcher, health, setup idempotence.

DO NOT print WEBHOOK_CRON_SECRET.
"""
import os
import re
import subprocess
import time
import uuid

import httpx
import pytest

BASE_URL = "https://txn-orchestrate.preview.emergentagent.com"
API = f"{BASE_URL}/api"
PW = "Demo@2026!"


def sh(cmd, timeout=60, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed {cmd}: {r.stderr}")
    return r


def sv_status():
    return sh("sudo supervisorctl status").stdout


def wait_status(name, state, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        out = sv_status()
        for line in out.splitlines():
            if line.startswith(name):
                if state in line:
                    return True
                break
        time.sleep(1)
    return False


def login(email):
    c = httpx.Client(base_url=API, timeout=30.0)
    r = c.post("/auth/login", json={"email": email, "password": PW},
               headers={"Origin": BASE_URL})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    sess = r.cookies.get("samanvay_session")
    csrf = r.cookies.get("samanvay_csrf")
    assert sess and csrf
    c.cookies.set("samanvay_session", sess)
    c.headers.update({"X-CSRF-Token": csrf, "Origin": BASE_URL})
    return c


# ----- health -----
def test_supervisor_all_running():
    out = sv_status()
    for svc in ["backend", "samanvay-redis", "samanvay-events"]:
        assert re.search(rf"^{svc}\s+RUNNING", out, re.M), f"{svc} not RUNNING:\n{out}"


def test_redis_ping():
    r = sh("redis-cli ping")
    assert r.stdout.strip() == "PONG", r.stdout


def test_api_root():
    r = httpx.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert "service" in r.json()


def test_monitoring_overview_redis_ok():
    c = login("operator@demo.in")
    r = c.get("/monitoring/overview")
    assert r.status_code == 200, r.text
    infra = r.json().get("infrastructure", {})
    assert infra.get("redis") == "HEALTHY", infra
    assert infra.get("consumer") == "HEALTHY", infra


# ----- auth -----
def test_login_operator():
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "operator@demo.in", "password": PW},
                   headers={"Origin": BASE_URL}, timeout=15)
    assert r.status_code == 200
    names = {c.name for c in r.cookies.jar}
    assert "samanvay_session" in names and "samanvay_csrf" in names


def test_login_citizen():
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "citizen@demo.in", "password": PW},
                   headers={"Origin": BASE_URL}, timeout=15)
    assert r.status_code == 200
    names = {c.name for c in r.cookies.jar}
    assert "samanvay_session" in names and "samanvay_csrf" in names


def test_login_wrong_password_401():
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "citizen@demo.in", "password": "wrong"},
                   headers={"Origin": BASE_URL}, timeout=15)
    assert r.status_code == 401


# ----- e2e journey -----
def test_e2e_citizen_application_completes():
    c = login("citizen@demo.in")
    r = c.post("/applications",
               json={"course_code": "DATA_ANALYTICS", "district": "Pune",
                     "eligibility_consent": True, "payment_consent": True,
                     "service_code": "MH_SKILL_BENEFIT"},
               headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    app = r.json()
    aid = app["id"]
    tid = app["transaction_id"]

    end = time.time() + 45
    final = None
    while time.time() < end:
        rr = c.get(f"/applications/{aid}")
        assert rr.status_code == 200
        final = rr.json()
        if final["status"] == "COMPLETED":
            break
        time.sleep(2)
    assert final and final["status"] == "COMPLETED", f"status={final and final['status']}"
    stages = final["stages"]
    assert len(stages) == 4
    assert all(s["state"] == "COMPLETED" for s in stages)

    # operator: payment evidence
    op = login("operator@demo.in")
    ev = op.get(f"/transactions/{tid}/payment-evidence")
    assert ev.status_code == 200
    assert ev.json().get("disbursement_count") == 1


# ----- resilience -----
def test_worker_survives_redis_outage_and_recovers():
    # stop redis, expect events still RUNNING (not FATAL)
    sh("sudo supervisorctl stop samanvay-redis", check=True)
    time.sleep(8)
    out = sv_status()
    events_line = [l for l in out.splitlines() if l.startswith("samanvay-events")][0]
    assert "RUNNING" in events_line, f"worker not running during outage: {events_line}"

    # login should now return 503 AUTH_UNAVAILABLE (by design)
    r = httpx.post(f"{API}/auth/login",
                   json={"email": "operator@demo.in", "password": PW},
                   headers={"Origin": BASE_URL}, timeout=15)
    assert r.status_code == 503, f"expected 503 during outage, got {r.status_code}"

    # restart redis
    sh("sudo supervisorctl start samanvay-redis", check=True)
    assert wait_status("samanvay-redis", "RUNNING", 20)
    time.sleep(10)

    # login works again
    r2 = httpx.post(f"{API}/auth/login",
                    json={"email": "operator@demo.in", "password": PW},
                    headers={"Origin": BASE_URL}, timeout=15)
    assert r2.status_code == 200, r2.text

    # heartbeat present
    hb = sh("redis-cli GET samanvay:consumer:heartbeat").stdout.strip()
    assert hb, "no heartbeat after redis restart"


def test_worker_startup_with_redis_down():
    sh("sudo supervisorctl stop samanvay-events samanvay-redis", check=True)
    time.sleep(3)
    sh("sudo supervisorctl start samanvay-events", check=True)
    time.sleep(8)
    out = sv_status()
    events_line = [l for l in out.splitlines() if l.startswith("samanvay-events")][0]
    assert "RUNNING" in events_line, f"worker crashed on startup w/o redis: {events_line}"

    # start redis, verify worker proceeds
    sh("sudo supervisorctl start samanvay-redis", check=True)
    assert wait_status("samanvay-redis", "RUNNING", 20)
    time.sleep(10)

    # verify new application processes
    c = login("citizen@demo.in")
    r = c.post("/applications",
               json={"course_code": "DATA_ANALYTICS", "district": "Pune",
                     "eligibility_consent": True, "payment_consent": True,
                     "service_code": "MH_SKILL_BENEFIT"},
               headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    end = time.time() + 45
    final = None
    while time.time() < end:
        rr = c.get(f"/applications/{aid}")
        final = rr.json()
        if final["status"] == "COMPLETED":
            break
        time.sleep(2)
    assert final["status"] == "COMPLETED", f"final={final['status']}"


# ----- dispatcher / maintenance -----
def test_dispatcher_wrong_bearer_401():
    r = httpx.post(f"{API}/internal/maintenance/recover",
                   json={"event": "schedule.triggered", "run_id": str(uuid.uuid4())},
                   headers={"Authorization": "Bearer wrong"}, timeout=15)
    assert r.status_code == 401


def test_dispatcher_success_and_idempotent():
    endpoint = f"{API}/internal/maintenance/recover"
    b64 = subprocess.check_output(
        f"printf '%s' '{endpoint}' | base64 -w0", shell=True, text=True).strip()
    env = os.environ.copy()
    env.update({"CRON_NAME": "workflow-recovery", "METHOD": "POST",
                "ENDPOINT_URL_B64": b64})
    r = subprocess.run(["/bin/sh", "/app/.emergent/cron/dispatch_webhook.sh"],
                       env=env, capture_output=True, text=True, timeout=30)
    combined = (r.stdout + r.stderr)
    assert "http=202" in combined, f"dispatcher output missing 202: {combined[-500:]}"

    # second run within same minute should still return 202 (idempotent)
    r2 = subprocess.run(["/bin/sh", "/app/.emergent/cron/dispatch_webhook.sh"],
                        env=env, capture_output=True, text=True, timeout=30)
    combined2 = (r2.stdout + r2.stderr)
    assert "http=202" in combined2, f"second dispatcher missing 202: {combined2[-500:]}"

    # check receipt in mongo
    mongo = sh("mongosh --quiet test_database --eval "
               "'db.maintenance_receipts.find({},{_id:0,id:1,queued:1}).sort({_id:-1}).limit(3).toArray()'")
    assert "workflow-recovery-" in mongo.stdout, mongo.stdout


# ----- setup idempotence -----
def test_setup_local_idempotent():
    r1 = sh("cd /app/backend && python setup_local.py")
    assert r1.returncode == 0, r1.stderr
    r2 = sh("cd /app/backend && python setup_local.py")
    assert r2.returncode == 0, r2.stderr
    # keys check (no values printed)
    keys = sh("cut -d= -f1 /app/backend/.env").stdout.split()
    assert "WEBHOOK_CRON_SECRET" in keys
    assert "MONGO_URL" in keys
    assert "DB_NAME" in keys
    local = sh("cut -d= -f1 /app/backend/.env.local").stdout.split()
    assert "WEBHOOK_CRON_SECRET" not in local


def test_restore_runtime():
    r = sh("python /app/scripts/restore_runtime.py", timeout=180)
    assert r.returncode == 0, r.stderr[-500:]
    # all services still running
    out = sv_status()
    for svc in ["backend", "samanvay-redis", "samanvay-events"]:
        assert re.search(rf"^{svc}\s+RUNNING", out, re.M), out
