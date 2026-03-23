#!/usr/bin/env python3
"""
Wait for health monitoring to collect data
"""

import time
import requests

def wait_for_health():
    print('Waiting for monitoring to collect data...')
    
    for i in range(10):
        time.sleep(1)
        try:
            response = requests.get('http://localhost:8000/api/fleet/overview')
            if response.status_code == 200:
                overview = response.json()
                avg_health = overview['data']['average_health_score']
                print(f'Second {i+1}: Average health = {avg_health}%')
                
                # Show server details
                for server_id, server in overview['data']['servers'].items():
                    print(f'  {server["name"]}: {server["health_score"]}%')
                
                if avg_health > 0:
                    print('Health monitoring is working!')
                    break
        except Exception as e:
            print(f'Error: {e}')
    
    # Final check
    try:
        response = requests.get('http://localhost:8000/api/fleet/overview')
        if response.status_code == 200:
            overview = response.json()
            print(f'\nFinal fleet status:')
            print(f'  Total: {overview["data"]["total_servers"]}')
            print(f'  Online: {overview["data"]["online_servers"]}')
            print(f'  Average Health: {overview["data"]["average_health_score"]}%')
            print(f'  Total Alerts: {overview["data"]["total_alerts"]}')
    except Exception as e:
        print(f'Final check error: {e}')

if __name__ == '__main__':
    wait_for_health()
