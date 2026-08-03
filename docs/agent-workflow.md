# 诊断 Agent 工作流

1. `anomaly_detector` 校验数据质量、阈值和复合指标，计算健康分。
2. `knowledge_search` 按设备类型、故障描述和异常证据检索已发布手册/SOP/案例。
3. 生成 `FaultDiagnosis`，保留可能原因、原始证据、引用和置信度。
4. `risk_predictor` 生成确定性的失效概率、剩余寿命和维护窗口。
5. `maintenance_strategy` 生成维修步骤、技能、备件和危险操作。
6. 高/紧急风险由 `work_order_creator` 自动建单、匹配人员并预留备件。
7. 每一步写入 `AgentRun` 与 `ToolInvocation`，便于审计和问题复现。

规则检测、健康分与首期风险预测不依赖 LLM。LLM 只用于解释型 Copilot；Provider 失败时回退到确定性结果，并记录降级状态。诊断置信度低于 `0.8` 时设置 `requires_human_review=true`，不得把模型推断当作已确认根因。

RAG 引用只来自 `published` 知识条目。自动生成的维修案例是 `draft`，经人工审核发布后才会参与后续检索。
