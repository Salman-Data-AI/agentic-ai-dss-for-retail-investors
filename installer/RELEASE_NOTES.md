# Agentic DSS Windows Installer

This release contains the Windows installer for Agentic AI DSS for Retail Investors.

## 0.1.1

- Missing PE, EPS, and daily change metrics now remain absent instead of being converted to `0`.
- Approved-rule deterministic evaluation now fails closed with `ERROR` when required metrics are missing.
- Deterministic rationale generation can no longer overwrite the code-fetched `data_fetched` audit payload.
- Added regression coverage for threshold boundaries, persistence of missing metrics, deterministic reproducibility, and invalid approval-state fallback.
- Updated README wording for batch evaluation and deterministic approved-rule behavior.

API keys are entered by the user inside the app and stay on that user's machine.

## If Windows Shows "Windows protected your PC"

This app is not code-signed, so Windows SmartScreen may show a blue warning the
first time you run the downloaded installer.

This is expected for this study build.

To continue:

1. Double-click `AgenticDSS-Setup.exe`.
2. If you see "Windows protected your PC", click **More info**.
3. Click **Run anyway**.
4. Follow the installer prompts.
5. Leave **Launch Agentic AI DSS for Retail Investors now** checked if you want the
   app to open immediately after installation.

You may see the same warning once more the first time the app itself opens. If so,
click **More info**, then **Run anyway** again.

The installer does not require administrator rights. It installs the app only for
your Windows user account.
