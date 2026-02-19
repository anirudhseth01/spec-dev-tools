"""Registry for test generators."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.testing.generators.base import BaseTestGenerator


class GeneratorRegistry:
    """Registry for test generators."""

    def __init__(self):
        self._generators: dict[str, BaseTestGenerator] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in generators."""
        from src.agents.testing.generators.pytest_generator import PytestGenerator
        from src.agents.testing.generators.jest_generator import JestGenerator

        self.register(PytestGenerator())
        self.register(JestGenerator())

    def register(self, generator: BaseTestGenerator) -> None:
        """Register a test generator."""
        self._generators[generator.language] = generator

    def get(self, language: str) -> BaseTestGenerator:
        """Get generator for a language."""
        language = language.lower()
        if language not in self._generators:
            raise ValueError(
                f"No generator for language: {language}. "
                f"Available: {list(self._generators.keys())}"
            )
        return self._generators[language]

    def has(self, language: str) -> bool:
        """Check if a generator exists for a language."""
        return language.lower() in self._generators

    def list_languages(self) -> list[str]:
        """List all registered languages."""
        return list(self._generators.keys())

    def detect_language(self, project_root: Path) -> str:
        """Auto-detect project language from files."""
        indicators = {
            "python": [
                "pyproject.toml",
                "setup.py",
                "requirements.txt",
                "Pipfile",
                "poetry.lock",
                "pytest.ini",
                "conftest.py",
            ],
            "typescript": [
                "tsconfig.json",
                "jest.config.ts",
                "jest.config.js",
            ],
        }

        # Check for language-specific files
        for lang, files in indicators.items():
            for filename in files:
                if (project_root / filename).exists():
                    # For package.json, check if it's TypeScript
                    if filename in ("jest.config.js",):
                        if (project_root / "tsconfig.json").exists():
                            return "typescript"
                        continue
                    return lang

        # Check for test directories
        if (project_root / "tests").exists():
            py_tests = list((project_root / "tests").rglob("test_*.py"))
            if py_tests:
                return "python"

        if (project_root / "src" / "__tests__").exists():
            ts_tests = list((project_root / "src" / "__tests__").rglob("*.test.ts"))
            if ts_tests:
                return "typescript"

        # Count source files as fallback
        py_count = len(list(project_root.rglob("*.py")))
        ts_count = len(list(project_root.rglob("*.ts")))

        if ts_count > py_count:
            return "typescript"
        elif py_count > 0:
            return "python"

        return "python"  # Default fallback

    def detect_from_tech_stack(self, tech_stack: str | list[str]) -> str | None:
        """Detect language from spec's tech stack.

        Args:
            tech_stack: Either a string (comma-separated) or list of tech stack items.

        Returns:
            Detected language or None.
        """
        language_keywords = {
            "python": ["python", "django", "flask", "fastapi", "pytest"],
            "typescript": [
                "typescript", "ts", "node", "express", "nestjs", "jest", "react"
            ],
        }

        # Handle string or list
        if isinstance(tech_stack, str):
            tech_items = [t.strip().lower() for t in tech_stack.split(",")]
        else:
            tech_items = [t.lower() for t in tech_stack]

        for lang, keywords in language_keywords.items():
            for tech in tech_items:
                if any(kw in tech for kw in keywords):
                    if self.has(lang):
                        return lang

        return None

    def get_test_framework(self, language: str) -> str:
        """Get the test framework for a language."""
        generator = self.get(language)
        return generator.test_framework

    def get_test_file_extension(self, language: str) -> str:
        """Get the test file extension for a language."""
        generator = self.get(language)
        return generator.file_extension
