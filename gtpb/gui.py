"""GUI（tkinter）：连接设置 + Profile（加载/保存/另存为）+ 启动/停止 + 急停 + 日志面板 + 语言/帮助菜单。

文件语义（与 main.py / config.py 保持一致）：
  - configsetting.ini        软件依赖（出厂配置），随 EXE 根目录发布，运行时只读
  - profiles/*.json          用户个性化文件（GUI 唯一可加载/保存的对象）
  - .gtpb_settings           内部状态：用户上次加载的 Profile 路径 + 语言
  - gtpb.log                 单文件滚动日志

连接设置在 Profile 里——切 Profile 自动切连接配置，保存 Profile 自动保存连接设置。

i18n：所有用户可见字符串走 gtpb.i18n.t()；用户切语言后整个界面重新构建。
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import i18n
from .config import AppConfig, ChannelMapping, Profile, SettingsLoader
from .i18n import (
    t, set_language, get_language, available_languages,
    save_user_language, backend_port,
)
from .models import CHANNELS
from .proxy import BridgeService

# BASE_DIR：兼容 PyInstaller frozen 模式（EXE 所在目录）
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(BASE_DIR)

# OSR6 六轴语义（MFP DeviceSettings 默认轴表）
AXIS_LABELS = {
    "L0": "主行程", "L1": "前后", "L2": "左右",
    "R0": "扭转", "R1": "横滚", "R2": "俯仰",
}

# 软件版本号（显示在窗口标题）
APP_VERSION = "1.0.1"


class ToolTip:
    """悬停提示：绑定控件后，鼠标悬停延迟显示说明文本（切换语言时随界面重建）。"""

    _tip = None  # 全局唯一当前可见的提示窗口

    def __init__(self, widget, text, delay_ms=300):
        self.widget = widget
        self.text = text
        self._delay_ms = delay_ms
        self._after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _e=None):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
        self._after_id = self.widget.after(self._delay_ms, self._show)

    def _on_leave(self, _e=None):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if ToolTip._tip is not None:
            try:
                ToolTip._tip.destroy()
            except Exception:
                pass
            ToolTip._tip = None

    def _show(self):
        self._after_id = None
        self._on_leave()
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.attributes("-topmost", True)
            lbl = tk.Label(tip, text=self.text, justify="left",
                           background="#ffffe0", foreground="#212121",
                           relief="solid", borderwidth=1, padx=8, pady=5,
                           wraplength=420, font=("Microsoft YaHei", 9))
            lbl.pack()
            ToolTip._tip = tip
        except tk.TclError:
            pass  # 控件已销毁

    @classmethod
    def destroy_all(cls):
        """销毁残留提示窗口（切换语言重建界面时调用）。"""
        if cls._tip is not None:
            try:
                cls._tip.destroy()
            except Exception:
                pass
            cls._tip = None


class BridgeThread:
    """在独立线程 + 独立事件循环中运行 BridgeService（GUI 线程安全）。"""

    def __init__(self, config: AppConfig, profile: Profile, on_log, log_path: str = None):
        self._config = config
        self._profile = profile
        self._on_log = on_log
        self._log_path = log_path
        self.service: BridgeService = None
        self.loop = None
        self.start_error = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def start(self):
        self._thread.start()

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        service = BridgeService(
            self._config, self._profile,
            log_callback=self._on_log,
            log_path=self._log_path,
        )
        self.service = service
        try:
            loop.run_until_complete(service.start())
            self.start_error = None
            loop.run_until_complete(service.wait_stopped())
        except Exception as e:
            self.start_error = str(e)
            self._on_log("system", "ERROR", f"桥接服务异常: {e}")
        finally:
            try:
                loop.run_until_complete(service.stop())
            except Exception:
                pass
            loop.close()
            self.service = None
            self.loop = None
            self._on_log("system", "INFO", "桥接服务线程已退出")

    def apply_profile(self, profile):
        if self.loop is not None and self.service is not None:
            self.loop.call_soon_threadsafe(self.service.apply_profile, profile)

    def stop(self):
        if self.loop is not None and self.service is not None:
            self.loop.call_soon_threadsafe(self.service.request_stop)

    def engage_estop(self):
        if self.loop is not None and self.service is not None:
            self.loop.call_soon_threadsafe(self.service.engage_estop)

    def release_estop(self):
        if self.loop is not None and self.service is not None:
            self.loop.call_soon_threadsafe(self.service.release_estop)

    def channel_levels(self) -> dict:
        """读取各通道当前电平（跨线程读字典，供柱状图轮询）。"""
        if self.service is not None:
            try:
                return self.service.channel_levels()
            except Exception:
                pass
        return {}


class GtpbGui:

    POLL_LOG_MS = 120
    POLL_STATUS_MS = 1000
    POLL_METER_MS = 30

    def __init__(self, config: AppConfig, profile: Profile, profile_path: str = None,
                 log_path: str = None, settings: SettingsLoader = None):
        self._settings = settings or SettingsLoader()
        self._initial_config = config
        self._initial_profile = profile
        self._profile_path = profile_path or os.path.join(BASE_DIR, "profiles", "default.json")
        self._log_path = log_path or os.path.join(BASE_DIR, "gtpb.log")
        self._bridge: BridgeThread = None
        self._estop_on = False
        self._last_dev_text = ""
        self._log_q = queue.Queue()
        self.root = tk.Tk()
        self._rebuild_ui()
        self._check_port_conflict_on_startup()
        self.root.after(self.POLL_LOG_MS, self._poll_logs)
        self.root.after(self.POLL_STATUS_MS, self._poll_status)
        self.root.after(self.POLL_METER_MS, self._poll_meter)

    # ---------------- 重建 UI（切语言时用） ----------------

    def _rebuild_ui(self):
        """销毁并重新构建整个界面（用于切换语言）。"""
        # 停掉旧 bridge？不切语言时不应该运行；但保险起见先停
        # 实际上切语言时不应该在运行；GUI 状态保留，bridge 不重建
        ToolTip.destroy_all()
        for w in self.root.winfo_children():
            w.destroy()
        self.root.title(f"{t('app_title')}  V{APP_VERSION}")
        self.root.geometry("1080x760")
        self._build_menu()
        self._build_ui()
        self._map_hint_var = None  # type: ignore  # 重新构建后失效
        # 切语言后 mapping rows 失效，需要在 _build_ui 内重新初始化

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        # 语言菜单
        lang_menu = tk.Menu(menubar, tearoff=0)
        for code, display in available_languages().items():
            lang_menu.add_command(
                label=f"{display} ({code})",
                command=lambda c=code: self._on_change_language(c))
        menubar.add_cascade(label=t("menu_language"), menu=lang_menu)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=t("menu_usage"), command=self._on_show_usage)
        menubar.add_cascade(label=t("menu_help"), menu=help_menu)

        self.root.config(menu=menubar)

    def _on_change_language(self, lang: str):
        if not set_language(lang):
            return
        # 持久化
        try:
            save_user_language(os.path.join(BASE_DIR, ".gtpb_settings"), lang)
        except Exception:
            pass
        # 重建 UI
        self._rebuild_ui()

    def _on_show_usage(self):
        """弹出使用说明窗口。"""
        win = tk.Toplevel(self.root)
        win.title(t("usage_title"))
        win.geometry("780x600")
        text = scrolledtext.ScrolledText(win, wrap="word", padx=12, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("1.0", t("usage_text"))
        text.config(state="disabled")
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=8)

    # ---------------- 端口冲突检查 ----------------

    def _check_port_conflict_on_startup(self):
        """启动时强警告端口冲突。"""
        ws_p = int(self._initial_config.proxy.ws_port)
        bp = backend_port(self._initial_config.proxy.backend_url)
        if bp is not None and ws_p == int(bp):
            messagebox.showwarning(
                t("msg_port_conflict_title"),
                t("msg_port_conflict_body", ws_port=ws_p, backend_port=bp))

    # ---------------- UI 构建 ----------------

    def _build_ui(self):
        # 连接设置（来自 Profile.proxy 段）
        top = ttk.LabelFrame(self.root, text=t("frame_connection"))
        top.pack(fill="x", padx=8, pady=6)

        self._v_listen = tk.StringVar(value=self._initial_profile.listen_address)
        self._v_ws = tk.StringVar(value=str(self._initial_profile.ws_port))
        self._v_tcp = tk.StringVar(value=str(self._initial_profile.tcp_port))
        self._v_backend = tk.StringVar(value=self._initial_profile.backend_url)

        fields = (
            (t("lbl_listen"), self._v_listen, 14, "tip_listen"),
            (t("lbl_ws_port"), self._v_ws, 8, "tip_ws_port"),
            (t("lbl_tcp_port"), self._v_tcp, 8, "tip_tcp_port"),
            (t("lbl_backend"), self._v_backend, 26, "tip_backend"),
        )
        for col, (label, var, width, tip_key) in enumerate(fields):
            lb = ttk.Label(top, text=label)
            lb.grid(row=0, column=col * 2, sticky="e", padx=4, pady=3)
            ent = ttk.Entry(top, textvariable=var, width=width)
            ent.grid(row=0, column=col * 2 + 1, padx=4)
            ToolTip(lb, t(tip_key))
            ToolTip(ent, t(tip_key))
        top.columnconfigure(7, weight=1)

        # Profile 操作栏
        prof_bar = ttk.Frame(self.root)
        prof_bar.pack(fill="x", padx=8, pady=2)
        ttk.Label(prof_bar, text=t("lbl_profile")).pack(side="left", padx=4)
        self._v_profile_path = tk.StringVar(value=self._profile_path)
        prof_entry = ttk.Entry(prof_bar, textvariable=self._v_profile_path, state="readonly", width=70)
        prof_entry.pack(side="left", padx=4, fill="x", expand=True)
        btn_load = ttk.Button(prof_bar, text=t("btn_load_profile"),
                              command=self._on_load_profile)
        btn_load.pack(side="left", padx=2)
        btn_save = ttk.Button(prof_bar, text=t("btn_save_profile"),
                              command=self._on_save_profile)
        btn_save.pack(side="left", padx=2)
        btn_save_as = ttk.Button(prof_bar, text=t("btn_save_profile_as"),
                                 command=self._on_save_profile_as)
        btn_save_as.pack(side="left", padx=2)
        ToolTip(btn_load, t("tip_load_profile"))
        ToolTip(btn_save, t("tip_save_profile"))
        ToolTip(btn_save_as, t("tip_save_as"))

        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", padx=8, pady=2)
        self._btn_start = ttk.Button(ctrl, text=t("btn_start"), command=self._on_start)
        self._btn_stop = ttk.Button(ctrl, text=t("btn_stop"), command=self._on_stop, state="disabled")
        self._btn_estop = tk.Button(
            ctrl, text=t("btn_estop"), bg="#c62828", fg="white",
            font=("Microsoft YaHei", 11, "bold"), width=16, command=self._on_estop)
        self._btn_start.pack(side="left", padx=4)
        self._btn_stop.pack(side="left", padx=4)
        self._btn_estop.pack(side="right", padx=4)
        ToolTip(self._btn_start, t("tip_start"))
        ToolTip(self._btn_stop, t("tip_stop"))
        ToolTip(self._btn_estop, t("tip_estop"))

        self._status_var = tk.StringVar(value=t("status_idle"))
        ttk.Label(self.root, textvariable=self._status_var).pack(anchor="w", padx=10, pady=2)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        self._tab_sys = scrolledtext.ScrolledText(nb, height=18, state="disabled")
        self._tab_game = scrolledtext.ScrolledText(nb, height=18, state="disabled")
        self._tab_dev = scrolledtext.ScrolledText(nb, height=18, state="disabled")
        self._tab_map = ttk.Frame(nb, padding=4)
        nb.add(self._tab_sys, text=t("tab_sys_log"))
        nb.add(self._tab_game, text=t("tab_game_rx_tx"))
        nb.add(self._tab_dev, text=t("tab_devices"))
        nb.add(self._tab_map, text=t("tab_mapping"))

        self._tab_sys.tag_config("WARNING", foreground="#e65100")
        self._tab_sys.tag_config("ERROR", foreground="#c62828")
        self._tab_game.tag_config("RX", foreground="#1565c0")
        self._tab_game.tag_config("TX", foreground="#2e7d32")

        self._build_mapping_editor(self._tab_map)

    # ---------------- 收集界面数据 → 内部状态 ----------------

    def _collect_profile_from_ui(self) -> Profile:
        p = Profile.default()
        base = self._initial_profile
        p.name = base.name
        p.game_name = base.game_name
        p.bindings = dict(base.bindings)
        p.virtual_mode = self._v_mode.get()
        p.listen_address = self._v_listen.get().strip() or "127.0.0.1"
        try:
            p.ws_port = int(self._v_ws.get())
        except ValueError:
            p.ws_port = 12345
        try:
            p.tcp_port = int(self._v_tcp.get() or 0)
        except ValueError:
            p.tcp_port = 0
        p.backend_url = self._v_backend.get().strip() or p.backend_url
        for ch_val, row in self._map_rows.items():
            m = p.channels.get(ch_val) or ChannelMapping()
            sel = row["actuator"].get()
            if sel == t("actuator_unmapped") or not sel:
                m.enabled = False
            else:
                mapped = next((i for i in self._actuator_items if i[0] == sel), None)
                if mapped is not None:
                    m.target, m.motor = mapped[1], mapped[2]
                else:
                    parts = sel.rsplit(" #", 1)
                    if len(parts) == 2 and parts[0] in ("Vibrate", "Rotate", "Linear"):
                        m.target = parts[0]
                        try:
                            m.motor = int(parts[1])
                        except ValueError:
                            pass
                m.enabled = True
            m.invert = bool(row["invert"].get())
            m.midpoint = bool(row["mid"].get())
            m.dedupe = bool(row["dedupe"].get())
            m.pulse_enabled = bool(row["pulse"].get())
            try:
                m.pulse_ms = int(row["pulse_ms"].get())
            except (ValueError, TypeError):
                pass
            try:
                m.delay_ms = int(row["delay"].get())
            except (ValueError, TypeError):
                pass
            for key, attr in (("scale", "scale"), ("min", "min"),
                              ("max", "max"), ("dz", "deadzone")):
                try:
                    setattr(m, attr, float(row[key].get()))
                except (ValueError, TypeError):
                    pass
            p.channels[ch_val] = m
        return p

    def _build_config_from_profile(self, p: Profile) -> AppConfig:
        cfg = AppConfig.load(None, settings=self._settings)
        cfg.proxy.listen_address = p.listen_address
        cfg.proxy.ws_port = p.ws_port
        cfg.proxy.tcp_port = p.tcp_port
        cfg.proxy.backend_url = p.backend_url
        if not os.path.isabs(cfg.logging.dir):
            cfg.logging.dir = os.path.join(BASE_DIR, cfg.logging.dir)
        cfg.profile_path = self._profile_path
        return cfg

    # ---------------- 启动/停止/急停 ----------------

    def _on_start(self):
        if self._bridge is not None and self._bridge.alive:
            return
        # 启动前再检查一次端口冲突
        profile = self._collect_profile_from_ui()
        config = self._build_config_from_profile(profile)
        ws_p = int(config.proxy.ws_port)
        bp = backend_port(config.proxy.backend_url)
        if bp is not None and ws_p == int(bp):
            messagebox.showwarning(
                t("msg_port_conflict_title"),
                t("msg_port_conflict_body", ws_port=ws_p, backend_port=bp))
            return
        self._initial_profile = profile
        self._initial_config = config
        self._bridge = BridgeThread(config, profile, self._log_q.put,
                                    log_path=self._log_path)
        self._bridge.start()
        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")

    def _on_stop(self):
        if self._bridge is not None:
            self._bridge.stop()
        self._btn_stop.config(state="disabled")

    def _on_estop(self):
        if self._bridge is None or not self._bridge.alive:
            return
        if not self._estop_on:
            self._bridge.engage_estop()
            self._estop_on = True
            self._btn_estop.config(text=t("btn_estop_engaged"), bg="#455a64")
        else:
            self._bridge.release_estop()
            self._estop_on = False
            self._btn_estop.config(text=t("btn_estop"), bg="#c62828")

    # ---------------- 轮询日志 ----------------

    def _poll_logs(self):
        try:
            while True:
                source, level, text = self._log_q.get_nowait()
                stamp = time.strftime("%H:%M:%S")
                if source == "game":
                    tag = level if level in ("RX", "TX") else None
                    self._append_text(self._tab_game, f"[{stamp}] [{level}] {text}", tag)
                else:
                    tag = level if level in ("WARNING", "ERROR") else None
                    self._append_text(self._tab_sys, f"[{stamp}] [{level}] {text}", tag)
        except queue.Empty:
            pass
        self.root.after(self.POLL_LOG_MS, self._poll_logs)

    # ---------------- 通道映射编辑器 ----------------

    def _build_mapping_editor(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 4))
        self._v_mode = tk.StringVar(
            value=getattr(self._initial_profile, "virtual_mode", "passthrough"))
        rb_passthrough = ttk.Radiobutton(top, text=t("mapping_passthrough"),
                                         variable=self._v_mode, value="passthrough")
        rb_passthrough.pack(side="left", padx=6)
        rb_osr6 = ttk.Radiobutton(top, text=t("mapping_osr6"), variable=self._v_mode,
                                  value="osr6")
        rb_osr6.pack(side="left", padx=6)
        ToolTip(rb_passthrough, t("tip_mode_passthrough"))
        ToolTip(rb_osr6, t("tip_mode_osr6"))
        ttk.Label(top, text=t("mapping_hint_edit"),
                  foreground="#546e7a").pack(side="right", padx=6)
        self._map_hint = tk.StringVar(value=t("mapping_hint_empty"))
        ttk.Label(parent, textvariable=self._map_hint,
                  foreground="#546e7a").pack(anchor="w", pady=(0, 4))

        headers = (t("col_channel"), t("col_enabled"), t("col_actuator"),
                   t("col_invert"), t("col_scale"), t("col_min"), t("col_max"),
                   t("col_midpoint"), t("col_deadzone"),
                   t("col_dedupe"), t("col_pulse"), t("col_pulse_ms"), t("col_delay_ms"))
        header_tips = ("tip_channel", "tip_enabled", "tip_actuator", "tip_invert",
                       "tip_scale", "tip_min", "tip_max", "tip_midpoint",
                       "tip_deadzone", "tip_dedupe", "tip_pulse", "tip_pulse_ms",
                       "tip_delay_ms")
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        for col, (text, tip_key) in enumerate(zip(headers, header_tips)):
            lb = ttk.Label(grid, text=text)
            lb.grid(row=0, column=col, padx=3, pady=2)
            ToolTip(lb, t(tip_key))

        self._map_rows = {}
        for row, ch in enumerate(CHANNELS, start=1):
            m = self._initial_profile.channels.get(ch.value) or ChannelMapping()
            ch_label = ttk.Label(grid, text=f"{ch.value} {AXIS_LABELS.get(ch.value, '')}")
            ch_label.grid(row=row, column=0, sticky="w", padx=3)
            ToolTip(ch_label, t("tip_channel"))
            v_enabled = tk.BooleanVar(value=m.enabled)
            v_actuator = tk.StringVar()
            v_invert = tk.BooleanVar(value=m.invert)
            v_scale = tk.StringVar(value=str(m.scale))
            v_min = tk.StringVar(value=str(m.min))
            v_max = tk.StringVar(value=str(m.max))
            v_mid = tk.BooleanVar(value=m.midpoint)
            v_dz = tk.StringVar(value=str(m.deadzone))
            v_dedupe = tk.BooleanVar(value=m.dedupe)
            v_pulse = tk.BooleanVar(value=m.pulse_enabled)
            v_pulse_ms = tk.StringVar(value=str(m.pulse_ms))
            v_delay = tk.StringVar(value=str(m.delay_ms))
            cb_enabled = ttk.Checkbutton(grid, variable=v_enabled)
            cb_enabled.grid(row=row, column=1)
            combo = ttk.Combobox(grid, textvariable=v_actuator, width=18, state="readonly")
            combo.grid(row=row, column=2, padx=3)
            cb_invert = ttk.Checkbutton(grid, variable=v_invert)
            cb_invert.grid(row=row, column=3)
            e_scale = ttk.Entry(grid, textvariable=v_scale, width=6)
            e_scale.grid(row=row, column=4, padx=3)
            e_min = ttk.Entry(grid, textvariable=v_min, width=5)
            e_min.grid(row=row, column=5, padx=3)
            e_max = ttk.Entry(grid, textvariable=v_max, width=5)
            e_max.grid(row=row, column=6, padx=3)
            cb_mid = ttk.Checkbutton(grid, variable=v_mid)
            cb_mid.grid(row=row, column=7)
            e_dz = ttk.Entry(grid, textvariable=v_dz, width=5)
            e_dz.grid(row=row, column=8, padx=3)
            cb_dedupe = ttk.Checkbutton(grid, variable=v_dedupe)
            cb_dedupe.grid(row=row, column=9)
            cb_pulse = ttk.Checkbutton(grid, variable=v_pulse)
            cb_pulse.grid(row=row, column=10)
            e_pulse_ms = ttk.Entry(grid, textvariable=v_pulse_ms, width=6)
            e_pulse_ms.grid(row=row, column=11, padx=3)
            e_delay = ttk.Entry(grid, textvariable=v_delay, width=6)
            e_delay.grid(row=row, column=12, padx=3)
            ToolTip(cb_enabled, t("tip_enabled"))
            ToolTip(combo, t("tip_actuator"))
            ToolTip(cb_invert, t("tip_invert"))
            ToolTip(e_scale, t("tip_scale"))
            ToolTip(e_min, t("tip_min"))
            ToolTip(e_max, t("tip_max"))
            ToolTip(cb_mid, t("tip_midpoint"))
            ToolTip(e_dz, t("tip_deadzone"))
            ToolTip(cb_dedupe, t("tip_dedupe"))
            ToolTip(cb_pulse, t("tip_pulse"))
            ToolTip(e_pulse_ms, t("tip_pulse_ms"))
            ToolTip(e_delay, t("tip_delay_ms"))
            self._map_rows[ch.value] = {
                "enabled": v_enabled, "actuator": v_actuator, "combo": combo,
                "invert": v_invert, "scale": v_scale, "min": v_min,
                "max": v_max, "mid": v_mid, "dz": v_dz,
                "dedupe": v_dedupe, "pulse": v_pulse,
                "pulse_ms": v_pulse_ms, "delay": v_delay,
            }
        self._actuator_items = []
        self._load_mapping_rows(self._initial_profile)

        # 信号柱状图（MFP 频谱风格，嵌入映射页底部）
        meter = ttk.LabelFrame(parent, text=t("meter_title"))
        meter.pack(fill="x", pady=(8, 0))
        self._meter_canvas = tk.Canvas(
            meter, height=130, bg="#fafafa",
            highlightthickness=1, highlightbackground="#cccccc")
        self._meter_canvas.pack(fill="x", padx=4, pady=4)
        ToolTip(self._meter_canvas, t("tip_meter"))
        self._draw_meter({})

    def _display_for(self, m: ChannelMapping) -> str:
        for display, a_type, motor in self._actuator_items:
            if a_type == m.target and motor == m.motor:
                return display
        if not m.enabled:
            return t("actuator_unmapped")
        return f"{m.target} #{m.motor}"

    def _load_mapping_rows(self, profile: Profile):
        for ch_val, row in self._map_rows.items():
            m = profile.channels.get(ch_val)
            if m is None:
                row["actuator"].set(t("actuator_unmapped"))
                row["enabled"].set(False)
                continue
            row["enabled"].set(m.enabled)
            row["invert"].set(m.invert)
            row["scale"].set(str(m.scale))
            row["min"].set(str(m.min))
            row["max"].set(str(m.max))
            row["mid"].set(m.midpoint)
            row["dz"].set(str(m.deadzone))
            row["dedupe"].set(m.dedupe)
            row["pulse"].set(m.pulse_enabled)
            row["pulse_ms"].set(str(m.pulse_ms))
            row["delay"].set(str(m.delay_ms))
            row["actuator"].set(self._display_for(m))
        self._v_mode.set(getattr(profile, "virtual_mode", "passthrough"))

    def _refresh_actuator_choices(self, devices):
        items = []
        for d in devices:
            for a in d.get("actuators", []):
                items.append((f"[{d['index']}] {a['label']} #{a['motor']}",
                              a["type"], a["motor"]))
        if items == self._actuator_items:
            return
        self._actuator_items = items
        values = [t("actuator_unmapped")] + [i[0] for i in items]
        for row in self._map_rows.values():
            row["combo"].configure(values=values)
        self._load_mapping_rows(self._collect_profile_from_ui())
        self._map_hint.set(
            f"已加载 {len(items)} 个执行器（来自 {len(devices)} 台设备）"
            if get_language() == "zh-CN" else
            f"Loaded {len(items)} actuators (from {len(devices)} devices)")

    # ---------------- Profile 加载/保存 ----------------

    def _initial_dir(self) -> str:
        d = os.path.join(BASE_DIR, "profiles")
        return d if os.path.isdir(d) else BASE_DIR

    def _remember_profile_path(self, path: str):
        self._profile_path = path
        self._v_profile_path.set(path)
        self._initial_config.profile_path = path
        try:
            settings_path = os.path.join(BASE_DIR, ".gtpb_settings")
            data = {}
            if os.path.isfile(settings_path):
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception:
                    data = {}
            data["lastProfile"] = path
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_loaded_profile(self, p: Profile):
        self._initial_profile = p
        self._v_listen.set(p.listen_address)
        self._v_ws.set(str(p.ws_port))
        self._v_tcp.set(str(p.tcp_port))
        self._v_backend.set(p.backend_url)
        self._load_mapping_rows(p)
        self._initial_config = self._build_config_from_profile(p)

    def _on_load_profile(self):
        if self._bridge is not None and self._bridge.alive:
            if not messagebox.askyesno(t("msg_load_profile_title"),
                                        t("msg_load_profile_running")):
                return
        path = filedialog.askopenfilename(
            title=t("btn_load_profile"),
            initialdir=self._initial_dir(),
            initialfile=os.path.basename(self._profile_path),
            filetypes=[("Profile JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            p = Profile.load(path, settings=self._settings)
        except Exception as e:
            messagebox.showerror(t("btn_load_profile"),
                                 t("msg_load_profile_fail", path=path, err=e))
            return
        self._apply_loaded_profile(p)
        self._remember_profile_path(path)
        messagebox.showinfo(t("btn_load_profile"),
                            t("msg_load_profile_ok", path=path))

    def _on_save_profile(self):
        profile = self._collect_profile_from_ui()
        path = self._profile_path
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or BASE_DIR, exist_ok=True)
            profile.save(path)
        except Exception as e:
            messagebox.showerror(t("btn_save_profile"),
                                 t("msg_save_profile_fail", path=path, err=e))
            return
        self._initial_profile = profile
        self._initial_config = self._build_config_from_profile(profile)
        if self._bridge is not None and self._bridge.alive:
            self._bridge.apply_profile(profile)
            messagebox.showinfo(
                t("btn_save_profile"),
                t("msg_save_profile_ok", hot=t("msg_save_profile_hot"), path=path))
        else:
            messagebox.showinfo(
                t("btn_save_profile"),
                t("msg_save_profile_ok", hot="", path=path) + t("msg_save_profile_idle"))

    def _on_save_profile_as(self):
        path = filedialog.asksaveasfilename(
            title=t("msg_save_profile_as_title"),
            initialdir=self._initial_dir(),
            initialfile=os.path.basename(self._profile_path) or "new_profile.json",
            defaultextension=".json",
            filetypes=[("Profile JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        profile = self._collect_profile_from_ui()
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)) or BASE_DIR, exist_ok=True)
            profile.save(path)
        except Exception as e:
            messagebox.showerror(t("btn_save_profile"),
                                 t("msg_save_profile_fail", path=path, err=e))
            return
        self._initial_profile = profile
        self._initial_config = self._build_config_from_profile(profile)
        self._remember_profile_path(path)
        messagebox.showinfo(t("btn_save_profile"),
                            t("msg_save_profile_as_ok", path=path))

    # ---------------- 状态轮询 ----------------

    def _poll_status(self):
        bridge = self._bridge
        if bridge is None or not bridge.alive:
            if bridge is not None and not bridge.alive:
                if bridge.start_error:
                    err = bridge.start_error
                    bridge.start_error = None
                    hint = ""
                    if "10048" in err or "bind" in err.lower():
                        hint = t("msg_start_fail_port_hint")
                    messagebox.showerror(
                        t("msg_start_fail_title"),
                        t("msg_start_fail_body", err=err, hint=hint))
                try:
                    if str(self._btn_start.cget("state")) == "disabled":
                        self._btn_start.config(state="normal")
                except Exception:
                    pass
                self._estop_on = False
                self._btn_estop.config(text=t("btn_estop"), bg="#c62828")
            self._status_var.set(t("status_idle"))
        else:
            service = bridge.service
            if service is not None:
                st = service.status()
                estop = t("status_estop") if st["estop"] else ""
                mode = t("mode_osr6") if st.get("virtual_mode") == "osr6" else t("mode_passthrough")
                backend = t("backend_connected") if st["backend"] else t("backend_disconnected")
                self._status_var.set(t(
                    "status_running",
                    mode=mode, backend=backend,
                    sessions=st["sessions"], devices=len(st["devices"]), estop=estop))
                self._refresh_devices(st["devices"])
                self._refresh_actuator_choices(st["devices"])
        self.root.after(self.POLL_STATUS_MS, self._poll_status)

    # ---------------- 信号柱状图 ----------------

    def _poll_meter(self):
        levels = self._bridge.channel_levels() if self._bridge is not None else {}
        self._draw_meter(levels)
        self.root.after(self.POLL_METER_MS, self._poll_meter)

    def _channel_color(self, ch: str) -> str:
        m = self._initial_profile.channels.get(ch)
        if m is None:
            return "#90a4ae"
        return {"Vibrate": "#1565c0", "Rotate": "#e65100",
                "Linear": "#2e7d32"}.get(m.target, "#90a4ae")

    def _draw_meter(self, levels: dict):
        c = getattr(self, "_meter_canvas", None)
        if c is None:
            return
        c.delete("all")
        w = max(c.winfo_width(), 120)
        h = 112
        n = len(CHANNELS)
        if n == 0:
            return
        gap = 14
        bw = max((w - gap * (n + 1)) / n, 24)
        base = h - 12
        for i, ch in enumerate(CHANNELS):
            x0 = gap + i * (bw + gap)
            v = max(0.0, min(1.0, float(levels.get(ch.value, 0.0))))
            bh = max(3, int(v * (h - 30)))
            y0 = base - bh
            color = self._channel_color(ch.value)
            c.create_rectangle(x0, y0, x0 + bw, base, fill=color, outline="")
            c.create_text(x0 + bw / 2, base + 10, text=ch.value,
                          font=("Microsoft YaHei", 8))
            c.create_text(x0 + bw / 2, y0 - 9, text=f"{v:.2f}",
                          font=("Microsoft YaHei", 7))

    def _refresh_devices(self, devices):
        lines = [f"[{d['index']}] {d['name']}   能力: {', '.join(d['capabilities']) or '无'}"
                 for d in devices]
        text = "\n".join(lines) if lines else t("devices_empty")
        if text != self._last_dev_text:
            self._last_dev_text = text
            self._append_text(self._tab_dev, text, None, clear=True)

    # ---------------- 工具 ----------------

    @staticmethod
    def _append_text(widget, text: str, tag, clear: bool = False):
        widget.config(state="normal")
        if clear:
            widget.delete("1.0", "end")
        widget.insert("end", text + "\n", tag)
        try:
            lines = int(widget.index("end-1c").split(".")[0])
            if lines > 4000:
                widget.delete("1.0", "2000.0")
        except Exception:
            pass
        widget.config(state="disabled")
        widget.see("end")

    def run(self):
        self.root.mainloop()


def run_gui(config: AppConfig, profile: Profile, profile_path: str = None,
            log_path: str = None, settings: SettingsLoader = None):
    GtpbGui(config, profile, profile_path=profile_path, log_path=log_path,
            settings=settings).run()
