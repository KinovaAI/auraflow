"""AuraFlow — Load Testing with Locust

Usage:
    pip install locust
    locust -f apps/api/tests/load/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to configure and start the test.
"""
from locust import HttpUser, task, between


class AuraFlowUser(HttpUser):
    wait_time = between(1, 5)

    @task(10)
    def health_check(self):
        self.client.get("/health")

    @task(5)
    def login(self):
        self.client.post(
            "/api/v1/auth/login",
            data={"username": "demo@example.com", "password": "demo"},
            catch_response=True,
        )

    @task(3)
    def get_schedule(self):
        self.client.get(
            "/api/v1/scheduling/sessions",
            headers={"Authorization": f"Bearer {getattr(self, '_token', 'fake')}"},
            catch_response=True,
        )

    def on_start(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            data={"username": "demo@example.com", "password": "demo"},
            catch_response=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            self._token = data.get("access_token", "")
