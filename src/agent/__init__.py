"""Agent package exports."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "run_agent":
        from .agent import run_agent

        return run_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["run_agent"]
