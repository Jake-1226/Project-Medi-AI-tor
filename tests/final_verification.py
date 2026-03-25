#!/usr/bin/env python3
"""FINAL VERIFICATION: Test the complete user journey with real F710 data.
Tests: Login → Connect → All tabs with data → Chat → Investigation → Operations → Fleet → Monitoring
"""
import requests, urllib3, json, time, asyncio
urllib3.disable_warnings()

S = requests.Session()
S.verify = False
BASE = "http://localhost"
passed = failed = 0
errors = []

def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail[:100]}")

def get(path, token=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return S.get(f"{BASE}{path}", headers=h, timeout=30, **kw)

def post(path, token=None, data=None, **kw):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return S.post(f"{BASE}{path}", headers=h, json=data, timeout=60, **kw)

# ═══════════════════════════════════════════
print("=== 1. LOGIN ===")
r = post("/api/auth/login", data={"username": "admin", "password": "admin123"})
ok("Login succeeds", r.status_code == 200 and r.json().get("status") == "success")
token = r.json().get("token")
admin_sid = r.json().get("session_id")

# ═══════════════════════════════════════════
print("\n=== 2. CONNECT TO REAL iDRAC ===")
r = post("/api/connect", token=token, data={"host":"100.71.148.195","username":"root","password":"calvin","port":443})
ok("iDRAC connect", r.status_code == 200 and "success" in r.text)

# ═══════════════════════════════════════════
print("\n=== 3. QUICK STATUS ===")
r = get("/api/server/quick-status", token=token)
ok("Quick status returns data", r.status_code == 200)
qs = r.json().get("data", {})
ok("Server model is PowerScale F710", "F710" in str(qs.get("model", "")), qs.get("model"))
ok("Service tag is 3KQ38Y3", qs.get("service_tag") == "3KQ38Y3", qs.get("service_tag"))
ok("Server is powered on", qs.get("power_state") == "On", qs.get("power_state"))
ok("Has CPU info", "Xeon" in str(qs.get("cpu_model", "")), qs.get("cpu_model"))
ok("Has 512GB RAM", qs.get("total_memory_gb") == 512, str(qs.get("total_memory_gb")))

# ═══════════════════════════════════════════
print("\n=== 4. EXECUTE EVERY COMMAND ===")
commands = [
    ("get_server_info", "server_info"),
    ("health_check", "health_status"),
    ("get_temperature_sensors", "temperatures"),
    ("get_power_supplies", "power_supplies"),
    ("get_fans", "fans"),
    ("get_processors", "processors"),
    ("get_memory", "memory"),
    ("get_storage_devices", "storage_devices"),
    ("get_network_interfaces", "network_interfaces"),
    ("collect_logs", "logs"),
    ("get_bios_attributes", "bios"),
    ("get_idrac_info", "idrac_info"),
    ("get_firmware_inventory", "firmware_inventory"),
    ("get_lifecycle_logs", "lifecycle_logs"),
    ("performance_analysis", "performance_metrics"),
    ("get_post_codes", "post_codes"),
    ("get_jobs", "jobs"),
    ("get_boot_order", "boot_order"),
    ("get_idrac_network_config", "idrac_network"),
    ("get_lifecycle_status", "lifecycle_status"),
]
for cmd, key in commands:
    r = post("/api/execute", token=token, data={"action": cmd, "action_level": "read_only", "parameters": {}})
    has_data = r.status_code == 200 and key in r.json().get("result", {})
    ok(f"{cmd} returns {key}", has_data, f"{r.status_code}" if not has_data else "")

# ═══════════════════════════════════════════
print("\n=== 5. VERIFY DATA CONTENT ===")
# Server info
r = post("/api/execute", token=token, data={"action":"get_server_info","action_level":"read_only","parameters":{}})
si = r.json()["result"]["server_info"]
ok("Model correct", si.get("model") == "PowerScale F710", si.get("model"))
ok("BIOS version present", len(si.get("bios_version", "")) > 0, si.get("bios_version"))

# Temperatures
r = post("/api/execute", token=token, data={"action":"get_temperature_sensors","action_level":"read_only","parameters":{}})
temps = r.json()["result"]["temperatures"]
ok("Has temperature sensors", len(temps) > 5, f"found {len(temps)}")
inlet = [t for t in temps if "inlet" in t.get("name", "").lower()]
ok("Has inlet temperature", len(inlet) > 0)
if inlet:
    ok("Inlet temp is reasonable (15-45C)", 15 <= inlet[0].get("reading_celsius", 0) <= 45, str(inlet[0].get("reading_celsius")))

# Fans
r = post("/api/execute", token=token, data={"action":"get_fans","action_level":"read_only","parameters":{}})
fans = r.json()["result"]["fans"]
ok("Has fans", len(fans) > 5, f"found {len(fans)}")

# Power supplies
r = post("/api/execute", token=token, data={"action":"get_power_supplies","action_level":"read_only","parameters":{}})
psus = r.json()["result"]["power_supplies"]
ok("Has power supplies", len(psus) >= 2, f"found {len(psus)}")

# Memory
r = post("/api/execute", token=token, data={"action":"get_memory","action_level":"read_only","parameters":{}})
mem = r.json()["result"]["memory"]
ok("Has memory DIMMs", len(mem) > 0, f"found {len(mem)}")

# Storage
r = post("/api/execute", token=token, data={"action":"get_storage_devices","action_level":"read_only","parameters":{}})
storage = r.json()["result"]["storage_devices"]
ok("Has storage devices", len(storage) > 0, f"found {len(storage)}")

# BIOS
r = post("/api/execute", token=token, data={"action":"get_bios_attributes","action_level":"read_only","parameters":{}})
bios = r.json()["result"]["bios"]
ok("Has BIOS attributes", len(bios) > 10, f"found {len(bios)} attrs")

# Firmware
r = post("/api/execute", token=token, data={"action":"get_firmware_inventory","action_level":"read_only","parameters":{}})
fw = r.json()["result"]["firmware_inventory"]
ok("Has firmware inventory", len(fw) > 5, f"found {len(fw)} items")

# ═══════════════════════════════════════════
print("\n=== 6. CHAT ===")
r = post("/api/chat", token=token, data={"message":"what is the server model?","action_level":"read_only"})
ok("Chat responds", r.status_code == 200)
resp = r.json().get("response", {})
ok("Chat mentions F710", "F710" in str(resp) or "PowerScale" in str(resp), str(resp)[:80])

# ═══════════════════════════════════════════
print("\n=== 7. AI INVESTIGATION ===")
r = post("/api/investigate", token=token, data={
    "server_info":{"host":"100.71.148.195","username":"root","password":"calvin","port":443},
    "issue_description":"Check overall server health","action_level":"read_only"
})
ok("Investigation completes", r.status_code == 200)
inv = r.json()
ok("Has diagnosis", bool(inv.get("diagnosis")))
ok("Has recommendations", len(inv.get("recommendations", [])) > 0, f"found {len(inv.get('recommendations',[]))}")
ok("Has reasoning chain", len(inv.get("reasoning_chain", [])) > 0, f"found {len(inv.get('reasoning_chain',[]))}")

# ═══════════════════════════════════════════
print("\n=== 8. DIAGNOSTICS SUMMARY ===")
r = get("/api/server/diagnostics-summary", token=token)
ok("Diagnostics summary", r.status_code == 200)
ds = r.json().get("summary", {})
ok("Has thermal status", "status" in ds.get("thermal", {}))
ok("Has power status", "status" in ds.get("power", {}))

# ═══════════════════════════════════════════
print("\n=== 9. BATCH EXECUTE ===")
r = post("/api/execute/batch", token=token, data={"commands":[
    {"action":"health_check","action_level":"read_only","parameters":{}},
    {"action":"get_server_info","action_level":"read_only","parameters":{}}
]})
ok("Batch execute", r.status_code == 200 and r.json().get("status") == "success")

# ═══════════════════════════════════════════
print("\n=== 10. SERVER SNAPSHOT ===")
r = get("/api/server/snapshot", token=token)
ok("Server snapshot", r.status_code == 200)
snap = r.json().get("snapshot", {})
ok("Snapshot has thermal", bool(snap.get("thermal")))

# ═══════════════════════════════════════════
print("\n=== 11. MONITORING ===")
r = post("/monitoring/start", token=token)
ok("Start monitoring", r.status_code == 200)
time.sleep(2)
r = get("/monitoring/status")
ok("Monitoring active", r.json().get("monitoring_status",{}).get("status") == "active")
r = get("/monitoring/metrics", token=token)
ok("Metrics available", r.status_code == 200)
metrics = r.json().get("data",{}).get("metrics",{})
ok("Has inlet_temp metric", "inlet_temp" in metrics)
ok("Has cpu_temp metric", "cpu_temp" in metrics)
ok("Has fan_speed metric", "avg_fan_speed" in metrics or "max_fan_speed" in metrics)
r = post("/monitoring/stop", token=token)
ok("Stop monitoring", r.status_code == 200)

# ═══════════════════════════════════════════
print("\n=== 12. FLEET ===")
r = get("/api/fleet/overview", token=token)
ok("Fleet overview", r.status_code == 200)
r = get("/api/v1/fleet/servers", token=token)
ok("Fleet servers", r.status_code == 200)

# ═══════════════════════════════════════════
print("\n=== 13. CONNECTION STATUS ===")
r = get("/api/connection/status", token=token)
ok("Connection status", r.status_code == 200)
cs = r.json().get("connection", {})
ok("iDRAC connected", cs.get("idrac",{}).get("connected") == True)

# ═══════════════════════════════════════════
print("\n=== 14. SESSION ISOLATION ===")
# Login as operator
r2 = post("/api/auth/login", data={"username":"operator","password":"operator123"})
op_token = r2.json().get("token")
r = get("/api/server/quick-status", token=op_token)
op_qs = r.json()
op_connected = op_qs.get("data",{}).get("connected", op_qs.get("connected", False))
ok("Operator NOT connected (isolation)", not op_connected, f"connected={op_connected}")

# ═══════════════════════════════════════════
print("\n=== 15. DISCONNECT ===")
r = post("/api/disconnect", token=token)
ok("Disconnect", r.status_code == 200)
r = get("/api/server/quick-status", token=token)
ok("Disconnected confirmed", r.json().get("status") == "disconnected" or r.json().get("connected") == False)

# ═══════════════════════════════════════════
total = passed + failed
print(f"\n{'='*50}")
print(f"FINAL: {passed} passed, {failed} failed out of {total}")
print(f"{'='*50}")
if errors:
    print("\nFAILURES:")
    for e in errors:
        print(f"  - {e}")
