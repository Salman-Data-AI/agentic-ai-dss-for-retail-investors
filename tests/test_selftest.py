from __future__ import annotations

import selftest


def test_run_selftest_returns_zero_when_fmp_and_llm_pass(monkeypatch):
    output = []

    monkeypatch.setattr(
        selftest,
        "_load_env_files",
        lambda: [
            selftest.EnvLoad("default .env search", "C:/repo/.env", True, True),
            selftest.EnvLoad("user app-data .env", "C:/Users/User/AppData/app/.env", False, False),
        ],
    )
    monkeypatch.setattr(
        selftest,
        "_run_fmp_check",
        lambda: selftest.CheckResult("FMP", True, "quote returned data"),
    )
    monkeypatch.setattr(
        selftest,
        "_run_llm_check",
        lambda: selftest.CheckResult("LLM", True, "provider returned text"),
    )

    exit_code = selftest.run_selftest(output.append)

    assert exit_code == 0
    assert "FMP: PASS - quote returned data" in output
    assert "LLM: PASS - provider returned text" in output


def test_run_selftest_returns_nonzero_and_prints_errors(monkeypatch):
    output = []

    monkeypatch.setattr(selftest, "_load_env_files", lambda: [])
    monkeypatch.setattr(
        selftest,
        "_run_fmp_check",
        lambda: selftest.CheckResult(
            "FMP",
            False,
            "quote failed",
            "SSL certificate verify failed",
        ),
    )
    monkeypatch.setattr(
        selftest,
        "_run_llm_check",
        lambda: selftest.CheckResult("LLM", True, "provider returned text"),
    )

    exit_code = selftest.run_selftest(output.append)

    assert exit_code == 1
    assert "FMP: FAIL - quote failed" in output
    assert "SSL certificate verify failed" in output
    assert "This looks like an SSL/certificate problem in the frozen build." in output
