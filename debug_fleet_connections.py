#!/usr/bin/env python3
"""
Debug fleet connection issues
"""

import asyncio
import sys
import os
import logging

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

from core.fleet_manager import fleet_manager

async def debug_connections():
    print('=== Debug Fleet Connections ===')
    
    try:
        # Get current fleet overview
        overview = fleet_manager.get_fleet_overview()
        print(f'Current servers: {len(overview["servers"])}')
        
        # Test each server connection individually
        for server_id, server_data in overview["servers"].items():
            print(f'\n--- Testing Server: {server_data["name"]} ---')
            print(f'Host: {server_data["host"]}:{server_data.get("port", 443)}')
            print(f'Current Status: {server_data["status"]}')
            
            # Test connection
            print('Attempting connection...')
            try:
                success = await fleet_manager.connect_server(server_id)
                print(f'Connection result: {success}')
                
                # Check updated status
                updated_server = fleet_manager.get_server(server_id)
                if updated_server:
                    print(f'Updated status: {updated_server.status.value}')
                    print(f'Health score: {updated_server.health_score}')
                    print(f'Alert count: {updated_server.alert_count}')
                
            except Exception as e:
                print(f'Connection error: {e}')
                import traceback
                traceback.print_exc()
        
        # Test RedfishClient directly
        print('\n--- Testing RedfishClient Directly ---')
        try:
            from integrations.redfish_client import RedfishClient
            
            client = RedfishClient(
                host='100.71.148.195',
                username='root',
                password='calvin',
                port=443
            )
            
            print('Created RedfishClient')
            
            # Test basic connection
            result = await client.connect()
            print(f'Direct connection result: {result}')
            
            if result:
                # Test getting system info
                try:
                    system_info = await client.get_system_info()
                    print(f'System info keys: {list(system_info.keys()) if isinstance(system_info, dict) else type(system_info)}')
                except Exception as e:
                    print(f'Error getting system info: {e}')
            
        except Exception as e:
            print(f'Error with direct RedfishClient: {e}')
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f'Error during debug: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(debug_connections())
