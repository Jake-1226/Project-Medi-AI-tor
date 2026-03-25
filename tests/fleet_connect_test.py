#!/usr/bin/env python3
"""Full fleet management test — clean, add, connect, verify, disconnect, reconnect."""
import requests, urllib3, json
urllib3.disable_warnings()
S = requests.Session()
S.verify = False

# Login
r = S.post("http://localhost/api/auth/login", json={"username":"admin","password":"admin123"})
H = {"Authorization": f"Bearer {r.json()['token']}"}

# 1. Check current fleet
print("=== Current Fleet ===")
r = S.get("http://localhost/api/fleet/overview", headers=H)
ov = r.json().get("data", {})
print(f"Total: {ov.get('total_servers',0)}, Online: {ov.get('online_servers',0)}")

r = S.get("http://localhost/api/v1/fleet/servers", headers=H)
servers = r.json().get("data", [])
for s in servers:
    sid = s['id'][:12]
    print(f"  {sid}... {s['name']} host={s['host']} status={s['status']}")

# 2. Delete ALL (stale encrypted passwords from previous restarts)
print("\n=== Deleting stale servers ===")
for s in servers:
    r = S.delete(f"http://localhost/api/fleet/servers/{s['id']}", headers=H)
    print(f"  Delete {s['name']}: {r.status_code}")

# 3. Add F710 fresh with correct password
print("\n=== Adding F710 ===")
r = S.post("http://localhost/api/fleet/servers", json={
    "name": "Dell PowerScale F710",
    "host": "100.71.148.195",
    "username": "root",
    "password": "calvin",
    "port": 443,
    "environment": "production",
    "model": "PowerScale F710",
    "service_tag": "3KQ38Y3"
}, headers=H)
print(f"Add: {r.status_code}")
new_id = r.json().get("server_id")
print(f"Server ID: {new_id}")

# 4. Connect
print("\n=== Connecting ===")
r = S.post(f"http://localhost/api/fleet/servers/{new_id}/connect", headers=H, timeout=60)
result = r.json()
print(f"Connect: {r.status_code} status={result.get('status')} msg={result.get('message')}")

# 5. Verify
print("\n=== Verify ===")
r = S.get("http://localhost/api/fleet/overview", headers=H)
ov = r.json().get("data", {})
print(f"Total: {ov.get('total_servers',0)}, Online: {ov.get('online_servers',0)}")

r = S.get(f"http://localhost/api/fleet/servers/{new_id}", headers=H)
srv = r.json().get("server", {})
print(f"Status: {srv.get('status')}")
print(f"Health: {srv.get('health_score')}")
print(f"Last seen: {srv.get('last_seen')}")

# 6. Disconnect
print("\n=== Disconnect ===")
r = S.post(f"http://localhost/api/fleet/servers/{new_id}/disconnect", headers=H)
print(f"Disconnect: {r.status_code} {r.json().get('status')}")

# 7. Reconnect
print("\n=== Reconnect ===")
r = S.post(f"http://localhost/api/fleet/servers/{new_id}/connect", headers=H, timeout=60)
result = r.json()
print(f"Reconnect: {r.status_code} status={result.get('status')} msg={result.get('message')}")

# 8. Final state
print("\n=== Final State ===")
r = S.get("http://localhost/api/fleet/overview", headers=H)
ov = r.json().get("data", {})
print(f"Total: {ov.get('total_servers',0)}, Online: {ov.get('online_servers',0)}, Offline: {ov.get('offline_servers',0)}")

# Disconnect for cleanup
S.post(f"http://localhost/api/fleet/servers/{new_id}/disconnect", headers=H)
print("\nDone.")
