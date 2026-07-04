"""PyInstaller entry point for the Streamlit desktop dashboard."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    src_dir = bundle_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    if "--selftest" in sys.argv:
        from selftest import main as selftest_main

        raise SystemExit(selftest_main())

    dashboard = src_dir / "dashboard" / "app.py"
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")

    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        str(dashboard),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    streamlit_cli.main()


if __name__ == "__main__":
    main()
