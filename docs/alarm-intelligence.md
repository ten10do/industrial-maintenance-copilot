# Industrial Alarm Intelligence

## Problem

OPC UA 报警原本只提供状态通知和人工确认。Alarm Intelligence 在同一平台内增加
关联、证据约束根因分析、风险评估和维护建议，但不创建第二套遥测、RAG、审批或
工单系统。定位是 **AI-assisted industrial alarm analysis**，不是自主工业控制。

## Architecture

```text
OPC UA subscription / polling
  → IndustrialAlarm
  → deterministic correlation
  → AlarmAnalysisRecord
  → telemetry + fault prediction + existing RAG
  → deterministic risk + maintenance recommendation
  → supervisor/admin review
  → existing WorkOrder
  → existing OperationApproval before any equipment command
```

分析过程复用 `AgentRun` 与 `ToolInvocation`，记录报警 ID、关联结果、知识文章 ID、
风险、置信度和耗时。确定性 Mock 不伪造 token usage。

## Alarm Correlation

- 同设备报警在配置化 `window_seconds`（默认 300 秒，API 允许 30–3600 秒）内关联。
- 报警文本提取轴承温度、振动、电流/负载、电压与 Alarm 位等透明指标族；明显无关
  的指标不因“同设备”而误合并，温升/振动/Alarm 位允许形成轴承退化复合信号。
- 同产线、时间窗重叠的设备组可形成 `line_cascade`。
- 成员集合通过 UUID5 生成稳定组 ID；既有报警状态机抑制持续状态重复记录，分析表
  对 `alarm_id` 唯一，重复分析不会制造新的业务事件。

## Root Cause Analysis

输入包括原始报警、最新遥测、既有异常事件证据、设备元数据/健康分、最新故障预测
与关联报警数。根因只是
假设；置信度由遥测越限、多信号一致性、确定性处置知识、真实 RAG 命中、预测支持
和冲突扣分组成，最高 0.85。没有可验证证据时返回
`insufficient_evidence / manual_review_required`，不得生成高置信度结论。

## Evidence

知识检索复用现有 `search_articles`。引用只来自已发布知识文章，并保留 `source`、
`document_id/article_id`、`section`（若不存在为 `null`）、`snippet` 和 `score`。
检索为空时 `citations=[]`，置信度不会获得 RAG 加分，并强制人工复核。

## Risk Evaluation

风险等级为 `LOW / MEDIUM / HIGH / CRITICAL`。规则综合报警严重度、故障概率、设备
健康分、关联报警数和设备已有风险等级。`CRITICAL` 报警叠加故障概率 ≥ 0.70、健康
分 ≤ 50 或关联报警 ≥ 3 时升级为 `CRITICAL`。输入与命中原因随分析记录持久化；LLM
不决定风险等级。

## Maintenance Recommendation

建议复用 `FAULT_GUIDANCE` 和既有开放工单，只输出行动、优先级、技能/备件预核提示
和 LOTO 要求。建议不等于执行，不会自动调度、停机、锁备件或下发 PLC 命令。

## Human Review

状态流为：

```text
NEW → WAITING_REVIEW → APPROVED → WORK_ORDER_CREATED
                     ↘ REJECTED
                     ↺ request_more_evidence
```

主管或管理员可 `approve`、`reject`、`request_more_evidence`。低置信度、证据冲突、
RAG 为空或高/关键风险会标记强制复核；非法状态转换返回 409。

## Work Order Gate

`POST /api/v1/alarms/{id}/create-work-order` 只接受已人工批准的分析。创建使用既有
`WorkOrder`、状态历史和检查清单，重复请求返回同一工单。该动作不创建或执行设备
命令；后续任何设备命令仍须通过既有 `OperationApproval`。

## API

- `GET /api/v1/alarms`
- `GET /api/v1/alarms/{id}`
- `POST /api/v1/alarms/correlate`
- `POST /api/v1/alarms/{id}/analyze`
- `GET /api/v1/alarms/{id}/analysis`
- `POST /api/v1/alarms/{id}/review`
- `POST /api/v1/alarms/{id}/create-work-order`

读接口要求登录；关联、分析、复核和创建工单要求 supervisor/admin。

## Safety

- PLC write：不存在。
- Autonomous equipment command：不存在。
- Human approval：保留。
- High-risk bypass：不存在。
- 报警分析不会调用 `EquipmentGateway.execute_command()`。

## Limitations

首版是规则关联和关键词 RAG，不是学习型因果图。文本指标族只覆盖当前电机/轴承
报警；`section` 取决于知识库是否具备章节元数据。分析记录引用最新遥测/预测快照，
不代表已在现场确认根因。
