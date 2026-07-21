"""Filing-season load profile.

Run only against a dedicated test/staging environment:
  locust -f tests/load/locustfile.py --host https://staging.example.com
Set GP_LOAD_TOKEN and GP_LOAD_CASE_ID to a synthetic test tenant/case.
"""
from __future__ import annotations

import os
from locust import HttpUser, between, task


class CAWorkbenchUser(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        token = os.environ["GP_LOAD_TOKEN"]
        self.case_id = os.environ["GP_LOAD_CASE_ID"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(5)
    def case_workspace(self):
        self.client.get(f"/api/cases/{self.case_id}", name="/api/cases/:id")
        self.client.get(f"/api/cases/{self.case_id}/facts", name="/api/cases/:id/facts")
        self.client.get(f"/api/cases/{self.case_id}/candidate-facts", name="/api/cases/:id/candidates")

    @task(3)
    def review_panels(self):
        self.client.get(f"/api/cases/{self.case_id}/missing-items", name="/api/cases/:id/missing")
        self.client.get(f"/api/cases/{self.case_id}/reconciliation", name="/api/cases/:id/reconciliation")
        self.client.get(f"/api/cases/{self.case_id}/audit-events", name="/api/cases/:id/audit")

    @task(1)
    def latest_computation(self):
        self.client.get(f"/api/cases/{self.case_id}/computations/latest", name="/api/cases/:id/computations/latest")
