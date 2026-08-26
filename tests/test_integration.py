"""集成测试：模拟 Intiface 后端 + 模拟游戏客户端，验证全链路。

链路: 模拟游戏 -> GTPB(WebSocket, Buttplug v3) -> 映射/转换 -> 模拟 Intiface -> 断言指令
覆盖: v3 握手 / 设备同步与虚拟化 / 指令映射转换 / 扫描广播 / 急停 / 幽灵设备清理

运行: python -m unittest discover -s tests -v   （在 gtpb-python 目录下）
"""

import asyncio
import json
import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websockets.asyncio.client import connect as ws_connect
from websockets.asyncio.server import serve as ws_serve

from gtpb import buttplug as bp
from gtpb.config import AppConfig, Profile
from gtpb.proxy import BridgeService


async def get_free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class MockIntiface:
    """最小 Intiface Central 模拟（buttplug v3 新版格式，与 TryFun Meta 2 一致）。"""

    DEVICE0 = {
        "DeviceIndex": 0,
        "DeviceName": "MockToy",
        "DeviceMessageTimingGap": 100,
        "DeviceMessages": {
            "ScalarCmd": [
                {"ActuatorType": "Oscillate", "FeatureDescriptor": "", "StepCount": 100},
                {"ActuatorType": "Vibrate", "FeatureDescriptor": "", "StepCount": 100},
                {"ActuatorType": "Rotate", "FeatureDescriptor": "", "StepCount": 100},
            ],
            "RotateCmd": [{"ActuatorType": "Rotate", "FeatureDescriptor": "", "StepCount": 100}],
            "LinearCmd": [{"ActuatorType": "Linear", "FeatureDescriptor": "", "StepCount": 100}],
            "StopDeviceCmd": {},
        },
    }
    DEVICE1 = {  # StartScanning 时"发现"的新设备
        "DeviceIndex": 1,
        "DeviceName": "MockToy2",
        "DeviceMessages": {"VibrateCmd": {"FeatureCount": 1}},
    }

    def __init__(self):
        self.devices = {0: dict(self.DEVICE0)}
        self.received = []          # 记录 (type, body)
        self.server = None
        self.port = 0
        self.clients = set()

    async def start(self):
        self.server = await ws_serve(self._handler, "127.0.0.1", 0, max_size=2 ** 20)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handler(self, ws):
        self.clients.add(ws)
        try:
            async for raw in ws:
                for msg_type, body in bp.parse_messages(raw):
                    await self._on(ws, msg_type, body)
        finally:
            self.clients.discard(ws)

    async def _send(self, ws, messages):
        await ws.send(bp.serialize(messages))

    async def _on(self, ws, msg_type: str, body: dict):
        mid = body.get("Id", 0)
        if msg_type == "RequestServerInfo":
            await self._send(ws, [("ServerInfo", {
                "Id": mid, "ServerName": "MockIntiface",
                "MessageVersion": 3, "MaxPingTime": 10000})])
        elif msg_type == "RequestDeviceList":
            await self._send(ws, [("DeviceList", {
                "Id": mid, "Devices": list(self.devices.values())})])
        elif msg_type == "StartScanning":
            await self._send(ws, [("Ok", {"Id": mid})])
            if 1 not in self.devices:
                self.devices[1] = dict(self.DEVICE1)
                await self._send(ws, [("DeviceAdded", dict(self.DEVICE1))])
            await self._send(ws, [("ScannerFinished", {})])
        elif msg_type in ("VibrateCmd", "RotateCmd", "LinearCmd", "ScalarCmd",
                          "StopDeviceCmd", "StopAllDevices"):
            self.received.append((msg_type, body))
            await self._send(ws, [("Ok", {"Id": mid})])
        else:
            await self._send(ws, [("Ok", {"Id": mid})])

    async def wait_received(self, msg_type: str, timeout: float = 5.0, after: int = 0):
        """等待第 after+1 条指定类型消息（after=0 表示第一条）。"""
        async def _wait():
            while True:
                matches = [(t, b) for t, b in self.received if t == msg_type]
                if len(matches) > after:
                    return matches[after]
                await asyncio.sleep(0.01)
        return await asyncio.wait_for(_wait(), timeout)


class TestEndToEnd(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock = MockIntiface()
        backend_port = await self.mock.start()

        config = AppConfig()
        config.proxy.listen_address = "127.0.0.1"
        config.proxy.ws_port = await get_free_port()
        config.proxy.tcp_port = 0
        config.proxy.backend_url = f"ws://127.0.0.1:{backend_port}"
        config.logging.dir = tempfile.mkdtemp(prefix="gtpb-itest-")
        config.logging.capture_raw = False
        config.safety.command_min_interval_ms = 5
        self.config = config

        self.service = BridgeService(config, Profile.default())
        await self.service.start()
        for _ in range(200):  # 等后端连接 + 设备同步
            if self.service.backend.connected and self.service.backend.devices:
                break
            await asyncio.sleep(0.05)
        self.assertTrue(self.service.backend.connected, "后端未连上 mock")
        self.assertIn(0, self.service.backend.devices, "设备未同步")

    async def asyncTearDown(self):
        await self.service.stop()
        await self.mock.stop()

    # ---------------- 工具 ----------------

    async def _game_connect(self):
        ws = await ws_connect(
            f"ws://127.0.0.1:{self.config.proxy.ws_port}",
            proxy=None, open_timeout=5)
        await ws.send(bp.serialize(
            [("RequestServerInfo", {"Id": 1, "ClientName": "TestGame",
                                    "MessageVersion": 3})]))
        reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
        return ws, reply

    async def _recv_until(self, ws, want_type: str, timeout: float = 5.0):
        """持续接收消息数组，直到出现指定类型。"""
        async def _wait():
            while True:
                raw = await ws.recv()
                for item in json.loads(raw):
                    for t, b in item.items():
                        if t == want_type:
                            return t, b
        return await asyncio.wait_for(_wait(), timeout)

    # ---------------- 用例 ----------------

    async def test_handshake_and_device_list(self):
        ws, reply = await self._game_connect()
        try:
            self.assertIn("ServerInfo", reply[0])
            info = reply[0]["ServerInfo"]
            self.assertEqual(info["MessageVersion"], 3)
            # 镜像 Intiface：ServerName/MaxPingTime 与真实后端一致
            self.assertEqual(info["ServerName"], "Intiface Server")
            self.assertEqual(info["MaxPingTime"], 0)

            await ws.send(bp.serialize([("RequestDeviceList", {"Id": 2})]))
            _, dev_list = await self._recv_until(ws, "DeviceList")
            self.assertEqual(len(dev_list["Devices"]), 1)
            dev = dev_list["Devices"][0]
            self.assertEqual(dev["DeviceName"], "MockToy")
            self.assertEqual(dev["DeviceMessageTimingGap"], 100)
            msgs = dev["DeviceMessages"]
            # 纯透传：与后端声明完全一致，不增不减
            self.assertEqual(len(msgs["ScalarCmd"]), 3)
            self.assertEqual(msgs["ScalarCmd"][1]["ActuatorType"], "Vibrate")
            self.assertIn("RotateCmd", msgs)
            self.assertIn("LinearCmd", msgs)
            self.assertIn("StopDeviceCmd", msgs)
            self.assertNotIn("VibrateCmd", msgs)  # 后端没有的能力绝不虚构
        finally:
            await ws.close()

    async def test_vibrate_pipeline(self):
        ws, _ = await self._game_connect()
        try:
            # 电机0: 游戏 Vibrate 0.8 -> L0 -> 设备无原生 VibrateCmd -> ScalarCmd[0]("Oscillate")
            await ws.send(bp.serialize([("VibrateCmd", {
                "Id": 10, "DeviceIndex": 0,
                "Speeds": [{"Index": 0, "Speed": 0.8}]})]))
            _, body = await self.mock.wait_received("ScalarCmd")
            self.assertEqual(body["DeviceIndex"], 0)
            self.assertEqual(body["Scalars"],
                             [{"Index": 0, "Scalar": 0.8, "ActuatorType": "Oscillate"}])

            # 电机1: 0.3 -> L1 -> ScalarCmd[1]("Vibrate")
            await ws.send(bp.serialize([("VibrateCmd", {
                "Id": 11, "DeviceIndex": 0,
                "Speeds": [{"Index": 1, "Speed": 0.3}]})]))
            _, body = await self.mock.wait_received("ScalarCmd", after=1)
            self.assertEqual(body["Scalars"],
                             [{"Index": 1, "Scalar": 0.3, "ActuatorType": "Vibrate"}])

            # 游戏应收到 Ok 应答
            _, ok_body = await self._recv_until(ws, "Ok")
            self.assertIn(ok_body["Id"], (10, 11))
        finally:
            await ws.close()

    async def test_scalar_cmd_pipeline(self):
        """新版客户端直接发 ScalarCmd：全局索引 -> 通道 -> 设备。"""
        ws, _ = await self._game_connect()
        try:
            await ws.send(bp.serialize([("ScalarCmd", {
                "Id": 15, "DeviceIndex": 0,
                "Scalars": [{"Index": 1, "Scalar": 0.7, "ActuatorType": "Vibrate"}]})]))
            _, body = await self.mock.wait_received("ScalarCmd")
            self.assertEqual(body["Scalars"],
                             [{"Index": 1, "Scalar": 0.7, "ActuatorType": "Vibrate"}])
        finally:
            await ws.close()

    async def test_rotate_and_linear_pipeline(self):
        ws, _ = await self._game_connect()
        try:
            await ws.send(bp.serialize([("RotateCmd", {
                "Id": 20, "DeviceIndex": 0,
                "Rotations": [{"Index": 0, "Speed": 0.6, "Clockwise": False}]})]))
            _, rot = await self.mock.wait_received("RotateCmd")
            self.assertEqual(rot["Rotations"],
                             [{"Index": 0, "Speed": 0.6, "Clockwise": False}])

            await ws.send(bp.serialize([("LinearCmd", {
                "Id": 21, "DeviceIndex": 0,
                "Vectors": [{"Index": 0, "Duration": 400, "Position": 0.9}]})]))
            _, lin = await self.mock.wait_received("LinearCmd")
            self.assertEqual(lin["Vectors"],
                             [{"Index": 0, "Duration": 400, "Position": 0.9}])
        finally:
            await ws.close()

    async def test_osr6_virtual_device_and_mapping(self):
        """OSR6 模式：游戏看到虚拟六轴设备，六轴指令经映射到真实执行器。"""
        profile = self.service.profile
        profile.virtual_mode = "osr6"
        profile.channels["L0"].target = "Vibrate"
        profile.channels["L0"].motor = 0
        profile.channels["R0"].target = "Rotate"
        profile.channels["R0"].motor = 0
        profile.channels["R0"].midpoint = True
        ws, _ = await self._game_connect()
        try:
            await ws.send(bp.serialize([("RequestDeviceList", {"Id": 2})]))
            _, dev_list = await self._recv_until(ws, "DeviceList")
            devs = dev_list["Devices"]
            self.assertEqual(len(devs), 1)
            self.assertEqual(devs[0]["DeviceName"], "GTPB OSR6")
            msgs = devs[0]["DeviceMessages"]
            # 第 7 次实验布局：ScalarCmd + LinearCmd[Position] + RotateCmd
            # （正常工作参考实现的声明：LinearCmd [Position]，TCode v0.3）
            self.assertEqual(len(msgs["ScalarCmd"]), 3)
            self.assertEqual(msgs["ScalarCmd"][0]["ActuatorType"], "Position")
            self.assertEqual(len(msgs["LinearCmd"]), 1)
            self.assertEqual(msgs["LinearCmd"][0]["ActuatorType"], "Position")
            self.assertEqual(msgs["LinearCmd"][0]["StepCount"], 9999)
            self.assertEqual(len(msgs["RotateCmd"]), 3)
            self.assertEqual(msgs["RotateCmd"][2]["FeatureDescriptor"], "R2")

            # 游戏 piston：LinearCmd[0](L0, Duration+Position) -> L0 通道
            await ws.send(bp.serialize([("LinearCmd", {
                "Id": 19, "DeviceIndex": 0,
                "Vectors": [{"Index": 0, "Duration": 300, "Position": 0.8}]})]))
            _, body = await self.mock.wait_received("ScalarCmd")
            self.assertEqual(body["Scalars"][0],
                             {"Index": 0, "Scalar": 0.8, "ActuatorType": "Oscillate"})

            # 游戏发 R0 值 0.8 -> 中点旋转: speed=|0.8-0.5|*2=0.6, 顺时针
            await ws.send(bp.serialize([("RotateCmd", {
                "Id": 21, "DeviceIndex": 0,
                "Rotations": [{"Index": 0, "Speed": 0.8, "Clockwise": True}]})]))
            _, rot = await self.mock.wait_received("RotateCmd")
            self.assertAlmostEqual(rot["Rotations"][0]["Speed"], 0.6, places=5)
            self.assertTrue(rot["Rotations"][0]["Clockwise"])

            # R2 -> 默认 Linear motor0（mock 有原生 LinearCmd）
            await ws.send(bp.serialize([("RotateCmd", {
                "Id": 22, "DeviceIndex": 0,
                "Rotations": [{"Index": 2, "Speed": 0.9, "Clockwise": True}]})]))
            _, lin = await self.mock.wait_received("LinearCmd")
            self.assertEqual(lin["Vectors"][0]["Position"], 0.9)
        finally:
            await ws.close()

    async def test_start_scanning_broadcasts_device_added(self):
        ws, _ = await self._game_connect()
        try:
            await ws.send(bp.serialize([("StartScanning", {"Id": 30})]))
            _, added = await self._recv_until(ws, "DeviceAdded", timeout=5)
            self.assertEqual(added["DeviceName"], "MockToy2")
            self.assertEqual(added["DeviceMessages"]["VibrateCmd"]["FeatureCount"], 1)
            _, finished = await self._recv_until(ws, "ScannerFinished", timeout=5)
            self.assertEqual(finished, {})
        finally:
            await ws.close()

    async def test_emergency_stop(self):
        ws, _ = await self._game_connect()
        try:
            self.service.engage_estop("test")
            # 急停应向后端发送 StopAllDevices
            await self.mock.wait_received("StopAllDevices")
            self.mock.received.clear()

            # 急停期间指令被拦截：游戏收到 Ok，但后端不收到任何动作指令
            await ws.send(bp.serialize([("VibrateCmd", {
                "Id": 40, "DeviceIndex": 0,
                "Speeds": [{"Index": 0, "Speed": 0.5}]})]))
            await self._recv_until(ws, "Ok")
            await asyncio.sleep(0.3)
            self.assertFalse(
                any(t in ("VibrateCmd", "RotateCmd", "LinearCmd", "ScalarCmd")
                    for t, _ in self.mock.received),
                "急停期间不应有动作指令到达后端")

            # 释放后恢复（Rotate 走设备原生命令）
            self.service.release_estop()
            await ws.send(bp.serialize([("RotateCmd", {
                "Id": 41, "DeviceIndex": 0,
                "Rotations": [{"Index": 0, "Speed": 0.5, "Clockwise": True}]})]))
            await self.mock.wait_received("RotateCmd")
        finally:
            await ws.close()

    async def test_backend_disconnect_stops_devices(self):
        ws, _ = await self._game_connect()
        try:
            self.assertEqual(len(self.service.backend.devices), 1)
            await self.mock.stop()  # 后端"崩溃"
            # 服务应感知断开（连接状态翻转）
            for _ in range(200):
                if not self.service.backend.connected:
                    break
                await asyncio.sleep(0.05)
            self.assertFalse(self.service.backend.connected)
        finally:
            await ws.close()


if __name__ == "__main__":
    unittest.main()
