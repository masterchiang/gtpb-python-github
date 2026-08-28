"""行程模拟 + 通道时序延时引擎。

背景
----
TryFun Meta2 等设备的 oscillate 是「速度」语义：滑块 >0 即持续做活塞运动，
数值只控制速度，不能像 OSR 那样「移动到某位置后停止」。但这类设备有一个
特性：收到 oscillate = 0 时，行程会复位到初始位置。

利用这一点把速度型活塞模拟成 OSR 行程：
  - 游戏发非 0 值 v -> 立即发送 v（推进）
  - 每个非 0 信号触发一次独立的「推进 -> 复位」循环：延迟 pulse_ms 后自动
    发送 0（复位），由此产生与游戏频率同步的往复行程。
  - pulse_ms 可调：信号间隔大时调大、间隔小时调小，避免复位与下一个游戏
    信号冲突。

同时提供 MFP（MultiFunPlayer）风格的通道时序延时：
  - 每通道 delay_ms 可正可负（正=滞后发送，负=相对提前）。
  - 实现：以所有启用通道中最负的延时为基线做时间线缓冲，
    使负延时通道「相对」其他通道提前输出。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable, Dict, List, Optional

from .config import Profile
from .logs import LogManager
from .models import NormalizedCommand
from .transform import CommandDispatcher


class PulseEngine:
    """通道信号处理器：行程模拟（pulse）+ 通道延时（delay）+ 电平采样。

    设计：
      - 所有进入的命令统一先进延迟队列（delay=0 时几乎即时输出），
        保证「推进/复位」与通道延时的一致性时序。
      - 行程模拟用每通道单「armed」定时器：收到非 0 信号时若未 armed 则
        安排 pulse_ms 后的复位；收到 0 则立即复位并取消待发复位。
    """

    TICK_S = 0.005  # 内部时钟（秒），决定延时/复位精度

    def __init__(self, dispatcher: CommandDispatcher,
                 profile_provider: Callable[[], Profile],
                 log: LogManager):
        self._dispatcher = dispatcher
        self._profile_provider = profile_provider
        self._log = log
        self._running = False
        # 行程模拟状态（按通道）
        self._armed: Dict[str, bool] = {}
        self._reset_due: Dict[str, float] = {}          # monotonic 秒
        self._last_cmd: Dict[str, NormalizedCommand] = {}
        # 去重状态（按通道）：最后转发的输入值（相同值跳过，不受内部复位影响）
        self._last_input: Dict[str, float] = {}
        # 通道延时队列：channel -> deque[(due, cmd)]
        self._delay_queues: Dict[str, deque] = {}
        # 信号电平采样（供 GUI 柱状图）
        self._levels: Dict[str, float] = {}

    # ---------------- 公共入口 ----------------

    def process_cmds(self, cmds: List[NormalizedCommand]):
        """处理映射后的命令（须在事件循环线程内调用）。"""
        for cmd in cmds:
            self._process_cmd(cmd)

    def channel_levels(self) -> Dict[str, float]:
        """各通道最新电平（0..1），供 GUI 柱状图轮询。"""
        return dict(self._levels)

    def clear(self):
        """清空待发状态（急停/停止时调用）。"""
        self._armed.clear()
        self._reset_due.clear()
        self._last_cmd.clear()
        self._last_input.clear()
        self._delay_queues.clear()
        self._levels.clear()

    async def run(self):
        self._running = True
        while self._running:
            self._tick()
            await asyncio.sleep(self.TICK_S)

    def stop(self):
        self._running = False

    # ---------------- 内部 ----------------

    def _process_cmd(self, cmd: NormalizedCommand):
        ch = cmd.channel.value
        profile = self._profile_provider()
        m = profile.channels.get(ch) if profile else None
        # 去重：仅数值变化才转发（游戏重复发同一数值时跳过，防反复触发）
        if m is not None and m.enabled and m.dedupe:
            if ch in self._last_input and abs(cmd.value - self._last_input[ch]) < 1e-4:
                self._levels[ch] = cmd.value  # 柱状图仍反映输入信号
                return
            self._last_input[ch] = cmd.value
        pulse_on = m is not None and m.enabled and m.pulse_enabled
        if pulse_on:
            if cmd.value > 0.0:
                self._last_cmd[ch] = cmd
                if not self._armed.get(ch, False):
                    self._armed[ch] = True
                    self._reset_due[ch] = (time.monotonic()
                                           + max(1, m.pulse_ms) / 1000.0)
            else:
                # 手动归零：立即复位并取消待发复位
                self._armed.pop(ch, None)
                self._reset_due.pop(ch, None)
        self._queue_cmd(cmd)

    def _queue_cmd(self, cmd: NormalizedCommand):
        ch = cmd.channel.value
        self._levels[ch] = cmd.value
        m = self._profile_provider().channels.get(ch)
        delay = m.delay_ms if (m is not None and m.enabled) else 0
        eff = max(0, delay - self._min_delay())
        self._delay_queues.setdefault(ch, deque()).append(
            (time.monotonic() + eff / 1000.0, cmd))

    def _min_delay(self) -> int:
        """所有启用通道中最负的延时（基线补偿，支持负延时=提前）。"""
        profile = self._profile_provider()
        vals = [m.delay_ms for m in profile.channels.values() if m.enabled]
        return min(vals + [0])

    def _build_reset(self, ch: str) -> Optional[NormalizedCommand]:
        last = self._last_cmd.get(ch)
        if last is None:
            return None
        return NormalizedCommand(
            channel=last.channel, value=0.0, raw_value=0.0,
            target=last.target, motor=last.motor,
            device_index=last.device_index, meta=dict(last.meta))

    def _tick(self):
        now = time.monotonic()
        # 1) 到期的复位定时器 -> 生成复位命令入队
        for ch in list(self._armed):
            if self._reset_due.get(ch, float("inf")) <= now:
                self._armed.pop(ch, None)
                reset = self._build_reset(ch)
                if reset is not None:
                    self._queue_cmd(reset)
        # 2) 到期的延时队列 -> 提交给 dispatcher（latest-wins 合并发送）
        for ch, dq in list(self._delay_queues.items()):
            while dq and dq[0][0] <= now:
                _, cmd = dq.popleft()
                self._dispatcher.submit([cmd])
            if not dq:
                del self._delay_queues[ch]
