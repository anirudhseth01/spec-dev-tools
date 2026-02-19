"""TypeScript language plugin for code generation."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from src.agents.coding.plugins.base import LanguagePlugin, LanguageConventions


class TypeScriptPlugin(LanguagePlugin):
    """TypeScript-specific code generation plugin."""

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def conventions(self) -> LanguageConventions:
        return LanguageConventions(
            file_extension=".ts",
            import_style="explicit",
            type_annotation="inline",
            error_handling="exceptions",
            naming_convention="camelCase",
            docstring_format="jsdoc",
            test_framework="jest",
        )

    def generate_skeleton_prompt(self, spec_context: str) -> str:
        return f"""Generate TypeScript code skeletons based on the following specification.

Create ONLY:
- Interfaces for all data structures
- Abstract classes with abstract methods
- Type aliases for complex types
- Function signatures that throw 'Not implemented'
- Enums for fixed choices

DO NOT generate implementations yet.

## TypeScript Conventions
- Use `interface` for data shapes, `type` for unions/aliases
- Use `readonly` for immutable properties
- Export all public types
- Use JSDoc comments for documentation
- PascalCase for types/interfaces, camelCase for functions/variables

## Specification
{spec_context}

Generate the skeleton files. For each file, use this format:
```typescript
// FILE: path/to/file.ts
<skeleton code>
```
"""

    def generate_implementation_prompt(
        self,
        skeleton: str,
        spec_context: str,
        code_context: str,
    ) -> str:
        return f"""Implement the following TypeScript code skeleton with production-quality code.

## Skeleton to Implement
```typescript
{skeleton}
```

## Specification Requirements
{spec_context}

## Existing Code Context
{code_context}

## Implementation Guidelines
- Replace `throw new Error('Not implemented')` with actual implementations
- Follow existing patterns from the context files
- Use try/catch for error handling
- Add appropriate logging
- Maintain the exact function signatures from the skeleton
- Use async/await for asynchronous operations

Generate the complete implementation. For each file, use this format:
```typescript
// FILE: path/to/file.ts
<implementation code>
```
"""

    def parse_generated_code(self, llm_response: str) -> dict[str, str]:
        """Parse LLM response into file path -> content mapping."""
        files = {}

        # Pattern to match code blocks with FILE: header
        pattern = r"```typescript\s*\n//\s*FILE:\s*(.+?)\n(.*?)```"
        matches = re.findall(pattern, llm_response, re.DOTALL)

        for filepath, content in matches:
            filepath = filepath.strip()
            content = content.strip()
            files[filepath] = content

        # Fallback: if no FILE: headers, try to extract any typescript blocks
        if not files:
            pattern = r"```typescript\s*\n(.*?)```"
            matches = re.findall(pattern, llm_response, re.DOTALL)
            for i, content in enumerate(matches):
                files[f"generated_{i}.ts"] = content.strip()

        return files

    def validate_syntax(self, code: str) -> list[str]:
        """Validate TypeScript syntax using tsc if available."""
        errors = []

        # Basic validation without tsc
        # Check for common syntax issues
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            errors.append(f"Mismatched braces: {open_braces} open, {close_braces} close")

        open_parens = code.count("(")
        close_parens = code.count(")")
        if open_parens != close_parens:
            errors.append(f"Mismatched parentheses: {open_parens} open, {close_parens} close")

        # Try tsc if available
        try:
            result = subprocess.run(
                ["tsc", "--noEmit", "--allowJs", "--checkJs", "-"],
                input=code,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 and result.stderr:
                for line in result.stderr.strip().split("\n"):
                    if line.strip():
                        errors.append(line.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # tsc not available or timed out, skip
            pass

        return errors

    def extract_interfaces(self, code: str) -> list[dict[str, Any]]:
        """Extract interface and type definitions from code."""
        interfaces = []

        # Extract interfaces
        interface_pattern = r"(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([^{]+))?\s*\{"
        for match in re.finditer(interface_pattern, code):
            interfaces.append({
                "type": "interface",
                "name": match.group(1),
                "extends": match.group(2).strip() if match.group(2) else None,
            })

        # Extract type aliases
        type_pattern = r"(?:export\s+)?type\s+(\w+)\s*="
        for match in re.finditer(type_pattern, code):
            interfaces.append({
                "type": "type_alias",
                "name": match.group(1),
            })

        # Extract classes
        class_pattern = r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?\s*\{"
        for match in re.finditer(class_pattern, code):
            interfaces.append({
                "type": "class",
                "name": match.group(1),
                "extends": match.group(2),
                "implements": match.group(3).strip() if match.group(3) else None,
            })

        return interfaces
