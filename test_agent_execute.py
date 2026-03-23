#!/usr/bin/env python3
"""
Test Agent Execute Action
Debug the agent execute_action method
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.agent_core import DellAIAgent
from core.config import AgentConfig

async def test_agent_execute():
    print("🧪 Testing Agent Execute Action")
    print("=" * 40)
    
    try:
        # Initialize agent
        config = AgentConfig()
        agent = DellAIAgent(config)
        
        print("✅ Agent initialized successfully")
        
        # Test execute_action method signature without connection
        try:
            result = await agent.execute_action(
                action_level="read_only",
                command="health_check",
                parameters={}
            )
            print(f"✅ Execute action successful: {result}")
        except Exception as e:
            print(f"❌ Execute action failed: {e}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error details: {str(e)}")
            
            # This is expected - agent needs to be connected first
            if "Not connected to any server" in str(e):
                print("✅ This is expected - agent needs to be connected first")
        
        # Test method signature by checking the method
        import inspect
        sig = inspect.signature(agent.execute_action)
        print(f"✅ Method signature: {sig}")
        
        # Test with different parameters
        try:
            result = await agent.execute_action(
                action_level="read_only",
                command="get_system_info",
                parameters={}
            )
            print(f"✅ Another execute action successful: {result}")
        except Exception as e:
            print(f"❌ Another execute action failed: {e}")
            
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error details: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_agent_execute())
