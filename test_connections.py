#!/usr/bin/env python3
"""
Test fleet connections
"""

import requests

def test_connections():
    base_url = "http://localhost:8000"
    
    # Connect to all servers
    response = requests.post(f"{base_url}/api/fleet/connect-all")
    print(f'Connect all response: {response.status_code}')
    if response.status_code == 200:
        result = response.json()
        print(f'Connection result: {result}')
    
    # Get updated fleet overview
    response = requests.get(f"{base_url}/api/fleet/overview")
    if response.status_code == 200:
        overview = response.json()
        print(f'Updated fleet: {overview["data"]["online_servers"]} online, {overview["data"]["offline_servers"]} offline')
        print(f'Average health: {overview["data"]["average_health_score"]}%')
        
        # Show server details
        for server_id, server in overview["data"]["servers"].items():
            print(f'Server {server["name"]}: Status={server["status"]}, Health={server["health_score"]}%')

if __name__ == '__main__':
    test_connections()
