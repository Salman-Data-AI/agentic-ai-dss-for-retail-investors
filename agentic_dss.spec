# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


app_name = "AgenticDSS"

datas = []
for root, dirs, files in os.walk("src"):
    dirs[:] = [dirname for dirname in dirs if dirname != "__pycache__"]
    for filename in files:
        rel_path = os.path.normpath(os.path.join(root, filename))
        rel_from_src = os.path.normpath(os.path.relpath(rel_path, "src"))
        if filename.endswith(".pyc"):
            continue
        if rel_from_src in {
            os.path.normpath("database/signals.db"),
            os.path.normpath("data/fmp_usage.json"),
        }:
            continue
        target_dir = os.path.join("src", os.path.dirname(rel_from_src))
        datas.append((rel_path, target_dir))
datas += collect_data_files("streamlit")
datas += copy_metadata("streamlit")
datas += copy_metadata("pandas")
datas += copy_metadata("requests")
datas += copy_metadata("python-dotenv")
datas += copy_metadata("anthropic")
datas += copy_metadata("openai")

hiddenimports = []
hiddenimports += collect_submodules("streamlit")
hiddenimports += collect_submodules("anthropic")
hiddenimports += collect_submodules("openai")
hiddenimports += [
    "config",
    "main",
    "paths",
    "selftest",
    "agent",
    "agent.agent",
    "agent.llm",
    "agent.tools",
    "agent.tool_schemas",
    "dashboard",
    "dashboard.app",
    "dashboard.logic",
    "database",
    "database.store",
]

a = Analysis(
    ["packaging/desktop_launcher.py"],
    pathex=["src"],
    binaries=[],
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
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name,
)
