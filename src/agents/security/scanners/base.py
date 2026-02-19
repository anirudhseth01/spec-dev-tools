"""Base scanner interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.security.findings import Finding
    from src.spec.schemas import Spec


@dataclass
class ScanContext:
    """Context for security scanning."""

    files: dict[str, str]  # path -> content
    project_root: Path
    spec: Spec | None = None
    previous_findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        """Number of files to scan."""
        return len(self.files)


class BaseScanner(ABC):
    """Abstract base class for security scanners."""

    name: str = "base"
    description: str = "Base scanner"
    is_heavyweight: bool = False  # If True, only run in heavyweight mode

    @abstractmethod
    def scan(self, context: ScanContext) -> list[Finding]:
        """Scan files for vulnerabilities.

        Args:
            context: Scanning context with files and metadata.

        Returns:
            List of findings.
        """
        pass

    def supports_language(self, language: str) -> bool:
        """Check if scanner supports a language.

        Override in subclasses for language-specific scanners.
        """
        return True

    def get_file_extensions(self) -> list[str]:
        """Get file extensions this scanner handles.

        Override in subclasses for specific file types.
        Returns empty list for all files.
        """
        return []
