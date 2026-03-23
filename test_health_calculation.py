#!/usr/bin/env python3
"""
Test health calculation for fleet servers
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.fleet_manager import fleet_manager

async def test_health_calculation():
    print('=== Test Health Calculation ===')
    
    try:
        # Get fleet overview
        overview = fleet_manager.get_fleet_overview()
        print(f'Current servers: {len(overview["servers"])}')
        
        # Test health calculation for each server
        for server_id, server_data in overview["servers"].items():
            print(f'\n--- Testing Health for: {server_data["name"]} ---')
            
            # Get server object
            server = fleet_manager.get_server(server_id)
            if not server:
                print(f'Server not found: {server_id}')
                continue
            
            print(f'Status: {server.status.value}')
            print(f'Current health: {server.health_score}')
            
            # If connected, test metrics collection
            if server.status.value == 'online' and server_id in fleet_manager.active_connections:
                print('Collecting metrics...')
                try:
                    metrics = await fleet_manager._collect_server_metrics(
                        fleet_manager.active_connections[server_id], 
                        server_id
                    )
                    print(f'Metrics collected: {list(metrics.keys())}')
                    
                    # Calculate health
                    health_score = fleet_manager._calculate_health_score(metrics)
                    print(f'Calculated health: {health_score}')
                    
                    # Update server health
                    server.health_score = health_score
                    print(f'Updated server health: {server.health_score}')
                    
                except Exception as e:
                    print(f'Error collecting metrics: {e}')
                    import traceback
                    traceback.print_exc()
            else:
                print('Server not connected or no active connection')
        
        # Run fleet health check
        print('\n--- Running Fleet Health Check ---')
        health_check = await fleet_manager.run_fleet_health_check()
        print(f'Health check completed')
        print(f'Connected servers: {health_check["connected_servers"]}')
        
        # Show final health scores
        for server_id, server_result in health_check["servers"].items():
            print(f'{server_result["name"]}: Health={server_result.get("health_score", 0)}')
        
    except Exception as e:
        print(f'Error during health test: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_health_calculation())
