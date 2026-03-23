#!/usr/bin/env python3
"""
Browser Endpoint Test
Test exactly what the browser is trying to access
"""

import requests
import json
from datetime import datetime

def test_browser_endpoints():
    base_url = "http://localhost:8000"
    server_host = "100.71.148.195"
    username = "root"
    password = "calvin"
    port = "443"
    
    print("🌐 Browser Endpoint Test")
    print("=" * 50)
    
    # Test data
    connection_data = {
        "serverHost": server_host,
        "username": username,
        "password": password,
        "port": port
    }
    
    # Test 1: /api/connect (correct endpoint)
    print("1. Testing /api/connect (correct endpoint)")
    try:
        response = requests.post(f"{base_url}/api/connect", json=connection_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS: /api/connect works")
            # Disconnect
            requests.post(f"{base_url}/api/disconnect", timeout=10)
        else:
            print("   ❌ FAILED: /api/connect failed")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    print()
    
    # Test 2: /connect (old endpoint)
    print("2. Testing /connect (old endpoint)")
    try:
        response = requests.post(f"{base_url}/connect", json=connection_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS: /connect works")
            # Disconnect
            requests.post(f"{base_url}/api/disconnect", timeout=10)
        else:
            print("   ❌ FAILED: /connect failed")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    print()
    
    # Test 3: Check what the browser console might see
    print("3. Simulating browser JavaScript fetch")
    try:
        # This is exactly what the JavaScript does
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = requests.post(
            f"{base_url}/api/connect", 
            json=connection_data, 
            headers=headers, 
            timeout=30
        )
        
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ SUCCESS: Browser simulation works")
            # Disconnect
            requests.post(f"{base_url}/api/disconnect", timeout=10)
        else:
            print("   ❌ FAILED: Browser simulation failed")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    print()
    
    # Test 4: Check if there are any routing conflicts
    print("4. Checking for routing conflicts")
    try:
        # Test with different methods
        methods = ["GET", "POST", "PUT", "DELETE"]
        for method in methods:
            try:
                if method == "GET":
                    response = requests.get(f"{base_url}/api/connect", timeout=10)
                else:
                    response = requests.request(method, f"{base_url}/api/connect", json=connection_data, timeout=10)
                
                if response.status_code != 405:  # Method not allowed
                    print(f"   {method}: {response.status_code} - {response.text[:100]}")
            except Exception as e:
                print(f"   {method}: ERROR - {e}")
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print()
    
    # Test 5: Check technician dashboard loading
    print("5. Checking technician dashboard")
    try:
        response = requests.get(f"{base_url}/technician", timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            content = response.text
            if "api/connect" in content:
                print("   ✅ Dashboard contains api/connect reference")
            else:
                print("   ⚠️  Dashboard might not reference api/connect")
            
            if "connectToServer" in content:
                print("   ✅ Dashboard contains connectToServer function")
            else:
                print("   ⚠️  Dashboard might not have connectToServer function")
        else:
            print(f"   ❌ Dashboard failed: {response.status_code}")
    except Exception as e:
        print(f"   ERROR: {e}")

if __name__ == "__main__":
    test_browser_endpoints()
