#!/usr/bin/env python3
"""
Error Diagnosis Tool
Comprehensive tool to diagnose and fix continuing connection errors
"""

import requests
import json
import time
from datetime import datetime

class ErrorDiagnosisTool:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.test_results = []
        self.server_host = "100.71.148.195"
        self.username = "root"
        self.password = "calvin"
        self.server_port = 443
        
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
    
    def test_server_health(self):
        """Test basic server health"""
        print("🏥 Server Health Check")
        print("=" * 40)
        
        # Test 1: Basic connectivity
        try:
            response = requests.get(f"{self.base_url}/", timeout=10)
            if response.status_code == 200:
                self.log_test("Server Health", "Basic Connectivity", "PASS", "Server responds")
            else:
                self.log_test("Server Health", "Basic Connectivity", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Server Health", "Basic Connectivity", "FAIL", f"Error: {e}")
            return False
        
        # Test 2: API health
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Server Health", "API Health", "PASS", f"API healthy: {data.get('status')}")
            else:
                self.log_test("Server Health", "API Health", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Server Health", "API Health", "FAIL", f"Error: {e}")
        
        return True
    
    def test_connection_endpoints(self):
        """Test all connection endpoints"""
        print("🔌 Connection Endpoints Test")
        print("=" * 40)
        
        # Test 1: API connect endpoint
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=30)
            
            print(f"   Status: {response.status_code}")
            print(f"   Headers: {dict(response.headers)}")
            print(f"   Body: {response.text}")
            
            if response.status_code == 200:
                self.log_test("Connection Endpoints", "API Connect", "PASS", "Connection successful")
                
                # Test disconnect
                disconnect_response = requests.post(f"{self.base_url}/api/disconnect", timeout=15)
                if disconnect_response.status_code == 200:
                    self.log_test("Connection Endpoints", "API Disconnect", "PASS", "Disconnect successful")
                else:
                    self.log_test("Connection Endpoints", "API Disconnect", "FAIL", f"Status: {disconnect_response.status_code}")
            else:
                self.log_test("Connection Endpoints", "API Connect", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_test("Connection Endpoints", "API Connect", "FAIL", f"Error: {e}")
        
        # Test 2: Old connect endpoint
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/connect", json=connection_data, timeout=30)
            if response.status_code == 200:
                self.log_test("Connection Endpoints", "Old Connect", "PASS", "Old endpoint works")
                requests.post(f"{self.base_url}/api/disconnect", timeout=10)
            else:
                self.log_test("Connection Endpoints", "Old Connect", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_test("Connection Endpoints", "Old Connect", "FAIL", f"Error: {e}")
    
    def test_technician_dashboard(self):
        """Test technician dashboard loading and JavaScript"""
        print("🔧 Technician Dashboard Test")
        print("=" * 40)
        
        # Test 1: Dashboard loading
        try:
            response = requests.get(f"{self.base_url}/technician", timeout=10)
            if response.status_code == 200:
                self.log_test("Technician Dashboard", "Dashboard Loading", "PASS", "Dashboard loads")
                
                # Check for critical elements
                content = response.text
                critical_elements = [
                    ("connectionForm", "Connection form"),
                    ("connectBtn", "Connect button"),
                    ("disconnectBtn", "Disconnect button"),
                    ("serverHost", "Server host field"),
                    ("username", "Username field"),
                    ("password", "Password field"),
                    ("port", "Port field"),
                    ("app.js", "JavaScript file")
                ]
                
                missing_elements = []
                for element, name in critical_elements:
                    if element not in content:
                        missing_elements.append(name)
                
                if missing_elements:
                    self.log_test("Technician Dashboard", "Critical Elements", "WARN", f"Missing: {missing_elements}")
                else:
                    self.log_test("Technician Dashboard", "Critical Elements", "PASS", "All elements present")
            else:
                self.log_test("Technician Dashboard", "Dashboard Loading", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Technician Dashboard", "Dashboard Loading", "FAIL", f"Error: {e}")
        
        # Test 2: JavaScript accessibility
        try:
            response = requests.get(f"{self.base_url}/static/js/app.js", timeout=10)
            if response.status_code == 200:
                self.log_test("Technician Dashboard", "JavaScript File", "PASS", "JavaScript accessible")
                
                # Check for critical functions
                js_content = response.text
                critical_functions = [
                    ("connectToServer", "Connect function"),
                    ("disconnectFromServer", "Disconnect function"),
                    ("fetch", "Fetch API"),
                    ("api/connect", "API endpoint")
                ]
                
                missing_functions = []
                for function, name in critical_functions:
                    if function not in js_content:
                        missing_functions.append(name)
                
                if missing_functions:
                    self.log_test("Technician Dashboard", "Critical Functions", "WARN", f"Missing: {missing_functions}")
                else:
                    self.log_test("Technician Dashboard", "Critical Functions", "PASS", "All functions present")
            else:
                self.log_test("Technician Dashboard", "JavaScript File", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Technician Dashboard", "JavaScript File", "FAIL", f"Error: {e}")
    
    def test_browser_simulation(self):
        """Simulate exact browser behavior"""
        print("🌐 Browser Simulation Test")
        print("=" * 40)
        
        # Test 1: Exact browser request simulation
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/technician"
            }
            
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            print(f"   Sending request to: {self.base_url}/api/connect")
            print(f"   Headers: {dict(headers)}")
            print(f"   Data: {connection_data}")
            
            response = requests.post(
                f"{self.base_url}/api/connect", 
                json=connection_data, 
                headers=headers, 
                timeout=30,
                allow_redirects=True
            )
            
            print(f"   Response Status: {response.status_code}")
            print(f"   Response Headers: {dict(response.headers)}")
            print(f"   Response Body: {response.text}")
            
            if response.status_code == 200:
                self.log_test("Browser Simulation", "Exact Request", "PASS", "Browser simulation successful")
                
                # Test disconnect
                disconnect_response = requests.post(f"{self.base_url}/api/disconnect", headers=headers, timeout=15)
                if disconnect_response.status_code == 200:
                    self.log_test("Browser Simulation", "Disconnect Request", "PASS", "Disconnect successful")
                else:
                    self.log_test("Browser Simulation", "Disconnect Request", "FAIL", f"Status: {disconnect_response.status_code}")
            else:
                self.log_test("Browser Simulation", "Exact Request", "FAIL", f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_test("Browser Simulation", "Exact Request", "FAIL", f"Error: {e}")
    
    def test_error_scenarios(self):
        """Test various error scenarios"""
        print("🚨 Error Scenarios Test")
        print("=" * 40)
        
        # Test 1: Invalid endpoint
        try:
            response = requests.post(f"{self.base_url}/api/invalid", json={}, timeout=10)
            if response.status_code == 404:
                self.log_test("Error Scenarios", "Invalid Endpoint", "PASS", "Correctly returns 404")
            else:
                self.log_test("Error Scenarios", "Invalid Endpoint", "FAIL", f"Should return 404: {response.status_code}")
        except Exception as e:
            self.log_test("Error Scenarios", "Invalid Endpoint", "FAIL", f"Error: {e}")
        
        # Test 2: Invalid method
        try:
            response = requests.get(f"{self.base_url}/api/connect", timeout=10)
            if response.status_code == 405:
                self.log_test("Error Scenarios", "Invalid Method", "PASS", "Correctly returns 405")
            else:
                self.log_test("Error Scenarios", "Invalid Method", "FAIL", f"Should return 405: {response.status_code}")
        except Exception as e:
            self.log_test("Error Scenarios", "Invalid Method", "FAIL", f"Error: {e}")
        
        # Test 3: Invalid data
        try:
            response = requests.post(f"{self.base_url}/api/connect", json={}, timeout=10)
            if response.status_code == 400:
                self.log_test("Error Scenarios", "Invalid Data", "PASS", "Correctly returns 400")
            else:
                self.log_test("Error Scenarios", "Invalid Data", "FAIL", f"Should return 400: {response.status_code}")
        except Exception as e:
            self.log_test("Error Scenarios", "Invalid Data", "FAIL", f"Error: {e}")
    
    def generate_diagnosis_report(self):
        """Generate comprehensive diagnosis report"""
        print("🎯 ERROR DIAGNOSIS REPORT")
        print("=" * 80)
        print()
        
        # Summary statistics
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        warning_tests = len([r for r in self.test_results if r["status"] == "WARN"])
        
        print("📊 DIAGNOSIS SUMMARY:")
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
        
        # Warning tests
        if warning_tests > 0:
            print("⚠️  WARNINGS:")
            for result in self.test_results:
                if result["status"] == "WARN":
                    print(f"  • {result['component']} - {result['test']}: {result['details']}")
            print()
        
        # Overall assessment
        if failed_tests == 0:
            overall_status = "🏆 EXCELLENT"
        elif failed_tests <= 3:
            overall_status = "✅ GOOD"
        else:
            overall_status = "❌ NEEDS WORK"
        
        print(f"🎯 OVERALL DIAGNOSIS STATUS: {overall_status}")
        print("=" * 80)
        
        # Recommendations
        print("🚀 DIAGNOSIS RECOMMENDATIONS:")
        if failed_tests == 0:
            print("  ✅ All tests passed - connection should work")
            print("  🔧 If still having issues, check browser console")
            print("  🔧 Clear browser cache and reload")
            print("  🔧 Check network connectivity")
        else:
            print("  ❌ Issues found - check the following:")
            print("  🔧 Review failed tests above")
            print("  🔧 Check browser console for JavaScript errors")
            print("  🔧 Verify server is running correctly")
            print("  🔧 Check network firewall settings")
            print("  🔧 Clear browser cache and reload")
        print()
        
        print("🔗 ACCESS POINTS:")
        print(f"  • Technician Dashboard: {self.base_url}/technician")
        print(f"  • Browser Test: {self.base_url}/js_debug_test.html")
        print(f"  • Connection Test: {self.base_url}/browser_connection_test.html")
        print(f"  • Server: {self.server_host}:{self.server_port}")
        print()
        
        print("🔧 DEBUGGING STEPS:")
        print("  1. Open browser developer tools (F12)")
        print("  2. Go to Console tab")
        print("  3. Try connecting in technician dashboard")
        print("  4. Look for any JavaScript errors")
        print("  5. Check Network tab for failed requests")
        print()
        
        print("🏆 MEDI-AI-TOR: ERROR DIAGNOSIS COMPLETE")
        print("=" * 80)

def main():
    diagnosis = ErrorDiagnosisTool()
    
    print("🚀 Starting Error Diagnosis Tool...")
    print()
    print(f"Diagnosing connection issues for: {diagnosis.server_host}:{diagnosis.server_port}")
    print(f"Using credentials: {diagnosis.username} / {'*' * len(diagnosis.password)}")
    print()
    
    # Run all diagnosis tests
    diagnosis.test_server_health()
    diagnosis.test_connection_endpoints()
    diagnosis.test_technician_dashboard()
    diagnosis.test_browser_simulation()
    diagnosis.test_error_scenarios()
    
    # Generate diagnosis report
    diagnosis.generate_diagnosis_report()

if __name__ == "__main__":
    main()
