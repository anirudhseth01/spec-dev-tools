"""Builds code context for LLM generation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodeFile:
    """A source code file with metadata."""

    path: Path
    content: str
    language: str
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    token_estimate: int = 0

    def __post_init__(self):
        if self.token_estimate == 0:
            # Rough estimate: ~4 chars per token
            self.token_estimate = len(self.content) // 4 + 10


@dataclass
class CodeContext:
    """Context of related code for generation."""

    files: dict[str, CodeFile] = field(default_factory=dict)
    total_tokens: int = 0
    dependencies: list[str] = field(default_factory=list)
    type_definitions: list[str] = field(default_factory=list)

    def add_file(self, path: str, content: str, language: str = "python") -> None:
        """Add a file to the context."""
        code_file = CodeFile(path=Path(path), content=content, language=language)
        self.files[path] = code_file
        self.total_tokens += code_file.token_estimate

    def to_prompt(self) -> str:
        """Convert to prompt-ready format."""
        lines = ["## Existing Code Context\n"]

        for path, code_file in self.files.items():
            lines.append(f"### {path}")
            lines.append(f"```{code_file.language}")
            lines.append(code_file.content)
            lines.append("```\n")

        return "\n".join(lines)


class ContextBuilder:
    """Builds LLM context with full relevant file visibility."""

    def __init__(self, max_tokens: int = 70000):
        """Initialize context builder.

        Args:
            max_tokens: Maximum tokens for code context.
        """
        self.max_tokens = max_tokens

    def build_context(
        self,
        project_root: Path,
        target_files: list[Path],
        spec_context: str | None = None,
    ) -> CodeContext:
        """Gather full context for code generation.

        Strategy:
        1. Identify files that target files will import/depend on
        2. Identify files that import/depend on target files
        3. Load full content of related files (not snippets)
        4. Include project conventions (existing patterns)
        """
        context = CodeContext()

        # 1. Direct dependencies (imports)
        for target in target_files:
            if target.exists():
                deps = self._analyze_imports(target, project_root)
                for dep in deps:
                    if dep.exists() and str(dep) not in context.files:
                        content = self._read_full_file(dep)
                        if content:
                            context.add_file(
                                str(dep.relative_to(project_root)),
                                content,
                                self._detect_language(dep),
                            )

        # 2. Sibling files (same directory, likely related)
        for target in target_files:
            parent = target.parent if target.exists() else project_root
            if parent.exists():
                siblings = self._get_siblings(parent, target)
                for sibling in siblings[:5]:  # Limit to avoid explosion
                    if str(sibling) not in context.files:
                        content = self._read_full_file(sibling)
                        if content:
                            context.add_file(
                                str(sibling.relative_to(project_root)),
                                content,
                                self._detect_language(sibling),
                            )

        # 3. Type definitions / shared models
        type_files = self._find_type_files(project_root)
        for tf in type_files:
            if str(tf) not in context.files:
                content = self._read_full_file(tf)
                if content:
                    context.add_file(
                        str(tf.relative_to(project_root)),
                        content,
                        self._detect_language(tf),
                    )

        # 4. Truncate if over budget
        self._fit_to_budget(context)

        return context

    def _analyze_imports(self, file_path: Path, project_root: Path) -> list[Path]:
        """Analyze imports in a file to find dependencies."""
        dependencies = []

        if not file_path.exists():
            return dependencies

        try:
            content = file_path.read_text()
        except Exception:
            return dependencies

        # Python imports
        if file_path.suffix == ".py":
            # from x import y
            pattern = r"from\s+([\w.]+)\s+import"
            for match in re.finditer(pattern, content):
                module = match.group(1)
                dep_path = self._resolve_python_import(module, file_path, project_root)
                if dep_path and dep_path.exists():
                    dependencies.append(dep_path)

            # import x
            pattern = r"^import\s+([\w.]+)"
            for match in re.finditer(pattern, content, re.MULTILINE):
                module = match.group(1)
                dep_path = self._resolve_python_import(module, file_path, project_root)
                if dep_path and dep_path.exists():
                    dependencies.append(dep_path)

        # TypeScript imports
        elif file_path.suffix in [".ts", ".tsx"]:
            pattern = r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]"
            for match in re.finditer(pattern, content):
                import_path = match.group(1)
                dep_path = self._resolve_ts_import(import_path, file_path, project_root)
                if dep_path and dep_path.exists():
                    dependencies.append(dep_path)

        return dependencies

    def _resolve_python_import(
        self, module: str, source_file: Path, project_root: Path
    ) -> Path | None:
        """Resolve a Python import to a file path."""
        # Handle relative imports (e.g., "." or "..")
        if module.startswith("."):
            # Relative import
            parts = module.split(".")
            parent = source_file.parent
            for part in parts[:-1]:
                if part == "":
                    parent = parent.parent
            if parts[-1]:
                return parent / f"{parts[-1].replace('.', '/')}.py"
            return None

        # Absolute import within project
        module_path = module.replace(".", "/")
        candidates = [
            project_root / f"{module_path}.py",
            project_root / module_path / "__init__.py",
            project_root / "src" / f"{module_path}.py",
            project_root / "src" / module_path / "__init__.py",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _resolve_ts_import(
        self, import_path: str, source_file: Path, project_root: Path
    ) -> Path | None:
        """Resolve a TypeScript import to a file path."""
        if import_path.startswith("."):
            # Relative import
            base_dir = source_file.parent
            resolved = (base_dir / import_path).resolve()
            candidates = [
                resolved.with_suffix(".ts"),
                resolved.with_suffix(".tsx"),
                resolved / "index.ts",
                resolved / "index.tsx",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate
        else:
            # Could be aliased import (e.g., @/components)
            # Skip node_modules imports
            if not import_path.startswith("@/"):
                return None

            # Handle @/ alias (common in many projects)
            clean_path = import_path.replace("@/", "")
            candidates = [
                project_root / "src" / f"{clean_path}.ts",
                project_root / "src" / f"{clean_path}.tsx",
                project_root / "src" / clean_path / "index.ts",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate

        return None

    def _get_siblings(self, directory: Path, exclude: Path) -> list[Path]:
        """Get sibling files in the same directory."""
        siblings = []
        if not directory.exists():
            return siblings

        for f in directory.iterdir():
            if f.is_file() and f != exclude:
                if f.suffix in [".py", ".ts", ".tsx", ".js", ".jsx"]:
                    siblings.append(f)

        # Sort by modification time (most recent first)
        siblings.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return siblings

    def _find_type_files(self, project_root: Path) -> list[Path]:
        """Find type definition files in the project."""
        type_files = []

        # Common type file patterns
        patterns = [
            "**/types.py",
            "**/schemas.py",
            "**/models.py",
            "**/types.ts",
            "**/types/*.ts",
            "**/*.d.ts",
        ]

        for pattern in patterns:
            type_files.extend(project_root.glob(pattern))

        # Limit to reasonable number
        return type_files[:10]

    def _read_full_file(self, file_path: Path) -> str | None:
        """Read full file content."""
        try:
            return file_path.read_text()
        except Exception:
            return None

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
        }
        return ext_map.get(file_path.suffix, "text")

    def _fit_to_budget(self, context: CodeContext) -> None:
        """Truncate context to fit within token budget."""
        if context.total_tokens <= self.max_tokens:
            return

        # Sort files by importance (type files first, then by size)
        sorted_files = sorted(
            context.files.items(),
            key=lambda x: (
                not any(kw in x[0] for kw in ["types", "schemas", "models"]),
                x[1].token_estimate,
            ),
        )

        # Keep files until budget exceeded
        new_files = {}
        total = 0
        for path, code_file in sorted_files:
            if total + code_file.token_estimate <= self.max_tokens:
                new_files[path] = code_file
                total += code_file.token_estimate
            else:
                break

        context.files = new_files
        context.total_tokens = total
