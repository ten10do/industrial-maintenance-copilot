# 工业设备软件仿真

首期 Mock Equipment Gateway 模拟工业电机及轴承系统，不需要真实设备或 API Key。

| 场景 | 标识 | 主要变化 |
| --- | --- | --- |
| 正常运行 | `normal` | 指标在额定范围内轻微波动 |
| 温度缓慢上升 | `temperature_rise` | 轴承温度随采样推进上升 |
| 振动突然升高 | `vibration_spike` | 数个采样点后振动突升 |
| 电流持续过载 | `current_overload` | 电流、负载与温度升高 |
| 轴承磨损趋势 | `bearing_wear` | 振动与温度逐步恶化 |
| 电压波动 | `voltage_fluctuation` | 电压按确定函数波动 |
| 传感器断连 | `sensor_disconnect` | 质量降为零且指标缺失 |
| 多指标复合异常 | `composite_anomaly` | 振动、温度、电流、负载和电压耦合异常 |

控制台支持设备数量、生成间隔、场景、随机种子、启动、暂停、重置和单步。相同设备 UUID、场景、种子与采样序号产生相同数值，保证 CI 可重复。

Mock Gateway 只支持 `shutdown`、`emergency_stop`、`reset_alarm`、`restart/start`。这些命令仍必须先创建 `OperationApproval`，不能从仿真控制台直接绕过审批。

快速演示可用默认种子 `20260731`。轴承磨损是渐进场景，需要持续单步直至风险升级；复合异常用于较短的 Smoke。
