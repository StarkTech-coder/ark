# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.building.datastruct import TOC

# SPECPATH is provided by PyInstaller and points to the directory
# containing this spec file (desktop/). Repository root is its parent.
spec_dir = Path(SPECPATH).resolve()
project_root = spec_dir.parent

block_cipher = None

hiddenimports = [
    "chainlit",
    "chat_ui",
    "ddc459050edb75a05942__mypyc",
]

datas = [
    (str(project_root / "chat_ui.py"), "."),
    (str(project_root / "public"), "public"),
    (str(project_root / "assets"), "assets"),
    (str(project_root / ".chainlit"), ".chainlit"),
    (str(project_root / "config.json"), "."),
]

a = Analysis(
    [
        str(project_root / "desktop" / "main.py"),
        str(project_root / "desktop" / "backend_main.py"),
    ],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchaudio",
        "torchvision",
        "tensorflow",
        "tensorboard",
        "tests",
        "lancedb_data",
        "documents",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

desktop_scripts = TOC([script for script in a.scripts if script[0] == "main"])
backend_scripts = TOC([script for script in a.scripts if script[0] == "backend_main"])

if not desktop_scripts:
    raise RuntimeError("Desktop launcher script not found in analysis scripts")
if not backend_scripts:
    raise RuntimeError("Backend launcher script not found in analysis scripts")

desktop_exe = EXE(
    pyz,
    desktop_scripts,
    [],
    exclude_binaries=True,
    name="ARKDesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

backend_exe = EXE(
    pyz,
    backend_scripts,
    [],
    exclude_binaries=True,
    name="ARKBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    desktop_exe,
    backend_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ARKDesktop",
)

app = BUNDLE(
    coll,
    name="ARKDesktop.app",
    icon=None,
    bundle_identifier="com.starktech.ark.desktop",
)
