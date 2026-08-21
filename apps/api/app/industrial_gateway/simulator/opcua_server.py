"""软件 OPC UA Server：模拟工业现场设备（Industrial Motor）。

用途（需求第三阶段）：没有真实 PLC 时，提供与真实设备行为一致的
OPC UA Server 完成端到端 Demo。

节点布局（namespace 注册后默认为 ns=2）::

    Objects/
     └── Motor001
          ├── Temperature   20-100 ℃
          ├── Vibration     0-5 mm/s
          ├── Current       0-20 A
          ├── Speed         0-3000 rpm
          ├── Voltage       340-420 V   （扩展节点，供 AI 链路评估）
          ├── LoadRatio     0-120 %     （扩展节点，供 AI 链路评估）
          ├── RunningState  bool
          └── Alarm         bool

数值由 :mod:`.generator` 的固定种子确定性生成器产生，
支持 ``--seed`` 复现与 normal / warning / fault 三种场景。

运行::

    python -m app.industrial_gateway.simulator.opcua_server \
        --host 0.0.0.0 --port 4840 --seed 42 --scenario normal

安全说明：模拟器仅作为数据源；网关侧强制 read-only，
本进程不实现任何面向客户端的写授权。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from app.industrial_gateway.simulator.generator import (
    NODE_NAMES,
    SUPPORTED_SCENARIOS,
    MotorSimulator,
)

logger = logging.getLogger("app.industrial_gateway.simulator")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 4840
DEFAULT_PATH = "/industrial-simulator/"
NAMESPACE_URI = "http://industrial-maintenance.local/opcua-simulator/"
DEFAULT_NAMESPACE_INDEX = 2


class OpcUaSimulatorServer:
    """把 MotorSimulator 的确定性数值发布为真实 OPC UA 变量。"""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        path: str = DEFAULT_PATH,
        seed: int = 42,
        scenario: str = "normal",
        prefix: str = "Motor001",
        namespace_index: int = DEFAULT_NAMESPACE_INDEX,
    ) -> None:
        if scenario not in SUPPORTED_SCENARIOS:
            raise ValueError(f"不支持的仿真场景: {scenario}")
        self._endpoint = f"opc.tcp://{host}:{port}{path}"
        self._seed = seed
        self._scenario = scenario
        self._prefix = prefix
        self._namespace_index = namespace_index
        self._simulator = MotorSimulator(seed=seed, scenario=scenario, prefix=prefix)
        self._server: Any | None = None
        self._variables: dict[str, Any] = {}

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def simulator(self) -> MotorSimulator:
        return self._simulator

    async def start(self) -> None:
        from asyncua import Server, ua

        server = Server()
        await server.init()
        server.set_endpoint(self._endpoint)
        server.set_server_name("Industrial Maintenance OPC UA Device Simulator")
        # 预留 namespace 索引，保证演示 NodeId 稳定为 ns=2;s=Motor001.*。
        registered = await server.register_namespace(NAMESPACE_URI)
        if registered != self._namespace_index:
            logger.warning(
                "namespace index 实际为 ns=%d（演示映射默认按 ns=%d 编写）",
                registered,
                self._namespace_index,
            )
            self._namespace_index = registered

        objects = server.nodes.objects
        device = await objects.add_object(
            ua.NodeId(self._prefix, self._namespace_index),
            ua.QualifiedName(self._prefix, self._namespace_index),
        )
        initial = self._simulator.current_values()
        for name in NODE_NAMES:
            variable = await device.add_variable(
                ua.NodeId(f"{self._prefix}.{name}", self._namespace_index),
                ua.QualifiedName(name, self._namespace_index),
                initial[name],
            )
            # 不调用 set_writable：变量对客户端保持只读。
            self._variables[name] = variable

        await server.start()
        self._server = server
        logger.info(
            "OPC UA 模拟器已启动: %s (seed=%d, scenario=%s)",
            self._endpoint,
            self._seed,
            self._scenario,
        )

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop()
            self._server = None
            logger.info("OPC UA 模拟器已停止")

    async def publish_tick(self) -> dict[str, float | bool]:
        """推进仿真并写入全部变量。"""
        values = self._simulator.advance()
        for name, value in values.items():
            await self._variables[name].write_value(value)
        return values

    async def serve_forever(self, interval_seconds: float = 1.0) -> None:
        """启动服务器并按固定周期发布数据。"""
        await self.start()
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                values = await self.publish_tick()
                logger.debug("tick published: %s", values)
        finally:
            await self.stop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="工业电机 OPC UA 模拟服务器（确定性、可复现）"
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--seed", type=int, default=42, help="固定随机种子")
    parser.add_argument(
        "--scenario",
        default="normal",
        choices=sorted(SUPPORTED_SCENARIOS),
        help="运行场景：normal / warning / fault",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="发布周期（秒）")
    parser.add_argument("--prefix", default="Motor001", help="设备节点名")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    try:
        server = OpcUaSimulatorServer(
            host=args.host,
            port=args.port,
            path=args.path,
            seed=args.seed,
            scenario=args.scenario,
            prefix=args.prefix,
        )
        asyncio.run(server.serve_forever(interval_seconds=args.interval))
    except KeyboardInterrupt:
        logger.info("收到中断，模拟器退出")
    except ImportError as exc:  # pragma: no cover - 环境缺依赖时给出可操作提示
        logger.error("运行 OPC UA 模拟器需要安装 asyncua：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
