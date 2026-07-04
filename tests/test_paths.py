from __future__ import annotations

import sys
from pathlib import Path

import paths


def test_bundle_dir_uses_source_root_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert Path(paths.bundle_dir()) == Path(paths.__file__).resolve().parent


def test_bundle_dir_uses_meipass_when_frozen(workspace_tmp_path, monkeypatch):
    bundle = workspace_tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    assert Path(paths.bundle_dir()) == bundle.resolve()


def test_user_data_dir_uses_appdata_and_creates_app_folder(workspace_tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(workspace_tmp_path))

    data_dir = Path(paths.user_data_dir())

    assert data_dir == workspace_tmp_path / paths.APP_NAME
    assert data_dir.is_dir()
    assert Path(paths.signals_db_path()) == data_dir / "signals.db"
    assert Path(paths.fmp_usage_path()) == data_dir / "fmp_usage.json"
    assert Path(paths.user_env_path()) == data_dir / ".env"


def test_user_data_dir_skips_non_writable_appdata(workspace_tmp_path, monkeypatch):
    appdata = workspace_tmp_path / "appdata"
    localappdata = workspace_tmp_path / "localappdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))

    original_verify = paths._verify_writable

    def fake_verify(path):
        if path == appdata / paths.APP_NAME:
            raise PermissionError("blocked")
        original_verify(path)

    monkeypatch.setattr(paths, "_verify_writable", fake_verify)

    data_dir = Path(paths.user_data_dir())

    assert data_dir == localappdata / paths.APP_NAME
    assert data_dir.is_dir()


def test_user_data_dir_uses_workspace_fallback_before_temp(workspace_tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTIC_DSS_USER_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(workspace_tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(workspace_tmp_path / "localappdata"))
    monkeypatch.setattr(paths.tempfile, "gettempdir", lambda: str(workspace_tmp_path / "temp"))
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    expected = Path(paths.__file__).resolve().parents[1] / ".app-data" / paths.APP_NAME

    def fake_verify(path):
        if path != expected:
            raise PermissionError("blocked")
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(paths, "_verify_writable", fake_verify)

    assert Path(paths.user_data_dir()) == expected


def test_seed_user_csv_defaults_copies_missing_files(workspace_tmp_path, monkeypatch):
    appdata = workspace_tmp_path / "appdata"
    bundle = workspace_tmp_path / "bundle"
    data = bundle / "data"
    data.mkdir(parents=True)
    (data / "watchlist.csv").write_text("ticker\nAAPL\n", encoding="utf-8")
    (data / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\nMSFT,1,100,2026-01-01\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    user_dir = Path(paths.seed_user_csv_defaults())

    assert (user_dir / "watchlist.csv").read_text(encoding="utf-8") == "ticker\nAAPL\n"
    assert "MSFT" in (user_dir / "portfolio.csv").read_text(encoding="utf-8")


def test_seed_user_csv_defaults_uses_pyinstaller_src_data_layout(workspace_tmp_path, monkeypatch):
    appdata = workspace_tmp_path / "appdata"
    bundle = workspace_tmp_path / "_internal"
    data = bundle / "src" / "data"
    data.mkdir(parents=True)
    (data / "watchlist.csv").write_text("ticker\nAAPL\n", encoding="utf-8")
    (data / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\nMSFT,1,100,2026-01-01\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    user_dir = Path(paths.seed_user_csv_defaults())

    assert (user_dir / "watchlist.csv").read_text(encoding="utf-8") == "ticker\nAAPL\n"
    assert "MSFT" in (user_dir / "portfolio.csv").read_text(encoding="utf-8")


def test_seed_user_csv_defaults_does_not_overwrite_existing_user_files(workspace_tmp_path, monkeypatch):
    appdata = workspace_tmp_path / "appdata"
    user_dir = appdata / paths.APP_NAME
    user_dir.mkdir(parents=True)
    (user_dir / "watchlist.csv").write_text("ticker\nUSER\n", encoding="utf-8")
    bundle = workspace_tmp_path / "bundle"
    data = bundle / "data"
    data.mkdir(parents=True)
    (data / "watchlist.csv").write_text("ticker\nBUNDLE\n", encoding="utf-8")
    (data / "portfolio.csv").write_text(
        "ticker,qty,entry_price,entry_date\nMSFT,1,100,2026-01-01\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)

    paths.seed_user_csv_defaults()

    assert (user_dir / "watchlist.csv").read_text(encoding="utf-8") == "ticker\nUSER\n"
