from __future__ import annotations

from unittest.mock import Mock

import config
from agent import llm


def test_provider_settings_cover_supported_providers():
    assert set(config.PROVIDER_SETTINGS) == {"anthropic", "openai", "grok", "groq", "deepseek", "gemini", "cerebras"}
    assert config.PROVIDER_DEFAULT_MODELS == {
        "anthropic": "claude-haiku-4-5-20251001",
        "openai": "gpt-5.4-nano",
        "grok": "grok-4.3",
        "groq": "llama-3.1-8b-instant",
        "deepseek": "deepseek-v4-flash",
        "gemini": "gemini-2.5-flash",
        "cerebras": "gpt-oss-120b",
    }
    assert config.PROVIDER_SETTINGS["openai"] == {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    }
    assert config.PROVIDER_SETTINGS["grok"] == {
        "api_key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
    }
    assert config.PROVIDER_SETTINGS["groq"] == {
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
    }
    assert config.PROVIDER_SETTINGS["deepseek"] == {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
    }
    assert config.PROVIDER_SETTINGS["gemini"] == {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }
    assert config.PROVIDER_SETTINGS["cerebras"] == {
        "api_key_env": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
    }


def test_create_llm_client_routes_each_provider(monkeypatch):
    anthropic_adapter = Mock(return_value="anthropic-client")
    compatible_adapter = Mock(return_value="compatible-client")
    monkeypatch.setattr(llm, "AnthropicAdapter", anthropic_adapter)
    monkeypatch.setattr(llm, "OpenAICompatibleAdapter", compatible_adapter)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("XAI_API_KEY", "xai-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")

    assert llm.create_llm_client(
        provider="anthropic",
        model="m",
        system="s",
        user_content="u",
        provider_settings=config.PROVIDER_SETTINGS["anthropic"],
    ) == "anthropic-client"
    anthropic_adapter.assert_called_once_with(
        model="m",
        system="s",
        user_content="u",
        api_key="anthropic-key",
    )

    for provider, expected_key in [
        ("openai", "openai-key"),
        ("grok", "xai-key"),
        ("groq", "groq-key"),
        ("deepseek", "deepseek-key"),
        ("gemini", "gemini-key"),
        ("cerebras", "cerebras-key"),
    ]:
        assert llm.create_llm_client(
            provider=provider,
            model="m",
            system="s",
            user_content="u",
            provider_settings=config.PROVIDER_SETTINGS[provider],
        ) == "compatible-client"
        assert compatible_adapter.call_args.kwargs["api_key"] == expected_key
        assert compatible_adapter.call_args.kwargs["base_url"] == config.PROVIDER_SETTINGS[provider]["base_url"]

    assert compatible_adapter.call_count == 6


def test_create_llm_client_passes_optional_max_tokens(monkeypatch):
    compatible_adapter = Mock(return_value="compatible-client")
    monkeypatch.setattr(llm, "OpenAICompatibleAdapter", compatible_adapter)
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")

    assert llm.create_llm_client(
        provider="cerebras",
        model="m",
        system="s",
        user_content="u",
        provider_settings=config.PROVIDER_SETTINGS["cerebras"],
        tool_schemas=[],
        max_tokens=8192,
    ) == "compatible-client"

    assert compatible_adapter.call_args.kwargs["tool_schemas"] == []
    assert compatible_adapter.call_args.kwargs["max_tokens"] == 8192


def test_create_llm_client_passes_optional_temperature(monkeypatch):
    compatible_adapter = Mock(return_value="compatible-client")
    monkeypatch.setattr(llm, "OpenAICompatibleAdapter", compatible_adapter)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    assert llm.create_llm_client(
        provider="openai",
        model="m",
        system="s",
        user_content="u",
        provider_settings=config.PROVIDER_SETTINGS["openai"],
        temperature=0.0,
    ) == "compatible-client"

    assert compatible_adapter.call_args.kwargs["temperature"] == 0.0
