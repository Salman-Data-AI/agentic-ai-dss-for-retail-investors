"""
Stable fingerprinting for compiled-rule approval decisions.

The fingerprint is SHA-256 over a canonical JSON object with three string
inputs, in this explicit order: ``rule_text``, ``tool_schema_version``, and
``prompt_version``. JSON serialization with sorted keys and compact separators
keeps the digest stable across Python runs and avoids delimiter ambiguity.

Rule text canonicalization normalizes line endings to ``\\n`` and strips
trailing spaces from each line, then trims leading and trailing blank lines.
Interior blank lines, word changes, punctuation changes, and indentation at the
start of a line still affect the digest. This avoids re-approval for harmless
clipboard/newline noise while ensuring substantive raw-text edits change the
fingerprint. Model/provider are deliberately excluded per DI#4 D6.
"""

from __future__ import annotations

import hashlib
import json


def fingerprint_rule_inputs(rule_text: str, tool_schema_version: str, prompt_version: str) -> str:
    """Return a deterministic SHA-256 digest for the inputs a compile depended on."""
    payload = {
        "prompt_version": _require_string(prompt_version, "prompt_version"),
        "rule_text": _canonicalize_rule_text(_require_string(rule_text, "rule_text")),
        "tool_schema_version": _require_string(tool_schema_version, "tool_schema_version"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonicalize_rule_text(rule_text: str) -> str:
    normalized = rule_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _require_string(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    return value
