#!/usr/bin/env python3
"""Full realtime monitoring test — connect, start monitoring, check WS, check metrics."""
import requests, urllib3, json, time, asyncio, websockets

urllib3.disable_warnings()
S = requests.Session()
S.verify = False
BASE = "http://localhost"

# Login
r = S.post(f"{BASE}/api/auth/login", json={"username":"admin","password":"admin123"})
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}"}
print(f"Login: {r.status_code}")

# Step 1: Connect to iDRAC via technician API (per-session)
print("\n=== Step 1: Connect to iDRAC ===")
r = S.post(f"{BASE}/api/connect", json={
    "host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443
}, headers=H, timeout=30)
print(f"iDRAC connect: {r.status_code} {r.json().get('status')}")

# Step 2: Start monitoring
print("\n=== Step 2: Start monitoring ===")
r = S.post(f"{BASE}/monitoring/start", headers=H, timeout=10)
print(f"Start monitoring: {r.status_code} {r.text[:150]}")

# Step 3: Check monitoring status
print("\n=== Step 3: Monitoring status ===")
r = S.get(f"{BASE}/monitoring/status")
print(f"Status: {r.status_code}")
status = r.json().get("monitoring_status", {})
print(f"  Active: {status.get('status')}")
print(f"  Checks: {len(status.get('checks', []))}")

# Step 4: Test the WebSocket endpoint
print("\n=== Step 4: WebSocket test ===")
async def test_ws():
    ws_url = f"ws://localhost/ws/monitoring?token={token}"
    try:
        async with websockets.connect(ws_url, close_timeout=5) as ws:
            print(f"  WS connected!")
            # Wait for first message
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(msg)
                print(f"  First message type: {data.get('type')}")
                if data.get('metrics'):
                    print(f"  Metrics keys: {list(data['metrics'].keys())[:5]}")
                elif data.get('type') == 'metrics_update':
                    print(f"  Metrics: {json.dumps(data)[:150]}")
                else:
                    print(f"  Data: {json.dumps(data)[:150]}")
                
                # Wait for second message
                msg2 = await asyncio.wait_for(ws.recv(), timeout=15)
                data2 = json.loads(msg2)
                print(f"  Second message type: {data2.get('type')}")
            except asyncio.TimeoutError:
                print(f"  Timeout waiting for WS message")
    except Exception as e:
        print(f"  WS error: {e}")

try:
    asyncio.run(test_ws())
except Exception as e:
    print(f"  WS test failed: {e}")

# Step 5: Check the realtime page connection form endpoint
print("\n=== Step 5: connectAndMonitor flow ===")
# This simulates what the realtime page's "Connect & Monitor" button does
r = S.post(f"{BASE}/api/connect", json={
    "host": "100.71.148.195", "username": "root", "password": "calvin", "port": 443
}, headers=H, timeout=30)
print(f"Connect: {r.status_code}")

r = S.post(f"{BASE}/monitoring/start", headers=H, timeout=10)
print(f"Monitoring start: {r.status_code}")

# Step 6: Check monitoring alerts endpoint  
print("\n=== Step 6: Monitoring alerts ===")
r = S.get(f"{BASE}/monitoring/alerts")
print(f"Alerts: {r.status_code} {r.text[:100]}")

# Step 7: Stop monitoring
print("\n=== Step 7: Stop monitoring ===")
r = S.post(f"{BASE}/monitoring/stop", headers=H)
print(f"Stop: {r.status_code} {r.json().get('status')}")

# Disconnect
S.post(f"{BASE}/api/disconnect", headers=H)
print("\nDone.")
