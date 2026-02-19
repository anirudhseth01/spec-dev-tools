"""LLM client interface for code generation."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.usage.get("total_tokens", 0)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            system_prompt: System/instruction prompt.
            user_prompt: User query/task.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with generated content.
        """
        pass

    @abstractmethod
    def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        """Generate a streaming response from the LLM.

        Yields chunks of the response as they're generated.
        """
        pass

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Default implementation uses rough character count.
        Subclasses can override with proper tokenizer.
        """
        # Rough estimate: ~4 characters per token
        return len(text) // 4


class ClaudeClient(LLMClient):
    """Claude API client implementation."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            model: Model ID to use.
        """
        self.model = model
        self._client = None

        try:
            import anthropic
            if api_key:
                self._client = anthropic.Anthropic(api_key=api_key)
            else:
                self._client = anthropic.Anthropic()  # Uses env var
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a response using Claude."""
        message = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        )

        return LLMResponse(
            content=message.content[0].text,
            model=message.model,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "total_tokens": message.usage.input_tokens + message.usage.output_tokens,
            },
            finish_reason=message.stop_reason,
        )

    def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        """Generate a streaming response using Claude."""
        with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        ) as stream:
            for text in stream.text_stream:
                yield text

    def count_tokens(self, text: str) -> int:
        """Count tokens using Claude's tokenizer."""
        try:
            response = self._client.count_tokens(text)
            return response
        except Exception:
            # Fallback to rough estimate
            return len(text) // 4


class ClaudeCodeClient(LLMClient):
    """LLM client that uses the Claude Code CLI.

    This client shells out to the `claude` CLI command, allowing spec-dev-tools
    to use the user's existing Claude Code authentication instead of requiring
    a separate API key.
    """

    def __init__(self, model: str | None = None, timeout: int = 300):
        """Initialize Claude Code client.

        Args:
            model: Optional model override (uses Claude Code default if not set).
            timeout: Command timeout in seconds (default 5 minutes).
        """
        self.model = model
        self.timeout = timeout
        self._verify_claude_cli()

    def _verify_claude_cli(self) -> None:
        """Verify that claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError("claude CLI returned non-zero exit code")
        except FileNotFoundError:
            raise RuntimeError(
                "claude CLI not found. Install Claude Code: "
                "https://docs.anthropic.com/claude-code"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("claude CLI timed out")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a response using Claude Code CLI.

        Uses the --print flag for non-interactive output.
        Note: max_tokens and temperature are ignored as Claude CLI
        handles these internally.
        """
        try:
            # Build command
            cmd = ["claude", "--print"]

            if self.model:
                cmd.extend(["--model", self.model])

            # Add system prompt if provided
            if system_prompt:
                cmd.extend(["--system-prompt", system_prompt])

            # Add the user prompt as the final argument
            cmd.append(user_prompt)

            # Run claude CLI
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                raise RuntimeError(f"claude CLI failed: {error_msg}")

            content = result.stdout.strip()

            # Estimate token usage
            input_text = (system_prompt or "") + user_prompt
            return LLMResponse(
                content=content,
                model=self.model or "claude-code",
                usage={
                    "input_tokens": self.count_tokens(input_text),
                    "output_tokens": self.count_tokens(content),
                    "total_tokens": self.count_tokens(input_text) + self.count_tokens(content),
                },
                finish_reason="stop",
                metadata={"source": "claude-code-cli"},
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude CLI timed out after {self.timeout}s")

    def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        """Generate a streaming response using Claude Code CLI.

        Note: Claude Code CLI doesn't support true streaming in --print mode,
        so this yields the complete response as a single chunk.
        """
        response = self.generate(system_prompt, user_prompt, max_tokens, temperature)
        yield response.content


def get_llm_client(prefer_claude_code: bool = True, **kwargs) -> LLMClient:
    """Get the best available LLM client.

    Args:
        prefer_claude_code: If True, prefer Claude Code CLI over API.
        **kwargs: Additional arguments passed to the client constructor.

    Returns:
        LLMClient instance.

    Raises:
        RuntimeError: If no LLM client is available.
    """
    errors = []

    # Try Claude Code CLI first if preferred
    if prefer_claude_code:
        try:
            return ClaudeCodeClient(**{k: v for k, v in kwargs.items() if k in ['model', 'timeout']})
        except Exception as e:
            errors.append(f"Claude Code CLI: {e}")

    # Try Anthropic API
    try:
        return ClaudeClient(**{k: v for k, v in kwargs.items() if k in ['api_key', 'model']})
    except Exception as e:
        errors.append(f"Anthropic API: {e}")

    # Try Claude Code CLI as fallback if not preferred
    if not prefer_claude_code:
        try:
            return ClaudeCodeClient(**{k: v for k, v in kwargs.items() if k in ['model', 'timeout']})
        except Exception as e:
            errors.append(f"Claude Code CLI: {e}")

    raise RuntimeError(
        "No LLM client available. Errors:\n" + "\n".join(f"  - {e}" for e in errors)
    )
