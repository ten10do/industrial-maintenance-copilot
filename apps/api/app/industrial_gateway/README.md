# Industrial Protocol Gateway（工业协议接入层）

OPC UA 只读遥测接入层：把 `OPC UA Device Layer → Gateway → Telemetry → AI 平台`
接入既有智能运维平台，**不旁路任何 AI 能力，不修改任何业务逻辑**。

支持两种并行的数据触发方式（共享同一质量层与 AI 链路）：

- **Polling**：周期性 `read_node`（`opcua/client.py`，既有能力）；
- **Subscription**：DataChange 事件驱动（`opcua/subscription.py` +
  `event_buffer.py`），轮询作为订阅不可用时的 fallback。

## 结构

```
industrial_gateway/
├── opcua/
│   ├── client.py        # OpcUaClient 协议 + AsyncuaOpcUaClient / MockOpcUaClient（轮询）
│   ├── subscription.py  # OpcUaSubscriptionClient 协议 + Asyncua / Mock（DataChange 订阅）
│   ├── models.py        # NodeRead / NodeDataChange 等内部结构、StatusCode 质量归类
│   └── service.py       # 编排：轮询 sync_once + 订阅 on_data_change → 缓冲 → flush → ingest
├── simulator/
│   ├── generator.py     # 固定种子确定性电机仿真（normal/warning/fault + 变更检测）
│   └── opcua_server.py  # 软件 OPC UA Server（asyncua），可执行 CLI
├── gateway.py           # GatewayConfig / 轮询与订阅客户端工厂
├── event_buffer.py      # Event Buffer：batch aggregation + debounce + duplicate suppression
├── alarms.py            # 报警状态机 NORMAL/WARNING/CRITICAL
├── mapping.py           # NodeId ↔ 设备资产映射（DB 表 + YAML 配置）
├── models.py            # GatewayConnection / OpcUaNodeMapping / GatewaySubscription / IndustrialAlarm
├── quality.py           # Data Quality Layer（缺失/坏质量/时间戳/单位/去重）
└── schemas.py           # API Pydantic 模型
```

## 数据流

```
【轮询】OPC UA Server → read_node() → DataQualityLayer → NodeMapping
【订阅】OPC UA Server → DataChange → on_data_change（mapping + 单事件质量闸门）
        → EventBuffer（debounce/batch/dedupe）→ flush 时从最新值缓存构建快照
        ▼
TelemetrySnapshot（scenario="opcua" 标记来源）
   ▼
intelligence_service.ingest_snapshot()   # 复用既有 AI 链路（无第二套 pipeline）
   └─ 订阅 flush 路径附带工业报警状态机 → industrial_alarms
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
