"""应用配置与 Profile（JSON）+ 软件出厂设置（INI）。"""

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from .models import CHANNELS

# 软件出厂配置文件名（dependency file，发布时打包进 EXE，运行时只读）
SETTINGS_INI_FILENAME = "configsetting.ini"


# ---------------------------------------------------------------- 软件出厂设置

class SettingsLoader:
    """读取 configsetting.ini（软件依赖），为 AppConfig / Profile 提供出厂默认值。

    设计原则：
      - INI 不可被用户编辑（不暴露在 GUI 的"加载"对话框里），但代码中可被覆写
        （用户修改 config.json 后启动，AppConfig.load 优先用 JSON，缺失字段才回落到此处）。
      - 找不到 INI 时静默回退到硬编码 fallback，保证软件在打包出错时仍能启动。
    """

    # 硬编码 fallback（与 configsetting.ini 内容完全一致；打包出错时兜底）
    _FALLBACK = {
        "proxy": {
            "listenAddress": "127.0.0.1",
            "wsPort": 12345,
            "tcpPort": 0,
            "backendUrl": "ws://127.0.0.1:12346",  # 本机硬约束
        },
        "logging": {
            "dir": "gtpb.log",
            "captureRaw": True,
            "level": "INFO",
        },
        "safety": {"commandMinIntervalMs": 5},
        "paths": {"defaultProfile": "profiles/default.json"},
        "profile": {"virtualMode": "passthrough"},
        "enum": {
            "validTargets": ("Vibrate", "Rotate", "Linear"),
            "virtualModes": ("passthrough", "osr6"),
            "defaultChannels": [
                ("L0", "Vibrate", 0), ("L1", "Vibrate", 1), ("L2", "Vibrate", 2),
                ("R0", "Rotate", 0), ("R1", "Rotate", 1), ("R2", "Linear", 0),
            ],
            "defaultBindings": [
                ("Vibrate:0:0", "L0"), ("Vibrate:0:1", "L1"), ("Vibrate:0:2", "L2"),
                ("Rotate:0:0", "R0"), ("Rotate:0:1", "R1"), ("Linear:0:0", "R2"),
            ],
        },
    }

    def __init__(self, ini_path: Optional[str] = None):
        self._raw: Dict[str, Dict[str, str]] = {}
        if ini_path and os.path.isfile(ini_path):
            try:
                cp = configparser.ConfigParser()
                cp.read(ini_path, encoding="utf-8")
                for section in cp.sections():
                    self._raw[section] = {k: v for k, v in cp.items(section)}
            except Exception:
                self._raw = {}

    # ---------- 取值工具 ----------
    def _get(self, section: str, key: str, default: str = "") -> str:
        return self._raw.get(section, {}).get(key, default)

    # ---------- proxy ----------
    def default_listen_address(self) -> str:
        return self._get("proxy", "listenAddress",
                         self._FALLBACK["proxy"]["listenAddress"]) or self._FALLBACK["proxy"]["listenAddress"]

    def default_ws_port(self) -> int:
        try:
            return int(self._get("proxy", "wsPort", str(self._FALLBACK["proxy"]["wsPort"])))
        except (TypeError, ValueError):
            return self._FALLBACK["proxy"]["wsPort"]

    def default_tcp_port(self) -> int:
        try:
            return int(self._get("proxy", "tcpPort", str(self._FALLBACK["proxy"]["tcpPort"])))
        except (TypeError, ValueError):
            return self._FALLBACK["proxy"]["tcpPort"]

    def default_backend_url(self) -> str:
        return self._get("proxy", "backendUrl", self._FALLBACK["proxy"]["backendUrl"]) \
            or self._FALLBACK["proxy"]["backendUrl"]

    # ---------- logging ----------
    def default_log_dir(self) -> str:
        return self._get("logging", "dir", self._FALLBACK["logging"]["dir"]) \
            or self._FALLBACK["logging"]["dir"]

    def default_capture_raw(self) -> bool:
        v = self._get("logging", "captureRaw", str(self._FALLBACK["logging"]["captureRaw"]))
        return v.strip().lower() in ("1", "true", "yes", "on")

    def default_log_level(self) -> str:
        return self._get("logging", "level", self._FALLBACK["logging"]["level"]) \
            or self._FALLBACK["logging"]["level"]

    # ---------- safety ----------
    def default_command_min_interval_ms(self) -> int:
        try:
            return int(self._get("safety", "commandMinIntervalMs",
                                 str(self._FALLBACK["safety"]["commandMinIntervalMs"])))
        except (TypeError, ValueError):
            return self._FALLBACK["safety"]["commandMinIntervalMs"]

    # ---------- paths ----------
    def default_profile_path(self) -> str:
        return self._get("paths", "defaultProfile",
                         self._FALLBACK["paths"]["defaultProfile"]) \
            or self._FALLBACK["paths"]["defaultProfile"]

    # ---------- profile ----------
    def default_virtual_mode(self) -> str:
        v = self._get("profile", "virtualMode", self._FALLBACK["profile"]["virtualMode"])
        return v if v in self.virtual_modes() else self._FALLBACK["profile"]["virtualMode"]

    # ---------- enum ----------
    def valid_targets(self) -> tuple:
        v = self._get("enum", "validTargets", "")
        if v:
            return tuple(s.strip() for s in v.split(",") if s.strip())
        return self._FALLBACK["enum"]["validTargets"]

    def virtual_modes(self) -> tuple:
        v = self._get("enum", "virtualModes", "")
        if v:
            return tuple(s.strip() for s in v.split(",") if s.strip())
        return self._FALLBACK["enum"]["virtualModes"]

    def default_channels(self) -> Dict[str, tuple]:
        """返回 {通道名: (target, motor)} 字典。"""
        v = self._get("enum", "defaultChannels", "")
        result: Dict[str, tuple] = {}
        if v:
            for entry in v.split(","):
                parts = entry.strip().split(":")
                if len(parts) == 3:
                    name, target, motor = parts
                    try:
                        result[name] = (target, int(motor))
                    except ValueError:
                        continue
        if not result:
            for name, target, motor in self._FALLBACK["enum"]["defaultChannels"]:
                result[name] = (target, motor)
        return result

    def default_bindings(self) -> Dict[str, str]:
        """返回 {设备指令键: 通道名} 字典。"""
        v = self._get("enum", "defaultBindings", "")
        result: Dict[str, str] = {}
        if v:
            for entry in v.split(","):
                parts = entry.strip().split(":")
                if len(parts) == 4:
                    actuator, dev, motor, ch = parts
                    result[f"{actuator}:{dev}:{motor}"] = ch
        if not result:
            for key, ch in self._FALLBACK["enum"]["defaultBindings"]:
                result[key] = ch
        return result


# ---------------------------------------------------------------- 用户配置（JSON）

@dataclass
class ProxyConfig:
    listen_address: str = "127.0.0.1"
    ws_port: int = 12345                     # 游戏端 WebSocket 监听
    tcp_port: int = 0                        # 游戏端 TCP 监听（0 = 禁用）
    backend_url: str = "ws://127.0.0.1:12346"  # Intiface Central 默认地址


@dataclass
class LoggingConfig:
    # 单文件日志路径（相对 BASE_DIR 或绝对路径），由 main.py 在启动时锚定
    dir: str = "gtpb.log"
    capture_raw: bool = True
    level: str = "INFO"


@dataclass
class SafetyConfig:
    command_min_interval_ms: int = 5         # 指令合并最小间隔（低延迟优先）


@dataclass
class AppConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    profile_path: str = "profiles/default.json"

    @staticmethod
    def load(path: Optional[str], settings: Optional[SettingsLoader] = None) -> "AppConfig":
        """读取用户 config.json；缺失字段回落到 configsetting.ini 出厂值。"""
        if settings is None:
            settings = SettingsLoader()
        cfg = AppConfig()
        # 把出厂默认值预填进去，JSON 文件中的值会覆盖
        cfg.proxy.listen_address = settings.default_listen_address()
        cfg.proxy.ws_port = settings.default_ws_port()
        cfg.proxy.tcp_port = settings.default_tcp_port()
        cfg.proxy.backend_url = settings.default_backend_url()
        cfg.logging.dir = settings.default_log_dir()
        cfg.logging.capture_raw = settings.default_capture_raw()
        cfg.logging.level = settings.default_log_level()
        cfg.safety.command_min_interval_ms = settings.default_command_min_interval_ms()
        cfg.profile_path = settings.default_profile_path()

        if not path or not os.path.isfile(path):
            return cfg
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return cfg
        proxy = data.get("proxy", {}) or {}
        if "listenAddress" in proxy:
            cfg.proxy.listen_address = str(proxy["listenAddress"])
        if "wsPort" in proxy:
            try: cfg.proxy.ws_port = int(proxy["wsPort"])
            except (TypeError, ValueError): pass
        if "tcpPort" in proxy:
            try: cfg.proxy.tcp_port = int(proxy["tcpPort"])
            except (TypeError, ValueError): pass
        if "backendUrl" in proxy:
            cfg.proxy.backend_url = str(proxy["backendUrl"])
        logging_ = data.get("logging", {}) or {}
        if "dir" in logging_:
            cfg.logging.dir = str(logging_["dir"])
        if "captureRaw" in logging_:
            cfg.logging.capture_raw = bool(logging_["captureRaw"])
        if "level" in logging_:
            cfg.logging.level = str(logging_["level"])
        safety = data.get("safety", {}) or {}
        if "commandMinIntervalMs" in safety:
            try: cfg.safety.command_min_interval_ms = int(safety["commandMinIntervalMs"])
            except (TypeError, ValueError): pass
        if "profilePath" in data:
            cfg.profile_path = str(data["profilePath"])
        return cfg

    def save(self, path: str):
        data = {
            "proxy": {
                "listenAddress": self.proxy.listen_address,
                "wsPort": self.proxy.ws_port,
                "tcpPort": self.proxy.tcp_port,
                "backendUrl": self.proxy.backend_url,
            },
            "logging": {
                "dir": self.logging.dir,
                "captureRaw": self.logging.capture_raw,
                "level": self.logging.level,
            },
            "safety": {"commandMinIntervalMs": self.safety.command_min_interval_ms},
            "profilePath": self.profile_path,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 用户 Profile（JSON）

@dataclass
class ChannelMapping:
    """单通道映射（MFP 风格）：Deadzone -> Scale -> Invert -> Min/Max 输出范围 -> Clamp。

    midpoint=True 时（位置轴 -> 旋转速度，MFP 约定）：
    速度 = |值-0.5|*2（0.5=停止中点），方向（顺/逆时针）= 值 > 0.5。
    """

    enabled: bool = True
    target: str = "Vibrate"     # Vibrate / Rotate / Linear
    device_index: int = -1      # -1 = 自动选择
    motor: int = 0
    invert: bool = False
    scale: float = 1.0
    clamp: bool = True
    deadzone: float = 0.0
    min: float = 0.0            # 输出范围下限（MFP Output Range Minimum）
    max: float = 1.0            # 输出范围上限（MFP Output Range Maximum）
    midpoint: bool = False      # 位置轴 -> 旋转速度（0.5 中点约定）


def _default_channels(channels: Optional[Dict[str, tuple]] = None) -> Dict[str, ChannelMapping]:
    src = channels or {
        "L0": ("Vibrate", 0), "L1": ("Vibrate", 1), "L2": ("Vibrate", 2),
        "R0": ("Rotate", 0), "R1": ("Rotate", 1), "R2": ("Linear", 0),
    }
    return {name: ChannelMapping(target=target, motor=motor)
            for name, (target, motor) in src.items()}


def _default_bindings(bindings: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    if bindings is None:
        bindings = {
            "Vibrate:0:0": "L0", "Vibrate:0:1": "L1", "Vibrate:0:2": "L2",
            "Rotate:0:0": "R0", "Rotate:0:1": "R1", "Linear:0:0": "R2",
        }
    return dict(bindings)


@dataclass
class Profile:
    name: str = "Default"
    game_name: str = ""
    # 设备呈现模式：passthrough = 透传真实设备描述（默认，已验证兼容）；
    #              osr6 = 向游戏虚拟一台 OSR6 六轴设备（L0-L2 线性 + R0-R2 旋转）
    virtual_mode: str = "passthrough"
    bindings: Dict[str, str] = field(default_factory=_default_bindings)
    channels: Dict[str, ChannelMapping] = field(default_factory=_default_channels)
    # 连接设置（与 Profile 一起保存/加载：监听地址、端口、TCP 端口、后端 Intiface）
    listen_address: str = "127.0.0.1"
    ws_port: int = 12345
    tcp_port: int = 0
    backend_url: str = "ws://127.0.0.1:12346"

    @staticmethod
    def default() -> "Profile":
        return Profile()

    @staticmethod
    def load(path: Optional[str], settings: Optional[SettingsLoader] = None) -> "Profile":
        """读取用户 Profile JSON；缺失字段回落到 configsetting.ini 出厂值。"""
        if settings is None:
            settings = SettingsLoader()
        # 初始值用出厂默认
        profile = Profile(
            virtual_mode=settings.default_virtual_mode(),
            bindings=_default_bindings(settings.default_bindings()),
            channels=_default_channels(settings.default_channels()),
            listen_address=settings.default_listen_address(),
            ws_port=settings.default_ws_port(),
            tcp_port=settings.default_tcp_port(),
            backend_url=settings.default_backend_url(),
        )
        if not path or not os.path.isfile(path):
            return profile
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return profile
        profile.name = data.get("name", profile.name)
        game = data.get("game", {}) or {}
        profile.game_name = game.get("name", game.get("gameName", ""))
        mode = data.get("virtualMode", profile.virtual_mode)
        if mode in settings.virtual_modes():
            profile.virtual_mode = mode
        bindings = data.get("bindings", {}) or {}
        if isinstance(bindings, dict):
            profile.bindings.update({str(k): str(v) for k, v in bindings.items()})
        mapping = data.get("mapping", {}) or {}
        valid_targets = settings.valid_targets()
        if isinstance(mapping, dict):
            for ch_name, m in mapping.items():
                base = profile.channels.get(ch_name) or ChannelMapping()
                if isinstance(m, dict):
                    base.enabled = bool(m.get("enabled", base.enabled))
                    target = str(m.get("target", base.target))
                    if target in valid_targets:
                        base.target = target
                    base.device_index = int(m.get("deviceIndex", base.device_index))
                    base.motor = int(m.get("motor", base.motor))
                    base.invert = bool(m.get("invert", base.invert))
                    base.scale = float(m.get("scale", base.scale))
                    base.clamp = bool(m.get("clamp", base.clamp))
                    base.deadzone = float(m.get("deadzone", base.deadzone))
                    base.min = float(m.get("min", base.min))
                    base.max = float(m.get("max", base.max))
                    base.midpoint = bool(m.get("midpoint", base.midpoint))
                profile.channels[ch_name] = base
        # 连接设置：可选段（兼容老 Profile JSON 没有 proxy 段的情况）
        proxy = data.get("proxy", {}) or {}
        if isinstance(proxy, dict):
            if "listenAddress" in proxy:
                profile.listen_address = str(proxy["listenAddress"])
            if "wsPort" in proxy:
                try: profile.ws_port = int(proxy["wsPort"])
                except (TypeError, ValueError): pass
            if "tcpPort" in proxy:
                try: profile.tcp_port = int(proxy["tcpPort"])
                except (TypeError, ValueError): pass
            if "backendUrl" in proxy:
                profile.backend_url = str(proxy["backendUrl"])
        return profile

    def save(self, path: str):
        data = {
            "name": self.name,
            "game": {"name": self.game_name},
            "virtualMode": self.virtual_mode,
            "bindings": self.bindings,
            "mapping": {
                name: {
                    "enabled": m.enabled, "target": m.target,
                    "deviceIndex": m.device_index, "motor": m.motor,
                    "invert": m.invert, "scale": m.scale,
                    "clamp": m.clamp, "deadzone": m.deadzone,
                    "min": m.min, "max": m.max, "midpoint": m.midpoint,
                } for name, m in self.channels.items()
            },
            # 连接设置与 Profile 一起保存；用户切 Profile 自动切连接配置
            "proxy": {
                "listenAddress": self.listen_address,
                "wsPort": self.ws_port,
                "tcpPort": self.tcp_port,
                "backendUrl": self.backend_url,
            },
        }
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------------- 与 AppConfig 互转 ----------------

    def to_proxy_config(self) -> tuple:
        """返回 (listen_address, ws_port, tcp_port, backend_url)——供 GUI 写回 AppConfig。"""
        return self.listen_address, self.ws_port, self.tcp_port, self.backend_url

    def apply_proxy(self, listen_address: str, ws_port: int, tcp_port: int, backend_url: str):
        self.listen_address = str(listen_address)
        self.ws_port = int(ws_port)
        self.tcp_port = int(tcp_port)
        self.backend_url = str(backend_url)

    def summary_lines(self):
        lines = [f"Profile: {self.name}  (游戏: {self.game_name or '自动/任意'})"]
        lines.append(f"── 连接：{self.listen_address}:{self.ws_port} (TCP={self.tcp_port})  →  {self.backend_url}")
        lines.append("── 通道映射（通道 -> 设备功能）──")
        for ch in CHANNELS:
            m = self.channels.get(ch.value)
            if m is None:
                continue
            state = "" if m.enabled else "  [禁用]"
            dev = "自动" if m.device_index < 0 else f"设备{m.device_index}"
            lines.append(
                f"  {ch.value} -> {m.target}[电机{m.motor}] @{dev}  "
                f"scale={m.scale}  invert={'开' if m.invert else '关'}  "
                f"deadzone={m.deadzone}  clamp={'开' if m.clamp else '关'}{state}")
        lines.append("── 游戏电机绑定（设备:类型:电机 -> 通道）──")
        for key, value in sorted(self.bindings.items()):
            lines.append(f"  {key} -> {value}")
        return lines

