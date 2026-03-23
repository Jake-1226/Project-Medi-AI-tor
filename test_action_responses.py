#!/usr/bin/env python3
"""
Test Action Responses
Check what data structure the actions return
"""

import requests
import json

def test_action_responses():
    print("🧪 Testing Action Responses")
    print("=" * 40)
    
    # First connect
    try:
        connection_data = {
            'host': '100.71.148.195',
            'username': 'root',
            'password': 'calvin',
            'port': 443
        }
        
        print("1. Connecting to server...")
        response = requests.post('http://localhost:8000/connect', json=connection_data, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Connection failed: {response.text}")
            return
            
        print("✅ Connected successfully")
        
        # Test different actions
        actions = [
            'get_system_info',
            'get_full_inventory', 
            'health_check',
            'get_temperature_sensors',
            'get_fans',
            'get_power_supplies'
        ]
        
        for action in actions:
            print(f"\n2.{actions.index(action) + 1} Testing {action}...")
            
            action_data = {
                'action': action,
                'action_level': 'read_only',
                'parameters': {}
            }
            
            try:
                response = requests.post('http://localhost:8000/api/execute', json=action_data, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"   Status: {response.status_code}")
                    
                    # Check what data structure is returned
                    if 'data' in result:
                        data = result['data']
                        print(f"   Data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        
                        # Check for expected keys
                        expected_keys = ['system_info', 'server_info', 'connection_info', 'processors', 'memory', 'storage_devices']
                        found_keys = [key for key in expected_keys if key in data]
                        print(f"   Expected keys found: {found_keys}")
                        
                        # Show sample data
                        if 'system_info' in data:
                            print(f"   System info sample: {str(data['system_info'])[:100]}...")
                        elif 'server_info' in data:
                            print(f"   Server info sample: {str(data['server_info'])[:100]}...")
                        else:
                            print(f"   Data sample: {str(data)[:100]}...")
                    else:
                        print(f"   No 'data' key in response")
                        print(f"   Response: {str(result)[:200]}...")
                        
                else:
                    print(f"   Status: {response.status_code}")
                    print(f"   Error: {response.text}")
                    
            except Exception as e:
                print(f"   Error: {e}")
        
        # Disconnect
        requests.post('http://localhost:8000/api/disconnect', timeout=10)
        print("\n✅ Disconnected")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_action_responses()
