"""Base classes for test generators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.spec.schemas import TestCase, EdgeCases


@dataclass
class TestGeneratorContext:
    """Context for test generation."""

    test_cases: list[TestCase] = field(default_factory=list)
    edge_cases: EdgeCases | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    code_under_test: dict[str, str] = field(default_factory=dict)  # filepath -> code
    spec_context: str = ""  # Additional spec context as text

    @property
    def has_test_cases(self) -> bool:
        """Check if there are test cases to generate."""
        return len(self.test_cases) > 0

    @property
    def has_edge_cases(self) -> bool:
        """Check if there are edge cases defined."""
        return (
            self.edge_cases is not None
            and (
                len(self.edge_cases.boundary_conditions) > 0
                or len(self.edge_cases.concurrency) > 0
                or len(self.edge_cases.failure_modes) > 0
            )
        )


@dataclass
class GeneratedTest:
    """A generated test file."""

    file_path: str
    content: str
    test_framework: str
    language: str
    test_count: int = 0
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "test_framework": self.test_framework,
            "language": self.language,
            "test_count": self.test_count,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }


@dataclass
class TestGenerationResult:
    """Result of test generation."""

    tests: list[GeneratedTest] = field(default_factory=list)
    fixtures: dict[str, str] = field(default_factory=dict)  # fixture name -> code
    mocks: dict[str, str] = field(default_factory=dict)  # mock name -> code
    summary: str = ""

    @property
    def total_tests(self) -> int:
        """Total number of tests generated."""
        return sum(t.test_count for t in self.tests)

    @property
    def all_valid(self) -> bool:
        """Check if all generated tests are valid."""
        return all(t.is_valid for t in self.tests)

    @property
    def validation_errors(self) -> list[str]:
        """Get all validation errors."""
        errors = []
        for test in self.tests:
            for err in test.validation_errors:
                errors.append(f"{test.file_path}: {err}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tests": [t.to_dict() for t in self.tests],
            "fixtures": self.fixtures,
            "mocks": self.mocks,
            "summary": self.summary,
            "total_tests": self.total_tests,
            "all_valid": self.all_valid,
        }


class BaseTestGenerator(ABC):
    """Abstract base class for test generators."""

    @property
    @abstractmethod
    def language(self) -> str:
        """Return language identifier."""
        pass

    @property
    @abstractmethod
    def test_framework(self) -> str:
        """Return test framework name."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return test file extension."""
        pass

    @abstractmethod
    def generate_unit_test_prompt(
        self,
        test_case: TestCase,
        code_context: str,
    ) -> str:
        """Generate prompt for unit test creation."""
        pass

    @abstractmethod
    def generate_edge_case_prompt(
        self,
        edge_cases: EdgeCases,
        code_context: str,
    ) -> str:
        """Generate prompt for edge case tests."""
        pass

    @abstractmethod
    def generate_fixture_prompt(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
    ) -> str:
        """Generate prompt for test fixtures/mocks."""
        pass

    @abstractmethod
    def parse_generated_tests(self, llm_response: str) -> list[GeneratedTest]:
        """Parse LLM response into generated test objects."""
        pass

    @abstractmethod
    def validate_test(self, code: str) -> list[str]:
        """Validate generated test code. Returns list of errors."""
        pass

    def get_system_prompt(self) -> str:
        """Get system prompt for test generation."""
        return f"""You are an expert test engineer specializing in {self.language} and {self.test_framework}.
Generate comprehensive, production-quality tests that:
- Follow {self.test_framework} best practices and conventions
- Include proper setup and teardown when needed
- Use descriptive test names following test_<unit>_<scenario> pattern
- Include edge case handling and error scenarios
- Use appropriate mocking for external dependencies
- Add helpful comments and docstrings

Output format:
For each test file, use this format:
```{self.language}
# FILE: path/to/test_file{self.file_extension}
<test code>
```
"""

    def get_fixture_system_prompt(self) -> str:
        """Get system prompt for fixture generation."""
        return f"""You are an expert test engineer specializing in {self.language} and {self.test_framework}.
Generate reusable test fixtures and mocks that:
- Follow {self.test_framework} fixture conventions
- Are modular and composable
- Handle cleanup properly
- Include type hints where applicable

Output format:
For each fixture file, use this format:
```{self.language}
# FILE: path/to/conftest{self.file_extension} or fixtures{self.file_extension}
<fixture code>
```
"""
