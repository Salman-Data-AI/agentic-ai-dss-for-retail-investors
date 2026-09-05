# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
    get_module_file_attribute,
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


# charset_normalizer ships mypyc-compiled speedups (cd/md plus the shared md__mypyc
# module). PyInstaller collects them under charset_normalizer/, where md__mypyc is no
# longer importable, so the whole package fails to import and requests silently falls
# back to no character detection. Drop the speedups and collect the pure-Python
# implementations they shadow instead.
charset_normalizer_speedups = ("cd", "md", "md__mypyc")


def charset_normalizer_speedup_module(entry):
    """Return the module name of a bundled charset_normalizer speedup, else None."""
    dest = os.path.normpath(entry[0])
    if os.path.basename(os.path.dirname(dest)) != "charset_normalizer":
        return None
    basename = os.path.basename(dest)
    if not basename.endswith((".pyd", ".dll")):
        return None
    stem = basename.split(".", 1)[0]
    return stem if stem in charset_normalizer_speedups else None


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
shadowed_modules = set()
for toc_name in ("binaries", "datas"):
    kept = []
    for entry in getattr(a, toc_name):
        module = charset_normalizer_speedup_module(entry)
        if module is None:
            kept.append(entry)
        else:
            shadowed_modules.add(module)
    setattr(a, toc_name, kept)

charset_normalizer_dir = os.path.dirname(get_module_file_attribute("charset_normalizer"))
collected_modules = {os.path.splitext(os.path.normpath(entry[0]))[0] for entry in a.datas}
for module in sorted(shadowed_modules):
    source = os.path.join(charset_normalizer_dir, f"{module}.py")
    if not os.path.isfile(source):
        # md__mypyc is a mypyc build artefact with no pure-Python counterpart.
        continue
    if os.path.join("charset_normalizer", module) in collected_modules:
        continue
    a.pure.append((f"charset_normalizer.{module}", source, "PYMODULE"))

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
