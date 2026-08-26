"""透传诊断代理：12345 -> Intiface(12346) 纯字节转发，全程记录双向流量。

用途：A/B 对照 —— 游戏连它等价于直连 Intiface Central。
运行: python tools/passthrough_probe.py   （先停掉 GTPB，释放 12345）
日志: logs/passthrough_YYYYMMDD.log（GAME->IF 为游戏发出，IF->GAME 为 Intiface 返回）
"""

import asyncio
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websockets.asyncio.client import connect as ws_connect
from websockets.asyncio.server import serve as ws_serve

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = "ws://127.0.0.1:12346"
LISTEN_PORT = 12345

os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
log_path = os.path.join(BASE_DIR, "logs",
                        f"passthrough_{datetime.now().strftime('%Y%m%d')}.log")
LOG = open(log_path, "a", encoding="utf-8")


def stamp() -> str:
    return time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"


def note(text: str):
    LOG.write(text + "\n")
    LOG.flush()
    print(text)


async def pump(src, dst, tag: str):
    try:
        async for msg in src:
            note(f"{stamp()} {tag} {msg}")
            await dst.send(msg)
    except Exception as e:
        note(f"{stamp()} {tag} 结束: {type(e).__name__}: {e}")


async def handler(ws):
    try:
        backend = await ws_connect(BACKEND, proxy=None, open_timeout=5)
    except Exception as e:
        note(f"{stamp()} 无法连接后端 {BACKEND}: {e}")
        return
    note(f"{stamp()} ===== 游戏接入 {ws.remote_address} =====")
    try:
        await asyncio.gather(
            pump(ws, backend, "GAME->IF"),
            pump(backend, ws, "IF->GAME"),
        )
    finally:
        note(f"{stamp()} ===== 游戏断开 =====")
        try:
            await backend.close()
        except Exception:
            pass


async def main():
    async with ws_serve(handler, "127.0.0.1", LISTEN_PORT, max_size=4 * 1024 * 1024):
        note(f"{stamp()} 透传代理已启动: 127.0.0.1:{LISTEN_PORT} -> {BACKEND}")
        note(f"{stamp()} 日志: {log_path}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
