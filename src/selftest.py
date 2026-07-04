"""Headless live connectivity self-test for the frozen executable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import find_dotenv, load_dotenv

import config
from paths import executable_env_path, user_env_path


@dataclass
class EnvLoad:
    label: str
    path: str
    exists: bool
    loaded: bool


@dataclass
class CheckResult:
    label: str
    passed: bool
    detail: str
    error: str | None = None


def _load_env_files() -> list[EnvLoad]:
    """Load env files using the same frozen-aware locations as the app."""
    default_path = find_dotenv(usecwd=True)
    default_loaded = load_dotenv(override=False)

    loaded = [
        EnvLoad(
            label="default .env search",
            path=default_path or "(not found)",
            exists=bool(default_path),
            loaded=default_loaded,
        )
    ]

    user_path = user_env_path()
    loaded.append(_load_explicit_env("user app-data .env", user_path))

    exe_path = executable_env_path()
    if exe_path:
        loaded.append(_load_explicit_env("executable-adjacent .env", exe_path))

    return loaded


def _load_explicit_env(label: str, path: str) -> EnvLoad:
    exists = Path(path).exists()
    return EnvLoad(
        label=label,
        path=path,
        exists=exists,
        loaded=load_dotenv(path, override=False) if exists else False,
    )


def _run_fmp_check(ticker: str = "AAPL") -> CheckResult:
    from agent import tools

    try:
        quote = tools.get_quote(ticker)
    except Exception as exc:
        return CheckResult("FMP", False, f"{tools._FMP_BASE_URL} quote for {ticker}", str(exc))

    if isinstance(quote, dict) and quote.get("error"):
        return CheckResult("FMP", False, f"{tools._FMP_BASE_URL} quote for {ticker}", quote["error"])
    if not isinstance(quote, dict):
        return CheckResult("FMP", False, f"{tools._FMP_BASE_URL} quote for {ticker}", f"Unexpected response: {quote!r}")

    name = quote.get("name") or quote.get("ticker") or ticker
    return CheckResult("FMP", True, f"{tools._FMP_BASE_URL} quote for {ticker} returned data for {name}")


def _run_llm_check() -> CheckResult:
    from agent.llm import create_llm_client

    provider = config.PROVIDER
    model = config.MODEL
    provider_settings = config.PROVIDER_SETTINGS.get(provider)
    if not provider_settings:
        return CheckResult(
            "LLM",
            False,
            f"Provider={provider} model={model}",
            f"Unsupported PROVIDER={provider!r}",
        )

    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            system="Reply with a short plain-text health check response.",
            user_content="Reply with exactly: OK",
            provider_settings=provider_settings,
        )
        response = client.next_step()
    except Exception as exc:
        return CheckResult("LLM", False, f"Provider={provider} model={model}", str(exc))

    if response.error:
        return CheckResult("LLM", False, f"Provider={provider} model={model}", response.error)
    if response.final_text:
        return CheckResult("LLM", True, f"Provider={provider} model={model} returned text")
    if response.tool_calls is not None:
        return CheckResult("LLM", True, f"Provider={provider} model={model} returned tool-call response")

    return CheckResult("LLM", False, f"Provider={provider} model={model}", "Provider returned no response")


def _looks_like_ssl_error(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(token in lowered for token in (
        "ssl",
        "certificate",
        "certifi",
        "certificate_verify_failed",
        "tls",
        "truststore",
    ))


def run_selftest(print_func: Callable[[str], None] = print) -> int:
    env_loads = _load_env_files()

    print_func("AgenticDSS frozen self-test")
    print_func("")
    print_func("Environment files checked:")
    for env in env_loads:
        status = "loaded" if env.loaded else "not loaded"
        exists = "exists" if env.exists else "missing"
        print_func(f"- {env.label}: {env.path} ({exists}, {status})")
    print_func("")

    from agent import tools

    print_func(f"FMP base URL: {tools._FMP_BASE_URL}")
    print_func(f"LLM provider/model: {config.PROVIDER} / {config.MODEL}")
    print_func("")

    results = [_run_fmp_check(), _run_llm_check()]
    for result in results:
        print_func(f"{result.label}: {'PASS' if result.passed else 'FAIL'} - {result.detail}")
        if result.error:
            print_func(result.error)
            if _looks_like_ssl_error(result.error):
                print_func("This looks like an SSL/certificate problem in the frozen build.")

    return 0 if all(result.passed for result in results) else 1


def main() -> int:
    return run_selftest()


if __name__ == "__main__":
    raise SystemExit(main())
