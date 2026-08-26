"""Intiface Central 后端客户端（Buttplug v3 over WebSocket，自动重连）。"""

from __future__ import annotations

import asyncio
import itertools
from typing import Callable, Dict, Optional

from websockets.asyncio.client import connect as ws_connect

from . import buttplug as bp
from .logs import LogManager
from .models import ActuatorInfo, ActuatorType, DeviceInfo, SCALAR_ACTUATOR_MAP

CLIENT_NAME = "GameToyProtocolBridge"

_ACTUATOR_KEYS = (
    (ActuatorType.VIBRATE, "VibrateCmd"),
    (ActuatorType.ROTATE, "RotateCmd"),
    (ActuatorType.LINEAR, "LinearCmd"),
)


class BackendNotConnected(RuntimeError):
    pass


class IntifaceClient:

    def __init__(self, url: str, log: LogManager,
                 on_devices_changed: Optional[Callable] = None,
                 on_event: Optional[Callable] = None,
                 on_state: Optional[Callable] = None):
        self.url = url
        self.log = log
        self.devices: Dict[int, DeviceInfo] = {}
        self.connected = False
        self._on_devices_changed = on_devices_changed
        self._on_event = on_event
        self._on_state = on_state
        self._ws = None
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._ids = itertools.count(1)
        self._routes: Dict[int, Callable] = {}
        self._handshake = asyncio.Event()

    # ---------------- 生命周期 ----------------

    def start(self):
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self.connected = False
        self._notify_state()

    async def _run(self):
        while not self._stop.is_set():
            try:
                async with ws_connect(self.url, open_timeout=5) as ws:
                    self._ws = ws
                    await self._session(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.sys_warning(f"后端连接失败/断开: {e}")
            if self.connected:
                self.connected = False
                self._notify_state()
            if self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _session(self, ws):
        self._handshake.clear()
        await self._send_raw(ws, [("RequestServerInfo",
                                   {"Id": next(self._ids), "ClientName": CLIENT_NAME,
                                    "MessageVersion": bp.MESSAGE_VERSION})])
        pump = asyncio.create_task(self._recv_loop(ws))
        try:
            await asyncio.wait_for(self._handshake.wait(), timeout=6)
        except asyncio.TimeoutError:
            pump.cancel()
            raise ConnectionError("后端握手超时（未收到 ServerInfo）")
        self.connected = True
        self._notify_state()
        self.log.sys_info(f"后端已连接: {self.url}")
        try:
            await self.send_messages([("RequestDeviceList", {})])
        except Exception:
            pass
        await pump

    async def _recv_loop(self, ws):
        async for raw in ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            self.log.capture("ws-backend", "rx", raw.encode("utf-8"))
            try:
                messages = bp.parse_messages(raw)
            except ValueError as e:
                self.log.sys_warning(f"后端消息解析失败: {e}")
                continue
            for msg_type, body in messages:
                await self._handle_message(msg_type, body)

    # ---------------- 消息处理 ----------------

    async def _handle_message(self, msg_type: str, body: dict):
        msg_id = body.get("Id")
        if msg_type == "ServerInfo":
            self._handshake.set()
            self.log.sys_info(
                f"后端 ServerInfo: {body.get('ServerName')} v{body.get('MessageVersion')}")
            return
        if msg_type == "DeviceList":
            self.devices.clear()
            for d in body.get("Devices", []):
                self._add_device(d)
            self.log.sys_info(f"后端设备列表: {len(self.devices)} 台")
            if self._on_devices_changed is not None:
                self._on_devices_changed("list", None)
            return
        if msg_type == "DeviceAdded":
            info = self._add_device(body)
            if info is not None and self._on_devices_changed is not None:
                self._on_devices_changed("added", info)
            return
        if msg_type == "DeviceRemoved":
            idx = body.get("DeviceIndex")
            info = self.devices.pop(idx, None)
            if info is not None and self._on_devices_changed is not None:
                self._on_devices_changed("removed", info)
            return
        if msg_type == "Ping":
            if self._ws is not None:
                await self._send_raw(self._ws, [("Ok", {"Id": msg_id})])
            return
        if msg_type == "Error":
            self.log.sys_warning(
                f"后端 Error: {body.get('ErrorMessage')} (code={body.get('ErrorCode')})")
            return
        if msg_type == "ScannerFinished":
            if self._on_event is not None:
                self._on_event(msg_type, body)
            return
        if msg_id in self._routes:
            cb = self._routes.pop(msg_id)
            cb(msg_type, body)
            return
        self.log.sys_debug(f"后端消息忽略: {msg_type} {body}")

    def _add_device(self, d: dict) -> Optional[DeviceInfo]:
        try:
            idx = int(d.get("DeviceIndex"))
        except (TypeError, ValueError):
            return None
        name = d.get("DeviceName") or d.get("DisplayName") or f"Device{idx}"
        msgs = d.get("DeviceMessages") or {}
        actuators = []
        # 新版 buttplug v3：ScalarCmd 以数组描述执行器（ActuatorType/FeatureDescriptor/StepCount）
        scalar_spec = msgs.get("ScalarCmd")
        if isinstance(scalar_spec, list):
            counters = {}
            for si, entry in enumerate(scalar_spec):
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("ActuatorType", "Vibrate"))
                a_type = SCALAR_ACTUATOR_MAP.get(label.lower(), ActuatorType.VIBRATE)
                type_index = counters.get(a_type.value, 0)
                counters[a_type.value] = type_index + 1
                actuators.append(ActuatorInfo(a_type, type_index,
                                              scalar_index=si, label=label))
        # 各类命令声明（新式数组描述符或旧式 FeatureCount 均可）
        for a_type, key in _ACTUATOR_KEYS:
            spec = msgs.get(key)
            if spec is None:
                continue
            if isinstance(spec, dict):
                count = int(spec.get("FeatureCount", 1))
            elif isinstance(spec, list):
                count = len(spec)
            elif isinstance(spec, (int, float)):
                count = int(spec)
            else:
                count = 1
            # ScalarCmd 已登记过的同类型执行器不重复计数
            existing = sum(1 for a in actuators if a.type == a_type)
            for i in range(existing, existing + max(0, min(count, 8))):
                actuators.append(ActuatorInfo(a_type, i))
        info = DeviceInfo(idx, name, actuators, d)
        self.devices[idx] = info
        caps = sorted({a.type.value for a in actuators})
        self.log.sys_info(f"设备[{idx}] {name} 能力: {', '.join(caps) or '无'}")
        return info

    # ---------------- 发送 ----------------

    async def send_messages(self, messages, route_cb: Optional[Callable] = None,
                            keep_ids: bool = False):
        if not self._ws or not self.connected:
            raise BackendNotConnected("后端 Intiface 未连接")
        out = []
        for msg_type, body in messages:
            b = dict(body)
            if not (keep_ids and "Id" in b):
                new_id = next(self._ids)
                if route_cb is not None:
                    self._routes[new_id] = route_cb
                b["Id"] = new_id
            out.append((msg_type, b))
        await self._send_raw(self._ws, out)

    async def _send_raw(self, ws, messages):
        text = bp.serialize(messages)
        await ws.send(text)
        self.log.capture("ws-backend", "tx", text.encode("utf-8"))

    async def stop_all_devices(self):
        await self.send_messages([("StopAllDevices", {})])

    def _notify_state(self):
        if self._on_state is not None:
            try:
                self._on_state(self.connected)
            except Exception:
                pass
