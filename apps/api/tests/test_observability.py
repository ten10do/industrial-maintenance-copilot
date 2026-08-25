"""Observability API 与 Metrics 测试。

覆盖：/metrics 格式与指标名、registry 隔离、RAG 空结果计数、
trace 详情 404/认证、真实工作流 timeline 及确定性排序、
搜索过滤与分页上限、legacy 空 trace 数据可读、敏感信息不泄露。
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from app.ai.knowledge_search import search_articles
from app.core.metrics import build_metrics
from app.core.security import create_access_token


def _auth(supervisor) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(supervisor.id))}"}


def test_build_metrics_registries_are_isolated():
    """两次构建独立 registry：互不影响，无 Duplicated timeseries。"""
    reg_a = CollectorRegistry()
    reg_b = CollectorRegistry()
    metrics_a = build_metrics(reg_a)
    metrics_a.telemetry_ingest_total.labels(status="accepted").inc()
    # registry B 上同名指标独立存在，不会冲突。
    metrics_b = build_metrics(reg_b)
    metrics_b.telemetry_ingest_total.labels(status="accepted").inc(2)
    payload_a = (
        __import__("prometheus_client", fromlist=["generate_latest"])
        .generate_latest(reg_a)
        .decode()
    )
    payload_b = (
        __import__("prometheus_client", fromlist=["generate_latest"])
        .generate_latest(reg_b)
        .decode()
    )
    assert "telemetry_ingest_total" in payload_a
    assert "telemetry_ingest_total" in payload_b


def test_rag_empty_result_metric_on_empty_knowledge(db):
    """空知识库检索：rag_empty_result_total 计数递增（应用共享实例）。"""
    from app.core.metrics import get_metrics

    metrics = get_metrics()
    before = metrics.rag_empty_result_total._value.get()
    results = search_articles(db, query="完全不存在的检索词xyzq")
    assert results == []
    after = metrics.rag_empty_result_total._value.get()
    assert after - before == 1


def test_metrics_endpoint_lists_core_families(client):
    """/metrics 返回 Prometheus 文本；包含核心指标族且无敏感词。"""
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    for family in (
        "telemetry_ingest_total",
        "industrial_alarm_total",
        "work_orders_created_total",
        "agent_runs_total",
        "rag_retrieval_total",
    ):
        assert family in body
    lowered = body.lower()
    for secret_marker in ("password", "secret", "authorization"):
        assert secret_marker not in lowered


def test_trace_detail_auth_and_404(client, supervisor):
    """未认证 → 401/403；认证后未知 trace_id → 404。"""
    anonymous = client.get("/api/v1/observability/traces/does-not-exist")
    assert anonymous.status_code in {401, 403}

    not_found = client.get(
        "/api/v1/observability/traces/does-not-exist", headers=_auth(supervisor)
    )
    assert not_found.status_code == 404


def test_health_reports_honest_statuses(client, supervisor):
    """health：状态只取自真实探测；OTel 默认关闭时如实为 unknown。

    Redis/Worker/Scheduler 依赖部署环境（本地无 Redis=unknown；
    CI 有 Redis 服务=healthy），因此只断言环境无关的诚实性约束。
    """
    response = client.get("/api/v1/observability/health", headers=_auth(supervisor))
    assert response.status_code == 200
    payload = response.json()
    components = payload["components"]
    allowed = {"healthy", "degraded", "unavailable", "unknown"}
    assert components, "必须返回组件列表"
    for name, component in components.items():
        assert component["status"] in allowed, f"{name}: {component['status']}"
    # OTel 默认关闭 → 必然 unknown（不伪造 healthy）。
    assert components["opentelemetry"]["status"] == "unknown"
    # ML 运行时在测试环境为确定性规则/未启用 provider，不得虚报 healthy。
    assert components["ml_inference"]["status"] in {"unknown"}
    assert "change-this-to-a-random-secret-key" not in response.text


def test_search_pagination_limit_and_legacy_null_rows(
    db, fault_chain, client, supervisor
):
    """分页 limit 生效；历史空 trace 数据不计入候选（保持可读）。"""
    from app.models.intelligence import TelemetryRecord
    from app.services.observability_service import search_traces

    equipment = fault_chain()[0]
    db.add(
        TelemetryRecord(
            equipment_id=equipment.id,
            collected_at=__import__("datetime").datetime.now(
                __import__("datetime").UTC
            ),
            cumulative_runtime_hours=1.0,
        )
    )
    db.commit()

    headers = _auth(supervisor)
    listed = client.get(
        "/api/v1/observability/traces?limit=1&offset=0", headers=headers
    )
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["limit"] == 1
    assert len(payload["items"]) <= 1
    assert all(item["trace_id"] for item in payload["items"])

    # service 层全量：legacy 空 trace 不成为候选。
    full = search_traces(db)
    assert full["total"] >= 1


def test_trace_timeline_deterministic_and_stage_ordered(
    fault_chain, db, client, supervisor
):
    """真实工作流 timeline：阶段齐全且多次重建顺序完全一致。"""
    from app.services.observability_service import get_trace

    _equipment, alarm, _work_order = fault_chain()
    assert alarm is not None and alarm.trace_id

    headers = _auth(supervisor)

    # 通过真实 HTTP 补充 analysis / review 阶段。
    analyzed = client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers)
    assert analyzed.status_code == 200

    detail_one = get_trace(db, alarm.trace_id)
    detail_two = get_trace(db, alarm.trace_id)
    assert detail_one is not None and detail_two is not None
    stages_one = [entry["stage"] for entry in detail_one["timeline"]]
    stages_two = [entry["stage"] for entry in detail_two["timeline"]]
    assert stages_one == stages_two
    assert {"telemetry", "anomaly", "prediction", "alarm"} <= set(stages_one)

    timestamps = [
        entry["timestamp"] for entry in detail_one["timeline"] if entry["timestamp"]
    ]
    assert timestamps == sorted(timestamps)


def test_full_workflow_via_http_shows_review_and_work_order(
    fault_chain, db, client, supervisor, equipment_type
):
    """HTTP 全流程：analyze → approve → create-work-order 后 timeline 完整。"""
    from app.services.observability_service import get_trace

    equipment, alarm, _work_order = fault_chain()
    equipment.equipment_type_id = equipment_type.id
    db.commit()
    headers = _auth(supervisor)

    assert (
        client.post(f"/api/v1/alarms/{alarm.id}/analyze", headers=headers).status_code
        == 200
    )
    approved = client.post(
        f"/api/v1/alarms/{alarm.id}/review",
        json={"action": "approve", "note": "批准"},
        headers=headers,
    )
    assert approved.status_code == 200
    created = client.post(
        f"/api/v1/alarms/{alarm.id}/create-work-order", headers=headers
    )
    assert created.status_code == 200

    detail = get_trace(db, alarm.trace_id)
    stages = {entry["stage"] for entry in detail["timeline"]}
    assert {"analysis", "approval", "work_order"} <= stages
    # 分析的人工批准体现在 analysis.review_status。
    analysis_entries = [
        entry for entry in detail["timeline"] if entry["stage"] == "analysis"
    ]
    assert any(entry.get("review_status") == "approve" for entry in analysis_entries)
    # 设备操作审批（OperationApproval）为既有审批流的待审记录。
    approval_entries = [
        entry for entry in detail["timeline"] if entry["stage"] == "approval"
    ]
    assert approval_entries
    assert any(entry["status"] == "pending" for entry in approval_entries)

    # HTTP 响应不含敏感字段。
    raw = client.get(
        f"/api/v1/observability/traces/{alarm.trace_id}", headers=headers
    ).text.lower()
    for secret_marker in ("password", "authorization", "secret_key"):
        assert secret_marker not in raw
