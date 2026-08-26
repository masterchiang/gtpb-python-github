# GameToyProtocolBridge (GTPB)

**Read this in other languages:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge (GTPB) is a **Buttplug v3 protocol bridge** that lets games (e.g. MultiFunPlayer) control hardware devices via WebSocket.

**Data path:**

```
Game (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → parse / map / transform → Intiface Central → toy hardware
```

## Features

- **Dual WebSocket + TCP proxy** — bidirectional communication between games and Intiface Central
- **Channel mapping** — flexible mapping of game channels to hardware actuators
- **OSR6 six-axis mode** — maps game OSR6 six-axis output to real hardware (L0 stroke / L1 in-out / L2 left-right / R0 twist / R1 roll / R2 pitch)
- **Emergency stop** — one-click interception of all device commands, sends StopAllDevices
- **Multi-language support** — Simplified Chinese, English, 日本語, Deutsch, Français, Русский, Español, Português (Brasil), 한국어
- **Profile management** — load, save, save-as for different connection configs and channel mapping schemes
- **Port conflict detection** — checks game and backend port conflicts on startup
- **Logging system** — system log, GameRx/Tx protocol log, capture log

## Quick start

### Prerequisites

1. Install and start [Intiface Central](https://intiface.com/central/)
2. Make sure your toy device is connected via Intiface Central

### Run

```bash
# Install dependencies
pip install -r requirements.txt

# GUI mode
python main.py

# Headless mode
python main.py --headless

# Specify profile and parameters
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### Package as EXE

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## Port configuration (important)

**The two ports must be different!**

| Port | Default | Description |
|------|---------|-------------|
| WebSocket port | 12345 | Port where games connect to GTPB (game-side convention, usually unchanged) |
| Backend Intiface | ws://127.0.0.1:12346 | Port where GTPB connects to Intiface Central |

If they are the same, the data flow loops into an infinite loop. GTPB auto-detects and warns on startup.

Fix: Intiface Central → Settings → Server → change Listening Port (suggest 12346), then update the GTPB "Backend Intiface" accordingly.

## File structure

```
gtpb-python/
├── gtpb/                    # Core modules
│   ├── __init__.py
│   ├── backend.py           # Intiface backend connection
│   ├── buttplug.py          # Buttplug v3 protocol parsing
│   ├── config.py            # Configuration loading (INI + JSON Profile)
│   ├── gui.py               # Tkinter GUI
│   ├── i18n.py              # Multi-language support
│   ├── logs.py              # Log manager
│   ├── mapping.py           # Channel mapping engine
│   ├── models.py            # Data models
│   ├── proxy.py             # Bridge service core
│   ├── safety.py            # Safety mechanism (emergency stop)
│   └── transform.py         # Value transforms
├── profiles/default.json    # Default profile
├── tests/                   # Unit tests
├── tools/                   # Development helper tools
├── configsetting.ini        # Factory config (do not modify)
├── main.py                  # Program entry
└── requirements.txt         # Python dependencies
```

## Runtime files

| File | Description |
|------|-------------|
| `profiles/*.json` | Your profiles (connection settings + channel mapping) |
| `.gtpb_settings` | Internal state (language, last loaded profile path) |
| `gtpb.log` | Rolling log (10KB cap, auto-trims old entries) |

## Command-line arguments

| Argument | Description |
|----------|-------------|
| `--headless` | Headless mode |
| `--profile <path>` | Specify profile file |
| `--listen <addr>` | Listen address (overrides profile) |
| `--ws-port <port>` | WebSocket port (overrides profile) |
| `--tcp-port <port>` | TCP port (overrides profile) |
| `--backend <url>` | Backend Intiface address (overrides profile) |

## License

MIT