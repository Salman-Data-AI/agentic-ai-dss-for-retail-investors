from __future__ import annotations

from unittest.mock import Mock

import config
from agent import llm


def test_provider_settings_cover_supported_providers():
    assert set(config.PROVIDER_SETTINGS) == {"anthropic", "openai", "grok", "groq", "deepseek"}
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

    assert compatible_adapter.call_count == 4
