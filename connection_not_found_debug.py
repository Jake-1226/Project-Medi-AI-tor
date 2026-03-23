#!/usr/bin/env python3
"""
Connection Not Found Debug Test
Debug and fix the "not found" connection error
"""

import requests
import json
import time
from datetime import datetime

class ConnectionNotFoundDebug:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_results = []
        self.server_host = "100.71.148.195"
        self.server_port = 443
        self.username = "root"
        self.password = "calvin"
        
    def log_test(self, component, test, status, details=""):
        """Log test result"""
        result = {
            "component": component,
            "test": test,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {component} - {test}: {status}")
        if details:
            print(f"   {details}")
        print()
    
    def test_server_status(self):
        """Test if the server is running"""
        print("🖥️ Server Status Test")
        print("=" * 40)
        
        # Test 1: Basic server health
        try:
            response = requests.get(f"{self.base_url}/", timeout=10)
            if response.status_code == 200:
                self.log_test("Server Status", "Basic Health", "PASS", "Server is running")
            else:
                self.log_test("Server Status", "Basic Health", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Server Status", "Basic Health", "FAIL", f"Error: {e}")
            return False
        
        # Test 2: API health endpoint
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Server Status", "API Health", "PASS", f"API healthy: {data.get('status', 'unknown')}")
            else:
                self.log_test("Server Status", "API Health", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Server Status", "API Health", "FAIL", f"Error: {e}")
        
        # Test 3: Technician dashboard
        try:
            response = requests.get(f"{self.base_url}/technician", timeout=10)
            if response.status_code == 200:
                self.log_test("Server Status", "Technician Dashboard", "PASS", "Dashboard accessible")
            else:
                self.log_test("Server Status", "Technician Dashboard", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Server Status", "Technician Dashboard", "FAIL", f"Error: {e}")
        
        return True
    
    def test_api_endpoints(self):
        """Test all API endpoints"""
        print("🔌 API Endpoints Test")
        print("=" * 40)
        
        endpoints = [
            ("/api/health", "GET", "Health Check"),
            ("/api/connect", "POST", "Connect Endpoint"),
            ("/api/disconnect", "POST", "Disconnect Endpoint"),
            ("/api/execute", "POST", "Execute Endpoint"),
            ("/api/chat", "POST", "Chat Endpoint"),
            ("/api/investigate", "POST", "Investigate Endpoint"),
            ("/api/troubleshoot", "POST", "Troubleshoot Endpoint"),
        ]
        
        for endpoint, method, name in endpoints:
            try:
                if method == "GET":
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                else:
                    # For POST endpoints, send minimal data
                    data = {}
                    if "connect" in endpoint:
                        data = {"serverHost": "test", "username": "test", "password": "test", "port": "443"}
                    elif "execute" in endpoint:
                        data = {"action": "test", "action_level": "read_only"}
                    elif "chat" in endpoint:
                        data = {"message": "test", "action_level": "read_only"}
                    elif "investigate" in endpoint or "troubleshoot" in endpoint:
                        data = {"server_info": {"host": "test", "username": "test", "password": "test"}, "issue_description": "test", "action_level": "read_only"}
                    
                    response = requests.post(f"{self.base_url}{endpoint}", json=data, timeout=10)
                
                if response.status_code == 200:
                    self.log_test("API Endpoints", name, "PASS", f"Endpoint accessible")
                elif response.status_code == 404:
                    self.log_test("API Endpoints", name, "FAIL", f"Endpoint not found (404)")
                elif response.status_code == 405:
                    self.log_test("API Endpoints", name, "FAIL", f"Method not allowed (405)")
                else:
                    self.log_test("API Endpoints", name, "WARN", f"Status: {response.status_code}")
            except Exception as e:
                self.log_test("API Endpoints", name, "FAIL", f"Error: {e}")
    
    def test_connection_scenarios(self):
        """Test different connection scenarios"""
        print("🔗 Connection Scenarios Test")
        print("=" * 40)
        
        # Test 1: Correct API endpoint
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=30)
            if response.status_code == 200:
                self.log_test("Connection Scenarios", "Correct API", "PASS", "Connection successful")
                # Disconnect
                requests.post(f"{self.base_url}/api/disconnect", timeout=10)
            else:
                self.log_test("Connection Scenarios", "Correct API", "FAIL", f"Status: {response.status_code} - {response.text}")
        except Exception as e:
            self.log_test("Connection Scenarios", "Correct API", "FAIL", f"Error: {e}")
        
        # Test 2: Wrong endpoint
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/connect", json=connection_data, timeout=15)
            if response.status_code == 404:
                self.log_test("Connection Scenarios", "Wrong Endpoint", "PASS", "Correctly returns 404")
            else:
                self.log_test("Connection Scenarios", "Wrong Endpoint", "FAIL", f"Should return 404: {response.status_code}")
        except Exception as e:
            self.log_test("Connection Scenarios", "Wrong Endpoint", "FAIL", f"Error: {e}")
        
        # Test 3: Wrong field names
        try:
            connection_data = {
                "host": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": self.server_port
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=15)
            if response.status_code == 200:
                self.log_test("Connection Scenarios", "Wrong Fields", "PASS", "Accepts alternative field names")
                requests.post(f"{self.base_url}/api/disconnect", timeout=10)
            else:
                self.log_test("Connection Scenarios", "Wrong Fields", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Connection Scenarios", "Wrong Fields", "FAIL", f"Error: {e}")
        
        # Test 4: Missing fields
        try:
            connection_data = {
                "serverHost": self.server_host,
                # Missing username, password
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=15)
            if response.status_code == 400:
                self.log_test("Connection Scenarios", "Missing Fields", "PASS", "Correctly validates required fields")
            else:
                self.log_test("Connection Scenarios", "Missing Fields", "FAIL", f"Should return 400: {response.status_code}")
        except Exception as e:
            self.log_test("Connection Scenarios", "Missing Fields", "FAIL", f"Error: {e}")
    
    def test_browser_simulation(self):
        """Simulate browser connection attempts"""
        print("🌐 Browser Simulation Test")
        print("=" * 40)
        
        # Test 1: Simulate exact browser request
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(
                f"{self.base_url}/api/connect", 
                json=connection_data, 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                self.log_test("Browser Simulation", "Exact Browser Request", "PASS", "Browser simulation successful")
                requests.post(f"{self.base_url}/api/disconnect", timeout=10)
            else:
                self.log_test("Browser Simulation", "Exact Browser Request", "FAIL", f"Status: {response.status_code} - {response.text}")
        except Exception as e:
            self.log_test("Browser Simulation", "Exact Browser Request", "FAIL", f"Error: {e}")
        
        # Test 2: Test with different content types
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "*/*"
            }
            
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(
                f"{self.base_url}/api/connect", 
                json=connection_data, 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code == 200:
                self.log_test("Browser Simulation", "Different Headers", "PASS", "Works with different headers")
                requests.post(f"{self.base_url}/api/disconnect", timeout=10)
            else:
                self.log_test("Browser Simulation", "Different Headers", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Browser Simulation", "Different Headers", "FAIL", f"Error: {e}")
    
    def test_detailed_error_analysis(self):
        """Detailed error analysis"""
        print("🔍 Detailed Error Analysis")
        print("=" * 40)
        
        # Test 1: Check exact error message
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=30)
            
            print(f"   Response Status: {response.status_code}")
            print(f"   Response Headers: {dict(response.headers)}")
            print(f"   Response Body: {response.text}")
            
            if response.status_code == 404:
                self.log_test("Error Analysis", "404 Error", "FAIL", "API endpoint not found - check server routing")
            elif response.status_code == 500:
                self.log_test("Error Analysis", "500 Error", "FAIL", "Server error - check server logs")
            elif response.status_code == 200:
                self.log_test("Error Analysis", "Success", "PASS", "Connection working")
            else:
                self.log_test("Error Analysis", "Other Error", "FAIL", f"Unexpected status: {response.status_code}")
        except Exception as e:
            self.log_test("Error Analysis", "Exception", "FAIL", f"Exception: {e}")
    
    def generate_debug_report(self):
        """Generate comprehensive debug report"""
        print("🎯 CONNECTION NOT FOUND DEBUG REPORT")
        print("=" * 80)
        print()
        
        # Summary statistics
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        warning_tests = len([r for r in self.test_results if r["status"] == "WARN"])
        
        print("📊 DEBUG TEST SUMMARY:")
        print(f"  • Total Tests: {total_tests}")
        print(f"  • Passed: {passed_tests}")
        print(f"  • Failed: {failed_tests}")
        print(f"  • Warnings: {warning_tests}")
        print(f"  • Success Rate: {(passed_tests/total_tests*100):.1f}%")
        print()
        
        # Component breakdown
        components = {}
        for result in self.test_results:
            component = result["component"]
            if component not in components:
                components[component] = {"pass": 0, "fail": 0, "warn": 0}
            
            components[component][result["status"].lower()] += 1
        
        print("🔧 COMPONENT STATUS:")
        for component, counts in components.items():
            total = counts["pass"] + counts["fail"] + counts["warn"]
            success_rate = (counts["pass"] / total * 100) if total > 0 else 0
            
            if success_rate >= 90:
                status = "✅ EXCELLENT"
            elif success_rate >= 75:
                status = "⚠️  GOOD"
            else:
                status = "❌ NEEDS WORK"
            
            print(f"  {status} {component}: {success_rate:.0f}% ({counts['pass']}/{total} tests)")
        print()
        
        # Failed tests
        if failed_tests > 0:
            print("❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  • {result['component']} - {result['test']}: {result['details']}")
            print()
        
        # Overall assessment
        if failed_tests == 0:
            overall_status = "🏆 EXCELLENT"
        elif failed_tests <= 3:
            overall_status = "✅ GOOD"
        else:
            overall_status = "❌ NEEDS WORK"
        
        print(f"🎯 OVERALL DEBUG STATUS: {overall_status}")
        print("=" * 80)
        
        # Recommendations
        print("🚀 DEBUG RECOMMENDATIONS:")
        if failed_tests == 0:
            print("  ✅ All tests passed - connection should work")
        else:
            print("  ❌ Issues found - check the following:")
            print("  🔧 Ensure server is running on correct port")
            print("  🔧 Check API endpoint routing in main.py")
            print("  🔧 Verify JavaScript is using correct endpoints")
            print("  🔧 Check browser console for JavaScript errors")
            print("  🔧 Verify server logs for any errors")
        print()
        
        print("🔗 ACCESS POINTS:")
        print(f"  • Technician Dashboard: {self.base_url}/technician")
        print(f"  • Browser Test: {self.base_url}/browser_connection_test.html")
        print(f"  • Server: {self.server_host}:{self.server_port}")
        print()
        
        print("🏆 MEDI-AI-TOR: CONNECTION NOT FOUND DEBUG COMPLETE")
        print("=" * 80)

def main():
    debugger = ConnectionNotFoundDebug()
    
    print("🚀 Starting Connection Not Found Debug Test...")
    print()
    print(f"Debugging connection to: {debugger.server_host}:{debugger.server_port}")
    print(f"Using credentials: {debugger.username} / {'*' * len(debugger.password)}")
    print()
    
    # Run all debug tests
    debugger.test_server_status()
    debugger.test_api_endpoints()
    debugger.test_connection_scenarios()
    debugger.test_browser_simulation()
    debugger.test_detailed_error_analysis()
    
    # Generate report
    debugger.generate_debug_report()

if __name__ == "__main__":
    main()
