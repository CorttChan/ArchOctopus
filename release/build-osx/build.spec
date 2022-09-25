# -*- mode: python ; coding: utf-8 -*-


block_cipher = None

added_files = [
    ("../../archoctopus/gui/resource", "./gui/resource"),
    ("../../archoctopus/plugins", "./plugins"),
    ("../../README.md", "."),
    ("../../LICENSE", ".")
]

a = Analysis(['../../archoctopus/main.py'],
             pathex=[],
             binaries=[],
             datas=added_files,
             hiddenimports=[],
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
          name='ArchOctopus',
          debug=True,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          console=False,
          disable_windowed_traceback=True,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None )

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='ArchOctopus')

app = BUNDLE(coll,
             name='ArchOctopus.app',
             icon='./profile.icns',
             version='2.0.3',
             bundle_identifier=None,
             info_plist={
                'NSPrincipalClass': 'NSApplication',
                'NSAppleScriptEnabled': False,
                'NSHumanReadableCopyright': '@ CorttChan 2020',
                'NSUserNotificationAlertStyle': 'alert',
            },)
