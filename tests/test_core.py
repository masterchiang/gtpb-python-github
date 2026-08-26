"""单元测试：映射引擎 / 转换引擎 / Buttplug v3 协议 / Profile。

运行: python -m unittest discover -s tests -v   （在 gtpb-python 目录下）
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gtpb.buttplug import parse_messages, serialize, server_info, virtual_device
from gtpb.config import Profile
from gtpb.mapping import MappingEngine
from gtpb.models import ActuatorInfo, ActuatorType, Channel, DeviceInfo, NormalizedCommand
from gtpb.transform import TransformEngine

DEVICES = {
    0: DeviceInfo(0, "TestToy", [
        ActuatorInfo(ActuatorType.VIBRATE, 0),
        ActuatorInfo(ActuatorType.VIBRATE, 1),
        ActuatorInfo(ActuatorType.ROTATE, 0),
        ActuatorInfo(ActuatorType.LINEAR, 0),
    ], raw={"DeviceMessages": {
        "VibrateCmd": {"FeatureCount": 2},
        "RotateCmd": {"FeatureCount": 1},
        "LinearCmd": {"FeatureCount": 1},
    }}),
}


class TestMappingEngine(unittest.TestCase):

    def setUp(self):
        self.profile = Profile.default()
        self.engine = MappingEngine(self.profile)

    def test_scale(self):
        self.profile.channels["L0"].scale = 0.5
        cmd = self.engine.apply(Channel.L0, 1.0)
        self.assertAlmostEqual(cmd.value, 0.5)

    def test_invert(self):
        self.profile.channels["L0"].invert = True
        cmd = self.engine.apply(Channel.L0, 0.2)
        self.assertAlmostEqual(cmd.value, 0.8)

    def test_input_clamped(self):
        cmd = self.engine.apply(Channel.L0, 1.5)
        self.assertAlmostEqual(cmd.value, 1.0)
        cmd = self.engine.apply(Channel.L0, -0.5)
        self.assertAlmostEqual(cmd.value, 0.0)

    def test_deadzone(self):
        self.profile.channels["L0"].deadzone = 0.2
        cmd = self.engine.apply(Channel.L0, 0.1)
        self.assertAlmostEqual(cmd.value, 0.0)
        cmd = self.engine.apply(Channel.L0, 0.6)
        self.assertAlmostEqual(cmd.value, 0.5)

    def test_output_range(self):
        """MFP Output Range: Lerp(min, max, v)。"""
        self.profile.channels["L0"].min = 0.2
        self.profile.channels["L0"].max = 0.8
        cmd = self.engine.apply(Channel.L0, 1.0)
        self.assertAlmostEqual(cmd.value, 0.8)
        cmd = self.engine.apply(Channel.L0, 0.0)
        self.assertAlmostEqual(cmd.value, 0.2)
        cmd = self.engine.apply(Channel.L0, 0.5)
        self.assertAlmostEqual(cmd.value, 0.5)

    def test_midpoint_rotate(self):
        """MFP 中点旋转约定：0.5=停止，偏离越多越快，方向由中点决定。"""
        m = self.profile.channels["R0"]
        m.target = "Rotate"
        m.motor = 0
        m.midpoint = True
        cmd = self.engine.apply(Channel.R0, 0.5)
        self.assertAlmostEqual(cmd.value, 0.0)
        self.assertFalse(cmd.meta["Clockwise"])
        cmd = self.engine.apply(Channel.R0, 0.75)
        self.assertAlmostEqual(cmd.value, 0.5)
        self.assertTrue(cmd.meta["Clockwise"])
        cmd = self.engine.apply(Channel.R0, 0.25)
        self.assertAlmostEqual(cmd.value, 0.5)
        self.assertFalse(cmd.meta["Clockwise"])
        # invert 翻转方向
        m.invert = True
        cmd = self.engine.apply(Channel.R0, 0.75)
        self.assertAlmostEqual(cmd.value, 0.5)
        self.assertFalse(cmd.meta["Clockwise"])

    def test_disabled_channel(self):
        self.profile.channels["L0"].enabled = False
        self.assertIsNone(self.engine.apply(Channel.L0, 1.0))

    def test_retarget(self):
        # L0 默认 -> Vibrate；改为 Rotate 后 target 改变
        self.profile.channels["L0"].target = "Rotate"
        cmd = self.engine.apply(Channel.L0, 0.7)
        self.assertEqual(cmd.target, ActuatorType.ROTATE)


class TestTransformEngine(unittest.TestCase):

    def setUp(self):
        self.engine = TransformEngine(lambda: DEVICES)

    def test_vibrate_grouping(self):
        cmds = [
            NormalizedCommand(Channel.L0, 0.8, 0.8, ActuatorType.VIBRATE, 0),
            NormalizedCommand(Channel.L1, 0.4, 0.4, ActuatorType.VIBRATE, 1),
        ]
        messages, skipped = self.engine.build_messages(cmds)
        self.assertEqual(len(messages), 1)
        msg_type, body = messages[0]
        self.assertEqual(msg_type, "VibrateCmd")
        self.assertEqual(body["DeviceIndex"], 0)
        self.assertEqual(body["Speeds"],
                         [{"Index": 0, "Speed": 0.8}, {"Index": 1, "Speed": 0.4}])
        self.assertEqual(skipped, set())

    def test_rotate_with_clockwise(self):
        cmds = [NormalizedCommand(Channel.R0, 0.5, 0.5, ActuatorType.ROTATE, 0,
                                  meta={"Clockwise": False})]
        messages, _ = self.engine.build_messages(cmds)
        msg_type, body = messages[0]
        self.assertEqual(msg_type, "RotateCmd")
        self.assertEqual(body["Rotations"][0]["Clockwise"], False)

    def test_linear_duration_passthrough(self):
        cmds = [NormalizedCommand(Channel.R2, 0.9, 0.9, ActuatorType.LINEAR, 0,
                                  meta={"Duration": 500})]
        messages, _ = self.engine.build_messages(cmds)
        msg_type, body = messages[0]
        self.assertEqual(msg_type, "LinearCmd")
        self.assertEqual(body["Vectors"][0], {"Index": 0, "Duration": 500, "Position": 0.9})

    def test_unsupported_target_skipped(self):
        engine = TransformEngine(lambda: {0: DeviceInfo(0, "VibeOnly", [
            ActuatorInfo(ActuatorType.VIBRATE, 0)],
            raw={"DeviceMessages": {"VibrateCmd": {"FeatureCount": 1}}})})
        cmds = [NormalizedCommand(Channel.R0, 0.5, 0.5, ActuatorType.ROTATE, 0)]
        messages, skipped = engine.build_messages(cmds)
        self.assertEqual(messages, [])
        self.assertEqual(skipped, {"Rotate"})


class TestButtplugV3(unittest.TestCase):

    def test_single_serialization(self):
        text = serialize([server_info(1)])
        # 一次 json.loads 即得到 dict（若发生二次序列化，这里会是 str）
        import json
        data = json.loads(text)
        self.assertIsInstance(data, list)
        self.assertIn("ServerInfo", data[0])
        info = data[0]["ServerInfo"]
        self.assertIsInstance(info, dict)
        self.assertEqual(info["Id"], 1)
        self.assertEqual(info["MessageVersion"], 3)
        self.assertNotIn("MessageType", info)  # v3：消息类型是键，不是字段

    def test_parse_array_and_single_object(self):
        self.assertEqual(parse_messages('[{"Ok":{"Id":2}}]'), [("Ok", {"Id": 2})])
        self.assertEqual(parse_messages('{"Ping":{"Id":3}}'), [("Ping", {"Id": 3})])

    def test_parse_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_messages("not-json")

    def test_virtual_device_passes_through(self):
        """虚拟设备 = 原样透传后端描述，不虚构能力（透传实验结论）。"""
        raw = {
            "DeviceMessages": {
                "ScalarCmd": [{"ActuatorType": "Vibrate", "FeatureDescriptor": "", "StepCount": 100}],
                "RotateCmd": [{"ActuatorType": "Rotate", "FeatureDescriptor": "", "StepCount": 100}],
            },
            "DeviceMessageTimingGap": 50,
        }
        dev = DeviceInfo(0, "X", [
            ActuatorInfo(ActuatorType.VIBRATE, 0, scalar_index=0, label="Vibrate"),
            ActuatorInfo(ActuatorType.ROTATE, 0, scalar_index=1, label="Rotate"),
        ], raw=raw)
        v = virtual_device(dev)
        self.assertEqual(v["DeviceMessages"]["ScalarCmd"], raw["DeviceMessages"]["ScalarCmd"])
        self.assertEqual(v["DeviceMessageTimingGap"], 50)
        self.assertIn("StopDeviceCmd", v["DeviceMessages"])
        # 后端没有 VibrateCmd/LinearCmd，绝不虚构
        self.assertNotIn("VibrateCmd", v["DeviceMessages"])
        self.assertNotIn("LinearCmd", v["DeviceMessages"])


class TestProfile(unittest.TestCase):

    def test_default_has_six_channels(self):
        profile = Profile.default()
        for name in ("L0", "L1", "L2", "R0", "R1", "R2"):
            self.assertIn(name, profile.channels)

    def test_load_default_file(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "profiles", "default.json")
        if os.path.isfile(path):
            profile = Profile.load(path)
            self.assertEqual(profile.name, "Default")
            self.assertAlmostEqual(profile.channels["L0"].scale, 1.0)

    def test_load_missing_returns_default(self):
        profile = Profile.load("Z:/not/exist.json")
        self.assertEqual(profile.name, "Default")


if __name__ == "__main__":
    unittest.main()
