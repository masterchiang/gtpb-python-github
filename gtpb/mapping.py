"""映射引擎：通道值 -> 归一化指令（Deadzone -> Scale -> Invert -> Clamp）。"""

from __future__ import annotations

from typing import Optional

from .config import Profile
from .models import ActuatorType, Channel, NormalizedCommand


class MappingEngine:

    def __init__(self, profile: Profile):
        self.profile = profile

    def apply(self, channel: Channel, value: float) -> Optional[NormalizedCommand]:
        m = self.profile.channels.get(channel.value)
        if m is None or not m.enabled:
            return None
        # 游戏输入先钳制到 0..1（Range Mapping：若游戏为 0~100，应由适配器先归一化）
        v = min(1.0, max(0.0, float(value)))
        raw = v

        # 中点旋转模式（MFP 约定）：位置轴 0.5=停止，偏离中点越多转速越快
        if m.midpoint:
            speed = abs(v - 0.5) * 2.0
            lo, hi = (m.min, m.max) if m.min <= m.max else (m.max, m.min)
            speed = lo + speed * (hi - lo)
            if m.clamp:
                speed = min(1.0, max(0.0, speed))
            clockwise = (v > 0.5)
            if m.invert:
                clockwise = not clockwise
            return NormalizedCommand(
                channel=channel, value=speed, raw_value=raw,
                target=ActuatorType(m.target), motor=m.motor,
                device_index=m.device_index,
                meta={"Clockwise": clockwise})

        if m.deadzone > 0.0:
            if v <= m.deadzone:
                v = 0.0
            else:
                v = (v - m.deadzone) / (1.0 - m.deadzone)
        v *= m.scale
        if m.invert:
            v = 1.0 - v
        # 输出范围重映射（MFP Output Range: Lerp(min, max, v)）
        lo, hi = (m.min, m.max) if m.min <= m.max else (m.max, m.min)
        v = lo + v * (hi - lo)
        if m.clamp:
            v = min(1.0, max(0.0, v))
        return NormalizedCommand(
            channel=channel,
            value=v,
            raw_value=raw,
            target=ActuatorType(m.target),
            motor=m.motor,
            device_index=m.device_index,
        )
