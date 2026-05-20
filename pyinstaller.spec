# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件
构建命令: pyinstaller pyinstaller.spec
"""

a = Analysis(
    ['backend/app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend'),
    ],
    hiddenimports=[
        'flask_sqlalchemy',
        'flask_cors',
        'flask_jwt_extended',
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.styles',
        'openpyxl.worksheet',
        'openpyxl.reader',
        'openpyxl.writer',
        'xlrd',
        'werkzeug',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='黔江区多维度精准考核评价系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
