# OPC UA Subscription（事件驱动接入）

> 状态：**simulated OPC UA subscription workflow**（OPC UA compatible simulation）。
> 本文档描述的是软件模拟环境下的 DataChange 订阅工作流，
> **不是 real factory deployment，未接入任何真实 PLC**。

## 1. Polling vs Subscription

| 维度 | Polling（既有，保留） | Subscription（本阶段新增） |
| --- | --- | --- |
| 触发方式 | 网关按固定周期逐节点 `read_node` | 服务器在值变化时推送 DataChange 通知 |
| 数据新鲜度 | 受轮询周期限制（默认 5s） | 变化即达（受 sampling/publishing interval 限制） |
| 网络开销 | 每周期全量请求（含未变化节点） | 仅传输变化节点 |
| 工业现场对应 | 简单数据采集 | OPC UA Monitored Items / Subscriptions 标准机制 |
| 失败语义 | 周期失败退避重试 | 订阅失败回退到轮询路径 |

**两者并存**：`GATEWAY_ENABLED` 轮询与订阅可同时运行；订阅不可用时轮询路径
完整保留，构成天然的 fallback。

## 2. 为什么工业现场需要事件驱动

- 高频信号（振动、电流瞬态）在轮询间隔内可能多次变化，轮询要么丢变化、
  要么为追新鲜度而疯狂缩短周期压垮网络；
- OPC UA 的 Subscription/MonitoredItem 是工业标准做法：客户端声明
  sampling interval，服务器只推送“发生了变化”的数据；
- 报警位（Alarm）、离散状态位天然是事件：不变化就不该有流量，
  一旦置位必须立刻可见。

## 3. 架构

```
opcua/
├── client.py         # 轮询客户端（保持不变）
├── subscription.py   # OpcUaSubscriptionClient 协议 + Asyncua / Mock 实现
└── service.py        # on_data_change → 缓冲 → flush → ingest_snapshot

event_buffer.py       # Event Buffer：batch aggregation + debounce + duplicate suppression
alarms.py             # 报警状态机 NORMAL/WARNING/CRITICAL → IndustrialAlarm
```

接口（不直接绑定 asyncua）：

```python
class OpcUaSubscriptionClient(Protocol):
    endpoint: str
    connected: bool
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read_node(self, node_id: str) -> NodeRead: ...   # 初始值灌注
    async def subscribe(self, node_ids, callback, *, sampling_interval_ms, publishing_interval_ms) -> SubscriptionHandle: ...
    async def unsubscribe(self, handle) -> None: ...
```

- `AsyncuaSubscriptionClient`：`create_subscription` + `subscribe_data_change`，
  把 asyncua 的 `datachange_notification` 归一化为 `NodeDataChange`；
- `MockSubscriptionClient`：进程内 `publish()` 驱动回调，Mock 模式零依赖；
- 两个实现都显式提供 `write_node` 并抛出 `PermissionError`（read-only 防线）。

## 4. DataChange Flow

```
OPC UA Server（模拟器或现场设备）
   │  DataChange Notification（只读）
   ▼
AsyncuaSubscriptionClient ──► NodeDataChange{node_id, value, source_timestamp, status_code}
   ▼
on_data_change()【同步回调，只做内存操作】
   ├─ Node Mapping 查找（未知节点计数丢弃）
   ├─ 单事件质量闸门（bad quality / missing / NaN → 拒绝）
   ├─ EventBuffer.add()（duplicate suppression）
   └─ 更新每节点最新值缓存（latest_values）
   ▼
flush 循环（debounce 到期，默认 1s）
   ├─ batch aggregation：窗口内每节点取最新值
   ├─ 从 latest_values 构建完整快照（复用 _build_snapshot：
   │   单位换算 + scale/offset + 5 必需指标完整性闸门）
   └─ ingest_snapshot()【既有 AI 链路，无第二套 pipeline】
```

示例：1 秒内 Temperature 变化 10 次 → 缓冲聚合为 1 个最新值 →
与其他节点合并为一个 TelemetrySnapshot → 一次入库。

## 5. Alarm Flow

```
DataChange 事件（含 Alarm 布尔位）
   ▼
flush 时快照入库成功后评估报警状态机
   NORMAL ⇄ WARNING ⇄ CRITICAL
   ├─ 判定阈值与平台 SENSOR_DEFINITIONS 对齐（温度>75 / 振动>4.5 /
   │   电流>27 / 负载>100 / 电压越出 342-418V）；
   ├─ Alarm 位 = True 直接判定 CRITICAL；
   ├─ 仅状态跃迁时产生/解除记录（不随高频事件刷屏）；
   └─ 写入 industrial_alarms 表（severity/message/source/acknowledged/cleared_at）
   ▼
GET /api/v1/alarms          # 报警中心页面展示
POST /api/v1/alarms/{id}/acknowledge   # 人工确认（仅平台内记录）
```

## 6. API

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/gateway/subscriptions` | 登录用户 | 订阅状态：active nodes / sampling interval / last event / event count |
| POST | `/api/v1/gateway/subscriptions/start` | supervisor/admin | 启动订阅（连接 → subscribe → 灌注缓存 → flush 循环） |
| POST | `/api/v1/gateway/subscriptions/stop` | supervisor/admin | 停止订阅（先冲刷缓冲；轮询保持可用） |
| GET | `/api/v1/alarms` | 登录用户 | 工业报警列表（status=active/acknowledged/cleared 过滤） |
| POST | `/api/v1/alarms/{id}/acknowledge` | supervisor/admin | 人工确认报警 |

## 7. Demo 方法

### Mock 模式（无需真实 PLC / 无需网络）

```bash
cd apps/api
python -m uvicorn app.main:app --port 8000
# 登录后（supervisor/admin）：
curl -X POST http://127.0.0.1:8000/api/v1/gateway/subscriptions/start -H "Authorization: Bearer <token>"
# Mock 运行时自动推进确定性仿真 tick 并把变更作为 DataChange 发布；
# flush 循环自动聚合入库。前端「工业网关」页可见事件计数，「工业报警中心」可见报警。
```

### OPC UA 模式（真实协议栈订阅）

```bash
# 终端 1：软件 OPC UA Server
python -m app.industrial_gateway.simulator.opcua_server --port 4840 --seed 42 --scenario warning
# 终端 2：网关以 opcua 模式启动后调用 subscriptions/start
# asyncua 客户端通过 create_subscription 接收 DataChange 通知。
```

确定性保证：`(seed, scenario, tick)` 唯一决定数值与变更集合——
同一 seed 下任意两次运行产生完全相同的事件序列。

## 8. 数据库

Alembic revision `20260811_03` / `20260811_04`（幂等创建，SQLite/PostgreSQL 兼容）：

- `gateway_subscriptions`：gateway_id（FK gateway_connections）、node_id、
  sampling_interval、status、last_event_at、event_count；
- `industrial_alarms`：equipment_id（FK equipment）、severity、message、source、
  created_at、acknowledged、acknowledged_at、acknowledged_by、cleared_at。

## 9. Limitations

- 当前为 **simulated OPC UA subscription workflow**，不是 real PLC deployment；
- Mock 模式的“事件”由进程内仿真推进产生，非网络传输；
- 尚未实现 OPC UA Alarm & Conditions（A&C）完整规范：仅以 Alarm 布尔位 +
  阈值状态机模拟报警语义，无 Acknowledge/Retain 回写设备（也永远不应有——
  平台侧确认只改平台记录）；
- 事件缓冲为单进程内存实现（无 Redis Stream/Kafka），API 进程重启即清空；
- flush 循环与 API 同进程，多实例部署时订阅应由单一实例持有；
- 订阅断线重连当前由人工重新 start（轮询路径在其间兜底）。
