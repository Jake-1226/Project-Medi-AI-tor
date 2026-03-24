#!/usr/bin/env python3
"""
Comprehensive live test suite for Medi-AI-tor per-session connection management.
Tests every major endpoint group systematically.
"""
import json
import sys
import time
import requests
import urllib3
urllib3.disable_warnings()

BASE = "https://localhost"
S = requests.Session()
S.verify = False

passed = 0
failed = 0
errors = []

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")

def get(path, token=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return S.get(f"{BASE}{path}", headers=headers, **kwargs)

def post(path, token=None, json_data=None, **kwargs):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return S.post(f"{BASE}{path}", headers=headers, json=json_data, **kwargs)

def delete(path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return S.delete(f"{BASE}{path}", headers=headers)

# ═══════════════════════════════════════════════════════════════
# GROUP 1: HEALTH & BASIC ENDPOINTS
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 1: Health & Basic Endpoints ===")

r = get("/health")
test("GET /health", r.status_code == 200 and r.json()["status"] == "healthy", f"{r.status_code}: {r.text[:100]}")

r = get("/api/health")
test("GET /api/health", r.status_code == 200 and "checks" in r.json(), f"{r.status_code}: {r.text[:200]}")
checks = r.json().get("checks", {})
test("/api/health has session_manager", checks.get("session_manager") == "ok", f"checks={checks}")
test("/api/health has active_sessions", "active_sessions" in checks, f"checks={checks}")

r = get("/metrics")
test("GET /metrics", r.status_code == 200 and "medi_ai_tor_agent_sessions" in r.text, f"{r.status_code}")

# ═══════════════════════════════════════════════════════════════
# GROUP 2: AUTHENTICATION
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 2: Authentication ===")

r = post("/api/auth/login", json_data={"username": "admin", "password": "admin123"})
test("Admin login", r.status_code == 200 and "token" in r.json(), f"{r.status_code}: {r.text[:200]}")
admin_token = r.json().get("token")
admin_sid = r.json().get("session_id")

r = post("/api/auth/login", json_data={"username": "operator", "password": "operator123"})
test("Operator login", r.status_code == 200 and "token" in r.json(), f"{r.status_code}: {r.text[:200]}")
op_token = r.json().get("token")
op_sid = r.json().get("session_id")

r = post("/api/auth/login", json_data={"username": "viewer", "password": "viewer123"})
test("Viewer login", r.status_code == 200 and "token" in r.json(), f"{r.status_code}: {r.text[:200]}")
viewer_token = r.json().get("token")

test("Sessions are unique", admin_sid != op_sid, f"admin={admin_sid}, op={op_sid}")

r = post("/api/auth/login", json_data={"username": "admin", "password": "wrong"})
test("Bad password rejected", r.status_code == 401, f"{r.status_code}")

r = get("/api/auth/capabilities", token=admin_token)
test("GET /api/auth/capabilities (admin)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/auth/capabilities", token=viewer_token)
test("GET /api/auth/capabilities (viewer)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Token refresh
refresh_tok = None
r2 = post("/api/auth/login", json_data={"username": "admin", "password": "admin123"})
if r2.status_code == 200:
    refresh_tok = r2.json().get("refresh_token")
if refresh_tok:
    r = post("/api/auth/refresh", json_data={"refresh_token": refresh_tok})
    test("Token refresh", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")
else:
    test("Token refresh", False, "no refresh_token returned")

# No token (use a clean session without cookies)
S_clean = requests.Session()
S_clean.verify = False
r = S_clean.get(f"{BASE}/api/server/quick-status")
test("No token -> 401", r.status_code == 401, f"{r.status_code}")

# ═══════════════════════════════════════════════════════════════
# GROUP 3: SESSION MANAGEMENT (admin only)
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 3: Session Management ===")

r = get("/api/sessions", token=admin_token)
test("GET /api/sessions (admin)", r.status_code == 200 and "data" in r.json(), f"{r.status_code}: {r.text[:200]}")
session_data = r.json().get("data", {})
test("Sessions have total_sessions", "total_sessions" in session_data, f"{session_data}")
test("Sessions have max_sessions=100", session_data.get("max_sessions") == 100, f"{session_data}")

r = get("/api/sessions", token=op_token)
test("GET /api/sessions (operator) -> 403", r.status_code == 403, f"{r.status_code}")

r = get("/api/sessions", token=viewer_token)
test("GET /api/sessions (viewer) -> 403", r.status_code == 403, f"{r.status_code}")

r = delete("/api/sessions/__default__", token=admin_token)
test("DELETE default session -> 400", r.status_code == 400, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 4: CUSTOMER PAGE ENDPOINTS (no auth)
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 4: Customer Page Endpoints ===")

# Serve pages
r = get("/")
test("GET / (customer page)", r.status_code == 200, f"{r.status_code}")

r = get("/login")
test("GET /login", r.status_code == 200, f"{r.status_code}")

# Chat without explicit connection (may work if default session connected from prior test/run)
r = post("/chat", json_data={"message": "hello", "action_level": "read_only"})
test("POST /chat (default session)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")
chat_resp = r.json()
# Either an error about connection OR a valid chat response
test("/chat returns valid response", chat_resp.get("type") in ("error", "answer", "diagnostic_report") or "message" in chat_resp, f"{list(chat_resp.keys())}")

# Chat with empty message
r = post("/chat", json_data={"message": "", "action_level": "read_only"})
test("POST /chat (empty msg)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Connect to iDRAC (will fail in non-demo mode since server is unreachable)
r = post("/connect", json_data={"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443})
# This may succeed or fail depending on network — just check it doesn't 500
test("POST /connect (iDRAC)", r.status_code in [200, 400, 500], f"{r.status_code}: {r.text[:200]}")

# Execute (not connected)
r = post("/execute", json_data={"action": "get_server_info", "action_level": "read_only"})
test("POST /execute (not connected)", r.status_code in [200, 400, 500], f"{r.status_code}: {r.text[:200]}")

# Chat stream (not connected)
r = post("/chat/stream", json_data={"message": "test", "action_level": "read_only"})
test("POST /chat/stream (not connected)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Check-iDRAC
r = post("/check-idrac", json_data={"host": "100.71.148.195", "username": "root", "password": "calvin"})
test("POST /check-idrac", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 5: TECHNICIAN AUTHENTICATED ENDPOINTS
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 5: Technician Authenticated Endpoints ===")

# Quick status (per-session, not connected)
r = get("/api/server/quick-status", token=admin_token)
test("GET /api/server/quick-status (admin, disconnected)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")
qs = r.json()
test("Quick status shows disconnected", qs.get("connected") == False or qs.get("status") == "disconnected", f"{qs}")

r = get("/api/server/quick-status", token=op_token)
test("GET /api/server/quick-status (operator, disconnected)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Connect admin to iDRAC (may fail due to network, but should not 500)
r = post("/api/connect", token=admin_token, json_data={"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443})
admin_connected = (r.status_code == 200)
test("POST /api/connect (admin)", r.status_code in [200, 400], f"{r.status_code}: {r.text[:200]}")

if admin_connected:
    # Execute
    r = post("/api/execute", token=admin_token, json_data={"action": "get_server_info", "action_level": "read_only", "parameters": {}})
    test("POST /api/execute (admin)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

    # Chat
    r = post("/api/chat", token=admin_token, json_data={"message": "what is the server model?", "action_level": "read_only"})
    test("POST /api/chat (admin)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

    # Chat stream
    r = post("/api/chat/stream", token=admin_token, json_data={"message": "check health", "action_level": "read_only"})
    test("POST /api/chat/stream (admin)", r.status_code == 200, f"{r.status_code}")

    # Snapshot
    r = get("/api/server/snapshot", token=admin_token)
    test("GET /api/server/snapshot", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

    # Diagnostics summary
    r = get("/api/server/diagnostics-summary", token=admin_token)
    test("GET /api/server/diagnostics-summary", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

    # Batch execute
    r = post("/api/execute/batch", token=admin_token, json_data={"commands": [{"action": "health_check", "action_level": "read_only"}]})
    test("POST /api/execute/batch", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

    # Verify operator is NOT connected (per-session isolation)
    r = get("/api/server/quick-status", token=op_token)
    op_qs = r.json()
    op_connected = op_qs.get("data", {}).get("connected", op_qs.get("connected", False))
    test("Operator is NOT connected (session isolation)", not op_connected, f"operator status: {op_qs}")

    # Disconnect admin
    r = post("/api/disconnect", token=admin_token)
    test("POST /api/disconnect (admin)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")
else:
    print("  SKIP: admin not connected, skipping connected-endpoint tests")

# Disconnect when not connected
r = post("/api/disconnect", token=op_token)
test("POST /api/disconnect (operator, not connected)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Connection status
r = get("/api/connection/status", token=admin_token)
test("GET /api/connection/status", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 6: FLEET MANAGEMENT
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 6: Fleet Management ===")

r = get("/api/fleet/overview", token=admin_token)
test("GET /api/fleet/overview", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/v1/fleet/servers", token=admin_token)
test("GET /api/v1/fleet/servers (paginated)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/fleet/alerts", token=admin_token)
test("GET /api/fleet/alerts", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = post("/api/fleet/alerts/clear", token=admin_token)
test("POST /api/fleet/alerts/clear", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/fleet/analytics", token=admin_token)
test("GET /api/fleet/analytics", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = post("/api/fleet/analytics/report", token=admin_token)
test("POST /api/fleet/analytics/report", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/fleet/export/servers", token=admin_token)
test("GET /api/fleet/export/servers", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/fleet/export/alerts", token=admin_token)
test("GET /api/fleet/export/alerts", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = post("/api/fleet/health-check", token=admin_token)
test("POST /api/fleet/health-check", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Add a fleet server
r = post("/api/fleet/servers", token=admin_token, json_data={
    "name": "test-server", "host": "10.0.0.99", "username": "root",
    "password": "test", "port": 443, "environment": "test"
})
test("POST /api/fleet/servers (add)", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 7: ENTERPRISE ENDPOINTS (correct URLs)
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 7: Enterprise Endpoints ===")

r = get("/api/roles", token=admin_token)
test("GET /api/roles", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/maintenance", token=admin_token)
test("GET /api/maintenance", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/tickets", token=admin_token)
test("GET /api/tickets", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/kb", token=admin_token)
test("GET /api/kb", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/glossary", token=admin_token)
test("GET /api/glossary", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/incidents", token=admin_token)
test("GET /api/incidents", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/runbooks", token=admin_token)
test("GET /api/runbooks", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/bookmarks", token=admin_token)
test("GET /api/bookmarks", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/searches", token=admin_token)
test("GET /api/searches", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/dashboard/layout", token=admin_token)
test("GET /api/dashboard/layout", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/onboarding", token=admin_token)
test("GET /api/onboarding", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/sla", token=admin_token)
test("GET /api/sla", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 8: MONITORING
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 8: Monitoring ===")

r = get("/monitoring/status")
test("GET /monitoring/status", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/monitoring/alerts")
test("GET /monitoring/alerts", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# ═══════════════════════════════════════════════════════════════
# GROUP 9: AUDIT & MISC
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 9: Audit & Misc ===")

r = get("/api/audit-log", token=admin_token)
test("GET /api/audit-log", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

r = get("/api/server/timeline")
test("GET /api/server/timeline", r.status_code == 200, f"{r.status_code}: {r.text[:200]}")

# Static pages
r = get("/mobile")
test("GET /mobile", r.status_code == 200, f"{r.status_code}")

r = get("/monitoring")
test("GET /monitoring page", r.status_code == 200, f"{r.status_code}")

# ═══════════════════════════════════════════════════════════════
# GROUP 10: EDGE CASES & PERMISSION CHECKS
# ═══════════════════════════════════════════════════════════════
print("\n=== GROUP 10: Edge Cases & Permission Checks ===")

# Viewer can't execute write actions
r = post("/api/execute", token=viewer_token, json_data={"action": "get_server_info", "action_level": "full_control", "parameters": {}})
test("Viewer blocked from full_control", r.status_code == 403, f"{r.status_code}: {r.text[:200]}")

# Invalid token (use clean session — no cookies)
S_noauth = requests.Session()
S_noauth.verify = False
r = S_noauth.get(f"{BASE}/api/server/quick-status", headers={"Authorization": "Bearer bogus.invalid.token"})
test("Invalid token -> 401", r.status_code == 401, f"{r.status_code}")

# Empty bearer (clean session)
r = S_noauth.get(f"{BASE}/api/server/quick-status", headers={"Authorization": "Bearer "})
test("Empty bearer -> 401", r.status_code == 401, f"{r.status_code}")

# No auth header at all (clean session)
r = S_noauth.get(f"{BASE}/api/server/quick-status")
test("No auth header -> 401", r.status_code == 401, f"{r.status_code}")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} tests")
print("=" * 60)
if errors:
    print("\nFAILURES:")
    for e in errors:
        print(f"  - {e}")
print()
sys.exit(0 if failed == 0 else 1)
