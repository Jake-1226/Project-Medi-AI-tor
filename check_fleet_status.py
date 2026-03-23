#!/usr/bin/env python3
"""
Check fleet status via API
"""

import requests

def check_fleet_status():
    base_url = "http://localhost:8000"
    
    # Get current fleet overview
    response = requests.get(f"{base_url}/api/fleet/overview")
    if response.status_code == 200:
        overview = response.json()
        print('Current fleet status:')
        print(f'Total servers: {overview["data"]["total_servers"]}')
        print(f'Online servers: {overview["data"]["online_servers"]}')
        print(f'Servers: {list(overview["data"]["servers"].keys())}')
        
        # Try to connect to first server if exists
        servers = overview["data"]["servers"]
        if servers:
            first_server_id = list(servers.keys())[0]
            print(f'\nTrying to connect to server: {first_server_id}')
            
            response = requests.post(f'{base_url}/api/fleet/servers/{first_server_id}/connect')
            print(f'Connect response: {response.status_code}')
            if response.status_code == 200:
                result = response.json()
                print(f'Connect result: {result}')
                
                # Check updated status
                response = requests.get(f'{base_url}/api/fleet/overview')
                if response.status_code == 200:
                    updated_overview = response.json()
                    print(f'Updated online servers: {updated_overview["data"]["online_servers"]}')
    else:
        print(f'Error getting fleet overview: {response.status_code}')

if __name__ == '__main__':
    check_fleet_status()
