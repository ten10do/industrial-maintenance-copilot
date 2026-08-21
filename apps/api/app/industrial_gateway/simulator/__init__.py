"""软件 OPC UA 设备模拟器子包。

提供与真实 PLC 行为一致的软件 OPC UA Server（Industrial Motor），
用于没有真实设备时的完整 Demo；数值由固定种子的确定性生成器产生，
可复现、不漂移。
"""

from __future__ import annotations
