# OPC UA 工业协议网关（Industrial Protocol Gateway）

> 状态：**OPC UA-compatible simulation**（软件模拟工业网关）。
> 当前平台**尚未接入任何真实工厂 PLC**；本文档描述的是可复现的
> 软件模拟设备层，以及未来接入真实 OPC UA Server / PLC 网关的路径。

## 1. 为什么增加 OPC UA

升级前，平台的数据链路是 `Simulator → AI Platform`：遥测由进程内的
`MockEquipmentGateway` 直接生成，虽然完整演示了 AI 闭环，但与真实工业
现场之间缺少标准协议层。工业现场的事实标准是 OPC UA（IEC 62541）：
PLC、SCADA、智能仪表普遍通过 OPC UA Server 暴露数据。

增加工业协议接入层后，链路升级为：

```
OPC UA Device Layer → Gateway → Telemetry Pipeline → AI Maintenance Platform
```

从而：

- 数据入口与真实工业部署同构（NodeId + Value + Timestamp + Quality）；
- Mock 模式仍然零配置可运行（无真实 PLC 时使用 OPC UA Simulator）；
- AI 能力（Health Score / 异常检测 / 故障预测 / 工单 / 审批）完全复用，
  不存在旁路。

## 2. 工业数据流

```
OPC UA Simulator（软件电机，固定种子，可复现）
   │  opc.tcp（只读）
   ▼
OpcUaClient.read_node()          # NodeId / Value / SourceTimestamp / StatusCode
   ▼
DataQualityLayer                 # missing / bad quality / 无效时间戳 / 单位换算 / 去重
   │  被拒绝的数据不进入业务
   ▼
NodeMapping（node_id → equipment + metric + unit + scale/offset）
   ▼
TelemetrySnapshot（scenario="opcua" 标记来源）
   ▼
intelligence_service.ingest_snapshot()   # 既有 AI 链路（未做任何修改）
   ├─ Health Score / 风险等级
   ├─ AnomalyEvent → FaultDiagnosis（Agent Run）
   ├─ RiskPrediction（RUL）→ MaintenanceRecommendation
   └─ WorkOrder + 备件预留 + OperationApproval（Human-in-the-loop）
```

## 3. 架构与模块

全部代码位于 `apps/api/app/industrial_gateway/`，不散落到设备业务代码中：

```
industrial_gateway/
├── opcua/
│   ├── client.py        # OpcUaClient 协议（只读）+ AsyncuaOpcUaClient / MockOpcUaClient
│   ├── models.py        # NodeRead、StatusCode 质量归类、来源标记
│   └── service.py       # 轮询编排、快照聚合、失败回退、运行时单例
├── simulator/
│   ├── generator.py     # 确定性电机仿真（normal / warning / fault，固定 seed）
│   └── opcua_server.py  # 软件 OPC UA Server（asyncua），可执行 CLI
├── gateway.py           # GatewayConfig（GATEWAY_* 环境变量）+ 客户端工厂
├── mapping.py           # 节点映射装载与 YAML 配置同步
├── quality.py           # Data Quality Layer
├── models.py            # GatewayConnection / OpcUaNodeMapping（数据库）
└── schemas.py           # API Pydantic 模型
```

运行模式：

| 模式 | 数据源 | 依赖 | 场景 |
| --- | --- | --- | --- |
| `GATEWAY_MODE=mock`（默认） | 进程内确定性仿真 | 无额外依赖 | 本机开发 / CI |
| `GATEWAY_MODE=opcua` | 真实 OPC UA 连接 | `asyncua` | 连接软件模拟器或现场 Server |

两种模式默认都关闭（`GATEWAY_ENABLED=false`），不影响既有 Mock 设备链路
（`MockEquipmentGateway` + 仿真控制器保持原样）。

## 4. 节点映射

映射完全配置化，**代码中不硬编码任何 NodeId**：

- 运行时事实来源：数据库表 `opcua_node_mappings`
  （`node_id`、`equipment_id`、`metric_name`、`unit`、`scale/offset`、
  `enabled`、`informational`）；
- 配置文件：`apps/api/configs/opcua-node-mapping.yaml`，通过
  `POST /api/v1/gateway/mappings/reload` 幂等 upsert 进数据库；
- `equipment_code` 必须与「设备资产中心」的设备编码一致（演示配置指向
  `EQ-MTR01`），解析不到的条目会被跳过并记录；
- `temperature / vibration / current / voltage / speed / load` 映射到平台
  遥测字段；`running / alarm` 为 informational 节点，仅展示不入库；
- 单位换算：温度支持 celsius / fahrenheit / kelvin，其余指标校验规范单位；
  `scale/offset` 支持工程值线性换算。

演示节点布局（软件模拟器，ns=2）：

```
Objects/
 └── Motor001
      ├── Temperature   20-100 ℃
      ├── Vibration     0-5 mm/s
      ├── Current       0-20 A
      ├── Speed         0-3000 rpm
      ├── Voltage       340-420 V   （扩展节点，供 AI 链路完整评估）
      ├── LoadRatio     0-120 %     （扩展节点，供 AI 链路完整评估）
      ├── RunningState  bool        （informational）
      └── Alarm         bool        （informational）
```

## 5. Demo 方法

### 5.1 Mock 模式（无需 asyncua、无需真实 PLC）

```bash
cd apps/api
# .env 或环境变量：
GATEWAY_ENABLED=true GATEWAY_MODE=mock python -m uvicorn app.main:app --port 8000
# 登录后（supervisor/admin）：
curl -X POST http://127.0.0.1:8000/api/v1/gateway/sync -H "Authorization: Bearer <token>"
```

前端进入「工业网关」页面查看连接状态、节点与最近遥测。

### 5.2 完整 OPC UA 模式（软件模拟器 + 真实协议栈）

```bash
# 终端 1：启动软件 OPC UA Server（固定种子，可复现）
cd apps/api
python -m app.industrial_gateway.simulator.opcua_server --port 4840 --seed 42 --scenario warning

# 终端 2：网关以 opcua 模式连接模拟器
GATEWAY_ENABLED=true GATEWAY_MODE=opcua \
GATEWAY_ENDPOINT=opc.tcp://127.0.0.1:4840/industrial-simulator/ \
python -m uvicorn app.main:app --port 8000
```

场景说明：`normal` 全指标健康；`warning` 温度缓慢越过 75 ℃ 警告阈值；
`fault` 温度/振动/电流强劣化并置位 `Alarm=true`，将触发平台异常 → 预测 →
工单 → 高风险审批完整链路。数值由 `(seed, scenario, tick)` 唯一决定，
固定 `--seed` 后任意两次运行完全一致。

### 5.3 Docker Compose

```bash
# 启动含 OPC UA 模拟器的完整栈（gateway profile）
GATEWAY_ENABLED=true docker compose --profile gateway up -d
# api 容器内 GATEWAY_ENDPOINT=opc.tcp://opcua-simulator:4840/industrial-simulator/
```

## 6. API

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/gateway/status` | 登录用户 | 连接状态 / OPC UA Server / 最近同步时间 |
| GET | `/api/v1/gateway/nodes` | 登录用户 | 当前映射节点、最近读数、质量状态 |
| POST | `/api/v1/gateway/test-connect` | 登录用户 | 只读连接探测（延迟 + 采样值），不入库 |
| POST | `/api/v1/gateway/sync` | supervisor/admin | 手动执行一次「读取→质量→入库」 |
| POST | `/api/v1/gateway/mappings/reload` | supervisor/admin | 从 YAML 幂等重载节点映射 |

## 7. 数据质量规则（Data Quality Layer）

| 问题 | 处理 |
| --- | --- |
| missing value | 拒绝（`missing_value`） |
| NaN / Inf / 非数值 | 拒绝（`non_numeric`） |
| OPC UA StatusCode = Bad | 拒绝（`bad_quality`）；Uncertain 接受但降低质量分 |
| 时间戳缺失 | 以接收时间替代，并记录 correction |
| 时间戳来自未来 / 过期 | 拒绝（`future_timestamp` / `stale_timestamp`） |
| 重复时间戳 | 拒绝（`duplicate_timestamp`） |
| 单位不符 / 无法换算 | 拒绝该指标（快照不完整则整批跳过） |

关键设计：组成完整评估所需的 5 个指标（振动 / 轴承温度 / 电流 / 电压 /
负载率）任一缺失时，**该设备本周期整批跳过**，绝不把不完整快照写入业务，
避免被误判为传感器故障。

## 8. 数据库

新增两张表（Alembic revision `20260811_02`，幂等创建，支持全新库与存量库）：

- `gateway_connections`：name、protocol、endpoint、mode、status、enabled、
  poll_interval_seconds、last_connected_at、last_sync_at、last_error；
- `opcua_node_mappings`：node_id（唯一）、equipment_id（FK → equipment）、
  metric_name、unit、scale、offset、enabled、informational，
  且 `(equipment_id, metric_name)` 唯一。

既有 SQLite / PostgreSQL 数据库不受影响；降级被显式拒绝以保护现场映射配置。

## 9. 安全（工业控制安全要求）

- **read-only mode**：`OpcUaClient` 协议不定义写方法；
  `AsyncuaOpcUaClient` 仅调用 `read_data_value`；
  两个实现均显式提供 `write_node` 并抛出 `PermissionError`，作为代码级防线；
- 模拟器侧变量未调用 `set_writable`，客户端写入被服务器以
  `BadUserAccessDenied` 拒绝；
- 网关 API 面上没有任何写 PLC 端点（由测试 `test_gateway_exposes_no_write_endpoints` 固定）；
- 未来若支持写操作：必须复用平台 Human-in-the-loop 审批
  （`OperationApproval` 流程），不允许从网关直接写设备。

## 10. 未来真实 PLC 接入方式

平台到真实现场只差「换端点、换映射」两步，无需改动网关代码：

1. 现场部署 OPC UA Server（PLC 内置 / OPC UA 网关 / KepServerEX 等），
   网络与证书按现场安全策略配置；
2. 设置 `GATEWAY_MODE=opcua`、`GATEWAY_ENDPOINT=opc.tcp://<server>:4840/...`；
3. 修改 `configs/opcua-node-mapping.yaml`：把现场 NodeId 映射到平台设备编码
   与指标，`POST /gateway/mappings/reload` 生效；
4. 先 `POST /gateway/test-connect` 验证只读连通性与采样值，
   再开启 `GATEWAY_ENABLED=true` 持续采集；
5. 如需用户名/密码或证书认证，可在 `AsyncuaOpcUaClient.connect()` 处按
   asyncua 标准方式扩展（当前演示为匿名 + None 安全策略）。

## 11. 当前限制

- 当前为 **OPC UA compatible simulation**，不是 real PLC deployment；
- 订阅（Subscription）/ 回调推送尚未实现，采用轮询模型（默认 5s）；
- 认证仅支持匿名端点，证书 / 用户名密码认证待现场需求接入；
- 历史访问（HA）节点、聚合节点未接入；
- 网关轮询与 API 同进程（与现有仿真器一致），多实例水平扩展未做。
