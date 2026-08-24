"""工业协议接入层（Industrial Protocol Gateway）。

当前实现 OPC UA 只读遥测接入：

    OPC UA Device Layer → Gateway → Validation → Telemetry → AI 平台

职责边界：

- 只读取设备数据，默认禁止任何写 PLC 操作；
- 原始节点读数必须经过 Data Quality Layer 校验后才允许进入业务；
- 节点与平台设备资产的映射全部配置化（数据库表 + YAML 配置）；
- 复用 ``intelligence_service.ingest_snapshot``，不旁路任何 AI 能力。

模块结构::

    industrial_gateway/
    ├── opcua/          # OPC UA Client 抽象与实现
    ├── simulator/      # 软件 OPC UA 设备模拟器（无真实 PLC 时的 Demo）
    ├── models.py       # GatewayConnection / OpcUaNodeMapping 数据库模型
    ├── quality.py      # Data Quality Layer
    ├── mapping.py      # 节点 → 设备资产映射
    └── gateway.py      # 配置与客户端工厂
"""

from __future__ import annotations

MODULE_NAME = "industrial_gateway"

__all__ = ["MODULE_NAME"]
