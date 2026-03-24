#!/usr/bin/env python3
import requests, urllib3, json
urllib3.disable_warnings()
S = requests.Session()
S.verify = False
BASE = "http://localhost"

# Login
r = S.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}"}

# Connect to iDRAC
r = S.post(f"{BASE}/api/connect", json={"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443}, headers=H, timeout=30)
print(f"Connect: {r.status_code} {r.text[:100]}")
if r.status_code != 200:
    print("FAILED TO CONNECT")
    exit(1)

# Test every action the dashboard calls
actions = [
    ("get_server_info", "Server Info"),
    ("health_check", "Health Check"),
    ("get_temperature_sensors", "Temperatures"),
    ("get_power_supplies", "Power Supplies"),
    ("get_fans", "Fans"),
    ("get_memory_devices", "Memory"),
    ("get_storage_devices", "Storage"),
    ("get_network_interfaces", "Network"),
    ("get_system_event_log", "SEL Logs"),
    ("get_lifecycle_log", "LC Logs"),
    ("get_full_inventory", "Full Inventory"),
    ("collect_logs", "Collect All"),
    ("performance_analysis", "Performance"),
    ("get_idrac_info", "iDRAC Info"),
    ("get_bios_attributes", "BIOS Attrs"),
]

print("\n=== Action Results ===")
for action, label in actions:
    try:
        r = S.post(f"{BASE}/api/execute", json={"action": action, "action_level": "read_only", "parameters": {}}, headers=H, timeout=30)
        if r.status_code == 200:
            res = r.json().get("result", {})
            keys = list(res.keys())[:4] if isinstance(res, dict) else str(type(res))
            print(f"  OK : {label:22s} keys={keys}")
        else:
            print(f"  FAIL: {label:22s} {r.status_code} {r.text[:80]}")
    except Exception as e:
        print(f"  ERR : {label:22s} {e}")

# Test AI investigation
print("\n=== AI Investigation ===")
try:
    r = S.post(f"{BASE}/api/investigate", json={
        "server_info": {"host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443},
        "issue_description": "Check overall server health",
        "action_level": "read_only"
    }, headers=H, timeout=120)
    if r.status_code == 200:
        d = r.json()
        print(f"  OK: diagnosis={bool(d.get('diagnosis'))}, recs={len(d.get('recommendations',[]))}, chain={len(d.get('reasoning_chain',[]))}")
    else:
        print(f"  FAIL: {r.status_code} {r.text[:100]}")
except Exception as e:
    print(f"  ERR: {e}")

# Quick status
r = S.get(f"{BASE}/api/server/quick-status", headers=H)
print(f"\n=== Quick Status: {r.status_code} ===")
if r.status_code == 200:
    d = r.json().get("data", r.json())
    for k in ["connected", "model", "service_tag", "health", "power_state", "cpu_model", "total_memory_gb"]:
        print(f"  {k}: {d.get(k, '?')}")

# Connection status
r = S.get(f"{BASE}/api/connection/status", headers=H)
print(f"\n=== Connection Status: {r.status_code} ===")
if r.status_code == 200:
    cs = r.json().get("connection", {})
    print(f"  idrac connected: {cs.get('idrac',{}).get('connected')}")
    print(f"  mode: {cs.get('mode')}")
    print(f"  features: {list(cs.get('features',{}).keys())[:5]}")

# Chat
print("\n=== Chat ===")
r = S.post(f"{BASE}/api/chat", json={"message": "what is the server model?", "action_level": "read_only"}, headers=H, timeout=60)
print(f"  {r.status_code}: {r.text[:150]}")

# Diagnostics summary
r = S.get(f"{BASE}/api/server/diagnostics-summary", headers=H, timeout=30)
print(f"\n=== Diagnostics Summary: {r.status_code} ===")
if r.status_code == 200:
    s = r.json().get("summary", {})
    print(f"  overall: {s.get('overall')}, thermal: {s.get('thermal',{}).get('status')}, power: {s.get('power',{}).get('status')}")

# OS SSH
print("\n=== OS SSH ===")
r = S.post(f"{BASE}/api/os/connect", json={"host": "100.71.148.201", "username": "dell", "password": "calvin", "port": 22}, headers=H, timeout=15)
print(f"  {r.status_code}: {r.text[:100]}")

# Disconnect
r = S.post(f"{BASE}/api/disconnect", headers=H)
print(f"\nDisconnect: {r.status_code}")
