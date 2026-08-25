# Industrial AI Observability & End-to-End Traceability

## 1. Purpose

为"一次工业事件从 OPC UA DataChange 到 Work Order / Human Approval"
提供端到端证据链，回答：

- 这个报警从哪里来？哪一个设备数据触发？
- 数据质量是否正常？
- 哪个模型参与判断？版本？概率？
- RAG 检索了什么？Agent 调用了什么工具？
- 为什么推荐这个维修动作？人工何时审批？
- 最终是否生成工单？整条链路哪一步最慢？

定位：**AI-assisted industrial maintenance platform with simulated OPC UA
integration** 的可观测性增强；不是生产级工厂监控系统。

## 2. Architecture

```text
OPC UA DataChange / Polling
        ↓  start_trace("gateway-subscription-flush" | "gateway-poll")
TelemetryRecord ──→ AnomalyEvent ──→ RiskPrediction
        └──────────────┬──────────────┘
              MaintenanceRecommendation
                      ↓
             IndustrialAlarm（订阅报警路径）
                      ↓  bind_trace(alarm.trace_id)
        AlarmAnalysisRecord ← AgentRun ← ToolInvocation
                      ↓  bind_trace(record.trace_id)
                 Work Order ──→ OperationApproval
```

所有阶段复用**既有领域对象**；Observability 不创建第二套事件表，
不改变任何审批/工单 gate。

## 3. Trace Context

- 实现：`app/core/trace.py`，基于 `contextvars`（async/task 隔离）；
- 入口规则：
  - 新工业事件入口（订阅 flush / 网关轮询 / 手动遥测摄入）→ `start_trace()`；
  - 报警分析 → `bind_trace(alarm.trace_id)`；
  - 分析创建工单 → `bind_trace(record.trace_id)`；
- `request_id`（HTTP 层）与工业业务 `trace_id` 语义严格分离。

## 4. Metrics

`GET /metrics`（Prometheus 文本格式）。指标族：

| 前缀 | 指标 |
|---|---|
| industrial_gateway_* | connected / events_total / quality_rejected_total / event_buffer_size / flush_latency_seconds |
| telemetry_* | ingest_total / ingest_latency_seconds / rejected_total |
| ml_inference_* | total / latency_seconds / errors_total |
| industrial_alarm_* | alarm_total |
| alarm_analysis_* | analysis_total / latency_seconds / manual_review_total |
| rag_* | retrieval_total / retrieval_latency_seconds / empty_result_total / result_count |
| agent_run* | agent_runs_total / agent_run_latency_seconds / agent_run_failures_total |
| workflow | work_orders_created_total / human_review_total / operation_approval_total |

标签只使用低基数集合（protocol/mode/status/severity/risk_level/
reason/model_family/agent_name/source/action）。禁止
trace_id/equipment_id/alarm_id/work_order_id/query 文本作为标签。

前端概览使用 JSON 聚合端点 `GET /api/v1/observability/metrics-summary`
（浏览器不解析 Prometheus 文本）。

## 5. OpenTelemetry

- 默认 `OTEL_ENABLED=false`：无 Collector 时系统完全正常；
- 开启后按 `OTEL_TRACE_SAMPLE_RATE`（ParentBased + TraceIdRatioBased）
  采样，经 OTLP HTTP 导出到 `OTEL_EXPORTER_OTLP_ENDPOINT`；
- span 只覆盖关键阶段（见 `app/core/otel.py::industrial_span` 及各
  `@traced_span` 装饰器）；
- 初始化/导出失败仅告警降级，绝不抛错阻断业务链路。

环境变量：`OTEL_ENABLED` / `OTEL_SERVICE_NAME` /
`OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_TRACE_SAMPLE_RATE`。

## 6. Prometheus

可选 profile：`docker compose --profile observability up -d`
（含 Prometheus 与 Grafana；默认开发环境不依赖）。抓取目标仅为
API `/metrics`。

## 7. Trace Explorer

- `GET /api/v1/observability/traces/{trace_id}`：从真实领域对象重建
  timeline（telemetry/anomaly/prediction/recommendation/alarm/
  analysis/rag/tool/agent/work_order/approval），确定性排序
  `(timestamp, stage_order, entity_id)`；
- `GET /api/v1/observability/traces?equipment_id=&status=&from=&to=&limit≤200&offset=`
  分页搜索；
- `GET /api/v1/observability/health`：运行健康概览（无法探测的组件
  如实返回 unknown）；
- `GET /api/v1/observability/metrics-summary`：JSON 核心指标汇总。

前端入口：`/observability`（健康 + 指标摘要 + 最近链路）、
`/observability/traces/[traceId]`（时间线详情）。

## 8. Security

- Observability 全部端点只读且需认证；
- 不提供 PLC 写、设备命令、审批或工单创建能力；
- 指标不含高基数敏感标签；timeline 不含 token/密钥/原始凭证；
- 错误日志只记录 error_type 与脱敏消息。

## 9. Failure Isolation

OTel Collector 不可达 / prometheus 渲染异常时：记录 warning 并继续；
Telemetry / Prediction / Alarm / WorkOrder 主链路不受影响（有测试锁定）。

## 10. Limitations

- trace 传播为进程内 contextvars，不跨进程/服务传播；
- 未接入真实工厂负载与 HA 观测后端；
- OPC UA 仍为模拟环境（asyncua + Mock 双实现）；
- 指标基数受标签白名单约束，不支持按设备下钻（设备维度走 Trace Explorer）。
