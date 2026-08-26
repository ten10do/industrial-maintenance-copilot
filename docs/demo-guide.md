# 完整演示指南

1. 使用主管账号登录，进入“实时状态监测”。
2. 选择工业电机、`bearing_wear`、随机种子 `20260731`，应用配置。
3. 连续单步，观察振动/温度趋势、健康分下降和开放异常。
4. 进入“预测性维护”，查看结构化诊断、可能原因、RAG 来源、风险、剩余寿命和维护窗口。
5. 确认系统只创建一张预测性工单，并显示人员匹配与备件预留/缺口。
6. 进入审批中心；不填写意见时批准会被阻止。
7. 填写维护窗口、现场负责人和 LOTO 确认后批准停机。
8. 分别创建并批准模拟复位、重启命令，生成正常遥测。
9. 以被分派工程师登录，接单、开始，完成检查清单、日志、工时和完工证据后提交。
10. 主管执行维修效果验证。健康分恢复且遥测正常时工单关闭、异常解决。
11. 在知识库确认生成 `[待审核]` 案例，状态为 `draft`。

自动化等价流程位于 `apps/web/e2e/intelligent-maintenance.spec.ts`。CI 和本地演示均使用 Mock Provider，不需要真实 PLC 或付费模型。

# 5-Minute Portfolio Demo（/demo）

> 定位声明：本演示运行在**确定性软件 OPC UA 模拟器**（Motor001）上，
> 未连接真实 PLC；AI 结论为证据绑定建议，必须经人工复核。

## 时间轴

- **0:00–0:30 开场**：打开 `/demo`；点开 Architecture 展开流程图
  （User → Scenario → Simulator(software OPC UA) → Gateway → Data Quality →
  Telemetry → AI Pipeline → Alarm Intelligence → Human Review → Work Order → Trace）。
- **0:30–1:30 切 FAULT**：数字视图温度/振动爬升，状态徽章变化，
  ALARM ACTIVE 出现；数据质量面板展示 Accepted/Rejected。
- **1:30–2:30 异常与预测**：Latest Anomaly（fault_type/severity/置信度）、
  Fault Prediction（`deterministic-rules-v1`、概率）。口径：Research/staging，
  非现场工况性能；RUL V2 未通过 promotion gate。
- **2:30–3:30 RCA 与 RAG**：根因假设、证据摘要、置信度上限 0.85；
  RAG citation（source/score/snippet）最多 3 条，无检索结果则明确显示空。
- **3:30–4:30 Review → Work Order**：批准建议走真实 `/alarms/{id}/review`；
  批准后创建工单（幂等，重复点击返回同一工单），可跳转工单详情。
- **4:30–5:00 Trace Explorer**：View Full Trace 打开
  `/observability/traces/{trace_id}` 完整时间线，回答“哪一步最慢”。

## Expected Outcome

FAULT 后 1 个确定性采样周期内出现 Anomaly + Prediction + Industrial Alarm；
批准后创建唯一工单；trace_id 贯穿全链并可在 Trace Explorer 回放。

## Troubleshooting

| 现象 | 处理 |
| --- | --- |
| 场景按钮返回 409 | 仅当 `GATEWAY_MODE` 不是 `mock`（如真实 OPC UA 模式）时拒绝；Demo 编排仅支持进程内软件模拟器 |
| 无报警产生 | 再点一次 FAULT 多推进一个确定性 tick；确认节点映射已配置 |
| 页面提示后端不可用 | 确认 API 启动且 `/ready`=200 |

## Safety Notes

全程 **PLC write = 0**；Human Review 与 OperationApproval 审批流不被绕过；
Demo 编排仅作用于进程内软件模拟器（Simulation only）。
