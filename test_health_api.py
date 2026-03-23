#!/usr/bin/env python3
"""
Test health check via API
"""

import requests
import time

def test_health_api():
    print('Testing fleet health check via API...')
    
    # Trigger health check
    response = requests.post('http://localhost:8000/api/fleet/health-check')
    print(f'Health check response: {response.status_code}')
    if response.status_code == 200:
        result = response.json()
        print(f'Health check result: {result["message"]}')
        print(f'Connected servers: {result["data"]["connected_servers"]}')
        
        # Check updated fleet overview
        response = requests.get('http://localhost:8000/api/fleet/overview')
        if response.status_code == 200:
            overview = response.json()
            print(f'Updated average health: {overview["data"]["average_health_score"]}%')
            
            for server_id, server in overview['data']['servers'].items():
                print(f'  {server["name"]}: {server["health_score"]}% health')
    else:
        print(f'Health check failed: {response.status_code}')

if __name__ == '__main__':
    test_health_api()
