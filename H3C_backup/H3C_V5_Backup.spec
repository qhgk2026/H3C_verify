# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# 获取当前脚本所在目录（修复 __file__ 未定义问题）
if '__file__' in locals():
    script_dir = os.path.dirname(os.path.abspath(__file__))
else:
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))

a = Analysis(
    ['H3C_V5_Backup.py'],  # 你的主脚本名
    pathex=[script_dir],    # 修复后的路径
    binaries=[],
    datas=[],
    hiddenimports=['paramiko', 'telnetlib', 'tkinter'],  # 显式声明隐藏依赖
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, optimize=0)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='H3C_V5_Backup',  # 生成的exe文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 启用UPX压缩（可选）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 图形界面程序，关闭控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如需自定义图标，填写图标路径：icon='xxx.ico'
)