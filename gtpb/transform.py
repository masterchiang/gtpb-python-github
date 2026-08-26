"""转换引擎 + 指令分发器：归一化指令 -> Buttplug 设备指令（latest-wins 合并）。"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, List, Optional, Tuple

from .logs import LogManager
from .models import ActuatorType, DeviceInfo, NormalizedCommand
from .safety import EmergencyStop


def assemble_message(msg_type: str, device_index: int, motors: Dict[int, dict]) -> Tuple[str, dict]:
    """按 Buttplug v3 格式组装设备指令体（不含 Id，由发送端统一分配）。"""
    if msg_type == "VibrateCmd":
        body = {
            "DeviceIndex": device_index,
            "Speeds": [{"Index": i, "Speed": float(p["Speed"])}
                       for i, p in sorted(motors.items())],
        }
    elif msg_type == "RotateCmd":
        body = {
            "DeviceIndex": device_index,
            "Rotations": [{"Index": i, "Speed": float(p["Speed"]),
                           "Clockwise": bool(p.get("Clockwise", True))}
                          for i, p in sorted(motors.items())],
        }
    elif msg_type == "LinearCmd":
        body = {
            "DeviceIndex": device_index,
            "Vectors": [{"Index": i, "Duration": int(p.get("Duration", 300)),
                         "Position": float(p["Position"])}
                        for i, p in sorted(motors.items())],
        }
    elif msg_type == "ScalarCmd":
        body = {
            "DeviceIndex": device_index,
            "Scalars": [{"Index": i, "Scalar": float(p["Scalar"]),
                         "ActuatorType": p.get("ActuatorType", "Vibrate")}
                        for i, p in sorted(motors.items())],
        }
    else:
        raise ValueError(f"未支持的指令类型: {msg_type}")
    return msg_type, body


# 各功能对应的原生命令名
NATIVE_COMMAND_KEY = {
    "Vibrate": "VibrateCmd",
    "Rotate": "RotateCmd",
    "Linear": "LinearCmd",
}


class TransformEngine:
    """将归一化通道命令聚合转换为真实设备指令。

    - 设备解析：优先 ChannelMapping.device_index，否则自动选择第一个支持该功能的设备
    - 不同来源通道可重定向到同一真实电机（后到者覆盖）
    """

    def __init__(self, devices_provider: Callable[[], Dict[int, DeviceInfo]]):
        self._devices_provider = devices_provider

    def _resolve_device(self, cmd: NormalizedCommand) -> Optional[int]:
        devices = self._devices_provider()
        if not devices:
            return None
        if cmd.device_index >= 0 and cmd.device_index in devices:
            if devices[cmd.device_index].supports(cmd.target):
                return cmd.device_index
        for idx in sorted(devices):
            if devices[idx].supports(cmd.target):
                return idx
        return None

    def build_messages(self, cmds: List[NormalizedCommand]) -> Tuple[List[Tuple[str, dict]], set]:
        groups: Dict[Tuple[int, str], Dict[int, dict]] = {}
        skipped = set()
        devices = self._devices_provider()
        for c in cmds:
            dev = self._resolve_device(c)
            if dev is None:
                skipped.add(c.target.value)
                continue
            info = devices.get(dev)
            actuator = None
            for a in info.actuators:
                if a.type == c.target and a.index == c.motor:
                    actuator = a
                    break
            if actuator is None:
                skipped.add(c.target.value)
                continue
            # 设备声明了原生命令则用原生命令，否则走 ScalarCmd
            native_key = NATIVE_COMMAND_KEY.get(c.target.value)
            raw_msgs = info.raw.get("DeviceMessages") or {}
            if native_key and native_key in raw_msgs:
                msg_type = native_key
                motor = actuator.index
            elif actuator.scalar_index >= 0:
                msg_type = "ScalarCmd"
                motor = actuator.scalar_index
            else:
                skipped.add(c.target.value)
                continue
            motors = groups.setdefault((dev, msg_type), {})
            if msg_type == "VibrateCmd":
                motors[motor] = {"Speed": c.value}
            elif msg_type == "RotateCmd":
                motors[motor] = {"Speed": c.value,
                                 "Clockwise": bool(c.meta.get("Clockwise", True))}
            elif msg_type == "LinearCmd":
                duration = int(min(max(int(c.meta.get("Duration", 300)), 0), 10000))
                motors[motor] = {"Position": c.value, "Duration": duration}
            else:  # ScalarCmd
                motors[motor] = {"Scalar": c.value,
                                 "ActuatorType": actuator.label or c.target.value}
        messages = [assemble_message(t, dev, motors)
                    for (dev, t), motors in groups.items()]
        return messages, skipped


class CommandDispatcher:
    """低延迟指令分发：latest-wins 合并 + 最小刷新间隔。"""

    def __init__(self, send_fn: Callable, transform: TransformEngine,
                 estop: EmergencyStop, log: LogManager, min_interval_ms: int = 5):
        self._send_fn = send_fn
        self._transform = transform
        self._estop = estop
        self._log = log
        self._interval = max(0, int(min_interval_ms)) / 1000.0
        self._pending: Dict[Tuple[int, str, int], dict] = {}
        self._wakeup = asyncio.Event()
        self._running = False
        self._warned: set = set()
        self._last_send_error = 0.0

    def reset_warnings(self):
        self._warned.clear()

    def submit(self, cmds: List[NormalizedCommand]):
        if self._estop.active or not cmds:
            return
        try:
            messages, skipped = self._transform.build_messages(cmds)
        except Exception as e:
            self._log.sys_error(f"指令转换失败: {e}")
            return
        for t in skipped:
            if t not in self._warned:
                self._warned.add(t)
                self._log.sys_warning(f"后端暂无支持 {t} 的设备，相关通道指令被丢弃")
        for msg_type, body in messages:
            dev = body["DeviceIndex"]
            if msg_type == "VibrateCmd":
                items, payload_fn = body["Speeds"], lambda it: {"Speed": it["Speed"]}
            elif msg_type == "RotateCmd":
                items = body["Rotations"]
                payload_fn = lambda it: {"Speed": it["Speed"], "Clockwise": it["Clockwise"]}  # noqa: E731
            elif msg_type == "ScalarCmd":
                items = body["Scalars"]
                payload_fn = lambda it: {"Scalar": it["Scalar"], "ActuatorType": it["ActuatorType"]}  # noqa: E731
            else:  # LinearCmd
                items = body["Vectors"]
                payload_fn = lambda it: {"Position": it["Position"], "Duration": it["Duration"]}  # noqa: E731
            for it in items:
                self._pending[(dev, msg_type, it["Index"])] = payload_fn(it)
        self._wakeup.set()

    async def run(self):
        self._running = True
        while self._running:
            await self._wakeup.wait()
            self._wakeup.clear()
            if not self._pending:
                continue
            if self._estop.active:
                self._pending.clear()
                continue
            batch, self._pending = self._pending, {}
            grouped: Dict[Tuple[int, str], Dict[int, dict]] = {}
            for (dev, msg_type, motor), payload in batch.items():
                grouped.setdefault((dev, msg_type), {})[motor] = payload
            messages = [assemble_message(t, dev, motors)
                        for (dev, t), motors in grouped.items()]
            try:
                await self._send_fn(messages)
            except Exception as e:
                now = time.monotonic()
                if now - self._last_send_error > 2.0:
                    self._last_send_error = now
                    self._log.sys_warning(f"指令发送失败: {e}")
            if self._interval > 0:
                await asyncio.sleep(self._interval)

    def stop(self):
        self._running = False
        self._wakeup.set()

    def clear(self):
        self._pending.clear()
