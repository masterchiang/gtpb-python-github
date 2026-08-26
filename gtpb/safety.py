"""安全：紧急停止。"""

from __future__ import annotations

import time
from typing import Callable, Optional


class EmergencyStop:
    """急停开关：触发后所有设备指令被丢弃，直到释放。

    on_engage 回调在触发时同步调用（可在事件循环线程内调度 StopAllDevices）。
    """

    def __init__(self, on_engage: Optional[Callable[[str], None]] = None):
        self._active = False
        self.engaged_at: Optional[float] = None
        self._on_engage = on_engage

    @property
    def active(self) -> bool:
        return self._active

    def engage(self, reason: str = "manual"):
        if self._active:
            return
        self._active = True
        self.engaged_at = time.time()
        if self._on_engage is not None:
            try:
                self._on_engage(reason)
            except Exception:
                pass

    def release(self):
        self._active = False
        self.engaged_at = None
