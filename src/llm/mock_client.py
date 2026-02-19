"""Mock LLM client for testing."""

from __future__ import annotations

from typing import Callable

from src.llm.client import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """Mock LLM client for testing without API calls."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default_response: str = "# FILE: generated.py\npass",
        response_fn: Callable[[str, str], str] | None = None,
    ):
        """Initialize mock client.

        Args:
            responses: Dict mapping prompt substrings to responses.
            default_response: Default response if no match found.
            response_fn: Function to generate custom responses.
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.response_fn = response_fn
        self.call_history: list[dict] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Generate a mock response."""
        # Record the call
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })

        # Use custom function if provided
        if self.response_fn:
            content = self.response_fn(system_prompt, user_prompt)
            return LLMResponse(
                content=content,
                model="mock",
                usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            )

        # Check for matching response
        for key, response in self.responses.items():
            if key in user_prompt or key in system_prompt:
                return LLMResponse(
                    content=response,
                    model="mock",
                    usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                )

        # Return default
        return LLMResponse(
            content=self.default_response,
            model="mock",
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )

    def generate_streaming(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        """Generate mock streaming response."""
        response = self.generate(
            system_prompt, user_prompt, max_tokens, temperature
        )

        # Yield content in chunks
        content = response.content
        chunk_size = 10
        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]

    def add_response(self, trigger: str, response: str) -> None:
        """Add a response mapping."""
        self.responses[trigger] = response

    def clear_history(self) -> None:
        """Clear call history."""
        self.call_history = []

    @property
    def last_call(self) -> dict | None:
        """Get the last call made."""
        return self.call_history[-1] if self.call_history else None

    @property
    def call_count(self) -> int:
        """Get number of calls made."""
        return len(self.call_history)


def create_skeleton_mock() -> MockLLMClient:
    """Create a mock client that returns Python skeletons."""
    def response_fn(system: str, user: str) -> str:
        if "skeleton" in system.lower():
            return '''```python
# FILE: src/feature/models.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class Request:
    """Input request model."""
    id: str
    data: dict
    metadata: Optional[dict] = None

@dataclass
class Response:
    """Output response model."""
    success: bool
    message: str
    result: Optional[dict] = None
```

```python
# FILE: src/feature/service.py
from abc import ABC, abstractmethod
from src.feature.models import Request, Response

class Service(ABC):
    """Abstract service interface."""

    @abstractmethod
    def process(self, request: Request) -> Response:
        """Process a request."""
        raise NotImplementedError
```'''
        else:
            return '''```python
# FILE: src/feature/service.py
from src.feature.models import Request, Response

class ServiceImpl(Service):
    """Concrete service implementation."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process(self, request: Request) -> Response:
        """Process a request."""
        self.logger.info(f"Processing request {request.id}")
        try:
            result = self._do_work(request.data)
            return Response(success=True, message="OK", result=result)
        except Exception as e:
            self.logger.error(f"Error processing: {e}")
            return Response(success=False, message=str(e))

    def _do_work(self, data: dict) -> dict:
        """Do the actual work."""
        return {"processed": True, **data}
```'''

    return MockLLMClient(response_fn=response_fn)
