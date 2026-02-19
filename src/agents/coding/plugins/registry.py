"""Plugin registry for language support."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.coding.plugins.base import LanguagePlugin


class PluginRegistry:
    """Registry for language plugins."""

    def __init__(self):
        self._plugins: dict[str, LanguagePlugin] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in plugins."""
        from src.agents.coding.plugins.python_plugin import PythonPlugin
        from src.agents.coding.plugins.typescript_plugin import TypeScriptPlugin

        self.register(PythonPlugin())
        self.register(TypeScriptPlugin())

    def register(self, plugin: LanguagePlugin) -> None:
        """Register a language plugin."""
        self._plugins[plugin.language_name] = plugin

    def get(self, language: str) -> LanguagePlugin:
        """Get plugin for a language."""
        language = language.lower()
        if language not in self._plugins:
            raise ValueError(
                f"No plugin for language: {language}. "
                f"Available: {list(self._plugins.keys())}"
            )
        return self._plugins[language]

    def has(self, language: str) -> bool:
        """Check if a plugin exists for a language."""
        return language.lower() in self._plugins

    def list_languages(self) -> list[str]:
        """List all registered languages."""
        return list(self._plugins.keys())

    def detect_language(self, project_root: Path) -> str:
        """Auto-detect project language from files."""
        indicators = {
            "python": [
                "pyproject.toml",
                "setup.py",
                "requirements.txt",
                "Pipfile",
                "poetry.lock",
            ],
            "typescript": [
                "tsconfig.json",
                "package.json",  # Could be JS too
            ],
        }

        # Check for language-specific files
        for lang, files in indicators.items():
            for filename in files:
                if (project_root / filename).exists():
                    # For package.json, check if it's TypeScript
                    if filename == "package.json":
                        if (project_root / "tsconfig.json").exists():
                            return "typescript"
                        # Could add more JS vs TS detection
                        continue
                    return lang

        # Count source files as fallback
        py_count = len(list(project_root.rglob("*.py")))
        ts_count = len(list(project_root.rglob("*.ts")))

        if ts_count > py_count:
            return "typescript"
        elif py_count > 0:
            return "python"

        return "python"  # Default fallback

    def detect_from_spec(self, tech_stack: str | list[str]) -> str | None:
        """Detect language from spec's tech stack.

        Args:
            tech_stack: Either a string (comma-separated) or list of tech stack items.

        Returns:
            Detected language or None.
        """
        language_keywords = {
            "python": ["python", "django", "flask", "fastapi", "pytest"],
            "typescript": ["typescript", "ts", "node", "express", "nestjs", "jest"],
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
