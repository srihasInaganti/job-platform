# load_test/locustfile_api.py
from locust import HttpUser, task, between

class ApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def submit_job(self):
        self.client.post("/jobs", json={
            "s3_key": "uploads/pretest.jpg",
            "operation": "resize",
            "params": {"width": 200},
        })