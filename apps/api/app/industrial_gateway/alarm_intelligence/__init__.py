"""Alarm Intelligence（工业报警智能分析）。

定位：**AI-assisted industrial alarm analysis**——对已持久化的
IndustrialAlarm 做关联合并、语义理解、根因分析与维护决策支持。

边界（重要约束）：

- 纯旁挂只读消费层：不修改 OPC UA Gateway / Subscription / 报警产生路径；
- 不修改 ML 模型与实验结果；分析为确定性规则 + 既有知识库检索；
- **只输出建议**：不创建、不执行任何设备控制；任何操作必须走
  既有 WorkOrder + Human Approval（OperationApproval）审批流。

结构::

    alarm_intelligence/
    ├── correlation.py   # 关联引擎：相关报警合并为事件组（确定性规则）
    └── engine.py        # 理解 / 根因分析 / 决策支持
"""

from __future__ import annotations

MODULE_NAME = "alarm_intelligence"

__all__ = ["MODULE_NAME"]
