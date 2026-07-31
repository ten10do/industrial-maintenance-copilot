# 领域模型

## 资产与遥测

| 模型 | 职责 |
| --- | --- |
| `Equipment` / `EquipmentType` | 资产档案、额定参数、状态、健康分和维护日期 |
| `EquipmentSensor` | 传感器阈值、在线状态、最新值和最后采集时间 |
| `TelemetryRecord` | 八类电机遥测、质量、场景与异常指标 |
| `AnomalyEvent` | 去重后的开放异常/报警、证据、严重度和生命周期 |

设备状态兼容旧值，并新增 `running`、`idle`、`warning`、`fault`、`maintenance`、`offline`。

## 智能诊断与维护

| 模型 | 职责 |
| --- | --- |
| `FaultDiagnosis` | 结构化根因候选、证据、RAG 引用、置信度与人工复核标记 |
| `RiskPrediction` | 失效概率、剩余寿命、失效时间与维护窗口 |
| `MaintenanceRecommendation` | 维修策略、技能、备件、危险动作和调度建议 |
| `SparePartReservation` | 按工单预留数量、缺口和状态，不直接扣减库存 |
| `AgentRun` / `ToolInvocation` | Agent 目标、输入输出、置信度与逐工具审计 |

同一设备、同一故障类型只保留一个开放异常。趋势由中风险升到高风险时创建一次预测性工单；后续重复遥测不会重复建单。

## 工单、安全与反馈

| 模型 | 职责 |
| --- | --- |
| `WorkOrder` 及既有关联模型 | 原工单 Copilot 的分派、执行、日志、工时、备件、报告和状态历史 |
| `OperationApproval` | 高风险命令、理由、审批人、结果和 Gateway 执行回执 |
| `MaintenanceVerification` | 维修前后遥测、健康分、通过/失败和知识草稿关联 |
| `KnowledgeArticle` | 手册、SOP、经验、案例；自动案例固定以 `draft` 等待人工审核 |

维修验证通过会把待验收工单关闭并解决开放异常；失败会把工单转为 `returned`、保留证据并要求重新处理。
