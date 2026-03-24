#!/usr/bin/env python3
"""
Medi-AI-tor — Comprehensive End-to-End Test Suite
Tests every major flow against the live VM.
"""
import json, sys, time, requests, urllib3
urllib3.disable_warnings()

BASE = "https://localhost"
passed = failed = 0
errors = []

def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail[:120]}")

def get(path, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(f"{BASE}{path}", headers=h, verify=False, timeout=30, **kw)

def post(path, token=None, data=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(f"{BASE}{path}", headers=h, json=data, verify=False, timeout=30, **kw)

def delete(path, token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.delete(f"{BASE}{path}", headers=h, verify=False, timeout=30)

# ═══════════════════════════════════════════
# 1. HEALTH & INFRASTRUCTURE
# ═══════════════════════════════════════════
print("=== 1. Health & Infrastructure ===")
r = get("/health"); ok("GET /health", r.status_code == 200 and r.json()["status"] == "healthy")
r = get("/api/health"); ok("GET /api/health", r.status_code == 200 and "checks" in r.json())
r = get("/metrics"); ok("GET /metrics", r.status_code == 200 and "medi_ai_tor" in r.text)

# Pages serve
for p in ["/", "/login", "/fleet", "/mobile", "/monitoring"]:
    r = get(p); ok(f"GET {p}", r.status_code == 200 and len(r.content) > 500, f"{r.status_code}")

# Static assets
for s in ["/static/css/style.css", "/static/js/app.js", "/static/css/customer.css", "/static/js/customer.js"]:
    r = get(s); ok(f"GET {s}", r.status_code == 200 and len(r.content) > 1000)

# ═══════════════════════════════════════════
# 2. AUTHENTICATION
# ═══════════════════════════════════════════
print("=== 2. Authentication ===")
r = post("/api/auth/login", data={"username": "admin", "password": "admin123"})
ok("Admin login", r.status_code == 200 and "token" in r.json())
admin_token = r.json().get("token")
admin_refresh = r.json().get("refresh_token")

r = post("/api/auth/login", data={"username": "operator", "password": "operator123"})
ok("Operator login", r.status_code == 200)
op_token = r.json().get("token")

r = post("/api/auth/login", data={"username": "viewer", "password": "viewer123"})
ok("Viewer login", r.status_code == 200)
viewer_token = r.json().get("token")

r = post("/api/auth/login", data={"username": "admin", "password": "wrong"})
ok("Bad password = 401", r.status_code == 401)

if admin_refresh:
    r = post("/api/auth/refresh", data={"refresh_token": admin_refresh})
    ok("Token refresh", r.status_code == 200 and "token" in r.json())

# No token = 401 (clean session)
S2 = requests.Session(); S2.verify = False
r = S2.get(f"{BASE}/api/server/quick-status"); ok("No token = 401", r.status_code == 401)
r = S2.get(f"{BASE}/api/server/quick-status", headers={"Authorization": "Bearer invalid.bad.token"})
ok("Bad token = 401", r.status_code == 401)

r = get("/api/auth/capabilities", token=admin_token); ok("Admin capabilities", r.status_code == 200)
r = get("/api/auth/capabilities", token=viewer_token); ok("Viewer capabilities", r.status_code == 200)

# ═══════════════════════════════════════════
# 3. SESSION MANAGEMENT
# ═══════════════════════════════════════════
print("=== 3. Session Management ===")
r = get("/api/sessions", token=admin_token); ok("GET /api/sessions (admin)", r.status_code == 200)
r = get("/api/sessions", token=op_token); ok("Operator blocked from /api/sessions", r.status_code == 403)
r = delete("/api/sessions/__default__", token=admin_token); ok("Cannot delete default session", r.status_code == 400)

# ═══════════════════════════════════════════
# 4. CUSTOMER CHAT FLOW (shared default connection)
# ═══════════════════════════════════════════
print("=== 4. Customer Chat Flow ===")
r = post("/chat", data={"message": "hello", "action_level": "read_only"})
ok("POST /chat (default)", r.status_code == 200)

r = post("/chat", data={"message": "", "action_level": "read_only"})
ok("POST /chat empty msg", r.status_code == 200)

r = post("/execute", data={"action": "get_server_info", "action_level": "read_only"})
ok("POST /execute (default)", r.status_code in [200, 400, 500])

r = post("/check-idrac", data={"host": "100.71.148.195", "username": "root", "password": "calvin"})
ok("POST /check-idrac", r.status_code == 200)

# Connect customer to real iDRAC
r = post("/connect", data={"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443})
cust_connected = r.status_code == 200
ok("POST /connect (iDRAC)", r.status_code in [200, 400])

if cust_connected:
    r = post("/chat", data={"message": "check health", "action_level": "read_only"})
    ok("Chat after connect", r.status_code == 200 and r.json().get("type") != "error", f"{r.json().get('type')}")

    r = post("/chat/stream", data={"message": "what is the server model?", "action_level": "read_only"})
    ok("POST /chat/stream (SSE)", r.status_code == 200)

    r = post("/execute", data={"action": "get_server_info", "action_level": "read_only"})
    ok("POST /execute after connect", r.status_code == 200)

# ═══════════════════════════════════════════
# 5. TECHNICIAN FLOW (per-session)
# ═══════════════════════════════════════════
print("=== 5. Technician Flow ===")
r = get("/api/server/quick-status", token=admin_token)
ok("Admin quick-status (disconnected)", r.status_code == 200)

# Connect admin to iDRAC
r = post("/api/connect", token=admin_token, data={"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443})
admin_connected = r.status_code == 200
ok("POST /api/connect (admin)", r.status_code in [200, 400], f"{r.status_code}: {r.text[:100]}")

if admin_connected:
    r = post("/api/execute", token=admin_token, data={"action": "get_server_info", "action_level": "read_only", "parameters": {}})
    ok("POST /api/execute (admin)", r.status_code == 200)

    r = post("/api/execute", token=admin_token, data={"action": "health_check", "action_level": "read_only", "parameters": {}})
    ok("Health check execute", r.status_code == 200)

    r = post("/api/execute", token=admin_token, data={"action": "get_temperature_sensors", "action_level": "read_only", "parameters": {}})
    ok("Temp sensors execute", r.status_code == 200)

    r = post("/api/execute", token=admin_token, data={"action": "get_power_supplies", "action_level": "read_only", "parameters": {}})
    ok("Power supplies execute", r.status_code == 200)

    r = post("/api/chat", token=admin_token, data={"message": "what is the server model?", "action_level": "read_only"})
    ok("POST /api/chat (admin)", r.status_code == 200)

    r = post("/api/chat/stream", token=admin_token, data={"message": "check health", "action_level": "read_only"})
    ok("POST /api/chat/stream (admin)", r.status_code == 200)

    r = get("/api/server/quick-status", token=admin_token)
    ok("Quick-status (connected)", r.status_code == 200)
    qs = r.json()
    ok("Quick-status has data", qs.get("data", {}).get("connected") == True or qs.get("connected") == True, f"{qs}")

    r = get("/api/server/snapshot", token=admin_token)
    ok("GET /api/server/snapshot", r.status_code == 200)

    r = get("/api/server/diagnostics-summary", token=admin_token)
    ok("GET /api/server/diagnostics-summary", r.status_code == 200)

    r = post("/api/execute/batch", token=admin_token, data={"commands": [
        {"action": "health_check", "action_level": "read_only"},
        {"action": "get_server_info", "action_level": "read_only"}
    ]})
    ok("POST /api/execute/batch", r.status_code == 200)

    r = get("/api/connection/status", token=admin_token)
    ok("GET /api/connection/status", r.status_code == 200)

    # 6. PER-SESSION ISOLATION
    print("=== 6. Per-Session Isolation ===")
    r = get("/api/server/quick-status", token=op_token)
    op_qs = r.json()
    op_conn = op_qs.get("data", {}).get("connected", op_qs.get("connected", False))
    ok("Operator NOT connected (isolation)", not op_conn, f"op connected={op_conn}")

    r = post("/api/execute", token=op_token, data={"action": "health_check", "action_level": "read_only", "parameters": {}})
    ok("Operator execute = not connected", r.status_code == 400 or "not connected" in r.text.lower(), f"{r.status_code}")

    # Disconnect admin
    r = post("/api/disconnect", token=admin_token)
    ok("POST /api/disconnect (admin)", r.status_code == 200)

    r = get("/api/server/quick-status", token=admin_token)
    ok("Admin disconnected", r.json().get("connected") == False or r.json().get("status") == "disconnected")

# ═══════════════════════════════════════════
# 7. FLEET MANAGEMENT
# ═══════════════════════════════════════════
print("=== 7. Fleet Management ===")
r = get("/api/fleet/overview", token=admin_token); ok("Fleet overview", r.status_code == 200)
r = get("/api/v1/fleet/servers", token=admin_token); ok("Fleet servers paginated", r.status_code == 200)
r = get("/api/fleet/alerts", token=admin_token); ok("Fleet alerts", r.status_code == 200)
r = post("/api/fleet/alerts/clear", token=admin_token); ok("Clear fleet alerts", r.status_code == 200)
r = get("/api/fleet/analytics", token=admin_token); ok("Fleet analytics", r.status_code == 200)
r = post("/api/fleet/analytics/report", token=admin_token); ok("Fleet report", r.status_code == 200)
r = get("/api/fleet/export/servers", token=admin_token); ok("Export servers", r.status_code == 200)
r = get("/api/fleet/export/alerts", token=admin_token); ok("Export alerts", r.status_code == 200)
r = post("/api/fleet/health-check", token=admin_token); ok("Fleet health-check", r.status_code == 200)
r = post("/api/fleet/servers", token=admin_token, data={
    "name": "cleanup-test", "host": "10.0.0.99", "username": "root",
    "password": "test", "port": 443, "environment": "test"
}); ok("Add fleet server", r.status_code == 200)

# ═══════════════════════════════════════════
# 8. ENTERPRISE ENDPOINTS
# ═══════════════════════════════════════════
print("=== 8. Enterprise Endpoints ===")
enterprise = ["/api/roles", "/api/maintenance", "/api/tickets", "/api/kb",
              "/api/glossary", "/api/incidents", "/api/runbooks", "/api/bookmarks",
              "/api/searches", "/api/dashboard/layout", "/api/onboarding", "/api/sla"]
for ep in enterprise:
    r = get(ep, token=admin_token); ok(f"GET {ep}", r.status_code == 200, f"{r.status_code}")

# ═══════════════════════════════════════════
# 9. MONITORING & AUDIT
# ═══════════════════════════════════════════
print("=== 9. Monitoring & Audit ===")
r = get("/monitoring/status"); ok("Monitoring status", r.status_code == 200)
r = get("/monitoring/alerts"); ok("Monitoring alerts", r.status_code == 200)
r = get("/api/audit-log", token=admin_token); ok("Audit log", r.status_code == 200)
r = get("/api/server/timeline"); ok("Server timeline", r.status_code == 200)

# ═══════════════════════════════════════════
# 10. PERMISSION CHECKS
# ═══════════════════════════════════════════
print("=== 10. Permission Checks ===")
r = post("/api/execute", token=viewer_token, data={"action": "x", "action_level": "full_control", "parameters": {}})
ok("Viewer blocked from full_control", r.status_code == 403)

r = post("/api/execute", token=viewer_token, data={"action": "x", "action_level": "diagnostic", "parameters": {}})
ok("Viewer blocked from diagnostic", r.status_code == 403)

r = post("/api/execute", token=op_token, data={"action": "x", "action_level": "full_control", "parameters": {}})
ok("Operator blocked from full_control", r.status_code == 403)

# ═══════════════════════════════════════════
# 11. ERROR HANDLING
# ═══════════════════════════════════════════
print("=== 11. Error Handling ===")
r = post("/api/connect", token=admin_token, data={"host": "", "username": "x", "password": "x"})
ok("Empty host = 400", r.status_code == 400)

r = post("/api/connect", token=admin_token, data={"host": "x", "username": "", "password": "x"})
ok("Empty username = 400", r.status_code == 400)

r = post("/api/execute/batch", token=admin_token, data={"commands": []})
ok("Empty batch = 400", r.status_code == 400)

r = post("/api/execute/batch", token=admin_token, data={"commands": [{"action": "x"}] * 25})
ok("Batch > 20 = 400", r.status_code == 400)

# ═══════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════
total = passed + failed
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed out of {total} tests")
print(f"{'='*60}")
if errors:
    print("\nFAILURES:")
    for e in errors:
        print(f"  - {e}")
sys.exit(0 if failed == 0 else 1)
