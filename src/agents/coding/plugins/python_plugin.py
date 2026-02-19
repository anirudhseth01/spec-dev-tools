"""Python language plugin for code generation."""

from __future__ import annotations

import ast
import re
from typing import Any

from src.agents.coding.plugins.base import LanguagePlugin, LanguageConventions


class PythonPlugin(LanguagePlugin):
    """Python-specific code generation plugin."""

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def conventions(self) -> LanguageConventions:
        return LanguageConventions(
            file_extension=".py",
            import_style="explicit",
            type_annotation="inline",
            error_handling="exceptions",
            naming_convention="snake_case",
            docstring_format="google",
            test_framework="pytest",
        )

    def generate_skeleton_prompt(self, spec_context: str) -> str:
        return f"""Generate Python code skeletons based on the following specification.

Create ONLY:
- Abstract base classes (ABC) with @abstractmethod decorators
- Dataclasses for data structures with full type hints
- Protocol classes for duck typing interfaces
- Function signatures with `raise NotImplementedError`
- Enum classes for fixed choices

DO NOT generate implementations yet.

## Python Conventions
- Use `from __future__ import annotations` for forward refs
- Use `@dataclass` for data containers
- Use `Optional[X]` for optional types
- Include docstrings in Google format
- All classes and functions must have type hints

## Specification
{spec_context}

Generate the skeleton files. For each file, use this format:
```python
# FILE: path/to/file.py
<skeleton code>
```
"""

    def generate_implementation_prompt(
        self,
        skeleton: str,
        spec_context: str,
        code_context: str,
    ) -> str:
        return f"""Implement the following Python code skeleton with production-quality code.

## Skeleton to Implement
```python
{skeleton}
```

## Specification Requirements
{spec_context}

## Existing Code Context
{code_context}

## Implementation Guidelines
- Replace `raise NotImplementedError` with actual implementations
- Follow existing patterns from the context files
- Handle errors using try/except with specific exception types
- Add logging using `logging` module or the project's logger
- Maintain the exact function signatures from the skeleton
- Add input validation where appropriate

Generate the complete implementation. For each file, use this format:
```python
# FILE: path/to/file.py
<implementation code>
```
"""

    def parse_generated_code(self, llm_response: str) -> dict[str, str]:
        """Parse LLM response into file path -> content mapping."""
        files = {}

        # Pattern to match code blocks with FILE: header
        pattern = r"```python\s*\n#\s*FILE:\s*(.+?)\n(.*?)```"
        matches = re.findall(pattern, llm_response, re.DOTALL)

        for filepath, content in matches:
            filepath = filepath.strip()
            content = content.strip()
            files[filepath] = content

        # Fallback: if no FILE: headers, try to extract any python blocks
        if not files:
            pattern = r"```python\s*\n(.*?)```"
            matches = re.findall(pattern, llm_response, re.DOTALL)
            for i, content in enumerate(matches):
                files[f"generated_{i}.py"] = content.strip()

        return files

    def validate_syntax(self, code: str) -> list[str]:
        """Validate Python syntax using ast.parse."""
        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Line {e.lineno}: {e.msg}")
        return errors

    def extract_interfaces(self, code: str) -> list[dict[str, Any]]:
        """Extract class and function interfaces from code."""
        interfaces = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return interfaces

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                interfaces.append({
                    "type": "class",
                    "name": node.name,
                    "bases": [self._get_name(b) for b in node.bases],
                    "methods": [
                        m.name for m in node.body
                        if isinstance(m, ast.FunctionDef)
                    ],
                })
            elif isinstance(node, ast.FunctionDef):
                # Top-level functions
                if not any(
                    isinstance(parent, ast.ClassDef)
                    for parent in ast.walk(tree)
                ):
                    interfaces.append({
                        "type": "function",
                        "name": node.name,
                        "args": [arg.arg for arg in node.args.args],
                    })

        return interfaces

    def _get_name(self, node: ast.expr) -> str:
        """Get string name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return str(node)
