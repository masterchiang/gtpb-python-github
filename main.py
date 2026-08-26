"""GameToyProtocolBridge (GTPB) - Python 版入口。

用法:
  python main.py                                    # GUI 模式
  python main.py --headless                         # 无界面模式
  python main.py --profile profiles/my.json         # 指定 Profile
  python main.py --headless --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346

链路:
  Game -> GTPB (ws://127.0.0.1:12345, Buttplug v3) -> 解析/映射/转换 -> Intiface Central -> 玩具

文件结构：
  - configsetting.ini        软件依赖（出厂配置），随 EXE 根目录发布，运行时只读
                              → 包含默认监听/端口/日志路径/枚举表/默认通道表
  - profiles/*.json          用户个性化文件（GUI 唯一可加载/保存/另存为的对象）
                              → 包含 name, game, virtualMode, bindings, mapping, proxy(连接设置)
  - .gtpb_settings           内部状态：用户上次加载的 Profile 路径
  - gtpb.log                 单文件滚动日志（10KB 阈值）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# 路径处理：兼容开发模式与 PyInstaller 打包后的 frozen 模式
if getattr(sys, 'frozen', False):
    # PyInstaller 单文件模式：
    #   sys.executable  -> EXE 自身绝对路径
    #   sys._MEIPASS    -> 运行时临时解压目录（包含 datas 打包的资源，主要是 configsetting.ini）
    # BASE_DIR    = 用户数据目录（EXE 所在目录，可写）
    # _BUNDLE_DIR = 只读资源目录（打包进去的 configsetting.ini）
    BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = BASE_DIR

sys.path.insert(0, _BUNDLE_DIR)

from gtpb.config import AppConfig, Profile, SettingsLoader, SETTINGS_INI_FILENAME
from gtpb.i18n import (
    t, get_language, set_language, load_user_language, save_user_language,
    backend_port,
)
from gtpb.logs import LogManager
from gtpb.proxy import BridgeService

# 用户上次加载的 Profile 路径
USER_SETTINGS_FILE = os.path.join(BASE_DIR, ".gtpb_settings")


def parse_args():
    parser = argparse.ArgumentParser(description="GameToyProtocolBridge (GTPB) - 游戏玩具协议桥")
    parser.add_argument("--headless", action="store_true", help="无界面模式")
    parser.add_argument("--profile", default=None, help="Profile 路径（缺省读 .gtpb_settings 的 lastProfile，"
                                                       "再缺省用 BASE_DIR/profiles/default.json）")
    parser.add_argument("--listen", default=None, help="监听地址（覆盖，仅本次启动）")
    parser.add_argument("--ws-port", type=int, default=None, help="WebSocket 监听端口（覆盖）")
    parser.add_argument("--tcp-port", type=int, default=None, help="TCP 监听端口（覆盖）")
    parser.add_argument("--backend", default=None, help="后端 Intiface 地址 ws://host:port（覆盖）")
    return parser.parse_args()


# ---------------------------------------------------------------- 工具

def _load_user_settings() -> dict:
    if not os.path.isfile(USER_SETTINGS_FILE):
        return {}
    try:
        with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_user_settings(settings: dict):
    try:
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _resolve_settings_ini() -> str:
    p = os.path.join(BASE_DIR, SETTINGS_INI_FILENAME)
    if os.path.isfile(p):
        return p
    p2 = os.path.join(_BUNDLE_DIR, SETTINGS_INI_FILENAME)
    return p2 if os.path.isfile(p2) else p


# ---------------------------------------------------------------- 启动

def load_settings_and_profile(args) -> (AppConfig, Profile, str, SettingsLoader):
    """加载软件依赖（configsetting.ini）+ 用户 Profile；构造内部 AppConfig。

    返回 (config, profile, profile_path, settings)：
      - config：内部运行时配置（合并自 INI 出厂值 + Profile 的 proxy 段）
      - profile：用户文件对象
      - profile_path：当前加载的 Profile 绝对路径
      - settings：SettingsLoader 实例
    """
    settings_ini_path = _resolve_settings_ini()
    settings = SettingsLoader(settings_ini_path)

    user_meta = _load_user_settings()

    # 1. 决定要打开的 Profile 路径
    if args.profile:
        profile_path = args.profile
    elif user_meta.get("lastProfile"):
        profile_path = user_meta["lastProfile"]
    else:
        profile_path = os.path.join(BASE_DIR, "profiles", "default.json")

    if not os.path.isabs(profile_path):
        profile_path = os.path.join(BASE_DIR, profile_path)

    # 2. 加载 Profile（缺失字段从 INI 派生）
    profile = Profile.load(profile_path, settings=settings)

    # 3. 用 Profile 的 proxy + INI 的 logging/safety 派生 AppConfig
    config = AppConfig.load(None, settings=settings)
    config.proxy.listen_address = profile.listen_address
    config.proxy.ws_port = profile.ws_port
    config.proxy.tcp_port = profile.tcp_port
    config.proxy.backend_url = profile.backend_url
    config.profile_path = profile_path

    # 4. 相对路径锚定到 BASE_DIR
    if not os.path.isabs(config.logging.dir):
        config.logging.dir = os.path.join(BASE_DIR, config.logging.dir)

    # 5. 命令行参数覆盖（仅本次启动生效，不写回 Profile）
    if args.listen:
        config.proxy.listen_address = args.listen
    if args.ws_port:
        config.proxy.ws_port = args.ws_port
    if args.tcp_port:
        config.proxy.tcp_port = args.tcp_port
    if args.backend:
        config.proxy.backend_url = args.backend

    return config, profile, profile_path, settings


def build_log_manager(config: AppConfig, callback=None, console: bool = False) -> LogManager:
    return LogManager(
        log_path=config.logging.dir,
        capture_raw=config.logging.capture_raw,
        level=config.logging.level,
        callback=callback,
        console=console,
    )


# ---------------------------------------------------------------- 端口冲突检查

def check_port_conflict(config: AppConfig):
    """检查游戏端 ws_port 与 Intiface 后端端口是否相同——必须不同。

    返回 (has_conflict: bool, ws_port: int, backend_port: int | None)。
    不抛异常；调用方决定如何提示用户。
    """
    ws_port = int(config.proxy.ws_port)
    bp = backend_port(config.proxy.backend_url)
    if bp is None:
        return False, ws_port, None
    return ws_port == int(bp), ws_port, int(bp)


# ---------------------------------------------------------------- 模式

def run_headless(config: AppConfig, profile: Profile):
    log = build_log_manager(config, console=True)
    log.sys_info(t("log_start_headless"))
    log.sys_info(t("log_log_file", path=log.log_path))
    log.sys_info(t("log_language_set", lang=get_language()))
    has_conflict, ws_p, bp = check_port_conflict(config)
    if has_conflict:
        log.sys_error(
            f"!!! 端口冲突：游戏端 WebSocket {ws_p} == Intiface 后端 {bp}。"
            f"GTPB 不会启动。请修改其中之一。")
        log.close()
        return
    service = BridgeService(config, profile, console=True, log_path=log.log_path)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(service.start())
        loop.run_forever()
    except KeyboardInterrupt:
        log.sys_info(t("log_sigint"))
    finally:
        try:
            loop.run_until_complete(service.stop())
        except Exception:
            pass
        loop.close()
        log.close()


def main():
    args = parse_args()
    config, profile, profile_path, settings = load_settings_and_profile(args)

    # 加载用户上次的语言（缺省按系统语言）
    load_user_language(USER_SETTINGS_FILE)

    # 端口冲突检查（写一次到日志——headless 模式可见；GUI 由 GUI 自己弹窗）
    has_conflict, ws_p, bp = check_port_conflict(config)
    if has_conflict:
        # 显式写一行——main() 还没建 log，先用 stderr
        import sys
        print(
            f"[GTPB][警告] 端口冲突：游戏端 WebSocket {ws_p} == Intiface 后端 {bp}，请修改其中之一！",
            file=sys.stderr)

    # 记录当前 Profile 路径到 .gtpb_settings（GUI 加载/另存为会更新它）
    user_meta = _load_user_settings()
    if user_meta.get("lastProfile") != profile_path:
        user_meta["lastProfile"] = profile_path
        _save_user_settings(user_meta)

    if args.headless:
        run_headless(config, profile)
    else:
        early_log = build_log_manager(config, console=False)
        early_log.sys_info(t("log_start_gui"))
        early_log.sys_info(t("log_log_file", path=early_log.log_path))
        early_log.sys_info(t("log_profile_path", path=profile_path))
        early_log.sys_info(t("log_language_set", lang=get_language()))
        if has_conflict:
            early_log.sys_error(
                f"!!! 端口冲突：游戏端 WebSocket {ws_p} == Intiface 后端 {bp}。"
                f"GTPB 不会启动。请修改其中之一（GUI 顶部的菜单「帮助 → 使用说明」有详细说明）。")
        from gtpb.gui import run_gui
        run_gui(config, profile, profile_path=profile_path,
                log_path=early_log.log_path, settings=settings)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        err_msg = f"GTPB 启动失败:\n\n{e}\n\n{traceback.format_exc()}"
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, err_msg, "GTPB Error", 0x10)
        except Exception:
            try:
                with open(os.path.join(BASE_DIR, "crash.log"), "w", encoding="utf-8") as f:
                    f.write(err_msg)
            except Exception:
                pass
        sys.exit(1)
