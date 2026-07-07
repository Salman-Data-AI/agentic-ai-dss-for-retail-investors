"""Temporary Chunk 2 CLI for compiling and approving deterministic rule sets."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from paths import executable_env_path, user_env_path

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)

sys.path.insert(0, os.path.dirname(__file__))

from agent.rule_approval import approve_current_rule_set, compile_current_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Temporary DI#4 Chunk 2 rule compile/approval CLI.")
    parser.add_argument("action", choices=("compile", "approve"))
    args = parser.parse_args()

    result = compile_current_settings() if args.action == "compile" else approve_current_rule_set()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
