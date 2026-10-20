# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Keep packaging policy in a testable module; do not bundle whole image trees.
import sys
sys.path.insert(0, SPECPATH)
from build_support.release_assets import collect_images as collect_release_images, collect_runtime_files

def collect_images():
    return collect_release_images(SPECPATH)


def collect_icons():
    datas = []
    icon_root = os.path.join('assets', 'icons')
    for f in os.listdir(icon_root):
        if f.lower().endswith(('.ico', '.png')):
            datas.append((os.path.join(icon_root, f), icon_root))
    return datas


datas = collect_images() + collect_runtime_files(SPECPATH) + [
    ('update_config.json', '.'),
    ('remote_script.json', '.'),
    ('src/chaos/recruitment_layout.json', 'src/chaos'),
    ('src/chaos/node_layout.json', 'src/chaos'),
] + collect_icons() + collect_data_files(
    'rapidocr_onnxruntime',
    includes=['config.yaml', 'models/*.onnx'],
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'cv2', 'numpy', 'PIL', 'tkinter', 'rapidocr_onnxruntime',
    ] + collect_submodules('src.backend') + collect_submodules('src.core') + collect_submodules('src.display') + collect_submodules('src.finder'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pure-python-adb',
        'pytest',
        'torch',
        'torchvision',
        'torchaudio',
        'transformers',
        'tensorflow',
        'tensorboard',
        'av',
    ],
    noarchive=False,
    optimize=0,
)
# Screenshot decoding and template matching use cv2.pyd, not the optional
# FFmpeg video backend. Keep every other binary and all image/OCR data intact.
a.binaries = [entry for entry in a.binaries
              if not (os.path.basename(entry[0].replace('\\', '/')).lower().startswith('opencv_videoio_ffmpeg')
                      and entry[0].lower().endswith('.dll'))]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EAB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/icons/app_icon_multi_size.ico',
    version='file_version_info.txt',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
updater_analysis = Analysis(['updater_main.py'], pathex=[], binaries=[], datas=[],
                            hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
updater_pyz = PYZ(updater_analysis.pure)
updater_exe = EXE(updater_pyz, updater_analysis.scripts, updater_analysis.binaries,
                  updater_analysis.datas, [], name='EAB-Updater',
                  console=False, upx=False, icon='assets/icons/app_icon_multi_size.ico')

launcher_analysis = Analysis(['legacy_launcher.py'], pathex=[], binaries=[], datas=[],
                             hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[], noarchive=False)
launcher_pyz = PYZ(launcher_analysis.pure)
launcher_exe = EXE(launcher_pyz, launcher_analysis.scripts, [], exclude_binaries=True,
                   name='SecretShopBot-E7', console=False, upx=False,
                   icon='assets/icons/app_icon_multi_size.ico')

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    updater_exe,
    launcher_exe,
    launcher_analysis.binaries,
    launcher_analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EAB',
)
