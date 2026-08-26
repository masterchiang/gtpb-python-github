"""Buttplug v3 协议（消息类型为 JSON 键；一次性序列化，严禁二次序列化）。"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from .models import ActuatorType, DeviceInfo

SERVER_NAME = "Intiface Server"   # 镜像 Intiface Central（游戏无需感知 GTPB 存在）
MESSAGE_VERSION = 3
MAX_PING_TIME = 0                 # 与本机 Intiface 实测一致


def parse_messages(text: str) -> List[Tuple[str, Dict]]:
    """解析 Buttplug v3 消息（JSON 数组或单对象，消息类型为键）。"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"非法 JSON: {e}") from e
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Buttplug 消息必须是 JSON 对象或数组")
    out: List[Tuple[str, Dict]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        for key, body in item.items():
            if key.startswith("$"):
                continue  # JSON-Schema 元字段
            out.append((key, body if isinstance(body, dict) else {}))
    return out


def serialize(messages: List[Tuple[str, Dict]]) -> str:
    """一次性序列化为 Buttplug v3 数组文本。

    约束：所有出站消息必须且只经此序列化一次（避免转义引号的双重序列化问题）。
    """
    return json.dumps([dict([(t, b)]) for t, b in messages],
                      separators=(",", ":"), ensure_ascii=False)


def server_info(msg_id, server_name: str = SERVER_NAME,
                version: int = MESSAGE_VERSION, max_ping: int = MAX_PING_TIME):
    return ("ServerInfo", {"Id": msg_id, "ServerName": server_name,
                           "MessageVersion": version, "MaxPingTime": max_ping})


def ok(msg_id):
    return ("Ok", {"Id": msg_id})


def error(msg_id, text, code: int = 4):
    return ("Error", {"Id": msg_id, "ErrorMessage": str(text), "ErrorCode": code})


def device_list(msg_id, devices: List[Dict]):
    return ("DeviceList", {"Id": msg_id, "Devices": devices})


OSR6_AXES = ("L0", "L1", "L2", "R0", "R1", "R2")  # MFP/OSR6 六轴语义


def virtual_osr6_device(index: int = 0, name: str = "GTPB OSR6") -> Dict:
    """构造向游戏呈现的 OSR6 虚拟六轴设备。

    实验记录（详见 serious bug.txt）：
    - 第 1/3 次：LinearCmd[数组式, ActuatorType="Linear"]  -> 卡"连接中"
    - 第 5 次：  LinearCmd[旧式 FeatureCount]               -> 卡"连接中"
    - 第 6 次：  ScalarCmd[Position] + RotateCmd             -> 设备可识别，但 piston 不显示
    - 第 7 次（当前）：ScalarCmd + LinearCmd[数组式, ActuatorType="Position"]
      依据（用户提供的正常工作参考实现，TCode v0.3 桥接器）：
        设备能力声明 "TCode Linear (L0)": LinearCmd [Position]
        即 LinearCmd 数组式描述符 + ActuatorType="Position"（TCode v0.3
        4 位精度 0-9999）。游戏的 piston 功能匹配的正是该组合 ——
        之前失败是标签用错（"Linear"），而非 LinearCmd 本身不被接受。
    """
    return {
        "DeviceIndex": index,
        "DeviceName": name,
        "DeviceMessageTimingGap": 100,
        "DeviceMessages": {
            "ScalarCmd": [
                {"ActuatorType": "Position", "FeatureDescriptor": "L0",
                 "StepCount": 100},
                {"ActuatorType": "Vibrate", "FeatureDescriptor": "L1",
                 "StepCount": 100},
                {"ActuatorType": "Vibrate", "FeatureDescriptor": "L2",
                 "StepCount": 100},
            ],
            "LinearCmd": [
                {"ActuatorType": "Position", "FeatureDescriptor": "L0",
                 "StepCount": 9999},
            ],
            "RotateCmd": [
                {"ActuatorType": "Rotate", "FeatureDescriptor": "R0",
                 "StepCount": 100},
                {"ActuatorType": "Rotate", "FeatureDescriptor": "R1",
                 "StepCount": 100},
                {"ActuatorType": "Rotate", "FeatureDescriptor": "R2",
                 "StepCount": 100},
            ],
            "StopDeviceCmd": {},
        },
    }


def virtual_device(info: DeviceInfo) -> Dict:
    """虚拟设备 = 原样透传后端真实描述。

    透传实验（tools/passthrough_probe.py）证明：游戏对 Intiface 原版响应完全兼容，
    任何额外的能力声明（补 VibrateCmd 等）或额外消息都会破坏部分客户端，
    因此严格镜像 —— 游戏直连 Intiface 能看到什么，经 GTPB 就看到什么。
    """
    msgs = dict(info.raw.get("DeviceMessages") or {})
    msgs.setdefault("StopDeviceCmd", {})
    device = {
        "DeviceIndex": info.index,
        "DeviceName": info.name,
        "DeviceMessages": msgs,
    }
    gap = info.raw.get("DeviceMessageTimingGap")
    if gap is not None:
        device["DeviceMessageTimingGap"] = gap
    return device
