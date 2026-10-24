# -*- mode: python ; coding: utf-8 -*-
"""Сборка портативной версии Double Sound (Windows x64)."""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
RES = ROOT / "app" / "resources"

datas = []
for name in ("icon.svg", "icon.png", "icon.ico"):
    candidate = RES / name
    if candidate.exists():
        datas.append((str(candidate), "resources"))
for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
    candidate = ROOT / name
    if candidate.exists():
        datas.append((str(candidate), "."))

binaries = []
fpcalc = RES / "fpcalc.exe"
if sys.platform == "win32" and fpcalc.exists():
    binaries.append((str(fpcalc), "resources"))

icon = str(RES / "icon.ico") if sys.platform == "win32" and (RES / "icon.ico").exists() else None
version_file = (
    str(ROOT / "version_info.txt")
    if sys.platform == "win32" and (ROOT / "version_info.txt").exists()
    else None
)

hiddenimports = ["send2trash"]
if sys.platform == "win32":
    # send2trash на Windows использует ctypes-бэкенд, если нет pywin32.
    hiddenimports.append("send2trash.win.legacy")
elif sys.platform == "darwin":
    hiddenimports.append("send2trash.mac.modern")

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DoubleSound",
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
    icon=icon,
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DoubleSound",
)
