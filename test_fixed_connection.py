#!/usr/bin/env python3
"""
Test Fixed Connection Method
"""

import requests

def test_fixed_connection():
    print("🧪 Testing Fixed Connection Method")
    print("=" * 40)
    
    try:
        # Test the exact same data the technician dashboard should send
        connection_data = {
            'host': '100.71.148.195',
            'username': 'root',
            'password': 'calvin',
            'port': 443
        }
        
        print("1. Testing /connect endpoint...")
        response = requests.post('http://localhost:8000/connect', json=connection_data, timeout=30)
        
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Connection successful!")
            
            # Test action execution
            action_data = {
                'action': 'health_check',
                'action_level': 'read_only',
                'parameters': {}
            }
            
            print("2. Testing action execution...")
            action_response = requests.post('http://localhost:8000/api/execute', json=action_data, timeout=30)
            print(f"   Status: {action_response.status_code}")
            
            if action_response.status_code == 200:
                print("✅ Action execution successful!")
                print("🎯 Backend is working correctly!")
            else:
                print(f"❌ Action execution failed: {action_response.text}")
                
        else:
            print(f"❌ Connection failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_fixed_connection()
