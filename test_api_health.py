#!/usr/bin/env python3
"""
Test health calculation through API
"""

import requests
import time

def test_api_health():
    base_url = "http://localhost:8000"
    
    print('=== Test API Health Calculation ===')
    
    # Get current fleet overview
    response = requests.get(f'{base_url}/api/fleet/overview')
    if response.status_code == 200:
        overview = response.json()
        print(f'Current fleet:')
        print(f'  Total servers: {overview["data"]["total_servers"]}')
        print(f'  Online servers: {overview["data"]["online_servers"]}')
        
        for server_id, server in overview['data']['servers'].items():
            print(f'  {server["name"]}: {server["status"]} ({server["health_score"]}% health)')
    
    # Wait a bit and check again
    print('\nWaiting 5 seconds for monitoring to collect data...')
    time.sleep(5)
    
    # Check again
    response = requests.get(f'{base_url}/api/fleet/overview')
    if response.status_code == 200:
        overview = response.json()
        print(f'Updated fleet:')
        print(f'  Total servers: {overview["data"]["total_servers"]}')
        print(f'  Online servers: {overview["data"]["online_servers"]}')
        print(f'  Average health: {overview["data"]["average_health_score"]}%')
        
        for server_id, server in overview['data']['servers'].items():
            print(f'  {server["name"]}: {server["status"]} ({server["health_score"]}% health, {server["alert_count"]} alerts)')
    
    # Test individual server details
    print('\n--- Individual Server Details ---')
    response = requests.get(f'{base_url}/api/fleet/overview')
    if response.status_code == 200:
        overview = response.json()
        for server_id in overview['data']['servers'].keys():
            response = requests.get(f'{base_url}/api/fleet/servers/{server_id}')
            if response.status_code == 200:
                server_info = response.json()
                print(f'Server {server_info["server"]["name"]}:')
                print(f'  Status: {server_info["server"]["status"]}')
                print(f'  Health: {server_info["server"]["health_score"]}%')
                print(f'  Alerts: {server_info["server"]["alert_count"]}')
                print(f'  Last Seen: {server_info["server"]["last_seen"]}')

if __name__ == '__main__':
    test_api_health()
