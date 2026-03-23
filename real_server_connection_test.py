#!/usr/bin/env python3
"""
Real Server Connection Test
Debug and fix specific server connection issues for the user's actual server
"""

import requests
import json
import time
import socket
import ssl
from datetime import datetime

class RealServerConnectionTest:
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
    
    def test_basic_server_connectivity(self):
        """Test basic connectivity to the actual server"""
        print("🌐 Basic Server Connectivity Test")
        print("=" * 50)
        
        # Test 1: TCP connection
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex((self.server_host, self.server_port))
            sock.close()
            
            if result == 0:
                self.log_test("Basic Connectivity", "TCP Connection", "PASS", f"Port {self.server_port} reachable")
            else:
                self.log_test("Basic Connectivity", "TCP Connection", "FAIL", f"Port {self.server_port} not reachable (error {result})")
                return False
        except Exception as e:
            self.log_test("Basic Connectivity", "TCP Connection", "FAIL", f"Error: {e}")
            return False
        
        # Test 2: SSL/TLS handshake
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with socket.create_connection((self.server_host, self.server_port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=self.server_host) as ssock:
                    ssock.settimeout(10)
                    cert = ssock.getpeercert()
                    self.log_test("Basic Connectivity", "SSL/TLS Handshake", "PASS", f"SSL handshake successful, cert subject: {cert.get('subject', 'N/A')}")
        except Exception as e:
            self.log_test("Basic Connectivity", "SSL/TLS Handshake", "FAIL", f"Error: {e}")
            return False
        
        # Test 3: Redfish API response
        try:
            url = f"https://{self.server_host}:{self.server_port}/redfish/v1/"
            response = requests.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.log_test("Basic Connectivity", "Redfish API", "PASS", f"Redfish API accessible, version: {data.get('RedfishVersion', 'N/A')}")
            else:
                self.log_test("Basic Connectivity", "Redfish API", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Basic Connectivity", "Redfish API", "FAIL", f"Error: {e}")
            return False
        
        return True
    
    def test_authentication_methods(self):
        """Test different authentication methods"""
        print("🔐 Authentication Methods Test")
        print("=" * 50)
        
        # Test 1: Basic auth via Redfish
        try:
            url = f"https://{self.server_host}:{self.server_port}/redfish/v1/Systems"
            auth = (self.username, self.password)
            response = requests.get(url, auth=auth, verify=False, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                systems = data.get('Members', [])
                self.log_test("Authentication", "Redfish Basic Auth", "PASS", f"Authentication successful, found {len(systems)} systems")
            else:
                self.log_test("Authentication", "Redfish Basic Auth", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Authentication", "Redfish Basic Auth", "FAIL", f"Error: {e}")
        
        # Test 2: Session creation
        try:
            session_url = f"https://{self.server_host}:{self.server_port}/redfish/v1/SessionService/Sessions"
            session_data = {
                "UserName": self.username,
                "Password": self.password
            }
            
            response = requests.post(session_url, json=session_data, verify=False, timeout=15)
            if response.status_code == 201:
                session_data = response.headers.get('X-Auth-Token', '')
                if session_data:
                    self.log_test("Authentication", "Session Creation", "PASS", "Session created successfully")
                else:
                    self.log_test("Authentication", "Session Creation", "FAIL", "No session token received")
            else:
                self.log_test("Authentication", "Session Creation", "FAIL", f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Authentication", "Session Creation", "FAIL", f"Error: {e}")
    
    def test_technician_dashboard_connection(self):
        """Test connection through technician dashboard"""
        print("🔧 Technician Dashboard Connection Test")
        print("=" * 50)
        
        # Test 1: Dashboard loading
        try:
            response = requests.get(f"{self.base_url}/technician", timeout=10)
            if response.status_code == 200:
                self.log_test("Technician Dashboard", "Dashboard Loading", "PASS", "Dashboard loads successfully")
            else:
                self.log_test("Technician Dashboard", "Dashboard Loading", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Technician Dashboard", "Dashboard Loading", "FAIL", f"Error: {e}")
            return False
        
        # Test 2: API connection with exact UI format
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=30)
            if response.status_code == 200:
                self.log_test("Technician Dashboard", "API Connection", "PASS", "Connection successful")
                
                # Test disconnect
                disconnect_response = requests.post(f"{self.base_url}/api/disconnect", timeout=15)
                if disconnect_response.status_code == 200:
                    self.log_test("Technician Dashboard", "API Disconnect", "PASS", "Disconnect successful")
                else:
                    self.log_test("Technician Dashboard", "API Disconnect", "FAIL", f"Status: {disconnect_response.status_code}")
            else:
                self.log_test("Technician Dashboard", "API Connection", "FAIL", f"Status: {response.status_code} - {response.text}")
        except Exception as e:
            self.log_test("Technician Dashboard", "API Connection", "FAIL", f"Error: {e}")
    
    def test_connection_debugging(self):
        """Debug connection issues with detailed logging"""
        print("🔍 Connection Debugging Test")
        print("=" * 50)
        
        # Test 1: Check if agent is initialized
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                self.log_test("Debugging", "Agent Health", "PASS", "Agent is healthy")
            else:
                self.log_test("Debugging", "Agent Health", "FAIL", f"Agent health check failed: {response.status_code}")
        except Exception as e:
            self.log_test("Debugging", "Agent Health", "FAIL", f"Error: {e}")
        
        # Test 2: Test connection with detailed error handling
        try:
            connection_data = {
                "serverHost": self.server_host,
                "username": self.username,
                "password": self.password,
                "port": str(self.server_port)
            }
            
            print(f"   Testing connection to: {self.server_host}:{self.server_port}")
            print(f"   Using credentials: {self.username} / {'*' * len(self.password)}")
            
            response = requests.post(f"{self.base_url}/api/connect", json=connection_data, timeout=30)
            
            print(f"   Response Status: {response.status_code}")
            print(f"   Response Headers: {dict(response.headers)}")
            print(f"   Response Body: {response.text}")
            
            if response.status_code == 200:
                self.log_test("Debugging", "Detailed Connection", "PASS", "Connection successful with detailed logging")
            else:
                self.log_test("Debugging", "Detailed Connection", "FAIL", f"Connection failed: {response.text}")
        except Exception as e:
            self.log_test("Debugging", "Detailed Connection", "FAIL", f"Error: {e}")
    
    def test_alternative_connection_methods(self):
        """Test alternative connection methods"""
        print("🔄 Alternative Connection Methods Test")
        print("=" * 50)
        
        # Test 1: Try different ports
        alternative_ports = [443, 8443, 5443, 4443, 8888]
        working_ports = []
        
        for port in alternative_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((self.server_host, port))
                sock.close()
                
                if result == 0:
                    working_ports.append(port)
                    self.log_test("Alternative Methods", f"Port {port}", "PASS", f"Port {port} is reachable")
                else:
                    self.log_test("Alternative Methods", f"Port {port}", "FAIL", f"Port {port} not reachable")
            except Exception as e:
                self.log_test("Alternative Methods", f"Port {port}", "FAIL", f"Error: {e}")
        
        if working_ports:
            self.log_test("Alternative Methods", "Port Summary", "PASS", f"Working ports: {working_ports}")
        else:
            self.log_test("Alternative Methods", "Port Summary", "FAIL", "No working ports found")
        
        # Test 2: Try different connection formats
        connection_formats = [
            {"serverHost": self.server_host, "username": self.username, "password": self.password, "port": "443"},
            {"host": self.server_host, "username": self.username, "password": self.password, "port": 443},
            {"serverHost": self.server_host, "username": self.username, "password": self.password, "port": 443},
        ]
        
        for i, format_data in enumerate(connection_formats):
            try:
                response = requests.post(f"{self.base_url}/api/connect", json=format_data, timeout=15)
                if response.status_code == 200:
                    self.log_test("Alternative Methods", f"Format {i+1}", "PASS", f"Format {i+1} works")
                    requests.post(f"{self.base_url}/api/disconnect", timeout=5)
                else:
                    self.log_test("Alternative Methods", f"Format {i+1}", "FAIL", f"Format {i+1} failed: {response.status_code}")
            except Exception as e:
                self.log_test("Alternative Methods", f"Format {i+1}", "FAIL", f"Error: {e}")
    
    def generate_connection_report(self):
        """Generate comprehensive connection report"""
        print("🎯 REAL SERVER CONNECTION REPORT")
        print("=" * 80)
        print()
        
        # Summary statistics
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        warning_tests = len([r for r in self.test_results if r["status"] == "WARN"])
        
        print("📊 CONNECTION TEST SUMMARY:")
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
        
        print(f"🎯 OVERALL CONNECTION STATUS: {overall_status}")
        print("=" * 80)
        
        # Recommendations
        print("🚀 CONNECTION RECOMMENDATIONS:")
        if failed_tests == 0:
            print("  ✅ All tests passed - connection should work perfectly")
        elif failed_tests <= 3:
            print("  ⚠️  Minor issues found - connection should work with some adjustments")
        else:
            print("  ❌ Major issues found - connection needs significant fixes")
        
        print("  🔧 Check server IP and port accessibility")
        print("  🔧 Verify credentials are correct")
        print("  🔧 Ensure iDRAC is enabled and accessible")
        print("  🔧 Check firewall settings")
        print()
        
        print("🔗 TECHNICIAN DASHBOARD ACCESS:")
        print(f"  • Technician Dashboard: {self.base_url}/technician")
        print(f"  • Server: {self.server_host}:{self.server_port}")
        print(f"  • Credentials: {self.username} / {'*' * len(self.password)}")
        print()
        
        print("🏆 MEDI-AI-TOR: REAL SERVER CONNECTION TEST COMPLETE")
        print("=" * 80)

def main():
    tester = RealServerConnectionTest()
    
    print("🚀 Starting Real Server Connection Test...")
    print()
    print(f"Testing connection to your actual server: {tester.server_host}:{tester.server_port}")
    print(f"Using your credentials: {tester.username} / {'*' * len(tester.password)}")
    print()
    
    # Run all tests
    tester.test_basic_server_connectivity()
    tester.test_authentication_methods()
    tester.test_technician_dashboard_connection()
    tester.test_connection_debugging()
    tester.test_alternative_connection_methods()
    
    # Generate report
    tester.generate_connection_report()

if __name__ == "__main__":
    main()
