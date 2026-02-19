"""Base classes for language plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LanguageConventions:
    """Language-specific conventions."""

    file_extension: str
    import_style: str  # "explicit", "wildcard", "namespace"
    type_annotation: str  # "inline", "separate", "optional"
    error_handling: str  # "exceptions", "result_types", "error_codes"
    naming_convention: str  # "snake_case", "camelCase", "PascalCase"
    docstring_format: str  # "google", "numpy", "jsdoc", "godoc"
    test_framework: str  # "pytest", "jest", "go test"


@dataclass
class GeneratedFile:
    """A generated code file."""

    path: str
    content: str
    language: str
    is_skeleton: bool = False
    is_test: bool = False


class LanguagePlugin(ABC):
    """Base class for language-specific code generation."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return language identifier."""
        pass

    @property
    @abstractmethod
    def conventions(self) -> LanguageConventions:
        """Return language conventions."""
        pass

    @abstractmethod
    def generate_skeleton_prompt(self, spec_context: str) -> str:
        """Generate language-specific skeleton prompt."""
        pass

    @abstractmethod
    def generate_implementation_prompt(
        self,
        skeleton: str,
        spec_context: str,
        code_context: str,
    ) -> str:
        """Generate language-specific implementation prompt."""
        pass

    @abstractmethod
    def parse_generated_code(self, llm_response: str) -> dict[str, str]:
        """Parse LLM response into file path -> content mapping."""
        pass

    @abstractmethod
    def validate_syntax(self, code: str) -> list[str]:
        """Validate generated code syntax. Returns list of error messages."""
        pass

    def get_skeleton_system_prompt(self) -> str:
        """Get system prompt for skeleton generation."""
        return f"""You are an expert {self.language_name} software engineer.
Generate ONLY code skeletons - interfaces, types, abstract classes, and function signatures.
DO NOT implement any logic yet.

Conventions for {self.language_name}:
- File extension: {self.conventions.file_extension}
- Naming: {self.conventions.naming_convention}
- Docstrings: {self.conventions.docstring_format} format
- Error handling: {self.conventions.error_handling}

Output format:
For each file, use this format:
```{self.language_name}
# FILE: path/to/file{self.conventions.file_extension}
<code here>
```
"""

    def get_implementation_system_prompt(self) -> str:
        """Get system prompt for implementation generation."""
        return f"""You are an expert {self.language_name} software engineer.
Implement the provided code skeleton with production-quality code.

Conventions for {self.language_name}:
- File extension: {self.conventions.file_extension}
- Naming: {self.conventions.naming_convention}
- Docstrings: {self.conventions.docstring_format} format
- Error handling: {self.conventions.error_handling}
- Test framework: {self.conventions.test_framework}

Rules:
- Keep the exact function signatures from the skeleton
- Add proper error handling
- Include appropriate logging
- Write maintainable, readable code

Output format:
For each file, use this format:
```{self.language_name}
# FILE: path/to/file{self.conventions.file_extension}
<code here>
```
"""
