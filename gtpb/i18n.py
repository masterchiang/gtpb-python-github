"""i18n：多语言支持。

用法:
  from gtpb.i18n import t, set_language, get_language, available_languages

  set_language("zh-CN")     # 切换
  print(t("btn_start"))     # 查表

设计:
  - 内置 9 种语言: zh-CN / en-US / ja-JP / de-DE / fr-FR / ru-RU / es-ES / pt-BR / ko-KR
  - 启动时按 Windows 系统区域自动选择（通过 GetUserDefaultLocaleName，返回 BCP-47 代码）
  - 偏僻 / 不在列表里的语言默认回落 en-US
  - 用户可通过 GUI 菜单切换；语言选择记到 .gtpb_settings，下次启动自动用回
  - 翻译字典用 dataclass 分组维护；漏译时回落到 key 本身（不静默失效）
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Dict, Optional

_LANG_KEY = "language"
_lock = threading.Lock()
_current: str = "en-US"   # 启动时按系统区域覆盖


# ---------------------------------------------------------------- 翻译字典

_ZH_CN: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': '语言',
    'menu_help': '帮助',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': '使用说明',
    'frame_connection': '连接设置（随 Profile 保存）',
    'frame_status': '状态',
    'frame_profile': 'Profile',
    'lbl_listen': '监听地址',
    'lbl_ws_port': 'WebSocket 端口',
    'lbl_tcp_port': 'TCP 端口(0=禁用)',
    'lbl_backend': '后端 Intiface',
    'lbl_profile': 'Profile:',
    'btn_load_profile': '加载 Profile...',
    'btn_save_profile': '保存 Profile',
    'btn_save_profile_as': '另存为 Profile...',
    'btn_start': '启动',
    'btn_stop': '停止',
    'btn_estop': '紧急停止',
    'btn_estop_engaged': '急停已触发 (点击释放)',
    'tab_sys_log': '系统日志',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': '设备',
    'tab_mapping': '通道映射',
    'mapping_passthrough': '透传真实设备',
    'mapping_osr6': 'OSR6 虚拟六轴',
    'mapping_hint_edit': '提示: 修改后点上方「保存 Profile」生效',
    'mapping_hint_empty': '执行器列表将在服务启动并同步设备后自动加载',
    'col_channel': '通道',
    'col_enabled': '启用',
    'col_actuator': '目标执行器',
    'col_invert': 'Invert',
    'col_scale': 'Scale',
    'col_min': 'Min',
    'col_max': 'Max',
    'col_midpoint': '中点旋转',
    'col_deadzone': 'Deadzone',
    'actuator_unmapped': '(未映射)',
    'status_idle': '状态: 未运行',
    'status_running': '状态: 运行中  |  模式: {mode}  |  后端: {backend}  |  游戏会话: {sessions}  |  设备: {devices}{estop}',
    'status_estop': '  |  急停中!',
    'mode_passthrough': '透传',
    'mode_osr6': 'OSR6六轴',
    'backend_connected': '已连接',
    'backend_disconnected': '未连接',
    'devices_empty': '（暂无设备，请确认 Intiface Central 已启动并扫描）',
    'msg_load_profile_title': '加载 Profile',
    'msg_load_profile_running': '服务正在运行，加载新 Profile 后需要重启才能完全生效。\n是否继续？',
    'msg_load_profile_ok': '已加载 Profile：\n{path}',
    'msg_load_profile_fail': '无法读取 Profile:\n{path}\n{err}',
    'msg_save_profile_ok': '已保存{hot}：\n{path}',
    'msg_save_profile_hot': '并热应用',
    'msg_save_profile_idle': '（服务未运行，下次启动生效）',
    'msg_save_profile_fail': '无法写入 Profile:\n{path}\n{err}',
    'msg_save_profile_as_title': '另存为 Profile',
    'msg_save_profile_as_ok': '已保存到：\n{path}',
    'msg_start_fail_title': 'GTPB 启动失败',
    'msg_start_fail_body': '桥接服务启动失败：\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\n原因：监听端口被占用 —— 请先关闭其他正在运行的GTPB 实例（包括 python main.py --headless 窗口），再点击"启动"。',
    'msg_port_conflict_title': '端口冲突警告',
    'msg_port_conflict_body': '本机游戏端 WebSocket 端口（{ws_port}）与 Intiface Central 后端端口（{backend_port}）相同！\n\nGTPB 监听 {ws_port} 端口等待游戏连接，同时还要作为客户端去连接 Intiface Central。\n如果两端端口相同，游戏 / GTPB / Intiface Central 三者之间的数据流会陷入死循环，将出现「游戏卡在连接中」「设备搜索不到」「Intiface 日志刷屏」等问题。\n\n解决方法：\n  1. 打开 Intiface Central → Settings → Server → 修改 Listening Port（建议 12346 等非 12345 端口）\n  2. 把本软件「后端 Intiface」一栏改成 Intiface 实际监听的端口（与上一步一致）\n  3. 保持本软件「WebSocket 端口」为 12345（这是游戏端约定的默认端口，不要改）\n\n请先解决端口冲突再启动。',
    'log_start_gui': '=== GTPB 启动 (GUI) ===',
    'log_start_headless': '=== GTPB 启动 (headless) ===',
    'log_log_file': '日志文件: {path}',
    'log_profile_path': 'Profile: {path}',
    'log_language_set': '界面语言: {lang}',
    'log_sigint': '收到退出信号，正在停止...',
    'usage_title': '使用说明',
    'usage_text': 'GameToyProtocolBridge (GTPB) 是一个 Buttplug v3 协议桥，让游戏通过 WebSocket 控制硬件。\n\n═══════════════════ 端口冲突（必读）═══════════════════\n⚠ 本软件监听游戏端 WebSocket 端口（默认 12345），同时作为客户端连接 Intiface Central。\n⚠ 这两个端口必须不同！\n  - 游戏端 WebSocket 端口 = 软件「WebSocket 端口」（默认 12345）\n  - Intiface Central 端口 = 软件「后端 Intiface」（默认 ws://127.0.0.1:12346）\n如果两者相同，会出现「游戏卡在连接中」「设备搜索不到」「数据流死循环」等问题，\n本软件启动时会自动检查端口冲突并强警告。\n解决方法：Intiface Central → Settings → Server Listening Port 改成 12346 或其他非 12345 端口，\n再把本软件「后端 Intiface」一栏同步改成该端口。\n\n═══════════════════ 工作链路 ═══════════════════\n  游戏 (MultiFunPlayer 等) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → 解析 / 映射 / 转换 → Intiface Central → 玩具硬件\n\n═══════════════════ 文件结构 ═══════════════════\n  configsetting.ini    软件依赖（出厂配置），不要修改\n  profiles/*.json      你的 Profile（连接设置 + 通道映射）\n  .gtpb_settings       内部状态（语言、上次加载的 Profile 路径）\n  gtpb.log             单文件滚动日志（10KB 上限自动裁旧）\n\n═══════════════════ 快速上手 ═══════════════════\n  1. 启动 Intiface Central，确认玩具已连接\n  2. 启动 GTPB，保持「WebSocket 端口 = 12345」和「后端 Intiface = Intiface 实际端口」\n  3. 启动游戏 / MultiFunPlayer，让它连接 ws://127.0.0.1:12345\n  4. 在 GTPB「通道映射」标签页调整映射，修改完点「保存 Profile」\n\n═══════════════════ OSR6 六轴模式 ═══════════════════\n  在「通道映射」标签页选「OSR6 虚拟六轴」，游戏会看到一台虚拟的六轴设备\n  （L0 主行程 / L1 前后 / L2 左右 / R0 扭转 / R1 横滚 / R2 俯仰）。\n  GTPB 会把六轴指令按映射表发到真实硬件。\n\n═══════════════════ 日志 ═══════════════════\n  「系统日志」标签页：本软件运行事件、错误\n  「GameRx/Tx」标签页：游戏 ↔ GTPB 之间的 Buttplug 消息（用于协议排查）\n  gtpb.log 同步写入，最多保留最近 10KB\n\n═══════════════════ 紧急停止 ═══════════════════\n  右上「紧急停止」按钮会立即拦截所有设备指令，并向后端发送 StopAllDevices。\n  再次点击释放，恢复正常指令通道。\n',
}

_EN_US: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Language',
    'menu_help': 'Help',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': 'User Guide',
    'frame_connection': 'Connection (saved with Profile)',
    'frame_status': 'Status',
    'frame_profile': 'Profile',
    'lbl_listen': 'Listen address',
    'lbl_ws_port': 'WebSocket port',
    'lbl_tcp_port': 'TCP port (0=disabled)',
    'lbl_backend': 'Backend Intiface',
    'lbl_profile': 'Profile:',
    'btn_load_profile': 'Load Profile...',
    'btn_save_profile': 'Save Profile',
    'btn_save_profile_as': 'Save Profile As...',
    'btn_start': 'Start',
    'btn_stop': 'Stop',
    'btn_estop': 'Emergency Stop',
    'btn_estop_engaged': 'E-Stop engaged (click to release)',
    'tab_sys_log': 'System Log',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Devices',
    'tab_mapping': 'Channel Mapping',
    'mapping_passthrough': 'Pass-through real device',
    'mapping_osr6': 'OSR6 virtual 6-axis',
    'mapping_hint_edit': 'Tip: click "Save Profile" after editing',
    'mapping_hint_empty': 'Actuator list loads automatically after service start',
    'col_channel': 'Channel',
    'col_enabled': 'Enabled',
    'col_actuator': 'Target Actuator',
    'col_invert': 'Invert',
    'col_scale': 'Scale',
    'col_min': 'Min',
    'col_max': 'Max',
    'col_midpoint': 'Midpoint',
    'col_deadzone': 'Deadzone',
    'actuator_unmapped': '(unmapped)',
    'status_idle': 'Status: stopped',
    'status_running': 'Status: running  |  Mode: {mode}  |  Backend: {backend}  |  Game sessions: {sessions}  |  Devices: {devices}{estop}',
    'status_estop': '  |  E-STOPPED!',
    'mode_passthrough': 'pass-through',
    'mode_osr6': 'OSR6 6-axis',
    'backend_connected': 'connected',
    'backend_disconnected': 'disconnected',
    'devices_empty': '(no devices — make sure Intiface Central is running and scanning)',
    'msg_load_profile_title': 'Load Profile',
    'msg_load_profile_running': 'Service is running; loading a new Profile requires restart to fully apply.\nContinue?',
    'msg_load_profile_ok': 'Profile loaded:\n{path}',
    'msg_load_profile_fail': 'Cannot read Profile:\n{path}\n{err}',
    'msg_save_profile_ok': 'Saved{hot}:\n{path}',
    'msg_save_profile_hot': ' and hot-applied',
    'msg_save_profile_idle': ' (service not running — applies on next start)',
    'msg_save_profile_fail': 'Cannot write Profile:\n{path}\n{err}',
    'msg_save_profile_as_title': 'Save Profile As',
    'msg_save_profile_as_ok': 'Saved to:\n{path}',
    'msg_start_fail_title': 'GTPB start failed',
    'msg_start_fail_body': 'Bridge service failed to start:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\nCause: listen port already in use — close other running GTPB instances (including `python main.py --headless`) before clicking Start.',
    'msg_port_conflict_title': 'Port conflict',
    'msg_port_conflict_body': 'The local game-side WebSocket port ({ws_port}) is the SAME as the Intiface Central backend port ({backend_port})!\n\nGTPB listens on port {ws_port} for the game, AND it also acts as a client to Intiface Central. If both ports are equal, the data flow between game / GTPB / Intiface Central will loop forever, causing "game stuck on Connecting", "device not found", and "Intiface log flooding".\n\nFix:\n  1. Open Intiface Central → Settings → Server → change Listening Port (e.g. 12346, NOT 12345)\n  2. Update GTPB\'s "Backend Intiface" field to match the new port\n  3. Keep GTPB\'s "WebSocket port" at 12345 (the default game-side port — do not change)\n\nResolve the port conflict before starting.',
    'log_start_gui': '=== GTPB start (GUI) ===',
    'log_start_headless': '=== GTPB start (headless) ===',
    'log_log_file': 'Log file: {path}',
    'log_profile_path': 'Profile: {path}',
    'log_language_set': 'UI language: {lang}',
    'log_sigint': 'Interrupt received, stopping...',
    'usage_title': 'User Guide',
    'usage_text': 'GameToyProtocolBridge (GTPB) is a Buttplug v3 protocol bridge that lets games control hardware via WebSocket.\n\n═══════════════════ Port Conflict (MUST READ) ═══════════════════\n⚠ GTPB listens on the game-side WebSocket port (default 12345), AND it also acts as a client connecting to Intiface Central.\n⚠ These two ports MUST be different!\n  - Game-side WebSocket port = GTPB\'s "WebSocket port" field (default 12345)\n  - Intiface Central port   = GTPB\'s "Backend Intiface" field (default ws://127.0.0.1:12346)\nIf they are the same, you\'ll see "game stuck on Connecting", "device not found", and infinite data loops.\nGTPB automatically checks this on startup and shows a strong warning.\nFix: open Intiface Central → Settings → Server Listening Port, change to 12346 or any port other than 12345, then update GTPB\'s "Backend Intiface" field to match.\n\n═══════════════════ Data Flow ═══════════════════\n  Game (MultiFunPlayer etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → parse / map / transform → Intiface Central → hardware\n\n═══════════════════ File Layout ═══════════════════\n  configsetting.ini    Software dependency (factory defaults) — do not edit\n  profiles/*.json      Your profiles (connection settings + channel mapping)\n  .gtpb_settings       Internal state (language, last-loaded Profile path)\n  gtpb.log             Single rolling log file (10KB cap)\n\n═══════════════════ Quick Start ═══════════════════\n  1. Start Intiface Central and confirm the device is connected\n  2. Start GTPB; keep "WebSocket port = 12345" and set "Backend Intiface" to Intiface\'s actual port\n  3. Launch the game / MultiFunPlayer and point it to ws://127.0.0.1:12345\n  4. Adjust channel mapping in GTPB\'s "Channel Mapping" tab, then click "Save Profile"\n\n═══════════════════ OSR6 6-Axis Mode ═══════════════════\n  In the "Channel Mapping" tab, select "OSR6 virtual 6-axis". The game will see a virtual 6-axis device (L0 main / L1 forward-back / L2 left-right / R0 twist / R1 roll / R2 pitch). GTPB will forward these axes to your real hardware according to the mapping table.\n\n═══════════════════ Logs ═══════════════════\n  System Log tab: software events and errors\n  GameRx/Tx tab:  Buttplug messages between the game and GTPB (for protocol debugging)\n  gtpb.log:       mirrored to disk, keeps the latest 10KB\n\n═══════════════════ Emergency Stop ═══════════════════\n  The "Emergency Stop" button intercepts all device commands immediately and sends StopAllDevices to the backend. Click again to release and resume normal operation.\n',
}

_JA_JP: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': '言語',
    'menu_help': 'ヘルプ',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': '使い方',
    'frame_connection': '接続設定 (プロファイルに保存)',
    'frame_status': '状態',
    'frame_profile': 'プロファイル',
    'lbl_listen': '待受アドレス',
    'lbl_ws_port': 'WebSocket ポート',
    'lbl_tcp_port': 'TCP ポート (0=無効)',
    'lbl_backend': 'バックエンド Intiface',
    'lbl_profile': 'プロファイル:',
    'btn_load_profile': 'プロファイルを読込...',
    'btn_save_profile': 'プロファイルを保存',
    'btn_save_profile_as': '名前を付けて保存...',
    'btn_start': '開始',
    'btn_stop': '停止',
    'btn_estop': '緊急停止',
    'btn_estop_engaged': '緊急停止中 (クリックで解除)',
    'tab_sys_log': 'システムログ',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'デバイス',
    'tab_mapping': 'チャネルマッピング',
    'mapping_passthrough': '実デバイスをパススルー',
    'mapping_osr6': 'OSR6 仮想 6 軸',
    'mapping_hint_edit': 'ヒント: 編集後は「プロファイルを保存」をクリック',
    'mapping_hint_empty': 'サービス開始後にアクチュエーター覧が自動で読み込まれます',
    'col_channel': 'チャネル',
    'col_enabled': '有効',
    'col_actuator': '対象アクチュエーター',
    'col_invert': '反転',
    'col_scale': 'スケール',
    'col_min': '最小',
    'col_max': '最大',
    'col_midpoint': '中点',
    'col_deadzone': '不感帯',
    'actuator_unmapped': '(未マッピング)',
    'status_idle': '状態: 停止中',
    'status_running': '状態: 稼働中  |  モード: {mode}  |  バックエンド: {backend}  |  ゲームセッション: {sessions}  |  デバイス: {devices}{estop}',
    'status_estop': '  |  緊急停止中!',
    'mode_passthrough': 'パススルー',
    'mode_osr6': 'OSR6 6 軸',
    'backend_connected': '接続済',
    'backend_disconnected': '未接続',
    'devices_empty': '(デバイスなし — Intiface Central が起動してスキャン中か確認してください)',
    'msg_load_profile_title': 'プロファイルを読込',
    'msg_load_profile_running': 'サービスは稼働中です。新しいプロファイルを読み込むには、完全に反映させるために再起動が必要です。続行しますか?',
    'msg_load_profile_ok': 'プロファイルを読み込みました:\n{path}',
    'msg_load_profile_fail': 'プロファイルを読み込めません:\n{path}\n{err}',
    'msg_save_profile_ok': '保存しました{hot}:\n{path}',
    'msg_save_profile_hot': ' (ホット適用)',
    'msg_save_profile_idle': ' (サービス未起動 — 次回開始時に反映)',
    'msg_save_profile_fail': 'プロファイルを書き込めません:\n{path}\n{err}',
    'msg_save_profile_as_title': '名前を付けてプロファイルを保存',
    'msg_save_profile_as_ok': '保存先:\n{path}',
    'msg_start_fail_title': 'GTPB 開始失敗',
    'msg_start_fail_body': 'ブリッジサービスの開始に失敗しました:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\n原因: 待受ポートが既に使われています。「開始」をクリックする前に、他の GTPB インスタンス (`python main.py --headless` を含む) を終了してください。',
    'msg_port_conflict_title': 'ポート競合',
    'msg_port_conflict_body': 'ゲーム側 WebSocket ポート ({ws_port}) が、Intiface Central のバックエンドポート ({backend_port}) と同一です!\n\nGTPB はポート {ws_port} でゲームからの接続を待ち受けると同時に、Intiface Central へのクライアントとしても動作します。両方のポートが同じ場合、ゲーム / GTPB / Intiface Central 間のデータフローが無限ループとなり、「ゲームが Connecting で止まる」「デバイスが見つからない」「Intiface のログが洪水のように流れる」といった問題が発生します。\n\n修正方法:\n  1. Intiface Central → Settings → Server → Listening Port を変更 (例: 12346、12345 以外)\n  2. GTPB の「バックエンド Intiface」欄を新しいポートに合わせて更新\n  3. GTPB の「WebSocket ポート」は 12345 のままにしてください (ゲーム側デフォルト — 変更不可)\n\n開始前にポート競合を解決してください。',
    'log_start_gui': '=== GTPB 開始 (GUI) ===',
    'log_start_headless': '=== GTPB 開始 (headless) ===',
    'log_log_file': 'ログファイル: {path}',
    'log_profile_path': 'プロファイル: {path}',
    'log_language_set': 'UI 言語: {lang}',
    'log_sigint': '割り込みを受信。停止しています...',
    'usage_title': '使い方',
    'usage_text': 'GameToyProtocolBridge (GTPB) は Buttplug v3 プロトコルのブリッジであり、ゲームが WebSocket 経由でハードウェアを制御できるようにします。\n\n═══════════════════ ポート競合 (必読) ═══════════════════\n⚠ GTPB はゲーム側 WebSocket ポート (デフォルト 12345) で待ち受けると同時に、Intiface Central へのクライアントとしても動作します。\n⚠ この 2 つのポートは必ず異なる値にしてください!\n  - ゲーム側 WebSocket ポート = GTPB の「WebSocket ポート」欄 (デフォルト 12345)\n  - Intiface Central ポート    = GTPB の「バックエンド Intiface」欄 (デフォルト ws://127.0.0.1:12346)\n両方が同じ場合、「ゲームが Connecting で止まる」「デバイスが見つからない」、データ無限ループが発生します。\nGTPB は起動時にこれを自動チェックし、強い警告を表示します。\n修正: Intiface Central → Settings → Server Listening Port を 12345 以外の値 (例: 12346) に変更し、GTPB の「バックエンド Intiface」欄をその値に合わせて更新してください。\n\n═══════════════════ データフロー ═══════════════════\n  ゲーム (MultiFunPlayer など) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → 解析 / マッピング / 変換 → Intiface Central → ハードウェア\n\n═══════════════════ ファイル構成 ═══════════════════\n  configsetting.ini    ソフトウェア依存 (工場出荷既定) — 編集不可\n  profiles/*.json      プロファイル (接続設定 + チャネルマッピング)\n  .gtpb_settings       内部状態 (言語、最後に読み込んだプロファイルのパス)\n  gtpb.log             単一ローリングログファイル (上限 10KB)\n\n═══════════════════ クイックスタート ═══════════════════\n  1. Intiface Central を起動し、デバイスが接続されていることを確認\n  2. GTPB を起動。「WebSocket ポート = 12345」のまま、「バックエンド Intiface」に Intiface 実ポートを設定\n  3. ゲーム / MultiFunPlayer を起動し、ws://127.0.0.1:12345 を指定\n  4. GTPB の「チャネルマッピング」タブでマッピングを調整し、「プロファイルを保存」をクリック\n\n═══════════════════ OSR6 6 軸モード ═══════════════════\n  「チャネルマッピング」タブで「OSR6 仮想 6 軸」を選択します。ゲームは仮想 6 軸デバイスを認識します (L0 主軸 / L1 前後 / L2 左右 / R0 ねじり / R1 ロール / R2 ピッチ)。GTPB はマッピングテーブルに従い、これらの軸を実ハードウェアへ転送します。\n\n═══════════════════ ログ ═══════════════════\n  システムログタブ: ソフトウェアのイベントとエラー\n  GameRx/Tx タブ:  ゲームと GTPB 間の Buttplug メッセージ (プロトコルデバッグ用)\n  gtpb.log:        ディスクへミラー出力、最新 10KB を保持\n\n═══════════════════ 緊急停止 ═══════════════════\n  「緊急停止」ボタンはすべてのデバイスコマンドを直ちに遮断し、バックエンドへ StopAllDevices を送信します。もう一度クリックすると解除され、通常の動作に戻ります。\n',
}

_DE_DE: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Sprache',
    'menu_help': 'Hilfe',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': 'Benutzerhandbuch',
    'frame_connection': 'Verbindung (mit Profil gespeichert)',
    'frame_status': 'Status',
    'frame_profile': 'Profil',
    'lbl_listen': 'Listen-Adresse',
    'lbl_ws_port': 'WebSocket-Port',
    'lbl_tcp_port': 'TCP-Port (0=deaktiviert)',
    'lbl_backend': 'Backend Intiface',
    'lbl_profile': 'Profil:',
    'btn_load_profile': 'Profil laden...',
    'btn_save_profile': 'Profil speichern',
    'btn_save_profile_as': 'Profil speichern unter...',
    'btn_start': 'Starten',
    'btn_stop': 'Stoppen',
    'btn_estop': 'Notaus',
    'btn_estop_engaged': 'Notaus aktiv (Klick zum Lösen)',
    'tab_sys_log': 'Systemlog',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Geräte',
    'tab_mapping': 'Kanalzuordnung',
    'mapping_passthrough': 'Echtes Gerät durchreichen',
    'mapping_osr6': 'OSR6 virtuell 6-Achsen',
    'mapping_hint_edit': 'Tipp: nach dem Bearbeiten auf „Profil speichern“ klicken',
    'mapping_hint_empty': 'Aktuatorliste wird nach dem Dienststart automatisch geladen',
    'col_channel': 'Kanal',
    'col_enabled': 'Aktiv',
    'col_actuator': 'Ziel-Aktuator',
    'col_invert': 'Invertieren',
    'col_scale': 'Skalierung',
    'col_min': 'Min',
    'col_max': 'Max',
    'col_midpoint': 'Mitte',
    'col_deadzone': 'Totzone',
    'actuator_unmapped': '(nicht zugeordnet)',
    'status_idle': 'Status: gestoppt',
    'status_running': 'Status: läuft  |  Modus: {mode}  |  Backend: {backend}  |  Game-Sessions: {sessions}  |  Geräte: {devices}{estop}',
    'status_estop': '  |  NOTAUS!',
    'mode_passthrough': 'Pass-Through',
    'mode_osr6': 'OSR6 6-Achsen',
    'backend_connected': 'verbunden',
    'backend_disconnected': 'getrennt',
    'devices_empty': '(keine Geräte — bitte prüfen, ob Intiface Central läuft und scannt)',
    'msg_load_profile_title': 'Profil laden',
    'msg_load_profile_running': 'Der Dienst läuft bereits; das Laden eines neuen Profils erfordert einen Neustart, damit es vollständig greift.\nFortfahren?',
    'msg_load_profile_ok': 'Profil geladen:\n{path}',
    'msg_load_profile_fail': 'Profil kann nicht gelesen werden:\n{path}\n{err}',
    'msg_save_profile_ok': 'Gespeichert{hot}:\n{path}',
    'msg_save_profile_hot': ' und sofort angewendet',
    'msg_save_profile_idle': ' (Dienst läuft nicht — wird beim nächsten Start angewendet)',
    'msg_save_profile_fail': 'Profil kann nicht geschrieben werden:\n{path}\n{err}',
    'msg_save_profile_as_title': 'Profil speichern unter',
    'msg_save_profile_as_ok': 'Gespeichert unter:\n{path}',
    'msg_start_fail_title': 'GTPB-Start fehlgeschlagen',
    'msg_start_fail_body': 'Bridge-Dienst konnte nicht gestartet werden:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\nUrsache: Listen-Port bereits belegt — beende andere laufende GTPB-Instanzen (auch `python main.py --headless`), bevor du auf Start klickst.',
    'msg_port_conflict_title': 'Port-Konflikt',
    'msg_port_conflict_body': 'Der lokale Game-seitige WebSocket-Port ({ws_port}) ist DERSELBE wie der Intiface-Central-Backend-Port ({backend_port})!\n\nGTPB lauscht auf Port {ws_port} für das Spiel UND agiert gleichzeitig als Client zu Intiface Central. Sind beide Ports identisch, gerät der Datenfluss zwischen Spiel / GTPB / Intiface Central in eine Endlosschleife, was zu „Spiel hängt bei Connecting“, „Gerät nicht gefunden“ und „Intiface-Log flutet“ führt.\n\nBehebung:\n  1. Intiface Central → Einstellungen → Server → Listening Port ändern (z. B. 12346, NICHT 12345)\n  2. GTPBs Feld „Backend Intiface“ auf den neuen Port anpassen\n  3. GTPBs „WebSocket-Port“ bei 12345 belassen (Standard-Game-Port — nicht ändern)\n\nBehebe den Port-Konflikt vor dem Start.',
    'log_start_gui': '=== GTPB-Start (GUI) ===',
    'log_start_headless': '=== GTPB-Start (Headless) ===',
    'log_log_file': 'Logdatei: {path}',
    'log_profile_path': 'Profil: {path}',
    'log_language_set': 'UI-Sprache: {lang}',
    'log_sigint': 'Unterbrechung empfangen, stoppe...',
    'usage_title': 'Benutzerhandbuch',
    'usage_text': 'GameToyProtocolBridge (GTPB) ist eine Buttplug-v3-Protokollbrücke, die Spielen erlaubt, Hardware über WebSocket zu steuern.\n\n═══════════════════ Port-Konflikt (UNBEDINGT LESEN) ═══════════════════\n⚠ GTPB lauscht auf dem Game-seitigen WebSocket-Port (Standard 12345) UND agiert gleichzeitig als Client zu Intiface Central.\n⚠ Diese beiden Ports MÜSSEN unterschiedlich sein!\n  - Game-seitiger WebSocket-Port = GTPBs Feld „WebSocket-Port“ (Standard 12345)\n  - Intiface-Central-Port        = GTPBs Feld „Backend Intiface“ (Standard ws://127.0.0.1:12346)\nSind sie identisch, treten „Spiel hängt bei Connecting“, „Gerät nicht gefunden“ und endlose Datenschleifen auf.\nGTPB prüft dies beim Start automatisch und zeigt eine deutliche Warnung.\nBehebung: Intiface Central → Einstellungen → Server Listening Port auf einen anderen Wert als 12345 setzen (z. B. 12346) und GTPBs Feld „Backend Intiface“ entsprechend anpassen.\n\n═══════════════════ Datenfluss ═══════════════════\n  Spiel (MultiFunPlayer usw.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → Parsen / Zuordnen / Transformieren → Intiface Central → Hardware\n\n═══════════════════ Dateilayout ═══════════════════\n  configsetting.ini    Software-Abhängigkeit (Werkseinstellungen) — nicht ändern\n  profiles/*.json      Deine Profile (Verbindungseinstellungen + Kanalzuordnung)\n  .gtpb_settings       Interner Zustand (Sprache, Pfad des zuletzt geladenen Profils)\n  gtpb.log             Einzelne rollierende Logdatei (10 KB Obergrenze)\n\n═══════════════════ Schnellstart ═══════════════════\n  1. Intiface Central starten und prüfen, ob das Gerät verbunden ist\n  2. GTPB starten; „WebSocket-Port = 12345“ beibehalten und „Backend Intiface“ auf den tatsächlichen Intiface-Port setzen\n  3. Spiel / MultiFunPlayer starten und auf ws://127.0.0.1:12345 zeigen lassen\n  4. Kanalzuordnung im Tab „Kanalzuordnung“ anpassen, dann auf „Profil speichern“ klicken\n\n═══════════════════ OSR6 6-Achsen-Modus ═══════════════════\n  Im Tab „Kanalzuordnung“ „OSR6 virtuell 6-Achsen“ auswählen. Das Spiel sieht ein virtuelles 6-Achsen-Gerät (L0 Haupt / L1 vor-zurück / L2 links-rechts / R0 Drehung / R1 Rollen / R2 Nicken). GTPB leitet diese Achsen gemäß der Zuordnungstabelle an die reale Hardware weiter.\n\n═══════════════════ Logs ═══════════════════\n  Systemlog-Tab: Software-Ereignisse und Fehler\n  GameRx/Tx-Tab:  Buttplug-Nachrichten zwischen Spiel und GTPB (zur Protokoll-Diagnose)\n  gtpb.log:        auf Festplatte gespiegelt, behält die letzten 10 KB\n\n═══════════════════ Notaus ═══════════════════\n  Die Schaltfläche „Notaus“ fängt alle Gerätebefehle sofort ab und sendet StopAllDevices an das Backend. Erneut klicken, um zu lösen und den normalen Betrieb wiederherzustellen.\n',
}

_FR_FR: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Langue',
    'menu_help': 'Aide',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': "Guide d'utilisation",
    'frame_connection': 'Connexion (enregistrée avec le profil)',
    'frame_status': 'État',
    'frame_profile': 'Profil',
    'lbl_listen': "Adresse d'écoute",
    'lbl_ws_port': 'Port WebSocket',
    'lbl_tcp_port': 'Port TCP (0=désactivé)',
    'lbl_backend': 'Backend Intiface',
    'lbl_profile': 'Profil :',
    'btn_load_profile': 'Charger un profil...',
    'btn_save_profile': 'Enregistrer le profil',
    'btn_save_profile_as': 'Enregistrer le profil sous...',
    'btn_start': 'Démarrer',
    'btn_stop': 'Arrêter',
    'btn_estop': "Arrêt d'urgence",
    'btn_estop_engaged': "Arrêt d'urgence activé (cliquer pour relâcher)",
    'tab_sys_log': 'Journal système',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Appareils',
    'tab_mapping': 'Mappage des canaux',
    'mapping_passthrough': 'Pass-through du périphérique réel',
    'mapping_osr6': 'OSR6 virtuel 6 axes',
    'mapping_hint_edit': 'Astuce : cliquer sur « Enregistrer le profil » après modification',
    'mapping_hint_empty': 'La liste des actionneurs se charge automatiquement après le démarrage du service',
    'col_channel': 'Canal',
    'col_enabled': 'Activé',
    'col_actuator': 'Actionneur cible',
    'col_invert': 'Inverser',
    'col_scale': 'Échelle',
    'col_min': 'Min',
    'col_max': 'Max',
    'col_midpoint': 'Point médian',
    'col_deadzone': 'Zone morte',
    'actuator_unmapped': '(non mappé)',
    'status_idle': 'État : arrêté',
    'status_running': 'État : en cours  |  Mode : {mode}  |  Backend : {backend}  |  Sessions de jeu : {sessions}  |  Appareils : {devices}{estop}',
    'status_estop': "  |  ARRÊT D'URGENCE !",
    'mode_passthrough': 'pass-through',
    'mode_osr6': 'OSR6 6 axes',
    'backend_connected': 'connecté',
    'backend_disconnected': 'déconnecté',
    'devices_empty': "(aucun appareil — vérifier qu'Intiface Central tourne et scanne)",
    'msg_load_profile_title': 'Charger un profil',
    'msg_load_profile_running': "Le service est en cours d'exécution ; le chargement d'un nouveau profil nécessite un redémarrage pour être pleinement appliqué.\nContinuer ?",
    'msg_load_profile_ok': 'Profil chargé :\n{path}',
    'msg_load_profile_fail': 'Impossible de lire le profil :\n{path}\n{err}',
    'msg_save_profile_ok': 'Enregistré{hot} :\n{path}',
    'msg_save_profile_hot': ' et appliqué immédiatement',
    'msg_save_profile_idle': ' (service non démarré — appliqué au prochain démarrage)',
    'msg_save_profile_fail': "Impossible d'écrire le profil :\n{path}\n{err}",
    'msg_save_profile_as_title': 'Enregistrer le profil sous',
    'msg_save_profile_as_ok': 'Enregistré sous :\n{path}',
    'msg_start_fail_title': 'Échec du démarrage de GTPB',
    'msg_start_fail_body': "Le service de pont n'a pas pu démarrer :\n{err}{hint}",
    'msg_start_fail_port_hint': "\n\nCause : le port d'écoute est déjà utilisé — ferme les autres instances de GTPB en cours d'exécution (y compris `python main.py --headless`) avant de cliquer sur Démarrer.",
    'msg_port_conflict_title': 'Conflit de ports',
    'msg_port_conflict_body': "Le port WebSocket côté jeu ({ws_port}) est IDENTIQUE au port backend d'Intiface Central ({backend_port}) !\n\nGTPB écoute sur le port {ws_port} pour le jeu ET agit également comme client vers Intiface Central. Si les deux ports sont identiques, le flux de données entre le jeu / GTPB / Intiface Central entre dans une boucle infinie, provoquant « le jeu reste bloqué sur Connecting », « périphérique introuvable » et « inondation des logs d'Intiface ».\n\nCorrectif :\n  1. Intiface Central → Paramètres → Serveur → modifier le Listening Port (p. ex. 12346, PAS 12345)\n  2. Mettre à jour le champ « Backend Intiface » de GTPB pour qu'il corresponde au nouveau port\n  3. Garder le « Port WebSocket » de GTPB à 12345 (port par défaut côté jeu — ne pas modifier)\n\nRésoudre le conflit de ports avant de démarrer.",
    'log_start_gui': '=== Démarrage de GTPB (GUI) ===',
    'log_start_headless': '=== Démarrage de GTPB (headless) ===',
    'log_log_file': 'Fichier de log : {path}',
    'log_profile_path': 'Profil : {path}',
    'log_language_set': "Langue de l'UI : {lang}",
    'log_sigint': 'Interruption reçue, arrêt en cours...',
    'usage_title': "Guide d'utilisation",
    'usage_text': "GameToyProtocolBridge (GTPB) est un pont vers le protocole Buttplug v3 qui permet aux jeux de piloter du matériel via WebSocket.\n\n═══════════════════ Conflit de ports (À LIRE IMPÉRATIVEMENT) ═══════════════════\n⚠ GTPB écoute sur le port WebSocket côté jeu (par défaut 12345) ET agit également comme client se connectant à Intiface Central.\n⚠ Ces deux ports DOIVENT être différents !\n  - Port WebSocket côté jeu = champ « Port WebSocket » de GTPB (par défaut 12345)\n  - Port Intiface Central   = champ « Backend Intiface » de GTPB (par défaut ws://127.0.0.1:12346)\nS'ils sont identiques, vous verrez « le jeu reste bloqué sur Connecting », « périphérique introuvable » et des boucles de données infinies.\nGTPB vérifie cela automatiquement au démarrage et affiche un avertissement explicite.\nCorrectif : ouvrir Intiface Central → Paramètres → Server Listening Port, choisir une valeur différente de 12345 (p. ex. 12346), puis mettre à jour le champ « Backend Intiface » de GTPB en conséquence.\n\n═══════════════════ Flux de données ═══════════════════\n  Jeu (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → analyse / mappage / transformation → Intiface Central → matériel\n\n═══════════════════ Organisation des fichiers ═══════════════════\n  configsetting.ini    Dépendance logicielle (valeurs d'usine) — ne pas modifier\n  profiles/*.json      Vos profils (paramètres de connexion + mappage des canaux)\n  .gtpb_settings       État interne (langue, chemin du dernier profil chargé)\n  gtpb.log             Fichier de log unique et rotatif (plafonné à 10 Ko)\n\n═══════════════════ Démarrage rapide ═══════════════════\n  1. Démarrer Intiface Central et vérifier que le périphérique est connecté\n  2. Démarrer GTPB ; conserver « Port WebSocket = 12345 » et saisir dans « Backend Intiface » le port réel d'Intiface\n  3. Lancer le jeu / MultiFunPlayer et le pointer vers ws://127.0.0.1:12345\n  4. Ajuster le mappage des canaux dans l'onglet « Mappage des canaux » de GTPB, puis cliquer sur « Enregistrer le profil »\n\n═══════════════════ Mode OSR6 6 axes ═══════════════════\n  Dans l'onglet « Mappage des canaux », sélectionner « OSR6 virtuel 6 axes ». Le jeu voit un périphérique virtuel à 6 axes (L0 principal / L1 avant-arrière / L2 gauche-droite / R0 torsion / R1 roulis / R2 tangage). GTPB transmet ces axes à votre matériel réel selon la table de mappage.\n\n═══════════════════ Logs ═══════════════════\n  Onglet Journal système : événements logiciels et erreurs\n  Onglet GameRx/Tx :      messages Buttplug entre le jeu et GTPB (pour le débogage du protocole)\n  gtpb.log :              mis en miroir sur disque, conserve les 10 derniers Ko\n\n═══════════════════ Arrêt d'urgence ═══════════════════\n  Le bouton « Arrêt d'urgence » intercepte immédiatement toutes les commandes envoyées aux appareils et envoie StopAllDevices au backend. Cliquer à nouveau pour relâcher et reprendre le fonctionnement normal.\n",
}

_RU_RU: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Язык',
    'menu_help': 'Справка',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': 'Руководство пользователя',
    'frame_connection': 'Подключение (сохраняется в профиль)',
    'frame_status': 'Состояние',
    'frame_profile': 'Профиль',
    'lbl_listen': 'Адрес прослушивания',
    'lbl_ws_port': 'Порт WebSocket',
    'lbl_tcp_port': 'Порт TCP (0=отключён)',
    'lbl_backend': 'Бэкенд Intiface',
    'lbl_profile': 'Профиль:',
    'btn_load_profile': 'Загрузить профиль...',
    'btn_save_profile': 'Сохранить профиль',
    'btn_save_profile_as': 'Сохранить профиль как...',
    'btn_start': 'Запуск',
    'btn_stop': 'Остановить',
    'btn_estop': 'Аварийный останов',
    'btn_estop_engaged': 'Аварийный останов активен (нажмите, чтобы снять)',
    'tab_sys_log': 'Системный журнал',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Устройства',
    'tab_mapping': 'Привязка каналов',
    'mapping_passthrough': 'Сквозная передача реального устройства',
    'mapping_osr6': 'OSR6 виртуальный 6-осевой',
    'mapping_hint_edit': 'Подсказка: после редактирования нажмите «Сохранить профиль»',
    'mapping_hint_empty': 'Список исполнительных механизмов загрузится автоматически после запуска сервиса',
    'col_channel': 'Канал',
    'col_enabled': 'Включён',
    'col_actuator': 'Целевой исполнитель',
    'col_invert': 'Инверсия',
    'col_scale': 'Масштаб',
    'col_min': 'Мин',
    'col_max': 'Макс',
    'col_midpoint': 'Середина',
    'col_deadzone': 'Мёртвая зона',
    'actuator_unmapped': '(не задан)',
    'status_idle': 'Состояние: остановлен',
    'status_running': 'Состояние: работает  |  Режим: {mode}  |  Бэкенд: {backend}  |  Игровых сессий: {sessions}  |  Устройств: {devices}{estop}',
    'status_estop': '  |  АВАРИЙНЫЙ ОСТАНОВ!',
    'mode_passthrough': 'сквозной',
    'mode_osr6': 'OSR6 6-осевой',
    'backend_connected': 'подключён',
    'backend_disconnected': 'отключён',
    'devices_empty': '(устройств нет — убедитесь, что Intiface Central запущен и выполняет сканирование)',
    'msg_load_profile_title': 'Загрузить профиль',
    'msg_load_profile_running': 'Сервис уже работает; загрузка нового профиля потребует перезапуска для полного применения.\nПродолжить?',
    'msg_load_profile_ok': 'Профиль загружен:\n{path}',
    'msg_load_profile_fail': 'Не удалось прочитать профиль:\n{path}\n{err}',
    'msg_save_profile_ok': 'Сохранено{hot}:\n{path}',
    'msg_save_profile_hot': ' и применено немедленно',
    'msg_save_profile_idle': ' (сервис не запущен — будет применено при следующем запуске)',
    'msg_save_profile_fail': 'Не удалось записать профиль:\n{path}\n{err}',
    'msg_save_profile_as_title': 'Сохранить профиль как',
    'msg_save_profile_as_ok': 'Сохранено в:\n{path}',
    'msg_start_fail_title': 'Не удалось запустить GTPB',
    'msg_start_fail_body': 'Не удалось запустить службу моста:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\nПричина: порт прослушивания уже занят — закройте другие работающие экземпляры GTPB (включая `python main.py --headless`) перед нажатием «Запуск».',
    'msg_port_conflict_title': 'Конфликт портов',
    'msg_port_conflict_body': 'Локальный игровой WebSocket-порт ({ws_port}) СОВПАДАЕТ с портом бэкенда Intiface Central ({backend_port})!\n\nGTPB ожидает подключения игры на порту {ws_port} И одновременно выступает клиентом к Intiface Central. Если оба порта одинаковы, поток данных между игрой / GTPB / Intiface Central зациклится бесконечно, вызывая «игра зависает на Connecting», «устройство не найдено» и «затопление логов Intiface».\n\nРешение:\n  1. Intiface Central → Настройки → Сервер → измените Listening Port (например, 12346, НЕ 12345)\n  2. Обновите поле «Бэкенд Intiface» в GTPB, указав новый порт\n  3. Оставьте «Порт WebSocket» GTPB равным 12345 (игровой порт по умолчанию — не менять)\n\nУстраните конфликт портов перед запуском.',
    'log_start_gui': '=== Запуск GTPB (GUI) ===',
    'log_start_headless': '=== Запуск GTPB (headless) ===',
    'log_log_file': 'Файл журнала: {path}',
    'log_profile_path': 'Профиль: {path}',
    'log_language_set': 'Язык интерфейса: {lang}',
    'log_sigint': 'Получен сигнал прерывания, останавливаюсь...',
    'usage_title': 'Руководство пользователя',
    'usage_text': 'GameToyProtocolBridge (GTPB) — это мост протокола Buttplug v3, позволяющий играм управлять оборудованием через WebSocket.\n\n═══════════════════ Конфликт портов (ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ) ═══════════════════\n⚠ GTPB ожидает подключения игры на игровом WebSocket-порту (по умолчанию 12345) И одновременно выступает клиентом, подключающимся к Intiface Central.\n⚠ Эти два порта ДОЛЖНЫ различаться!\n  - Игровой WebSocket-порт = поле «Порт WebSocket» в GTPB (по умолчанию 12345)\n  - Порт Intiface Central   = поле «Бэкенд Intiface» в GTPB (по умолчанию ws://127.0.0.1:12346)\nЕсли они совпадают, вы увидите «игра зависает на Connecting», «устройство не найдено» и бесконечные циклы данных.\nGTPB автоматически проверяет это при запуске и выводит строгое предупреждение.\nРешение: откройте Intiface Central → Настройки → Server Listening Port, установите значение, отличное от 12345 (например, 12346), затем обновите поле «Бэкенд Intiface» в GTPB соответствующим образом.\n\n═══════════════════ Поток данных ═══════════════════\n  Игра (MultiFunPlayer и т. п.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → разбор / привязка / преобразование → Intiface Central → оборудование\n\n═══════════════════ Файловая структура ═══════════════════\n  configsetting.ini    Зависимость ПО (заводские значения) — не редактировать\n  profiles/*.json      Ваши профили (параметры подключения + привязка каналов)\n  .gtpb_settings       Внутреннее состояние (язык, путь к последнему загруженному профилю)\n  gtpb.log             Единый ротируемый файл журнала (предел 10 КБ)\n\n═══════════════════ Быстрый старт ═══════════════════\n  1. Запустите Intiface Central и убедитесь, что устройство подключено\n  2. Запустите GTPB; оставьте «Порт WebSocket = 12345» и укажите в «Бэкенд Intiface» фактический порт Intiface\n  3. Запустите игру / MultiFunPlayer и укажите адрес ws://127.0.0.1:12345\n  4. Настройте привязку каналов на вкладке «Привязка каналов» GTPB, затем нажмите «Сохранить профиль»\n\n═══════════════════ Режим OSR6 6 осей ═══════════════════\n  На вкладке «Привязка каналов» выберите «OSR6 виртуальный 6-осевой». Игра увидит виртуальное 6-осевое устройство (L0 основной / L1 вперёд-назад / L2 влево-вправо / R0 скручивание / R1 крен / R2 тангаж). GTPB будет передавать эти оси на ваше реальное оборудование согласно таблице привязки.\n\n═══════════════════ Журналы ═══════════════════\n  Вкладка Системный журнал: события и ошибки ПО\n  Вкладка GameRx/Tx:       сообщения Buttplug между игрой и GTPB (для отладки протокола)\n  gtpb.log:                 зеркалируется на диск, сохраняет последние 10 КБ\n\n═══════════════════ Аварийный останов ═══════════════════\n  Кнопка «Аварийный останов» немедленно перехватывает все команды устройствам и отправляет StopAllDevices бэкенду. Нажмите ещё раз, чтобы снять останов и вернуться к нормальной работе.\n',
}

_ES_ES: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Idioma',
    'menu_help': 'Ayuda',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': 'Guía de uso',
    'frame_connection': 'Conexión (guardada con el perfil)',
    'frame_status': 'Estado',
    'frame_profile': 'Perfil',
    'lbl_listen': 'Dirección de escucha',
    'lbl_ws_port': 'Puerto WebSocket',
    'lbl_tcp_port': 'Puerto TCP (0=desactivado)',
    'lbl_backend': 'Backend Intiface',
    'lbl_profile': 'Perfil:',
    'btn_load_profile': 'Cargar perfil...',
    'btn_save_profile': 'Guardar perfil',
    'btn_save_profile_as': 'Guardar perfil como...',
    'btn_start': 'Iniciar',
    'btn_stop': 'Detener',
    'btn_estop': 'Parada de emergencia',
    'btn_estop_engaged': 'Parada de emergencia activada (clic para liberar)',
    'tab_sys_log': 'Registro del sistema',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Dispositivos',
    'tab_mapping': 'Mapeo de canales',
    'mapping_passthrough': 'Paso directo del dispositivo real',
    'mapping_osr6': 'OSR6 virtual 6 ejes',
    'mapping_hint_edit': 'Consejo: haga clic en «Guardar perfil» después de editar',
    'mapping_hint_empty': 'La lista de actuadores se carga automáticamente al iniciar el servicio',
    'col_channel': 'Canal',
    'col_enabled': 'Activado',
    'col_actuator': 'Actuador destino',
    'col_invert': 'Invertir',
    'col_scale': 'Escala',
    'col_min': 'Mín',
    'col_max': 'Máx',
    'col_midpoint': 'Punto medio',
    'col_deadzone': 'Zona muerta',
    'actuator_unmapped': '(sin asignar)',
    'status_idle': 'Estado: detenido',
    'status_running': 'Estado: en ejecución  |  Modo: {mode}  |  Backend: {backend}  |  Sesiones de juego: {sessions}  |  Dispositivos: {devices}{estop}',
    'status_estop': '  |  ¡PARADA DE EMERGENCIA!',
    'mode_passthrough': 'paso directo',
    'mode_osr6': 'OSR6 6 ejes',
    'backend_connected': 'conectado',
    'backend_disconnected': 'desconectado',
    'devices_empty': '(sin dispositivos — asegúrese de que Intiface Central esté en ejecución y escaneando)',
    'msg_load_profile_title': 'Cargar perfil',
    'msg_load_profile_running': 'El servicio está en ejecución; cargar un nuevo perfil requiere reiniciar para aplicarlo por completo.\n¿Continuar?',
    'msg_load_profile_ok': 'Perfil cargado:\n{path}',
    'msg_load_profile_fail': 'No se puede leer el perfil:\n{path}\n{err}',
    'msg_save_profile_ok': 'Guardado{hot}:\n{path}',
    'msg_save_profile_hot': ' y aplicado en caliente',
    'msg_save_profile_idle': ' (servicio no en ejecución — se aplicará en el próximo inicio)',
    'msg_save_profile_fail': 'No se puede escribir el perfil:\n{path}\n{err}',
    'msg_save_profile_as_title': 'Guardar perfil como',
    'msg_save_profile_as_ok': 'Guardado en:\n{path}',
    'msg_start_fail_title': 'Error al iniciar GTPB',
    'msg_start_fail_body': 'El servicio de puente no se pudo iniciar:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\nCausa: el puerto de escucha ya está en uso — cierre otras instancias de GTPB en ejecución (incluido `python main.py --headless`) antes de hacer clic en Iniciar.',
    'msg_port_conflict_title': 'Conflicto de puertos',
    'msg_port_conflict_body': '¡El puerto WebSocket del lado del juego ({ws_port}) es IDÉNTICO al puerto del backend de Intiface Central ({backend_port})!\n\nGTPB escucha en el puerto {ws_port} para el juego Y también actúa como cliente hacia Intiface Central. Si ambos puertos son iguales, el flujo de datos entre juego / GTPB / Intiface Central entrará en un bucle infinito, provocando «el juego se queda en Connecting», «dispositivo no encontrado» e «inundación del registro de Intiface».\n\nSolución:\n  1. Intiface Central → Ajustes → Servidor → cambie el Listening Port (p. ej. 12346, NO 12345)\n  2. Actualice el campo «Backend Intiface» de GTPB al nuevo puerto\n  3. Mantenga el «Puerto WebSocket» de GTPB en 12345 (puerto por defecto del juego — no lo cambie)\n\nResuelva el conflicto de puertos antes de iniciar.',
    'log_start_gui': '=== Inicio de GTPB (GUI) ===',
    'log_start_headless': '=== Inicio de GTPB (sin cabeza) ===',
    'log_log_file': 'Archivo de registro: {path}',
    'log_profile_path': 'Perfil: {path}',
    'log_language_set': 'Idioma de la UI: {lang}',
    'log_sigint': 'Interrupción recibida, deteniendo...',
    'usage_title': 'Guía de uso',
    'usage_text': 'GameToyProtocolBridge (GTPB) es un puente del protocolo Buttplug v3 que permite a los juegos controlar hardware a través de WebSocket.\n\n═══════════════════ Conflicto de puertos (LECTURA OBLIGATORIA) ═══════════════════\n⚠ GTPB escucha en el puerto WebSocket del lado del juego (por defecto 12345) Y también actúa como cliente conectándose a Intiface Central.\n⚠ ¡Estos dos puertos DEBEN ser diferentes!\n  - Puerto WebSocket del juego = campo «Puerto WebSocket» de GTPB (por defecto 12345)\n  - Puerto de Intiface Central  = campo «Backend Intiface» de GTPB (por defecto ws://127.0.0.1:12346)\nSi coinciden, verá «el juego se queda en Connecting», «dispositivo no encontrado» y bucles de datos infinitos.\nGTPB lo verifica automáticamente al arrancar y muestra una advertencia explícita.\nSolución: abra Intiface Central → Ajustes → Server Listening Port, cámbielo a un valor distinto de 12345 (por ejemplo, 12346) y actualice el campo «Backend Intiface» de GTPB en consecuencia.\n\n═══════════════════ Flujo de datos ═══════════════════\n  Juego (MultiFunPlayer, etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → análisis / mapeo / transformación → Intiface Central → hardware\n\n═══════════════════ Distribución de archivos ═══════════════════\n  configsetting.ini    Dependencia del software (valores de fábrica) — no editar\n  profiles/*.json      Sus perfiles (ajustes de conexión + mapeo de canales)\n  .gtpb_settings       Estado interno (idioma, ruta del último perfil cargado)\n  gtpb.log             Archivo de registro único y rotativo (tope 10 KB)\n\n═══════════════════ Inicio rápido ═══════════════════\n  1. Inicie Intiface Central y confirme que el dispositivo está conectado\n  2. Inicie GTPB; mantenga «Puerto WebSocket = 12345» y establezca en «Backend Intiface» el puerto real de Intiface\n  3. Lance el juego / MultiFunPlayer y apúntelo a ws://127.0.0.1:12345\n  4. Ajuste el mapeo de canales en la pestaña «Mapeo de canales» de GTPB y haga clic en «Guardar perfil»\n\n═══════════════════ Modo OSR6 6 ejes ═══════════════════\n  En la pestaña «Mapeo de canales», seleccione «OSR6 virtual 6 ejes». El juego verá un dispositivo virtual de 6 ejes (L0 principal / L1 adelante-atrás / L2 izquierda-derecha / R0 giro / R1 alabeo / R2 cabeceo). GTPB reenviará estos ejes a su hardware real según la tabla de mapeo.\n\n═══════════════════ Registros ═══════════════════\n  Pestaña Registro del sistema: eventos y errores del software\n  Pestaña GameRx/Tx:           mensajes Buttplug entre el juego y GTPB (para depurar el protocolo)\n  gtpb.log:                     volcado a disco, conserva los últimos 10 KB\n\n═══════════════════ Parada de emergencia ═══════════════════\n  El botón «Parada de emergencia» intercepta inmediatamente todos los comandos a los dispositivos y envía StopAllDevices al backend. Haga clic de nuevo para liberar y reanudar el funcionamiento normal.\n',
}

_KO_KR: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': '언어',
    'menu_help': '도움말',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': '사용 설명',
    'frame_connection': '연결 설정 (프로필에 저장)',
    'frame_status': '상태',
    'frame_profile': '프로필',
    'lbl_listen': '수신 주소',
    'lbl_ws_port': 'WebSocket 포트',
    'lbl_tcp_port': 'TCP 포트 (0=비활성화)',
    'lbl_backend': '백엔드 Intiface',
    'lbl_profile': '프로필:',
    'btn_load_profile': '프로필 불러오기...',
    'btn_save_profile': '프로필 저장',
    'btn_save_profile_as': '프로필을 다른 이름으로 저장...',
    'btn_start': '시작',
    'btn_stop': '중지',
    'btn_estop': '긴급 정지',
    'btn_estop_engaged': '긴급 정지 활성화됨 (클릭하여 해제)',
    'tab_sys_log': '시스템 로그',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': '장치',
    'tab_mapping': '채널 매핑',
    'mapping_passthrough': '실제 장치 통과',
    'mapping_osr6': 'OSR6 가상 6축',
    'mapping_hint_edit': '팁: 편집 후 "프로필 저장"을 클릭하세요',
    'mapping_hint_empty': '서비스 시작 후 액추에이터 목록이 자동으로 로드됩니다',
    'col_channel': '채널',
    'col_enabled': '활성화',
    'col_actuator': '대상 액추에이터',
    'col_invert': '반전',
    'col_scale': '배율',
    'col_min': '최소',
    'col_max': '최대',
    'col_midpoint': '중간점',
    'col_deadzone': '데드존',
    'actuator_unmapped': '(매핑되지 않음)',
    'status_idle': '상태: 중지됨',
    'status_running': '상태: 실행 중  |  모드: {mode}  |  백엔드: {backend}  |  게임 세션: {sessions}  |  장치: {devices}{estop}',
    'status_estop': '  |  긴급 정지 중!',
    'mode_passthrough': '통과',
    'mode_osr6': 'OSR6 6축',
    'backend_connected': '연결됨',
    'backend_disconnected': '연결 끊김',
    'devices_empty': '(장치 없음 — Intiface Central이 실행 중이고 스캔 중인지 확인하세요)',
    'msg_load_profile_title': '프로필 불러오기',
    'msg_load_profile_running': '서비스가 실행 중입니다. 새 프로필을 로드하려면 완전히 적용하려면 다시 시작해야 합니다.\n계속하시겠습니까?',
    'msg_load_profile_ok': '프로필을 불러왔습니다:\n{path}',
    'msg_load_profile_fail': '프로필을 읽을 수 없습니다:\n{path}\n{err}',
    'msg_save_profile_ok': '저장됨{hot}:\n{path}',
    'msg_save_profile_hot': ' 및 즉시 적용됨',
    'msg_save_profile_idle': ' (서비스가 실행 중이 아님 — 다음 시작 시 적용됨)',
    'msg_save_profile_fail': '프로필을 쓸 수 없습니다:\n{path}\n{err}',
    'msg_save_profile_as_title': '프로필을 다른 이름으로 저장',
    'msg_save_profile_as_ok': '저장 위치:\n{path}',
    'msg_start_fail_title': 'GTPB 시작 실패',
    'msg_start_fail_body': '브리지 서비스를 시작하지 못했습니다:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\n원인: 수신 포트가 이미 사용 중입니다 — "시작"을 클릭하기 전에 다른 실행 중인 GTPB 인스턴스(`python main.py --headless` 포함)를 종료하세요.',
    'msg_port_conflict_title': '포트 충돌',
    'msg_port_conflict_body': '로컬 게임 측 WebSocket 포트({ws_port})가 Intiface Central 백엔드 포트({backend_port})와 동일합니다!\n\nGTPB는 게임을 위해 포트 {ws_port}에서 수신 대기하면서 동시에 Intiface Central에 클라이언트로 연결됩니다. 두 포트가 같으면 게임 / GTPB / Intiface Central 간의 데이터 흐름이 무한 루프에 빠져 "게임이 Connecting에서 멈춤", "장치를 찾을 수 없음", "Intiface 로그가 넘쳐남"이 발생합니다.\n\n해결 방법:\n  1. Intiface Central → 설정 → 서버 → Listening Port 변경 (예: 12346, 12345는 사용하지 마세요)\n  2. GTPB의 "백엔드 Intiface" 필드를 새 포트에 맞게 업데이트\n  3. GTPB의 "WebSocket 포트"는 12345로 유지 (게임 측 기본 포트 — 변경하지 마세요)\n\n시작 전에 포트 충돌을 해결하세요.',
    'log_start_gui': '=== GTPB 시작 (GUI) ===',
    'log_start_headless': '=== GTPB 시작 (headless) ===',
    'log_log_file': '로그 파일: {path}',
    'log_profile_path': '프로필: {path}',
    'log_language_set': 'UI 언어: {lang}',
    'log_sigint': '종료 신호 수신, 중지 중...',
    'usage_title': '사용 설명',
    'usage_text': 'GameToyProtocolBridge (GTPB)는 게임이 WebSocket을 통해 하드웨어를 제어할 수 있게 해주는 Buttplug v3 프로토콜 브리지입니다.\n\n═══════════════════ 포트 충돌 (필독) ═══════════════════\n⚠ GTPB는 게임 측 WebSocket 포트(기본값 12345)에서 수신 대기하면서 동시에 Intiface Central에 연결되는 클라이언트 역할도 합니다.\n⚠ 이 두 포트는 반드시 달라야 합니다!\n  - 게임 측 WebSocket 포트 = GTPB의 "WebSocket 포트" 필드 (기본값 12345)\n  - Intiface Central 포트   = GTPB의 "백엔드 Intiface" 필드 (기본값 ws://127.0.0.1:12346)\n동일할 경우 "게임이 Connecting에서 멈춤", "장치를 찾을 수 없음", 데이터 무한 루프가 발생합니다.\nGTPB는 시작 시 이를 자동으로 확인하고 강력한 경고를 표시합니다.\n해결 방법: Intiface Central → 설정 → Server Listening Port를 12345가 아닌 값(예: 12346)으로 변경한 후, GTPB의 "백엔드 Intiface" 필드를 해당 값에 맞게 업데이트하세요.\n\n═══════════════════ 데이터 흐름 ═══════════════════\n  게임 (MultiFunPlayer 등) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → 분석 / 매핑 / 변환 → Intiface Central → 하드웨어\n\n═══════════════════ 파일 구조 ═══════════════════\n  configsetting.ini    소프트웨어 종속성 (출고 설정) — 편집하지 마세요\n  profiles/*.json      사용자 프로필 (연결 설정 + 채널 매핑)\n  .gtpb_settings       내부 상태 (언어, 마지막으로 불러온 프로필 경로)\n  gtpb.log             단일 롤링 로그 파일 (10KB 상한)\n\n═══════════════════ 빠른 시작 ═══════════════════\n  1. Intiface Central을 시작하고 장치가 연결되었는지 확인\n  2. GTPB를 시작합니다. "WebSocket 포트 = 12345"를 유지하고 "백엔드 Intiface"에 Intiface의 실제 포트를 설정\n  3. 게임 / MultiFunPlayer를 시작하고 ws://127.0.0.1:12345에 연결\n  4. GTPB의 "채널 매핑" 탭에서 매핑을 조정한 후 "프로필 저장"을 클릭\n\n═══════════════════ OSR6 6축 모드 ═══════════════════\n  "채널 매핑" 탭에서 "OSR6 가상 6축"을 선택합니다. 게임은 가상 6축 장치를 인식합니다 (L0 주축 / L1 앞뒤 / L2 좌우 / R0 비틀기 / R1 롤 / R2 피치). GTPB는 매핑 테이블에 따라 이러한 축을 실제 하드웨어로 전달합니다.\n\n═══════════════════ 로그 ═══════════════════\n  시스템 로그 탭: 소프트웨어 이벤트 및 오류\n  GameRx/Tx 탭:   게임과 GTPB 간의 Buttplug 메시지 (프로토콜 디버깅용)\n  gtpb.log:       디스크에 미러링, 최신 10KB 유지\n\n═══════════════════ 긴급 정지 ═══════════════════\n  "긴급 정지" 버튼은 모든 장치 명령을 즉시 차단하고 백엔드로 StopAllDevices를 전송합니다. 다시 클릭하면 해제되고 정상 작동이 재개됩니다.\n',
}

_PT_BR: Dict[str, str] = {
    'app_title': 'GameToyProtocolBridge (GTPB)',
    'menu_language': 'Idioma',
    'menu_help': 'Ajuda',
    'lang_zh_cn': '简体中文',
    'lang_en_us': 'English',
    'lang_ja_jp': '日本語',
    'lang_de_de': 'Deutsch',
    'lang_fr_fr': 'Français',
    'lang_ru_ru': 'Русский',
    'lang_es_es': 'Español',
    'lang_pt_br': 'Português (Brasil)',
    'lang_ko_kr': '한국어',
    'menu_usage': 'Guia do usuário',
    'frame_connection': 'Conexão (salva com o perfil)',
    'frame_status': 'Estado',
    'frame_profile': 'Perfil',
    'lbl_listen': 'Endereço de escuta',
    'lbl_ws_port': 'Porta WebSocket',
    'lbl_tcp_port': 'Porta TCP (0=desativada)',
    'lbl_backend': 'Backend Intiface',
    'lbl_profile': 'Perfil:',
    'btn_load_profile': 'Carregar perfil...',
    'btn_save_profile': 'Salvar perfil',
    'btn_save_profile_as': 'Salvar perfil como...',
    'btn_start': 'Iniciar',
    'btn_stop': 'Parar',
    'btn_estop': 'Parada de emergência',
    'btn_estop_engaged': 'Parada de emergência acionada (clique para liberar)',
    'tab_sys_log': 'Log do sistema',
    'tab_game_rx_tx': 'GameRx/Tx',
    'tab_devices': 'Dispositivos',
    'tab_mapping': 'Mapeamento de canais',
    'mapping_passthrough': 'Pass-through do dispositivo real',
    'mapping_osr6': 'OSR6 virtual 6 eixos',
    'mapping_hint_edit': 'Dica: clique em «Salvar perfil» após editar',
    'mapping_hint_empty': 'A lista de atuadores é carregada automaticamente após iniciar o serviço',
    'col_channel': 'Canal',
    'col_enabled': 'Ativado',
    'col_actuator': 'Atuador alvo',
    'col_invert': 'Inverter',
    'col_scale': 'Escala',
    'col_min': 'Mín',
    'col_max': 'Máx',
    'col_midpoint': 'Ponto médio',
    'col_deadzone': 'Zona morta',
    'actuator_unmapped': '(sem mapeamento)',
    'status_idle': 'Estado: parado',
    'status_running': 'Estado: em execução  |  Modo: {mode}  |  Backend: {backend}  |  Sessões de jogo: {sessions}  |  Dispositivos: {devices}{estop}',
    'status_estop': '  |  PARADA DE EMERGÊNCIA!',
    'mode_passthrough': 'pass-through',
    'mode_osr6': 'OSR6 6 eixos',
    'backend_connected': 'conectado',
    'backend_disconnected': 'desconectado',
    'devices_empty': '(sem dispositivos — verifique se o Intiface Central está em execução e escaneando)',
    'msg_load_profile_title': 'Carregar perfil',
    'msg_load_profile_running': 'O serviço está em execução; carregar um novo perfil exige reinicialização para ser totalmente aplicado.\nContinuar?',
    'msg_load_profile_ok': 'Perfil carregado:\n{path}',
    'msg_load_profile_fail': 'Não foi possível ler o perfil:\n{path}\n{err}',
    'msg_save_profile_ok': 'Salvo{hot}:\n{path}',
    'msg_save_profile_hot': ' e aplicado imediatamente',
    'msg_save_profile_idle': ' (serviço não está em execução — será aplicado no próximo início)',
    'msg_save_profile_fail': 'Não foi possível gravar o perfil:\n{path}\n{err}',
    'msg_save_profile_as_title': 'Salvar perfil como',
    'msg_save_profile_as_ok': 'Salvo em:\n{path}',
    'msg_start_fail_title': 'Falha ao iniciar o GTPB',
    'msg_start_fail_body': 'O serviço de bridge falhou ao iniciar:\n{err}{hint}',
    'msg_start_fail_port_hint': '\n\nCausa: a porta de escuta já está em uso — feche outras instâncias do GTPB em execução (incluindo `python main.py --headless`) antes de clicar em Iniciar.',
    'msg_port_conflict_title': 'Conflito de portas',
    'msg_port_conflict_body': 'A porta WebSocket do lado do jogo ({ws_port}) é IGUAL à porta do backend do Intiface Central ({backend_port})!\n\nGTPB escuta na porta {ws_port} para o jogo E também atua como cliente conectando-se ao Intiface Central. Se as duas portas forem iguais, o fluxo de dados entre jogo / GTPB / Intiface Central entrará em loop infinito, causando «jogo travado em Connecting», «dispositivo não encontrado» e «inundação do log do Intiface».\n\nCorreção:\n  1. Intiface Central → Configurações → Servidor → altere o Listening Port (ex.: 12346, NÃO 12345)\n  2. Atualize o campo «Backend Intiface» do GTPB para a nova porta\n  3. Mantenha a «Porta WebSocket» do GTPB em 12345 (porta padrão do lado do jogo — não altere)\n\nResolva o conflito de portas antes de iniciar.',
    'log_start_gui': '=== Início do GTPB (GUI) ===',
    'log_start_headless': '=== Início do GTPB (headless) ===',
    'log_log_file': 'Arquivo de log: {path}',
    'log_profile_path': 'Perfil: {path}',
    'log_language_set': 'Idioma da UI: {lang}',
    'log_sigint': 'Interrupção recebida, parando...',
    'usage_title': 'Guia do usuário',
    'usage_text': 'GameToyProtocolBridge (GTPB) é uma ponte do protocolo Buttplug v3 que permite aos jogos controlar hardware via WebSocket.\n\n═══════════════════ Conflito de portas (LEITURA OBRIGATÓRIA) ═══════════════════\n⚠ GTPB escuta na porta WebSocket do lado do jogo (padrão 12345) E também atua como cliente conectando-se ao Intiface Central.\n⚠ Essas duas portas DEVEM ser diferentes!\n  - Porta WebSocket do jogo   = campo «Porta WebSocket» do GTPB (padrão 12345)\n  - Porta do Intiface Central = campo «Backend Intiface» do GTPB (padrão ws://127.0.0.1:12346)\nSe forem iguais, você verá «jogo travado em Connecting», «dispositivo não encontrado» e loops de dados infinitos.\nGTPB verifica isso automaticamente na inicialização e exibe um forte aviso.\nCorreção: abra o Intiface Central → Configurações → Server Listening Port, defina um valor diferente de 12345 (por exemplo, 12346) e atualize o campo «Backend Intiface» do GTPB de acordo.\n\n═══════════════════ Fluxo de dados ═══════════════════\n  Jogo (MultiFunPlayer etc.) → GTPB (ws://127.0.0.1:12345, Buttplug v3)\n     → análise / mapeamento / transformação → Intiface Central → hardware\n\n═══════════════════ Layout dos arquivos ═══════════════════\n  configsetting.ini    Dependência do software (padrões de fábrica) — não edite\n  profiles/*.json      Seus perfis (configurações de conexão + mapeamento de canais)\n  .gtpb_settings       Estado interno (idioma, caminho do último perfil carregado)\n  gtpb.log             Arquivo de log único e rotativo (limite de 10 KB)\n\n═══════════════════ Início rápido ═══════════════════\n  1. Inicie o Intiface Central e confirme que o dispositivo está conectado\n  2. Inicie o GTPB; mantenha «Porta WebSocket = 12345» e defina em «Backend Intiface» a porta real do Intiface\n  3. Inicie o jogo / MultiFunPlayer e aponte-o para ws://127.0.0.1:12345\n  4. Ajuste o mapeamento de canais na aba «Mapeamento de canais» do GTPB e clique em «Salvar perfil»\n\n═══════════════════ Modo OSR6 6 eixos ═══════════════════\n  Na aba «Mapeamento de canais», selecione «OSR6 virtual 6 eixos». O jogo verá um dispositivo virtual de 6 eixos (L0 principal / L1 frente-trás / L2 esquerda-direita / R0 torção / R1 rolagem / R2 arfagem). GTPB encaminhará esses eixos para o seu hardware real conforme a tabela de mapeamento.\n\n═══════════════════ Logs ═══════════════════\n  Aba Log do sistema: eventos e erros do software\n  Aba GameRx/Tx:      mensagens Buttplug entre o jogo e o GTPB (para depuração do protocolo)\n  gtpb.log:            espelhado em disco, mantém os últimos 10 KB\n\n═══════════════════ Parada de emergência ═══════════════════\n  O botão «Parada de emergência» intercepta imediatamente todos os comandos aos dispositivos e envia StopAllDevices ao backend. Clique novamente para liberar e retomar o funcionamento normal.\n',
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "zh-CN": _ZH_CN,
    "en-US": _EN_US,
    "ja-JP": _JA_JP,
    "de-DE": _DE_DE,
    "fr-FR": _FR_FR,
    "ru-RU": _RU_RU,
    "es-ES": _ES_ES,
    "pt-BR": _PT_BR,
    "ko-KR": _KO_KR,
}


# ---------------------------------------------------------------- 系统区域检测

# Windows 区域码 → 内置语言的映射
_LOCALE_PREFIX_MAP = {
    "zh": "zh-CN",
    "en": "en-US",
    "ja": "ja-JP",
    "de": "de-DE",
    "fr": "fr-FR",
    "ru": "ru-RU",
    "es": "es-ES",
    "pt": "pt-BR",
    "ko": "ko-KR",
}


def _get_system_locale_bcp47() -> str:
    """获取系统区域，返回 BCP-47 代码（如 zh-CN / en-US / ja-JP）。

    优先 Windows API GetUserDefaultLocaleName（最准确）；
    退而求其次用 locale.getlocale() 的 Windows 形态。
    """
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            kernel32 = ctypes.windll.kernel32
            if kernel32.GetUserDefaultLocaleName(buf, 85):
                v = buf.value.strip()
                if v:
                    return v.replace("_", "-")
        except Exception:
            pass
    # 兜底
    try:
        import locale
        lang = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").replace("_", "-")
        return lang
    except Exception:
        return ""


def detect_system_language() -> str:
    """按系统区域推断首选语言；未识别的 / 偏僻语言 → en-US。"""
    raw = _get_system_locale_bcp47()
    if not raw:
        return "en-US"
    lang = raw.replace("_", "-")
    primary = lang.split("-", 1)[0].lower()  # 'zh' / 'en' / 'ja' / ...
    # 精确匹配优先
    if lang in TRANSLATIONS:
        return lang
    # 否则按 primary 前缀映射
    mapped = _LOCALE_PREFIX_MAP.get(primary)
    if mapped and mapped in TRANSLATIONS:
        return mapped
    return "en-US"


def available_languages() -> Dict[str, str]:
    """返回 {code: display_name}（用当前语言显示），用于 GUI 菜单。"""
    cur = _current_dict()
    out: Dict[str, str] = {}
    for code in TRANSLATIONS:
        key = f"lang_{code.lower().replace('-', '_')}"
        out[code] = cur.get(key, code)
    return out


# ---------------------------------------------------------------- 查表

def _current_dict() -> Dict[str, str]:
    return TRANSLATIONS.get(_current, TRANSLATIONS["en-US"])


def t(key: str, **kwargs) -> str:
    """查表翻译，缺译回落到 key 本身（并在 stderr 写一次 WARNING）。"""
    d = _current_dict()
    s = d.get(key)
    if s is None:
        s = key
        _log_missing(key)
    if kwargs:
        try:
            s = s.format(**kwargs)
        except Exception:
            pass
    return s


_missing_warned: set = set()


def _log_missing(key: str):
    if key in _missing_warned:
        return
    _missing_warned.add(key)
    try:
        print(f"[i18n] missing translation: {key!r} in {_current}", file=sys.stderr)
    except Exception:
        pass


# ---------------------------------------------------------------- 切换 / 持久化

def get_language() -> str:
    return _current


def set_language(lang: str) -> bool:
    """切换语言。返回是否真的改了。"""
    global _current
    with _lock:
        if lang not in TRANSLATIONS:
            return False
        if lang == _current:
            return False
        _current = lang
        _missing_warned.clear()
        return True


def load_user_language(settings_path: str) -> str:
    """从 .gtpb_settings 读取用户上次的语言选择（不存在则用系统区域）。"""
    global _current
    saved = None
    if settings_path and os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            saved = data.get(_LANG_KEY)
        except Exception:
            pass
    if saved and saved in TRANSLATIONS:
        _current = saved
    else:
        _current = detect_system_language()
    return _current


def save_user_language(settings_path: str, lang: str):
    if lang not in TRANSLATIONS:
        return
    data = {}
    if settings_path and os.path.isfile(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            pass
    data[_LANG_KEY] = lang
    try:
        os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 工具：解析后端 URL 里的端口
def backend_port(backend_url: str) -> Optional[int]:
    """从 ws://host:port 提取端口；解析失败返回 None。"""
    if not backend_url:
        return None
    try:
        s = backend_url
        if "://" in s:
            s = s.split("://", 1)[1]
        if "/" in s:
            s = s.split("/", 1)[0]
        if ":" in s:
            return int(s.rsplit(":", 1)[1])
    except Exception:
        return None
    return None
