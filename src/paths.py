"""Frozen-aware filesystem locations for the desktop build."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


APP_NAME = "Agentic AI DSS for Retail Investors"
_WRITE_TEST_FILENAME = ".write-test"


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def bundle_dir() -> str:
    """Return the read-only application base directory."""
    if is_frozen():
        return str(Path(getattr(sys, "_MEIPASS")).resolve())
    return str(Path(__file__).resolve().parent)


def user_data_dir() -> str:
    """Return the writable per-user application data directory."""
    candidates = [
        os.environ.get("AGENTIC_DSS_USER_DATA_DIR"),
        os.environ.get("APPDATA"),
        os.environ.get("LOCALAPPDATA"),
        str(Path.home() / "AppData" / "Roaming"),
    ]
    if not is_frozen():
        candidates.append(str(Path(__file__).resolve().parents[1] / ".app-data"))
    candidates.append(tempfile.gettempdir())

    for base in candidates:
        if not base:
            continue
        path = Path(base)
        if path.name != APP_NAME:
            path = path / APP_NAME
        try:
            path.mkdir(parents=True, exist_ok=True)
            _verify_writable(path)
        except OSError:
            continue
        return str(path)

    raise RuntimeError("Could not create a writable application data directory")


def _verify_writable(path: Path) -> None:
    probe = path / _WRITE_TEST_FILENAME
    probe.write_text("ok", encoding="utf-8")
    probe.read_text(encoding="utf-8")
    try:
        probe.unlink()
    except OSError:
        pass


def bundled_data_dir() -> str:
    base = Path(bundle_dir())
    candidates = [
        base / "data",
        base / "src" / "data",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return str(candidates[0])


def user_data_file(filename: str) -> str:
    return str(Path(user_data_dir()) / filename)


def signals_db_path() -> str:
    return user_data_file("signals.db")


def fmp_usage_path() -> str:
    return user_data_file("fmp_usage.json")


def user_env_path() -> str:
    return user_data_file(".env")


def executable_env_path() -> str | None:
    if not is_frozen():
        return None
    return str(Path(sys.executable).resolve().parent / ".env")


def seed_user_csv_defaults() -> str:
    """Copy bundled CSV defaults into user data on first run."""
    destination_dir = Path(user_data_dir())
    source_dir = Path(bundled_data_dir())

    for filename in ("watchlist.csv", "portfolio.csv"):
        destination = destination_dir / filename
        if destination.exists():
            continue
        source = source_dir / filename
        if source.exists():
            shutil.copy2(source, destination)

    return str(destination_dir)
