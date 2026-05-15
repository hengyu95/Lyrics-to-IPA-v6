# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = [('Audio', 'Audio')]
hiddenimports = []
datas += collect_data_files('eng_to_ipa')
hiddenimports += collect_submodules('PyQt5.QtMultimedia')


a = Analysis(
    ['LyricsToIPA.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    hiddenimports=['svgwrite'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LyricsToIPA',
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
)

import sys

# If PyInstaller is running on a Mac, build the .app bundle!
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='LyricsToIPA.app',
        icon=None,
        bundle_identifier=None,
    )