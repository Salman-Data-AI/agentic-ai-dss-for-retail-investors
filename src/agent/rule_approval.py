"""Approval state machine for compiled deterministic rule sets."""

from __future__ import annotations

from typing import Any

from settings import (
    RULE_APPROVAL_APPROVED,
    RULE_APPROVAL_COMPILED,
    RULE_APPROVAL_INVALIDATED,
    RULE_APPROVAL_UNVALIDATED,
    load_settings,
    save_settings,
)

from .rule_compiler import compile_rule_text, current_rule_fingerprint
from .rule_sets import validate_rule_set
from .tool_schemas import SUPPORTED_METRIC_KEYS


def prepare_rule_set(settings: dict[str, Any]) -> dict[str, Any]:
    """
    Return approved rule-set state or a structured block.

    Raw rule edits always win over a stale lock. When the current fingerprint no
    longer matches persisted state, this helper compiles the new text and saves
    it as ``compiled`` so the dashboard approval action can lock it later.
    """
    fingerprint = current_rule_fingerprint(settings["buy_rules"], settings["sell_rules"])
    saved_fingerprint = settings.get("compiled_rule_fingerprint") or ""
    saved_rule_set = settings.get("compiled_rule_set")
    saved_state = settings.get("rule_approval_state") or RULE_APPROVAL_UNVALIDATED

    if saved_fingerprint == fingerprint and isinstance(saved_rule_set, dict):
        validation = validate_rule_set(saved_rule_set, set(SUPPORTED_METRIC_KEYS))
        if validation["valid"] and saved_state == RULE_APPROVAL_APPROVED:
            return {"ok": True, "rule_set": saved_rule_set, "fingerprint": fingerprint, "state": RULE_APPROVAL_APPROVED}
        if validation["valid"] and saved_state == RULE_APPROVAL_COMPILED:
            return _blocked(
                "approval_required",
                "Rule set compiled and must be approved before analysis can run.",
                fingerprint,
                rule_set=saved_rule_set,
                state=RULE_APPROVAL_COMPILED,
            )
        save_settings(
            {
                **settings,
                "rule_approval_state": RULE_APPROVAL_INVALIDATED,
            }
        )
        return _blocked("invalidated", "Approved rule set no longer validates.", fingerprint, validation=validation)

    compile_result = compile_rule_text(
        buy_rules=settings["buy_rules"],
        sell_rules=settings["sell_rules"],
        provider=settings["provider"],
        model=settings["model"],
        temperature=settings.get("temperature"),
    )
    if not compile_result["ok"]:
        save_settings(
            {
                **settings,
                "compiled_rule_set": None,
                "compiled_rule_fingerprint": fingerprint,
                "rule_approval_state": RULE_APPROVAL_INVALIDATED,
            }
        )
        return {**compile_result, "state": RULE_APPROVAL_INVALIDATED}

    save_settings(
        {
            **settings,
            "compiled_rule_set": compile_result["rule_set"],
            "compiled_rule_fingerprint": fingerprint,
            "rule_approval_state": RULE_APPROVAL_COMPILED,
        }
    )
    return _blocked(
        "approval_required",
        "Rule set compiled and must be approved before analysis can run.",
        fingerprint,
        rule_set=compile_result["rule_set"],
        state=RULE_APPROVAL_COMPILED,
    )


def compile_current_settings() -> dict[str, Any]:
    """Compile current settings and persist the compiled-but-unapproved state."""
    return prepare_rule_set(load_settings())


def approve_current_rule_set() -> dict[str, Any]:
    """Approve the current compiled rule set through the shared state machine."""
    settings = load_settings()
    fingerprint = current_rule_fingerprint(settings["buy_rules"], settings["sell_rules"])
    if settings.get("compiled_rule_fingerprint") != fingerprint or not isinstance(
        settings.get("compiled_rule_set"), dict
    ):
        prepared = prepare_rule_set(settings)
        if prepared["ok"] or prepared.get("code") == "approval_required":
            settings = load_settings()
        else:
            return prepared

    settings = load_settings()
    if settings.get("compiled_rule_fingerprint") != fingerprint or not isinstance(
        settings.get("compiled_rule_set"), dict
    ):
        return _blocked(
            "approval_missing_compile", "No current compiled rule set is available to approve.", fingerprint
        )

    validation = validate_rule_set(settings["compiled_rule_set"], set(SUPPORTED_METRIC_KEYS))
    if not validation["valid"]:
        save_settings({**settings, "rule_approval_state": RULE_APPROVAL_INVALIDATED})
        return _blocked("invalidated", "Compiled rule set no longer validates.", fingerprint, validation=validation)

    save_settings({**settings, "rule_approval_state": RULE_APPROVAL_APPROVED})
    return {
        "ok": True,
        "state": RULE_APPROVAL_APPROVED,
        "fingerprint": fingerprint,
        "rule_set": settings["compiled_rule_set"],
    }


def _blocked(
    code: str,
    message: str,
    fingerprint: str,
    *,
    rule_set: dict | None = None,
    state: str | None = None,
    validation: dict | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "fingerprint": fingerprint,
        "rule_set": rule_set,
        "state": state,
        "validation": validation,
    }
