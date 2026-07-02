from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PYTEST_TMP = ROOT / ".pytest-tmp"
PYTEST_TMP.mkdir(exist_ok=True)
os.environ.setdefault("TMPDIR", str(PYTEST_TMP))
os.environ.setdefault("TEMP", str(PYTEST_TMP))
os.environ.setdefault("TMP", str(PYTEST_TMP))
tempfile.tempdir = str(PYTEST_TMP)

_OriginalTemporaryDirectory = tempfile.TemporaryDirectory


class _SafeTemporaryDirectory(_OriginalTemporaryDirectory):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("ignore_cleanup_errors", True)
        super().__init__(*args, **kwargs)


tempfile.TemporaryDirectory = _SafeTemporaryDirectory

os.environ.setdefault("FMP_API_KEY", "test-fmp-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")


@pytest.fixture(autouse=True)
def dummy_api_keys(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test-fmp-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")


@pytest.fixture
def workspace_tmp_path():
    path = PYTEST_TMP / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture
def isolated_fmp_usage(workspace_tmp_path, monkeypatch):
    from agent import tools

    usage_path = workspace_tmp_path / "fmp_usage.json"
    monkeypatch.setattr(tools, "_USAGE_PATH", str(usage_path))
    monkeypatch.setattr(tools, "_FMP_RUN_REQUEST_COUNT", 0)
    return usage_path


@pytest.fixture
def temp_db_path(workspace_tmp_path, monkeypatch):
    from database import store

    db_path = workspace_tmp_path / "signals.db"
    monkeypatch.setattr(store, "_DB_PATH", str(db_path))
    return db_path
