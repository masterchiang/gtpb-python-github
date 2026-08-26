# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 - GameToyProtocolBridge (GTPB)
打包为单文件 Windows EXE
"""

import os

block_cipher = None

# 项目根目录
project_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(project_dir, 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        # 软件出厂依赖：configsetting.ini（随 EXE 一起发布，运行时只读）
        # 用户配置文件 config.json 由用户自己创建/加载，profiles/*.json 也是用户文件
        # —— 都不打进 EXE。
        (os.path.join(project_dir, 'configsetting.ini'), '.'),
    ],
    hiddenimports=[
        # websockets 异步相关模块
        'websockets',
        'websockets.asyncio',
        'websockets.asyncio.client',
        'websockets.asyncio.server',
        'websockets.legacy',
        'websockets.legacy.client',
        'websockets.legacy.server',
        'websockets.http',
        'websockets.http11',
        'websockets.uri',
        'websockets.utils',
        'websockets.datastructures',
        'websockets.headers',
        'websockets.extensions',
        'websockets.frames',
        # tkinter GUI
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        # 标准库
        'asyncio',
        'argparse',
        'json',
        'dataclasses',
        'enum',
        'typing',
        'logging',
        'time',
        'threading',
        'queue',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块以减小体积
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
        'pytest',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GTPB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 模式无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可在此设置图标路径，例如 icon='gtpb.ico'
    version=None,
)
