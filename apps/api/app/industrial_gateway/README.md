# Industrial Protocol Gateway（工业协议接入层）

OPC UA 只读遥测接入层：把 `OPC UA Device Layer → Gateway → Telemetry → AI 平台`
接入既有智能运维平台，**不旁路任何 AI 能力，不修改任何业务逻辑**。

## 结构

```
industrial_gateway/
├── opcua/
│   ├── client.py     # OpcUaClient 协议 + AsyncuaOpcUaClient / MockOpcUaClient
│   ├── models.py     # NodeRead 等内部数据结构、StatusCode 质量归类
│   └── service.py    # 轮询编排：读取 → 质量 → 映射聚合 → ingest_snapshot
├── simulator/
│   ├── generator.py  # 固定种子确定性电机仿真（normal/warning/fault）
│   └── opcua_server.py  # 软件 OPC UA Server（asyncua），可执行 CLI
├── gateway.py        # GatewayConfig / 客户端工厂
├── mapping.py        # NodeId ↔ 设备资产映射（DB 表 + YAML 配置）
├── models.py         # GatewayConnection / OpcUaNodeMapping
├── quality.py        # Data Quality Layer（缺失/坏质量/时间戳/单位/去重）
└── schemas.py        # API Pydantic 模型
```

## 数据流

```
OPC UA Server（模拟器或现场设备）
   │  opc.tcp（只读）
   ▼
OpcUaClient.read_node() → NodeRead{value, source_timestamp, status_code}
   ▼
DataQualityLayer.process()      # 不合格数据在此被拒绝，绝不进入业务
   ▼
NodeMapping（equipment_id + metric + unit + scale/offset）
   ▼
TelemetrySnapshot（scenario="opcua" 标记来源）
   ▼
intelligence_service.ingest_snapshot()   # 复用既有 AI 链路
```

## 运行模式

| 模式 | 说明 | 依赖 |
| --- | --- | --- |
| `GATEWAY_MODE=mock`（默认） | 进程内模拟客户端，读 `simulator.generator` 的确定性数值 | 无额外依赖 |
| `GATEWAY_MODE=opcua` | 真实 OPC UA 客户端，连接模拟器或现场 Server | `asyncua` |

两种模式都默认关闭（`GATEWAY_ENABLED=false`），不影响既有 Mock 设备链路。

## 安全

- **read-only**：客户端协议无写方法；两个实现均显式抛出
  `PermissionError`。未来若支持写 PLC，必须走平台 Human Approval 流程。
- 模拟器变量不调用 `set_writable`，对客户端保持只读。

详细文档见 `docs/opcua-gateway.md`。
