#!/usr/bin/env python3
"""
Add test servers to fleet via API
"""

import requests
import json

def add_servers():
    base_url = "http://localhost:8000"
    
    # Add first server
    server1_data = {
        "name": "Production Server 1",
        "host": "100.71.148.195",
        "username": "root",
        "password": "calvin",
        "port": 443,
        "environment": "production",
        "location": "Data Center A",
        "tags": ["critical", "web"],
        "notes": "Primary production web server"
    }
    
    response = requests.post(f"{base_url}/api/fleet/servers", json=server1_data)
    print(f"Server 1 response: {response.status_code}")
    if response.status_code == 200:
        print(f"Server 1 added: {response.json()}")
    
    # Add second server
    server2_data = {
        "name": "Staging Server 1",
        "host": "100.71.148.106",
        "username": "root",
        "password": "calvin",
        "port": 443,
        "environment": "staging",
        "location": "Data Center B",
        "tags": ["staging", "test"],
        "notes": "Staging environment for testing"
    }
    
    response = requests.post(f"{base_url}/api/fleet/servers", json=server2_data)
    print(f"Server 2 response: {response.status_code}")
    if response.status_code == 200:
        print(f"Server 2 added: {response.json()}")
    
    # Get fleet overview
    response = requests.get(f"{base_url}/api/fleet/overview")
    print(f"Fleet overview: {response.status_code}")
    if response.status_code == 200:
        overview = response.json()
        print(f"Total servers: {overview['data']['total_servers']}")
        print(f"Online servers: {overview['data']['online_servers']}")

if __name__ == '__main__':
    add_servers()
