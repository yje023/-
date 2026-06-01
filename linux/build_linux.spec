# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / 'backend' / 'app.py')],
    pathex=[str(project_root / 'backend')],
    binaries=[],
    datas=[
        (str(project_root / 'frontend' / 'dist'), 'frontend'),
        (str(project_root / 'backend' / 'version.json'), '.'),
    ],
    hiddenimports=[
        'flask',
        'flask_cors',
        'flask_jwt_extended',
        'werkzeug',
        'werkzeug.security',
        'sqlalchemy',
        'sqlalchemy.ext',
        'openpyxl',
        'openpyxl.styles',
        'jinja2',
        'jinja2.ext',
        'itsdangerous',
        'xlrd',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
    ],
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
    name='考核评价系统',
    icon=None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
