"""Provider-agnostic LLM adapters for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sys
from typing import Protocol

from anthropic import Anthropic

from .tool_schemas import TOOL_SCHEMAS


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    tool_calls: list[ToolCall] | None = None
    final_text: str | None = None
    error: str | None = None


class LLMClient(Protocol):
    """Uniform interface consumed by run_agent."""

    def next_step(self) -> LLMResponse:
        """Ask the model for the next tool calls or final response text."""

    def append_tool_results(self, results: list[dict]) -> None:
        """Append executed tool results in the provider's native message format."""


class AnthropicAdapter:
    """Anthropic Messages API adapter preserving the existing tool-use flow."""

    def __init__(
        self,
        *,
        model: str,
        system: str,
        user_content: str,
        api_key: str,
        client=None,
        max_tokens: int = 1024,
    ) -> None:
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set for PROVIDER='anthropic'")
        self.model = model
        self.system = system
        self.max_tokens = max_tokens
        self.tools = TOOL_SCHEMAS
        self.messages = [{"role": "user", "content": user_content}]
        self.client = client or Anthropic(api_key=api_key)

    def next_step(self) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
        )

        if response.stop_reason == "tool_use":
            self.messages.append({"role": "assistant", "content": response.content})
            calls = [
                ToolCall(id=block.id, name=block.name, arguments=block.input)
                for block in response.content
                if getattr(block, "type", None) == "tool_use"
            ]
            return LLMResponse(tool_calls=calls)

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return LLMResponse(final_text=block.text.strip())
            return LLMResponse(error="Agent returned no text content")

        return LLMResponse(error=f"Unexpected stop reason: {response.stop_reason}")

    def append_tool_results(self, results: list[dict]) -> None:
        self.messages.append({"role": "user", "content": [
            {
                "type": "tool_result",
                "tool_use_id": result["id"],
                "content": json.dumps(result["result"]),
            }
            for result in results
        ]})


class OpenAICompatibleAdapter:
    """Chat Completions adapter for OpenAI-compatible providers."""

    def __init__(
        self,
        *,
        model: str,
        system: str,
        user_content: str,
        api_key: str,
        base_url: str,
        provider: str = "openai-compatible",
        client=None,
        max_tokens: int = 1024,
    ) -> None:
        if not api_key:
            raise RuntimeError("API key is not set for the selected OpenAI-compatible provider")
        if not base_url:
            raise RuntimeError("Base URL is not configured for the selected provider")

        self.model = model
        self.provider = provider
        self.max_tokens = max_tokens
        self.tools = self._render_tools(TOOL_SCHEMAS)
        self.messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        self.client = client or self._build_client(api_key=api_key, base_url=base_url)

    def next_step(self) -> LLMResponse:
        token_limit = (
            {"max_completion_tokens": self.max_tokens}
            if self.provider == "openai"
            else {"max_tokens": self.max_tokens}
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            tool_choice="auto",
            **token_limit,
        )
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            self.messages.append(self._assistant_message(message))
            return LLMResponse(tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=self._parse_arguments(call.function.arguments),
                )
                for call in tool_calls
            ])

        content = getattr(message, "content", None)
        if content:
            return LLMResponse(final_text=content.strip())

        finish_reason = getattr(choice, "finish_reason", "unknown")
        return LLMResponse(error=f"Unexpected stop reason: {finish_reason}")

    def append_tool_results(self, results: list[dict]) -> None:
        for result in results:
            self.messages.append({
                "role": "tool",
                "tool_call_id": result["id"],
                "content": json.dumps(result["result"]),
            })

    @staticmethod
    def _build_client(*, api_key: str, base_url: str):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required for PROVIDER values openai, grok, groq, and deepseek. "
                "Install dependencies in the Python environment running the app with: "
                f"{sys.executable} -m pip install -r requirements.txt"
            ) from exc
        return OpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _render_tools(tool_schemas: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tool_schemas
        ]

    @staticmethod
    def _assistant_message(message) -> dict:
        if hasattr(message, "model_dump"):
            return message.model_dump(exclude_none=True)
        return {
            "role": "assistant",
            "content": getattr(message, "content", None),
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in (getattr(message, "tool_calls", None) or [])
            ],
        }

    @staticmethod
    def _parse_arguments(raw_arguments: str | dict | None) -> dict:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def create_llm_client(
    *,
    provider: str,
    model: str,
    system: str,
    user_content: str,
    provider_settings: dict,
) -> LLMClient:
    """Build the selected provider adapter from config-provided settings."""
    normalized = provider.lower().strip()
    api_key_env = provider_settings["api_key_env"]
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"{api_key_env} is not set for PROVIDER={normalized!r}")

    if normalized == "anthropic":
        return AnthropicAdapter(
            model=model,
            system=system,
            user_content=user_content,
            api_key=api_key,
        )

    if normalized in {"openai", "grok", "groq", "deepseek"}:
        return OpenAICompatibleAdapter(
            model=model,
            system=system,
            user_content=user_content,
            api_key=api_key,
            base_url=provider_settings["base_url"],
            provider=normalized,
        )

    raise RuntimeError(
        f"Unsupported PROVIDER={provider!r}. Choose one of: anthropic, openai, grok, groq, deepseek."
    )
