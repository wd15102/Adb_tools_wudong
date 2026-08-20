# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# 收集 ttkbootstrap 全部资源（代码 + themes/assets 数据文件）
ttk_datas, ttk_binaries, ttk_hidden = collect_all('ttkbootstrap')

block_cipher = None


a = Analysis(['adbtool.py'],
             pathex=['D:\\WorkCode\\AdbTool-maste'],
             binaries=ttk_binaries,
             datas=[('tools','tools'),('script','script'),('src/capture/templates','src/capture/templates')] + ttk_datas,
             hiddenimports=ttk_hidden + ['engineio.async_drivers.threading'],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
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
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None , icon='D:\\WorkCode\\AdbTool-maste\\tools\\favicon_new.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='adbtool')
