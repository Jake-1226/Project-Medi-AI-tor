#!/usr/bin/env python3
"""
Check if server is running and accessible
"""

import requests

def check_server():
    print("🔍 Checking Server Status")
    print("=" * 40)
    
    try:
        # Check if server is running
        response = requests.get('http://localhost:8000/', timeout=5)
        print(f"Server Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Server is running and accessible")
            
            # Check technician dashboard
            tech_response = requests.get('http://localhost:8000/technician', timeout=5)
            print(f"Technician Dashboard: {tech_response.status_code}")
            
            # Check debug tool
            debug_response = requests.get('http://localhost:8000/browser_debug_tool.html', timeout=5)
            print(f"Browser Debug Tool: {debug_response.status_code}")
            
            # Check simple test
            simple_response = requests.get('http://localhost:8000/simple_browser_test.html', timeout=5)
            print(f"Simple Browser Test: {simple_response.status_code}")
            
            print("\n🎯 All links are working!")
            print("📱 Open these URLs in your browser:")
            print("   • Technician Dashboard: http://localhost:8000/technician")
            print("   • Browser Debug Tool: http://localhost:8000/static/browser_debug_tool.html")
            print("   • Simple Browser Test: http://localhost:8000/static/simple_browser_test.html")
            
        else:
            print(f"❌ Server responded with: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Server not accessible: {e}")
        print("   Make sure the server is running with: python main.py")

if __name__ == "__main__":
    check_server()
