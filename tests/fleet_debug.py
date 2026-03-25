#!/usr/bin/env python3
import requests, urllib3
urllib3.disable_warnings()
S = requests.Session()
S.verify = False

r = S.post("http://localhost/api/auth/login", json={"username":"admin","password":"admin123"})
H = {"Authorization": "Bearer " + r.json()["token"]}

# Check fleet
r = S.get("http://localhost/api/fleet/overview", headers=H)
ov = r.json().get("data", {})
print("Fleet: total=%d online=%d" % (ov.get("total_servers",0), ov.get("online_servers",0)))

r = S.get("http://localhost/api/v1/fleet/servers", headers=H)
servers = r.json().get("data", [])
print("Servers: %d" % len(servers))
for s in servers:
    print("  %s name=%s host=%s status=%s" % (s["id"][:12], s["name"], s["host"], s["status"]))

# Add if empty
if not servers:
    print("\nAdding F710...")
    r = S.post("http://localhost/api/fleet/servers", json={
        "name": "Dell PowerScale F710", "host": "100.71.148.195",
        "username": "root", "password": "calvin", "port": 443,
        "environment": "production", "model": "PowerScale F710", "service_tag": "3KQ38Y3"
    }, headers=H)
    print("Add: %d %s" % (r.status_code, r.json().get("status")))
    sid = r.json().get("server_id")
    servers = [{"id": sid, "name": "Dell PowerScale F710"}]

sid = servers[0]["id"]
print("\nConnecting %s..." % sid[:12])
r = S.post("http://localhost/api/fleet/servers/%s/connect" % sid, headers=H, timeout=60)
print("Connect: %d %s" % (r.status_code, r.text[:150]))

r = S.get("http://localhost/api/fleet/servers/%s" % sid, headers=H)
srv = r.json().get("server", {})
print("After connect: status=%s health=%s" % (srv.get("status"), srv.get("health_score")))

# Try disconnect + reconnect
S.post("http://localhost/api/fleet/servers/%s/disconnect" % sid, headers=H)
print("\nReconnecting...")
r = S.post("http://localhost/api/fleet/servers/%s/connect" % sid, headers=H, timeout=60)
print("Reconnect: %d %s" % (r.status_code, r.text[:150]))
