#!/usr/bin/env python3
"""
Debug monitoring issues in fleet management
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

async def debug_monitoring():
    print('=== Debug Fleet Monitoring ===')
    
    try:
        # Get fleet overview
        overview = fleet_manager.get_fleet_overview()
        print(f'Current servers: {len(overview["servers"])}')
        
        # Test monitoring for each server
        for server_id, server_data in overview["servers"].items():
            print(f'\n--- Debug Monitoring for: {server_data["name"]} ---')
            
            # Get server object
            server = fleet_manager.get_server(server_id)
            if not server:
                print(f'Server not found: {server_id}')
                continue
            
            print(f'Status: {server.status.value}')
            
            # If connected, test monitoring directly
            if server.status.value == 'online' and server_id in fleet_manager.active_connections:
                print('Testing monitoring process...')
                
                client = fleet_manager.active_connections[server_id]
                
                # Test each metric collection step
                print('\n1. Testing thermal data collection...')
                try:
                    thermal_data = await client.get_temperature_sensors()
                    print(f'   Thermal data type: {type(thermal_data)}')
                    if isinstance(thermal_data, dict):
                        print(f'   Thermal keys: {list(thermal_data.keys())}')
                        temps = thermal_data.get('Temperatures', [])
                        print(f'   Temperature count: {len(temps)}')
                        if temps:
                            print(f'   Sample temp: {temps[0]}')
                    else:
                        print(f'   Unexpected thermal data: {thermal_data}')
                except Exception as e:
                    print(f'   Thermal error: {e}')
                
                print('\n2. Testing power data collection...')
                try:
                    power_data = await client.get_power_supplies()
                    print(f'   Power data type: {type(power_data)}')
                    if isinstance(power_data, dict):
                        print(f'   Power keys: {list(power_data.keys())}')
                        psus = power_data.get('PowerSupplies', [])
                        print(f'   PSU count: {len(psus)}')
                        if psus:
                            print(f'   Sample PSU: {psus[0]}')
                    else:
                        print(f'   Unexpected power data: {power_data}')
                except Exception as e:
                    print(f'   Power error: {e}')
                
                print('\n3. Testing memory data collection...')
                try:
                    memory_data = await client.get_memory()
                    print(f'   Memory data type: {type(memory_data)}')
                    if isinstance(memory_data, dict):
                        print(f'   Memory keys: {list(memory_data.keys())}')
                        dimms = memory_data.get('Memory', [])
                        print(f'   DIMM count: {len(dimms)}')
                        if dimms:
                            print(f'   Sample DIMM: {dimms[0]}')
                    else:
                        print(f'   Unexpected memory data: {memory_data}')
                except Exception as e:
                    print(f'   Memory error: {e}')
                
                print('\n4. Testing storage data collection...')
                try:
                    storage_data = await client.get_storage()
                    print(f'   Storage data type: {type(storage_data)}')
                    if isinstance(storage_data, dict):
                        print(f'   Storage keys: {list(storage_data.keys())}')
                        drives = storage_data.get('drives', [])
                        print(f'   Drive count: {len(drives)}')
                        if drives:
                            print(f'   Sample drive: {drives[0]}')
                    else:
                        print(f'   Unexpected storage data: {storage_data}')
                except Exception as e:
                    print(f'   Storage error: {e}')
                
                print('\n5. Testing system info collection...')
                try:
                    system_info = await client.get_system_info()
                    print(f'   System info type: {type(system_info)}')
                    if hasattr(system_info, '__dict__'):
                        print(f'   System info attributes: {list(system_info.__dict__.keys())}')
                    else:
                        print(f'   System info: {system_info}')
                except Exception as e:
                    print(f'   System info error: {e}')
                
                # Test complete metrics collection
                print('\n6. Testing complete metrics collection...')
                try:
                    metrics = await fleet_manager._collect_server_metrics(client, server_id)
                    print(f'   Metrics collected: {list(metrics.keys())}')
                    
                    # Test health calculation
                    health_score = fleet_manager._calculate_health_score(metrics)
                    print(f'   Health score: {health_score}')
                    
                    # Update server health
                    server.health_score = health_score
                    print(f'   Updated server health: {server.health_score}')
                    
                except Exception as e:
                    print(f'   Complete metrics error: {e}')
                    import traceback
                    traceback.print_exc()
            else:
                print('Server not connected or no active connection')
        
    except Exception as e:
        print(f'Error during monitoring debug: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(debug_monitoring())
