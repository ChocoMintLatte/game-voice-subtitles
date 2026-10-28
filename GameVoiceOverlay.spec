# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('app_icon.png', '.'), ('app_icon.ico', '.')]
binaries = []
hiddenimports = [
    'faster_whisper', 'ctranslate2', 'huggingface_hub', 'tokenizers', 
    'onnxruntime', 'soundcard', 'cffi',
    'google.genai',
    'dotenv', 'python-dotenv'
]

# Collect all necessary packages and their dynamic libraries / data
packages_to_collect = [
    'faster_whisper', 'ctranslate2', 'huggingface_hub', 'tokenizers', 
    'soundcard', 'nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_nvrtc',
    'google.genai'
]

for pkg in packages_to_collect:
    try:
        tmp_datas, tmp_binaries, tmp_hidden = collect_all(pkg)
        datas += tmp_datas
        binaries += tmp_binaries
        hiddenimports += tmp_hidden
    except Exception as e:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='GameVoiceOverlay',
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
    icon=['app_icon.ico'],
)
