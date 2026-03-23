#!/usr/bin/env python3
"""
Final fleet status check
"""

import requests

def final_fleet_check():
    base_url = "http://localhost:8000"
    
    # Connect to second server
    response = requests.post(f'{base_url}/api/fleet/servers/0f2c078b-4845-4bdb-9cb8-41a1b383f5e8/connect')
    print(f'Second server connect: {response.status_code}')
    if response.status_code == 200:
        result = response.json()
        print(f'Result: {result}')
    
    # Get final fleet overview
    response = requests.get(f'{base_url}/api/fleet/overview')
    if response.status_code == 200:
        overview = response.json()
        print(f'Final fleet status:')
        print(f'  Total: {overview["data"]["total_servers"]}')
        print(f'  Online: {overview["data"]["online_servers"]}')
        print(f'  Offline: {overview["data"]["offline_servers"]}')
        print(f'  Avg Health: {overview["data"]["average_health_score"]}%')
        
        for server_id, server in overview['data']['servers'].items():
            print(f'  {server["name"]}: {server["status"]} ({server["health_score"]}% health)')

if __name__ == '__main__':
    final_fleet_check()
