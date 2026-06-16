# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['adbtool.py'],
    pathex=[],
    binaries=[],
    datas=[('tools','tools'),('script','script')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='adbtool',
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
    icon='tools/favicon.icns',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='adbtool',
)
app = BUNDLE(
    coll,
    name='adbtool.app',
    icon='tools/favicon.icns',
    bundle_identifier='com.wcy.adbtool',
)
