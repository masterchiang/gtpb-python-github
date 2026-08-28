"""桥接服务：游戏端 WebSocket/TCP 代理 <-> 映射/转换 <-> Intiface 后端。"""

from __future__ import annotations

import asyncio
import uuid
from typing import List, Optional, Tuple

from websockets.asyncio.server import serve as ws_serve

from . import buttplug as bp
from .backend import BackendNotConnected, IntifaceClient
from .config import AppConfig, Profile
from .logs import LogManager
from .mapping import MappingEngine
from .models import Channel
from .pulse import PulseEngine
from .safety import EmergencyStop
from .transform import CommandDispatcher, TransformEngine

DEVICE_COMMANDS = {"VibrateCmd", "LinearCmd", "RotateCmd", "ScalarCmd"}
STOP_COMMANDS = {"StopDeviceCmd", "StopAllDevices"}

# 游戏端虚拟电机 -> 通道 的默认绑定（Profile.bindings 可覆盖）
DEFAULT_BINDING_TABLE = {
    "Vibrate": ("L0", "L1", "L2"),
    "Rotate": ("R0", "R1"),
    "Linear": ("R2",),
}

# OSR6 虚拟设备模式的绑定：L0-L2 = 线性位置轴，R0-R2 = 旋转轴
OSR6_BINDING_TABLE = {
    "Vibrate": ("L0", "L1", "L2"),
    "Linear": ("L0", "L1", "L2"),
    "Rotate": ("R0", "R1", "R2"),
}


class GameSession:
    """单个游戏连接会话：本地应答握手，设备指令进入映射管线。"""

    def __init__(self, bridge: "BridgeService", transport: str, send_func, close_func):
        self.id = uuid.uuid4().hex[:8]
        self.bridge = bridge
        self.transport = transport
        self._send_func = send_func
        self._close_func = close_func
        self.closed = False

    async def send_text(self, text: str):
        if self.closed:
            return
        self.bridge.log.game_tx(self.transport, text)
        self.bridge.log.capture(self.transport, "tx", text.encode("utf-8"))
        await self._send_func(text)

    async def handle_text(self, text: str):
        self.bridge.log.game_rx(self.transport, text)
        self.bridge.log.capture(self.transport, "rx", text.encode("utf-8"))
        try:
            messages = bp.parse_messages(text)
        except ValueError as e:
            self.bridge.log.sys_warning(f"[{self.transport}] 消息解析失败: {e}")
            return
        replies = []
        for msg_type, body in messages:
            try:
                reply = await self._handle_message(msg_type, body)
            except Exception as e:
                self.bridge.log.sys_error(f"处理消息 {msg_type} 异常: {e}")
                reply = bp.error(body.get("Id", 0), f"GTPB internal error: {e}")
            if reply is not None:
                if isinstance(reply, list):
                    replies.extend(reply)
                else:
                    replies.append(reply)
        if replies:
            await self.send_text(bp.serialize(replies))

    async def _handle_message(self, msg_type: str, body: dict):
        bridge = self.bridge
        msg_id = body.get("Id", 0)

        # 急停期间：丢弃动作指令，但放行停止指令与握手
        if bridge.estop.active and msg_type in DEVICE_COMMANDS:
            return bp.ok(msg_id)

        if msg_type == "RequestServerInfo":
            # 始终以 v3 应答（消息类型为 JSON 键）
            return bp.server_info(msg_id)
        if msg_type == "Ping":
            return bp.ok(msg_id)
        if msg_type == "RequestLog":
            return bp.ok(msg_id)
        if msg_type == "RequestDeviceList":
            # 严格镜像 Intiface：只回 DeviceList 本身。
            # 透传实验证明额外消息（如同数组的 DeviceAdded）会卡死部分游戏客户端。
            return bp.device_list(msg_id, bridge.virtual_device_dicts())
        if msg_type in ("StartScanning", "StopScanning"):
            forwarded = await bridge.forward_request(msg_type, body)
            if forwarded:
                return bp.ok(msg_id)
            return bp.error(msg_id, "后端 Intiface 未连接", 2)
        if msg_type in STOP_COMMANDS:
            await bridge.forward_stop(msg_type, body)
            return bp.ok(msg_id)
        if msg_type in DEVICE_COMMANDS:
            bridge.handle_device_command(msg_type, body)
            return bp.ok(msg_id)
        if msg_id:
            self.bridge.log.sys_warning(f"[{self.transport}] 未支持消息 {msg_type}，已回 Ok")
            return bp.ok(msg_id)
        return None

    async def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            await self._close_func()
        except Exception:
            pass


class BridgeService:
    """总装：代理服务器 + 映射/转换/分发 + 后端客户端 + 日志/急停。"""

    def __init__(self, config: AppConfig, profile: Profile,
                 log_callback=None, console: bool = False,
                 log_path: Optional[str] = None):
        self.config = config
        self.profile = profile
        # 日志文件路径：若调用方已指定（如 main.py 启动时创建的 LogManager），复用；
        # 否则按 config.logging.dir（BASE_DIR/gtpb.log）创建。
        if not log_path:
            log_path = config.logging.dir
        self.log = LogManager(
            log_path, config.logging.capture_raw,
            config.logging.level, log_callback, console)
        self.estop = EmergencyStop(on_engage=self._on_estop_engaged)
        self.mapping = MappingEngine(profile)
        self.backend = IntifaceClient(
            config.proxy.backend_url, self.log,
            on_devices_changed=self._on_devices_changed,
            on_event=self._on_backend_event,
            on_state=self._on_backend_state)
        self.transform = TransformEngine(lambda: self.backend.devices)
        self.dispatcher = CommandDispatcher(
            self._send_device_messages, self.transform, self.estop,
            self.log, config.safety.command_min_interval_ms)
        self.pulse = PulseEngine(self.dispatcher, lambda: self.profile, self.log)
        self.sessions = {}
        self._servers = []
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._started = False

    # ---------------- 生命周期 ----------------

    async def start(self):
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        proxy = self.config.proxy
        self.log.sys_info("=" * 50)
        self.log.sys_info(f"GTPB 启动 (Profile={self.profile.name})")
        self._tasks.append(asyncio.create_task(
            self._supervise(self.dispatcher.run(), "dispatcher")))
        self._tasks.append(asyncio.create_task(
            self._supervise(self.pulse.run(), "pulse")))
        self.backend.start()
        if proxy.ws_port > 0:
            # 注意：不设置 subprotocols —— 游戏客户端（如 MultiFunPlayer）通常不携带
            # 子协议，websockets 17 在服务端配置 subprotocols 后会拒绝未携带的连接
            server = await ws_serve(
                self._ws_handler, proxy.listen_address, proxy.ws_port,
                max_size=4 * 1024 * 1024)
            self._servers.append(server)
            self.log.sys_info(f"WebSocket 监听: ws://{proxy.listen_address}:{proxy.ws_port}")
        if proxy.tcp_port > 0:
            tcp_server = await asyncio.start_server(
                self._tcp_handler, proxy.listen_address, proxy.tcp_port)
            self._servers.append(tcp_server)
            self.log.sys_info(f"TCP 监听: tcp://{proxy.listen_address}:{proxy.tcp_port}")
        self.log.sys_info(f"后端 Intiface: {proxy.backend_url}")

    async def _supervise(self, coro, name: str):
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.sys_error(f"{name} 异常退出: {e}")

    async def wait_stopped(self):
        await self._stop_event.wait()

    def request_stop(self):
        """请求停止（须在事件循环线程内调用，GUI 经 call_soon_threadsafe 调用）。"""
        self._stop_event.set()

    async def stop(self):
        if not self._started:
            return
        self._started = False
        # 退出前让设备安全停止
        try:
            await self.backend.stop_all_devices()
        except Exception:
            pass
        for server in self._servers:
            try:
                server.close()
                await server.wait_closed()
            except Exception:
                pass
        self._servers.clear()
        for session in list(self.sessions.values()):
            await session.close()
        self.sessions.clear()
        self.dispatcher.stop()
        self.pulse.stop()
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.backend.stop()
        self.log.sys_info("GTPB 已停止")
        self.log.close()

    # ---------------- 游戏端接入 ----------------

    async def _ws_handler(self, ws):
        session = GameSession(self, "ws-game", ws.send, ws.close)
        self.sessions[session.id] = session
        peer = getattr(ws, "remote_address", None)
        self.log.sys_info(f"游戏会话接入 [{session.id}] (WebSocket) 来自 {peer}")
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                await session.handle_text(raw)
        except Exception as e:
            self.log.sys_warning(f"游戏会话 [{session.id}] 连接异常: {e}")
        finally:
            # 会话清理（对应 C# 版 RaiseOnDisconnected 语义）
            self.sessions.pop(session.id, None)
            session.closed = True
            self.log.sys_info(f"游戏会话断开 [{session.id}]")

    async def _tcp_handler(self, reader, writer):
        def send_text(text: str):
            writer.write(text.encode("utf-8") + b"\n")
            return writer.drain()

        async def close_conn():
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        session = GameSession(self, "tcp-game", send_text, close_conn)
        self.sessions[session.id] = session
        peer = writer.get_extra_info("peername")
        self.log.sys_info(f"游戏会话接入 [{session.id}] (TCP) 来自 {peer}")
        buf = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", "replace").strip()
                    if text:
                        await session.handle_text(text)
        except Exception as e:
            self.log.sys_warning(f"游戏会话 [{session.id}] TCP 异常: {e}")
        finally:
            self.sessions.pop(session.id, None)
            session.closed = True
            await close_conn()
            self.log.sys_info(f"游戏会话断开 [{session.id}] (TCP)")

    # ---------------- 设备指令管线 ----------------

    def binding_channel(self, device_index: int, actuator: str, motor: int) -> Optional[Channel]:
        if self.profile.virtual_mode == "osr6":
            # OSR6 模式：固定按轴名绑定（虚拟设备描述符已标轴名），
            # 忽略透传模式的预设 bindings，避免两套语义互相污染
            table = OSR6_BINDING_TABLE
            name = None
        else:
            table = DEFAULT_BINDING_TABLE
            name = self.profile.bindings.get(f"{actuator}:{device_index}:{motor}")
        if name is None:
            arr = table.get(actuator, ())
            if motor < len(arr):
                name = arr[motor]
        if name is None:
            return None
        try:
            return Channel(name)
        except ValueError:
            return None

    def scalar_actuator(self, device_index: int, scalar_index: int):
        """按 ScalarCmd 全局执行器索引查找执行器信息。"""
        info = self.backend.devices.get(device_index)
        if info is None:
            return None
        for a in info.actuators:
            if a.scalar_index == scalar_index:
                return a
        return None

    def handle_device_command(self, msg_type: str, body: dict):
        actuator = msg_type[:-3]  # Vibrate / Linear / Rotate
        device_index = int(body.get("DeviceIndex", 0))
        entries = []  # (通道类型, 类型内电机号, 值, 附加 meta)
        if msg_type == "VibrateCmd":
            entries = [(actuator, int(s.get("Index", 0)), float(s.get("Speed", 0.0)), {})
                       for s in body.get("Speeds", [])]
        elif msg_type == "RotateCmd":
            entries = [(actuator, int(r.get("Index", 0)), float(r.get("Speed", 0.0)),
                        {"Clockwise": bool(r.get("Clockwise", True))})
                       for r in body.get("Rotations", [])]
        elif msg_type == "LinearCmd":
            entries = [(actuator, int(v.get("Index", 0)), float(v.get("Position", 0.0)),
                        {"Duration": int(v.get("Duration", 300))})
                       for v in body.get("Vectors", [])]
        elif msg_type == "ScalarCmd":
            # 新版 v3：按全局执行器索引换算为 (类型, 类型内电机号)
            if self.profile.virtual_mode == "osr6":
                # 虚拟 OSR6：ScalarCmd[0..2] 固定为 L0..L2 轴（虚拟设备布局自定）
                for s in body.get("Scalars", []):
                    si = int(s.get("Index", 0))
                    if 0 <= si <= 2:
                        entries.append(("Vibrate", si,
                                        float(s.get("Scalar", 0.0)), {}))
            else:
                for s in body.get("Scalars", []):
                    a = self.scalar_actuator(device_index, int(s.get("Index", 0)))
                    if a is None:
                        continue
                    entries.append((a.type.value, a.index,
                                    float(s.get("Scalar", 0.0)), {}))
        cmds = []
        for actuator_type, motor, value, meta in entries:
            channel = self.binding_channel(device_index, actuator_type, motor)
            if channel is None:
                continue
            n = self.mapping.apply(channel, value)
            if n is None:
                continue
            n.meta.update(meta)
            cmds.append(n)
        self.pulse.process_cmds(cmds)

    async def _send_device_messages(self, messages):
        await self.backend.send_messages(messages)

    async def forward_request(self, msg_type: str, body: dict) -> bool:
        try:
            await self.backend.send_messages(
                [(msg_type, {k: v for k, v in body.items() if k != "Id"})])
            return True
        except BackendNotConnected:
            return False
        except Exception as e:
            self.log.sys_warning(f"转发 {msg_type} 失败: {e}")
            return False

    async def forward_stop(self, msg_type: str, body: dict):
        try:
            await self.backend.send_messages(
                [(msg_type, {k: v for k, v in body.items() if k != "Id"})])
        except Exception as e:
            self.log.sys_warning(f"转发 {msg_type} 失败: {e}")

    # ---------------- 设备/事件广播 ----------------

    def virtualize(self, info) -> dict:
        """按 Profile 模式把后端设备虚拟化（列表与广播保持一致）。"""
        if self.profile.virtual_mode == "osr6":
            return bp.virtual_osr6_device(index=info.index)
        return bp.virtual_device(info)

    def virtual_device_dicts(self) -> List[dict]:
        if not self.backend.devices:
            return []
        if self.profile.virtual_mode == "osr6":
            return [bp.virtual_osr6_device()]
        return [bp.virtual_device(d) for _, d in sorted(self.backend.devices.items())]

    def apply_profile(self, profile: Profile):
        """热应用新 Profile（映射参数/绑定/虚拟模式即时生效）。"""
        self.profile = profile
        self.mapping.profile = profile
        self.log.sys_info(
            f"Profile 已热应用: {profile.name} (模式={profile.virtual_mode})")

    def broadcast(self, messages):
        if not self.sessions:
            return
        text = bp.serialize(messages)
        for session in list(self.sessions.values()):
            asyncio.ensure_future(session.send_text(text))

    def _on_backend_state(self, connected: bool):
        if connected:
            self.log.sys_info("后端 Intiface 已连接")
        else:
            self.log.sys_warning("后端 Intiface 连接断开")

    def _on_devices_changed(self, action: str, device):
        self.dispatcher.reset_warnings()
        if action == "added" and device is not None:
            self.broadcast([("DeviceAdded", self.virtualize(device))])
        elif action == "removed" and device is not None:
            self.broadcast([("DeviceRemoved", {"DeviceIndex": device.index})])

    def _on_backend_event(self, msg_type: str, body: dict):
        if msg_type == "ScannerFinished":
            self.broadcast([("ScannerFinished", {})])

    # ---------------- 急停 ----------------

    def _on_estop_engaged(self, reason: str):
        self.dispatcher.clear()
        self.pulse.clear()
        self.log.sys_error(f"!!! 紧急停止触发 ({reason})：所有设备指令被拦截 !!!")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._estop_stop_all())
        except RuntimeError:
            pass

    async def _estop_stop_all(self):
        try:
            await self.backend.stop_all_devices()
            self.log.sys_warning("已向后端发送 StopAllDevices")
        except Exception as e:
            self.log.sys_warning(f"急停发送 StopAllDevices 失败: {e}")

    def engage_estop(self, reason: str = "manual"):
        self.estop.engage(reason)

    def release_estop(self):
        self.estop.release()
        self.log.sys_info("急停已释放，恢复正常指令通道")

    # ---------------- 状态 ----------------

    def channel_levels(self) -> dict:
        """各通道当前电平（供 GUI 信号柱状图轮询）。"""
        return self.pulse.channel_levels()

    def status(self) -> dict:
        devices = []
        for d in self.backend.devices.values():
            devices.append({
                "index": d.index,
                "name": d.name,
                "capabilities": sorted({a.type.value for a in d.actuators}),
                "actuators": [
                    {"label": a.label or a.type.value, "type": a.type.value,
                     "motor": a.index}
                    for a in d.actuators
                ],
            })
        return {
            "running": self._started,
            "backend": self.backend.connected,
            "sessions": len(self.sessions),
            "estop": self.estop.active,
            "virtual_mode": self.profile.virtual_mode,
            "devices": devices,
        }
