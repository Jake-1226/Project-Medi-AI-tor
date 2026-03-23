#!/usr/bin/env python3
"""
Test script for Fleet Management functionality
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.fleet_manager import fleet_manager

async def test_fleet():
    print('=== Fleet Management Test ===')
    
    try:
        # Add first server
        server1_id = fleet_manager.add_server(
            name='Production Server 1',
            host='100.71.148.195',
            username='root',
            password='calvin',
            port=443,
            environment='production',
            location='Data Center A',
            tags=['critical', 'web']
        )
        print(f'Added server 1: {server1_id}')
        
        # Add second server
        server2_id = fleet_manager.add_server(
            name='Staging Server 1',
            host='100.71.148.106',
            username='root',
            password='calvin',
            port=443,
            environment='staging',
            location='Data Center B',
            tags=['staging', 'test']
        )
        print(f'Added server 2: {server2_id}')
        
        # Get fleet overview
        overview = fleet_manager.get_fleet_overview()
        print(f'Fleet overview: {overview["total_servers"]} servers total')
        
        # Test connection to first server
        print('Testing connection to server 1...')
        success1 = await fleet_manager.connect_server(server1_id)
        print(f'Server 1 connection: {"Success" if success1 else "Failed"}')
        
        # Test connection to second server
        print('Testing connection to server 2...')
        success2 = await fleet_manager.connect_server(server2_id)
        print(f'Server 2 connection: {"Success" if success2 else "Failed"}')
        
        # Get updated overview
        updated_overview = fleet_manager.get_fleet_overview()
        print(f'Updated fleet: {updated_overview["online_servers"]} online, {updated_overview["offline_servers"]} offline')
        
        # Show server details
        for server_id in [server1_id, server2_id]:
            server = fleet_manager.get_server(server_id)
            if server:
                print(f'Server {server.name}: Status={server.status.value}, Health={server.health_score:.1f}%, Alerts={server.alert_count}')
        
        # Test fleet health check
        print('Running fleet health check...')
        health_check = await fleet_manager.run_fleet_health_check()
        print(f'Health check completed for {health_check["connected_servers"]} servers')
        
        # Test recent alerts
        recent_alerts = fleet_manager.get_recent_alerts(hours=1, limit=10)
        print(f'Recent alerts: {len(recent_alerts)}')
        
        print('=== Fleet Management Test Complete ===')
        
    except Exception as e:
        print(f'Error during fleet test: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_fleet())
