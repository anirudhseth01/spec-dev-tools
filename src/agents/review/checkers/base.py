"""Base checker interface for code review."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.review.findings import ReviewComment
    from src.spec.schemas import Spec


@dataclass
class ReviewContext:
    """Context for code review checking."""

    files: dict[str, str]  # path -> content
    project_root: Path
    spec: Spec | None = None
    spec_context: str = ""  # Routed spec sections as text
    previous_comments: list[ReviewComment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        """Number of files to review."""
        return len(self.files)

    def get_file_extension(self, file_path: str) -> str:
        """Get the extension of a file."""
        return Path(file_path).suffix.lower()

    def get_python_files(self) -> dict[str, str]:
        """Get only Python files."""
        return {
            path: content
            for path, content in self.files.items()
            if self.get_file_extension(path) == ".py"
        }

    def get_typescript_files(self) -> dict[str, str]:
        """Get only TypeScript files."""
        return {
            path: content
            for path, content in self.files.items()
            if self.get_file_extension(path) in (".ts", ".tsx")
        }

    def get_javascript_files(self) -> dict[str, str]:
        """Get only JavaScript files."""
        return {
            path: content
            for path, content in self.files.items()
            if self.get_file_extension(path) in (".js", ".jsx")
        }


class BaseChecker(ABC):
    """Abstract base class for code review checkers."""

    name: str = "base"
    description: str = "Base checker"
    is_heavyweight: bool = False  # If True, only run with LLM

    @abstractmethod
    def check(self, context: ReviewContext) -> list[ReviewComment]:
        """Check files for issues.

        Args:
            context: Review context with files and metadata.

        Returns:
            List of review comments.
        """
        pass

    def supports_language(self, language: str) -> bool:
        """Check if checker supports a language.

        Override in subclasses for language-specific checkers.
        """
        return True

    def get_file_extensions(self) -> list[str]:
        """Get file extensions this checker handles.

        Override in subclasses for specific file types.
        Returns empty list for all files.
        """
        return []

    def _generate_id(self, prefix: str, file_path: str, line: int | None = None) -> str:
        """Generate a unique ID for a comment."""
        import hashlib
        base = f"{prefix}:{file_path}:{line or 0}"
        return hashlib.md5(base.encode()).hexdigest()[:8]
