# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


added_files = [
    ("..\\..\\archoctopus\\gui\\resource", ".\\gui\\resource"),
    ("..\\..\\archoctopus\\plugins", ".\\plugins"),
    ("..\\..\\README.md", "."),
    ("..\\..\\LICENSE", ".")
]

a = Analysis(['..\\..\\archoctopus\\main.py'],
             pathex=[],
             binaries=[(".\\dll\\x64", ".\\x64"),],
             datas=added_files,
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             # runtime_hooks=[".\\libs_hook.py",],
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
          name='ArchOctopus',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          version='.\\file_version_info.txt',
          icon='.\\profile.ico')

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='ArchOctopus')
