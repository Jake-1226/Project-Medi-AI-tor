#!/usr/bin/env python3
"""
Test manual health calculation
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.fleet_manager import fleet_manager

async def test_manual_health():
    print('=== Test Manual Health Calculation ===')
    
    try:
        # Get fleet overview
        overview = fleet_manager.get_fleet_overview()
        print(f'Current servers: {len(overview["servers"])}')
        
        # Test health calculation with sample data
        sample_metrics = {
            'thermal': {'Temperatures': [{'ReadingCelsius': 45}, {'ReadingCelsius': 50}]},
            'power': {'PowerSupplies': [{'Status': {'Health': 'OK'}}, {'Status': {'Health': 'OK'}}]},
            'memory': {'Memory': [{'Status': {'Health': 'OK'}}, {'Status': {'Health': 'OK'}}]},
            'storage': {'drives': [{'FailurePredicted': False}, {'FailurePredicted': False}]},
            'system': 'SystemInfo'
        }
        
        health_score = fleet_manager._calculate_health_score(sample_metrics)
        print(f'Sample health score: {health_score}%')
        
        # Test with empty metrics
        empty_health = fleet_manager._calculate_health_score({})
        print(f'Empty metrics health: {empty_health}%')
        
        # Test with partial data
        partial_metrics = {
            'thermal': {'Temperatures': [{'ReadingCelsius': 90}]},  # High temp
            'power': {},
            'memory': {},
            'storage': {},
            'system': {}
        }
        
        partial_health = fleet_manager._calculate_health_score(partial_metrics)
        print(f'Partial metrics health (high temp): {partial_health}%')
        
        # Now manually update server health in the running application
        print('\n--- Manually updating server health ---')
        
        for server_id, server_data in overview["servers"].items():
            print(f'Updating health for: {server_data["name"]}')
            
            # Get server object
            server = fleet_manager.get_server(server_id)
            if server:
                # Update health manually
                server.health_score = health_score
                print(f'Updated {server.name} health to {server.health_score}%')
        
        # Check updated overview
        updated_overview = fleet_manager.get_fleet_overview()
        print(f'\nUpdated fleet average health: {updated_overview["average_health_score"]}%')
        
    except Exception as e:
        print(f'Error during manual health test: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_manual_health())
