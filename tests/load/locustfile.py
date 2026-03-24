"""
Medi-AI-tor Load Test Script (#56)
Usage: pip install locust && locust -f tests/load/locustfile.py --host http://localhost:8000
"""
from locust import HttpUser, task, between
import json

class TechnicianUser(HttpUser):
    """Simulates a technician using the dashboard."""
    wait_time = between(1, 5)
    token = None

    def on_start(self):
        """Login on start."""
        r = self.client.post("/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"})
        if r.status_code == 200:
            self.token = r.json().get("token", "")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    @task(5)
    def health_check(self):
        self.client.get("/api/health")

    @task(3)
    def quick_status(self):
        self.client.get("/api/server/quick-status", headers=self._headers())

    @task(3)
    def fleet_overview(self):
        self.client.get("/api/fleet/overview", headers=self._headers())

    @task(2)
    def connection_status(self):
        self.client.get("/api/connection/status", headers=self._headers())

    @task(1)
    def fleet_alerts(self):
        self.client.get("/api/fleet/alerts?hours=24&limit=50", headers=self._headers())

    @task(1)
    def glossary(self):
        self.client.get("/api/glossary")

    @task(1)
    def metrics(self):
        self.client.get("/metrics")


class CustomerUser(HttpUser):
    """Simulates a customer using the chat page."""
    wait_time = between(2, 8)

    @task(5)
    def load_page(self):
        self.client.get("/")

    @task(2)
    def check_status(self):
        self.client.get("/api/server/quick-status")
