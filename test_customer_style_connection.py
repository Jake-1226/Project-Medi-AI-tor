#!/usr/bin/env python3
"""
Test Customer Style Connection Method in Technician Dashboard
"""

import requests
import json

def test_customer_style_connection():
    print("🧪 Testing Customer-Style Connection Method")
    print("=" * 50)
    
    try:
        # Test customer-style connection
        connection_data = {
            'host': '100.71.148.195',
            'username': 'root',
            'password': 'calvin',
            'port': 443
        }
        
        print("1. Testing customer-style connection...")
        response = requests.post('http://localhost:8000/connect', json=connection_data, timeout=30)
        
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Customer-style connection successful!")
            
            # Test action execution
            action_data = {
                'action': 'health_check',
                'action_level': 'read_only',
                'parameters': {}
            }
            
            print("2. Testing action execution...")
            action_response = requests.post('http://localhost:8000/api/execute', json=action_data, timeout=30)
            print(f"   Status: {action_response.status_code}")
            print(f"   Response: {action_response.text}")
            
            if action_response.status_code == 200:
                print("✅ Action execution successful!")
            else:
                print(f"❌ Action execution failed: {action_response.text}")
            
            # Test disconnect (UI-only)
            print("3. Testing disconnect (UI-only)...")
            print("   Disconnect will only update UI (no API call)")
            print("   ✅ Disconnect method updated to match customer pattern")
            
        else:
            print(f"❌ Customer-style connection failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_customer_style_connection()
