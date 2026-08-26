# GameToyProtocolBridge (GTPB)

**他の言語で読む:** [简体中文](README.zh-CN.md) · [English](README.md) · [日本語](README.ja-JP.md) · [한국어](README.ko-KR.md) · [Deutsch](README.de-DE.md) · [Français](README.fr-FR.md) · [Русский](README.ru-RU.md) · [Español](README.es-ES.md) · [Português (Brasil)](README.pt-BR.md)

GameToyProtocolBridge（GTPB）は、**ゲーム（例：MultiFunPlayer）が WebSocket 経由でハードウェアデバイスを制御**できるようにする **Buttplug v3 プロトコルブリッジ**です。

**データフロー：**

```
ゲーム（MultiFunPlayer など）→ GTPB (ws://127.0.0.1:12345, Buttplug v3)
  → 解析 / マッピング / 変換 → Intiface Central → 玩具ハードウェア
```

## 機能

- **WebSocket + TCP 二重プロトコルプロキシ** — ゲームと Intiface Central 間の双方向通信をサポート
- **チャンネルマッピング** — ゲームチャンネルからハードウェアアクチュエータへのマッピングを柔軟に設定
- **OSR6 六軸モード** — ゲームの OSR6 六軸出力を実ハードウェアにマッピング（L0 主行程 / L1 前後 / L2 左右 / R0 捻り / R1 ロール / R2 ピッチ）
- **緊急停止** — ワンクリックで全デバイスコマンドを遮断し、StopAllDevices を送信
- **多言語対応** — 简体中文、English、日本語、Deutsch、Français、Русский、Español、Português (Brasil)、한국어
- **プロファイル管理** — 接続設定とチャンネルマッピング構成の読み込み・保存・別名保存
- **ポート競合検出** — 起動時にゲームポートとバックエンドポートの競合を自動チェック
- **ログシステム** — システムログ、GameRx/Tx プロトコルログ、キャプチャログ

## クイックスタート

### 前提条件

1. [Intiface Central](https://intiface.com/central/) をインストールして起動
2. 玩具デバイスが Intiface Central 経由で接続されていることを確認

### 実行

```bash
# 依存関係をインストール
pip install -r requirements.txt

# GUI モード
python main.py

# ヘッドレスモード
python main.py --headless

# プロファイルとパラメータを指定
python main.py --profile profiles/my.json --listen 0.0.0.0 --ws-port 12345 --backend ws://127.0.0.1:12346
```

### EXE へのパッケージ化

```bash
pip install pyinstaller
pyinstaller gtpb.spec
```

## ポート設定（重要）

**2 つのポートは別にする必要があります！**

| ポート | デフォルト | 説明 |
|--------|-----------|------|
| WebSocket ポート | 12345 | ゲームが GTPB に接続するポート（ゲーム側の慣例、通常は変更しない） |
| バックエンド Intiface | ws://127.0.0.1:12346 | GTPB が Intiface Central に接続するポート |

両方が同じ場合、データフローが無限ループに陥ります。GTPB は起動時に自動検出して警告します。

解決策：Intiface Central → Settings → Server → Listening Port を変更（12346 を推奨）、GTPB の「バックエンド Intiface」も同期して変更します。

## ファイル構成

```
gtpb-python/
├── gtpb/                    # コアモジュール
│   ├── __init__.py
│   ├── backend.py           # Intiface バックエンド接続
│   ├── buttplug.py          # Buttplug v3 プロトコル解析
│   ├── config.py            # 設定の読み込み（INI + JSON プロファイル）
│   ├── gui.py               # Tkinter GUI
│   ├── i18n.py              # 多言語対応
│   ├── logs.py              # ログマネージャー
│   ├── mapping.py           # チャンネルマッピングエンジン
│   ├── models.py            # データモデル
│   ├── proxy.py             # ブリッジサービスの中核
│   ├── safety.py            # 安全機構（緊急停止）
│   └── transform.py         # 数値変換
├── profiles/default.json    # デフォルトプロファイル
├── tests/                   # ユニットテスト
├── tools/                   # 開発用補助ツール
├── configsetting.ini        # 出荷時設定（変更しないでください）
├── main.py                  # プログラムエントリ
└── requirements.txt         # Python 依存関係
```

## 実行時ファイル

| ファイル | 説明 |
|----------|------|
| `profiles/*.json` | プロファイル（接続設定 + チャンネルマッピング） |
| `.gtpb_settings` | 内部状態（言語、最後に読み込んだプロファイルのパス） |
| `gtpb.log` | ローリングログ（10KB 上限で自動的に古いものを切り捨て） |

## コマンドライン引数

| 引数 | 説明 |
|------|------|
| `--headless` | ヘッドレスモード |
| `--profile <path>` | プロファイルファイルを指定 |
| `--listen <addr>` | リッスンアドレス（プロファイルを上書き） |
| `--ws-port <port>` | WebSocket ポート（プロファイルを上書き） |
| `--tcp-port <port>` | TCP ポート（プロファイルを上書き） |
| `--backend <url>` | バックエンド Intiface アドレス（プロファイルを上書き） |

## ライセンス

MIT