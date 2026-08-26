"""核心数据模型：通道、原始帧、归一化指令、设备信息。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class Channel(str, Enum):
    """六个标准通道：L0-L2 / R0-R2。"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"


CHANNELS: List[Channel] = list(Channel)


class ActuatorType(str, Enum):
    VIBRATE = "Vibrate"
    ROTATE = "Rotate"
    LINEAR = "Linear"


# ScalarCmd 的 ActuatorType 标签 -> 内部归类
SCALAR_ACTUATOR_MAP = {
    "vibrate": ActuatorType.VIBRATE,
    "oscillate": ActuatorType.VIBRATE,
    "rotate": ActuatorType.ROTATE,
    "linear": ActuatorType.LINEAR,
    "position": ActuatorType.LINEAR,
}


@dataclass
class RawFrame:
    """原始数据帧（用于 Capture / Protocol Inspector）。"""

    transport: str            # ws-game / tcp-game / ws-backend
    direction: str            # rx / tx
    data: bytes
    timestamp: float = field(default_factory=time.time)


@dataclass
class NormalizedCommand:
    """归一化后的通道指令（映射引擎输出 / 转换引擎输入）。"""

    channel: Channel
    value: float              # 映射后 0..1
    raw_value: float          # 游戏原始值 0..1
    target: ActuatorType      # 目标功能
    motor: int                # 真实设备电机号
    device_index: int = -1    # -1 = 自动选择设备
    meta: Dict = field(default_factory=dict)  # Clockwise / Duration 等透传参数


@dataclass
class ActuatorInfo:
    type: ActuatorType          # 归类后的 Vibrate/Rotate/Linear
    index: int                  # 类型内电机号
    scalar_index: int = -1      # ScalarCmd 全局执行器索引（-1 = 非 Scalar 型）
    label: str = ""             # 设备声明的原始 ActuatorType 标签


@dataclass
class DeviceInfo:
    index: int
    name: str
    actuators: List[ActuatorInfo] = field(default_factory=list)
    raw: Dict = field(default_factory=dict)

    def feature_count(self, actuator_type: ActuatorType) -> int:
        return sum(1 for a in self.actuators if a.type == actuator_type)

    def supports(self, actuator_type: ActuatorType) -> bool:
        return self.feature_count(actuator_type) > 0
