"""Docker Compose 环境的最小智能运维闭环 Smoke。"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000/api/v1"


def request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def main() -> None:
    auth = request(
        "POST",
        "/auth/login",
        {"email": "admin@example.com", "password": "Demo123456"},
    )
    token = auth["access_token"]
    equipment = request("GET", "/equipment?page_size=100", token=token)["items"]
    motor = next(item for item in equipment if "MTR" in item["code"])

    request(
        "POST",
        "/intelligence/simulator/configure",
        {
            "equipment_ids": [motor["id"]],
            "interval_seconds": 1,
            "scenario": "composite_anomaly",
            "seed": 20260731,
            "auto_create_work_orders": True,
        },
        token,
    )
    created_orders = 0
    for _ in range(10):
        result = request("POST", "/intelligence/simulator/tick", {}, token)
        created_orders += result["work_orders_created"]

    detail = request("GET", f"/intelligence/equipment/{motor['id']}", token=token)
    diagnoses = request("GET", "/intelligence/diagnoses", token=token)
    recommendations = request("GET", "/intelligence/recommendations", token=token)
    assert detail["health_score"] < 80
    assert detail["anomalies"]
    assert diagnoses
    assert recommendations
    assert created_orders == 1
    print(
        f"intelligent loop smoke passed: equipment={motor['code']}, "
        f"health={detail['health_score']}, work_orders={created_orders}"
    )


if __name__ == "__main__":
    main()
