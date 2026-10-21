# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/samee/OneDrive/Desktop/issue slip/main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/samee/OneDrive/Desktop/issue slip/assets', 'assets'), ('C:/Users/samee/OneDrive/Desktop/issue slip/app/server/pwa', 'app/server/pwa')],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='IssueSlipManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/samee/OneDrive/Desktop/issue slip/assets/icons/app_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IssueSlipManager',
)
