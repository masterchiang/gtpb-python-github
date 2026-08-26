"""日志：单文件滚动日志（BASE_DIR/gtpb.log，10KB 上限自动裁掉最旧行）。

设计要点：
  1. 打包后日志就放在 EXE 同目录（BASE_DIR），用户容易找到；
  2. 只生成一个 gtpb.log 文件，不分日期/分类型；
  3. 文件大小 > 10KB 时，每次写完检查一次，把最早的行砍掉（保留尾部约 10KB）；
  4. 系统日志与游戏交互日志走同一条通道（便于排查时间线），但仍区分前缀；
  5. 可选 callback(source, level, text) 用于 GUI 推送。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Callable, Optional

# 单文件最大字节数；超过即按行裁剪最旧内容
MAX_LOG_BYTES = 10 * 1024


class RollingFileHandler(logging.Handler):
    """自定义 Handler：每次 emit 后检查文件大小，超过 MAX_LOG_BYTES 则按行裁剪。"""

    def __init__(self, path: str, max_bytes: int = MAX_LOG_BYTES,
                 encoding: str = "utf-8"):
        super().__init__()
        self._path = path
        self._max = max_bytes
        self._encoding = encoding
        # 写锁：logger 可能在多线程下被同时调用（GUI + bridge 线程）
        self._lock = threading.Lock()
        # 启动时若文件已超限，先裁剪一次
        self._trim()

    @property
    def path(self) -> str:
        return self._path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if not msg.endswith("\n"):
                msg += "\n"
            with self._lock:
                with open(self._path, "a", encoding=self._encoding) as f:
                    f.write(msg)
                self._trim()
        except Exception:
            # 日志自身失败不能影响业务
            pass

    def _trim(self) -> None:
        """如果文件大小超过上限，按行裁掉最旧内容，使文件大小 ≤ 上限的 ~80%。"""
        try:
            if not os.path.isfile(self._path):
                return
            size = os.path.getsize(self._path)
            if size <= self._max:
                return
            # 读全部行，保留尾部直到大小 ≤ 阈值的 80%
            with open(self._path, "r", encoding=self._encoding, errors="replace") as f:
                lines = f.readlines()
            target = int(self._max * 0.8)
            # 从尾部向前累积
            kept: list[str] = []
            cur = 0
            for line in reversed(lines):
                cur += len(line.encode(self._encoding, errors="replace"))
                if cur > target:
                    break
                kept.append(line)
            kept.reverse()
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding=self._encoding) as f:
                f.writelines(kept)
            os.replace(tmp, self._path)
        except Exception:
            pass


class LogManager:
    """统一日志管理器：单文件 + GUI 回调。

    兼容旧 API：sys_debug/sys_info/.../game_rx/game_tx/capture/close。
    """

    def __init__(self, log_path: str, capture_raw: bool = True,
                 level: str = "INFO", callback: Optional[Callable] = None,
                 console: bool = False):
        self._callback = callback
        self._capture_file = None

        # 确保父目录存在（BASE_DIR 一般是 EXE 目录，几乎必然存在；这里兜底）
        parent = os.path.dirname(os.path.abspath(log_path))
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception:
            pass

        self._log_path = log_path

        # 单一 logger，所有日志都进同一文件
        self._logger = logging.getLogger("gtpb")
        self._logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
        self._logger.handlers.clear()
        self._logger.propagate = False
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        self._handler = RollingFileHandler(log_path, MAX_LOG_BYTES)
        self._handler.setFormatter(fmt)
        self._logger.addHandler(self._handler)
        if console:
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self._logger.addHandler(sh)

        # 原始帧捕获文件（与日志文件同目录，独立文件名）
        if capture_raw:
            try:
                capture_path = os.path.join(parent, "gtpb_capture.jsonl")
                self._capture_file = open(capture_path, "a", encoding="utf-8")
            except Exception:
                self._capture_file = None

    @property
    def log_path(self) -> str:
        return self._log_path

    # ---------------- 系统日志 ----------------
    def sys_debug(self, msg: str):
        self._logger.debug(msg)
        self._emit("system", "DEBUG", msg)

    def sys_info(self, msg: str):
        self._logger.info(msg)
        self._emit("system", "INFO", msg)

    def sys_warning(self, msg: str):
        self._logger.warning(msg)
        self._emit("system", "WARNING", msg)

    def sys_error(self, msg: str):
        self._logger.error(msg)
        self._emit("system", "ERROR", msg)

    # ---------------- 游戏交互日志 ----------------
    def game_rx(self, transport: str, text: str):
        self._logger.info("[GameRx][%s] %s", transport, text)
        self._emit("game", "RX", f"[{transport}] {text}")

    def game_tx(self, transport: str, text: str):
        self._logger.info("[GameTx][%s] %s", transport, text)
        self._emit("game", "TX", f"[{transport}] {text}")

    # ---------------- Raw Capture ----------------
    def capture(self, transport: str, direction: str, data: bytes):
        if self._capture_file is None:
            return
        entry = {
            "ts": round(time.time(), 3),
            "transport": transport,
            "dir": direction,
            "len": len(data),
        }
        try:
            entry["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            entry["hex"] = data[:128].hex()
        try:
            self._capture_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._capture_file.flush()
        except Exception:
            pass

    def _emit(self, source: str, level: str, text: str):
        if self._callback is not None:
            try:
                self._callback(source, level, text)
            except Exception:
                pass

    def close(self):
        if self._capture_file is not None:
            try:
                self._capture_file.close()
            except Exception:
                pass
            self._capture_file = None
        try:
            self._logger.removeHandler(self._handler)
        except Exception:
            pass
        self._handler = None
