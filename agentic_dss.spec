# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


app_name = "AgenticDSS"


def runtime_submodule(name):
    excluded_parts = (
        ".tests",
        ".testing.tests",
        ".conftest",
        "._pyinstaller.tests",
    )
    return not any(part in name for part in excluded_parts)

datas = []
excluded_data_files = {
    os.path.normpath(".env"),
    os.path.normpath("database/signals.db"),
    os.path.normpath("data/fmp_usage.json"),
}
for root, dirs, files in os.walk("src"):
    dirs[:] = [dirname for dirname in dirs if dirname != "__pycache__"]
    for filename in files:
        rel_path = os.path.normpath(os.path.join(root, filename))
        rel_from_src = os.path.normpath(os.path.relpath(rel_path, "src"))
        if filename.endswith(".pyc"):
            continue
        if rel_from_src in excluded_data_files or filename == ".env":
            continue
        target_dir = os.path.join("src", os.path.dirname(rel_from_src))
        datas.append((rel_path, target_dir))
if any(os.path.basename(source) == ".env" for source, _ in datas):
    raise RuntimeError("Refusing to bundle .env in PyInstaller data files")
datas += collect_data_files("streamlit")
datas += collect_data_files("certifi")
datas += collect_dynamic_libs("numpy")
datas += collect_dynamic_libs("pandas")
datas += copy_metadata("streamlit")
datas += copy_metadata("numpy")
datas += copy_metadata("pandas")
datas += copy_metadata("requests")
datas += copy_metadata("certifi")
datas += copy_metadata("python-dotenv")
datas += copy_metadata("anthropic")
datas += copy_metadata("openai")

hiddenimports = []
hiddenimports += collect_submodules("streamlit")
hiddenimports += collect_submodules("numpy", filter=runtime_submodule)
hiddenimports += collect_submodules("pandas", filter=runtime_submodule)
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
    excludes=[
        "matplotlib",
        "pyspark",
        "scipy",
        "tensorflow",
    ],
    noarchive=True,
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
