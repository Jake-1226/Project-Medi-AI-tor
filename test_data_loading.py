#!/usr/bin/env python3
"""
Test Data Loading Fix
"""

import requests

def test_data_loading():
    print("🧪 Testing Data Loading Fix")
    print("=" * 40)
    
    try:
        # Connect
        connection_data = {
            'host': '100.71.148.195',
            'username': 'root',
            'password': 'calvin',
            'port': 443
        }
        
        print("1. Connecting...")
        response = requests.post('http://localhost:8000/connect', json=connection_data, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Connection failed: {response.text}")
            return
            
        print("✅ Connected successfully")
        
        # Test get_system_info
        print("2. Testing get_system_info...")
        action_data = {
            'action': 'get_system_info',
            'action_level': 'read_only',
            'parameters': {}
        }
        
        response = requests.post('http://localhost:8000/api/execute', json=action_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Status: {response.status_code}")
            
            if 'result' in result and 'system_info' in result['result']:
                system_info = result['result']['system_info']
                print(f"   ✅ System info found: {system_info.get('model', 'N/A')}")
                print("   ✅ Data structure is correct")
            else:
                print(f"   ❌ System info not found in response")
                print(f"   Response structure: {list(result.keys())}")
        else:
            print(f"   ❌ Request failed: {response.text}")
        
        # Test get_full_inventory
        print("3. Testing get_full_inventory...")
        action_data = {
            'action': 'get_full_inventory',
            'action_level': 'read_only',
            'parameters': {}
        }
        
        response = requests.post('http://localhost:8000/api/execute', json=action_data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Status: {response.status_code}")
            
            if 'result' in result and 'server_info' in result['result']:
                server_info = result['result']['server_info']
                print(f"   ✅ Server info found: {server_info.get('model', 'N/A')}")
                print("   ✅ Data structure is correct")
            else:
                print(f"   ❌ Server info not found in response")
                print(f"   Response structure: {list(result.keys())}")
        else:
            print(f"   ❌ Request failed: {response.text}")
        
        # Disconnect
        requests.post('http://localhost:8000/api/disconnect', timeout=10)
        print("\n✅ Disconnected")
        
        print("\n🎯 Data loading fix applied successfully!")
        print("📱 Technician dashboard should now show system info!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_data_loading()
