# GameToyProtocolBridge (GTPB)

**其他语言版本：** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) 是一个 **Buttplug v3 协议桥**，让游戏（如 MultiFunPlayer）通过 WebSocket 控制硬件设备。

**数据链路：**

```
游戏 (MultiFunPlayer 等) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → 解析 / 映射 / 转换 → Intiface Central → 玩具硬件
```

## 功能

- **WebSocket + TCP 双协议代理** — 兼容游戏与 Intiface Central 之间的双向通信
- **通道映射** — 灵活配置游戏通道到硬件执行器的映射关系
- **OSR6 六轴模式** — 将游戏输出的 OSR6 六轴指令映射到真实硬件（L0 主行程 / L1 前后 / L2 左右 / R0 扭转 / R1 横滚 / R2 俯仰）
- **紧急停止** — 一键拦截所有设备指令，发送 StopAllDevices
- **多语言支持** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **Profile 管理** — 加载、保存、另存为不同的连接配置和通道映射方案
- **端口冲突检测** — 启动时自动检查游戏端口与后端端口是否冲突
- **日志系统** — 系统日志、GameRx/Tx 协议日志、捕获日志

## 快速开始

### 前置条件

1. 安装并启动 [Intiface Central](https://intiface.com/central/)
2. 确保你的玩具设备已通过 Intiface Central 连接

### 运行

```bash
# 安装依赖
pip install -r requirements.txt

# GUI 模式
python main.py

# 无界面模式
python main.py --headless

# 指定 Profile 和参数
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### 打包 EXE

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## 端口配置（重要）

**两个端口必须不同！**

| 端口 | 默认值 | 说明 |
|------|--------|------|
| WebSocket 端口 | 12345 | 游戏连接 GTPB 的端口（游戏端约定，一般不改） |
| 后端 Intiface | ws://127.0.0.1:12346 | GTPB 连接 Intiface Central 的端口 |

如果两者相同，数据流会陷入死循环。GTPB 启动时会自动检测并警告。

解决方法：Intiface Central → Settings → Server → 修改 Listening Port（建议 12346），再把 GTPB 的「后端 Intiface」同步修改。

## 文件结构

```
gtpb-python/
├── gtpb/                    # 核心模块
│   ├── __init__.py
│   ├── backend.py           # Intiface 后端连接
│   ├── buttplug.py          # Buttplug v3 协议解析
│   ├── config.py            # 配置加载（INI + JSON Profile）
│   ├── gui.py               # Tkinter 图形界面
│   ├── i18n.py              # 多语言支持
│   ├── logs.py              # 日志管理器
│   ├── mapping.py           # 通道映射引擎
│   ├── models.py            # 数据模型
│   ├── proxy.py             # 桥接服务核心
│   ├── safety.py            # 安全机制（紧急停止）
│   └── transform.py         # 数值变换
├── profiles/default.json    # 默认 Profile
├── tests/                   # 单元测试
├── tools/                   # 开发辅助工具
├── configsetting.ini        # 出厂配置（不要修改）
├── main.py                  # 程序入口
└── requirements.txt         # Python 依赖
```

## 运行时文件

| 文件 | 说明 |
|------|------|
| `profiles/*.json` | 你的 Profile（连接设置 + 通道映射） |
| `.gtpb_settings` | 内部状态（语言、上次加载的 Profile 路径） |
| `gtpb.log` | 滚动日志（10KB 上限自动裁旧） |

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--headless` | 无界面模式 |
| `--profile <path>` | 指定 Profile 文件 |
| `--listen <addr>` | 监听地址（覆盖 Profile） |
| `--ws-port <port>` | WebSocket 端口（覆盖 Profile） |
| `--tcp-port <port>` | TCP 端口（覆盖 Profile） |
| `--backend <url>` | 后端 Intiface 地址（覆盖 Profile） |

## 许可证

MIT