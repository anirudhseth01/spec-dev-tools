"""TestGeneratorAgent for generating tests from specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus


@dataclass
class TestGenerationConfig:
    """Configuration for test generation."""

    framework: str = "pytest"  # pytest, jest, unittest
    coverage_target: int = 80
    include_unit: bool = True
    include_integration: bool = True
    include_edge_cases: bool = True
    mock_external: bool = True


class TestGeneratorAgent(BaseAgent):
    """Generates tests from specifications.

    Features:
    - Generates unit tests based on spec test cases
    - Generates integration tests for API endpoints
    - Creates edge case tests from spec edge cases
    - Supports multiple frameworks (pytest, jest)
    - Respects coverage targets from spec
    """

    name = "test_generator_agent"
    description = "Generates tests from specifications"
    requires = ["coding_agent"]  # Runs after code is generated

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        config: Optional[TestGenerationConfig] = None,
        dry_run: bool = False,
    ):
        """Initialize TestGeneratorAgent.

        Args:
            llm_client: LLM client for test generation.
            config: Test generation configuration.
            dry_run: If True, don't write test files.
        """
        self.llm = llm_client
        self.config = config or TestGenerationConfig()
        self.dry_run = dry_run

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute test generation."""
        try:
            # Get code from coding agent
            code_files = self._get_code_files(context)
            if not code_files:
                return AgentResult(
                    status=AgentStatus.SKIPPED,
                    message="No code files to generate tests for",
                )

            # Get test cases from spec
            test_cases = self._extract_test_cases(context)

            # Detect framework from project or config
            framework = self._detect_framework(context)

            # Generate tests
            generated_tests = self._generate_tests(
                code_files=code_files,
                test_cases=test_cases,
                spec_context=self._get_spec_context(context),
                framework=framework,
            )

            if not generated_tests:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message="Failed to generate any tests",
                    errors=["No test files were generated"],
                )

            # Write test files (unless dry run)
            test_files_created = []
            if not self.dry_run:
                for filepath, content in generated_tests.items():
                    full_path = context.project_root / filepath
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content)
                    test_files_created.append(filepath)

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=f"Generated {len(generated_tests)} test file(s)",
                data={
                    "tests": generated_tests,
                    "test_files": list(generated_tests.keys()),
                    "framework": framework,
                    "test_count": self._count_tests(generated_tests),
                },
                files_created=test_files_created,
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Test generation failed: {str(e)}",
                errors=[str(e)],
            )

    def _get_code_files(self, context: AgentContext) -> dict[str, str]:
        """Get code files from coding agent results."""
        files = {}

        # From previous results
        coding_result = context.get_result("coding_agent")
        if coding_result and coding_result.data:
            if "code" in coding_result.data:
                files.update(coding_result.data["code"])

        # From parent context artifacts
        if "artifacts" in context.parent_context:
            artifacts = context.parent_context["artifacts"]
            if "code" in artifacts:
                code_artifact = artifacts["code"]
                if isinstance(code_artifact, dict) and "value" in code_artifact:
                    files.update(code_artifact["value"])

        return files

    def _extract_test_cases(self, context: AgentContext) -> list[dict[str, Any]]:
        """Extract test case definitions from spec."""
        test_cases = []

        if context.spec and context.spec.test_cases:
            tc = context.spec.test_cases

            for unit in tc.unit_tests:
                test_cases.append({
                    "type": "unit",
                    "id": unit.test_id,
                    "description": unit.description,
                    "input": unit.input,
                    "expected": unit.expected_output,
                    "setup": unit.setup,
                    "teardown": unit.teardown,
                })

            for integration in tc.integration_tests:
                test_cases.append({
                    "type": "integration",
                    "id": integration.test_id,
                    "description": integration.description,
                    "input": integration.input,
                    "expected": integration.expected_output,
                    "setup": integration.setup,
                    "teardown": integration.teardown,
                })

        return test_cases

    def _detect_framework(self, context: AgentContext) -> str:
        """Detect test framework from project."""
        # Check config first
        if self.config.framework:
            return self.config.framework

        # Auto-detect from project files
        project_root = context.project_root

        # Check for pytest
        if (project_root / "pytest.ini").exists() or (project_root / "pyproject.toml").exists():
            return "pytest"

        # Check for jest
        if (project_root / "jest.config.js").exists() or (project_root / "jest.config.ts").exists():
            return "jest"

        # Check package.json for jest
        package_json = project_root / "package.json"
        if package_json.exists():
            try:
                import json
                pkg = json.loads(package_json.read_text())
                if "jest" in pkg.get("devDependencies", {}) or "jest" in pkg.get("dependencies", {}):
                    return "jest"
            except Exception:
                pass

        # Check for Python files
        if list(project_root.glob("**/*.py")):
            return "pytest"

        # Check for TypeScript/JavaScript files
        if list(project_root.glob("**/*.ts")) or list(project_root.glob("**/*.js")):
            return "jest"

        return "pytest"  # Default

    def _get_spec_context(self, context: AgentContext) -> str:
        """Get spec context for test generation."""
        lines = []

        if context.spec:
            spec = context.spec

            if spec.name:
                lines.append(f"# Test Context: {spec.name}")

            if spec.overview and spec.overview.summary:
                lines.append(f"\n## Summary\n{spec.overview.summary}")

            if spec.api_contract and spec.api_contract.endpoints:
                lines.append("\n## API Endpoints")
                for ep in spec.api_contract.endpoints:
                    lines.append(f"- {ep.method} {ep.path}: {ep.description}")

            if spec.edge_cases:
                if spec.edge_cases.boundary_conditions:
                    lines.append("\n## Edge Cases - Boundary Conditions")
                    for bc in spec.edge_cases.boundary_conditions:
                        lines.append(f"- {bc}")
                if spec.edge_cases.failure_modes:
                    lines.append("\n## Edge Cases - Failure Modes")
                    for fm in spec.edge_cases.failure_modes:
                        lines.append(f"- {fm}")

            if spec.error_handling and spec.error_handling.error_types:
                lines.append("\n## Error Types to Test")
                for et in spec.error_handling.error_types:
                    lines.append(f"- {et}")

        return "\n".join(lines)

    def _generate_tests(
        self,
        code_files: dict[str, str],
        test_cases: list[dict[str, Any]],
        spec_context: str,
        framework: str,
    ) -> dict[str, str]:
        """Generate test files using LLM or templates."""
        generated = {}

        if self.llm:
            # Use LLM for generation
            generated = self._generate_with_llm(
                code_files, test_cases, spec_context, framework
            )
        else:
            # Use template-based generation
            generated = self._generate_from_templates(
                code_files, test_cases, framework
            )

        return generated

    def _generate_with_llm(
        self,
        code_files: dict[str, str],
        test_cases: list[dict[str, Any]],
        spec_context: str,
        framework: str,
    ) -> dict[str, str]:
        """Generate tests using LLM."""
        generated = {}

        # Build prompt
        code_content = "\n\n".join([
            f"# File: {path}\n```\n{content}\n```"
            for path, content in code_files.items()
        ])

        test_cases_str = "\n".join([
            f"- [{tc['type']}] {tc['id']}: {tc['description']} "
            f"(input: {tc['input']}, expected: {tc['expected']})"
            for tc in test_cases
        ])

        system_prompt = self._get_system_prompt(framework)
        user_prompt = f"""Generate comprehensive tests for the following code.

## Spec Context
{spec_context}

## Test Cases from Spec
{test_cases_str or "No specific test cases defined - generate based on code analysis"}

## Code to Test
{code_content}

## Requirements
- Framework: {framework}
- Generate unit tests for all functions/methods
- Generate integration tests for API endpoints if present
- Cover edge cases and error handling
- Mock external dependencies
- Target high code coverage

Return the test files with clear file paths.
"""

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        generated = self._parse_generated_tests(response.content, framework)
        return generated

    def _get_system_prompt(self, framework: str) -> str:
        """Get system prompt for test generation."""
        if framework == "pytest":
            return """You are an expert Python test engineer. Generate pytest tests following best practices:
- Use pytest fixtures for setup/teardown
- Use parametrize for data-driven tests
- Use proper mocking with unittest.mock or pytest-mock
- Follow AAA pattern (Arrange, Act, Assert)
- Include docstrings describing test purpose
- Use descriptive test names: test_<function>_<scenario>

Return files in this format:
```python:tests/test_<module>.py
# test content
```
"""
        elif framework == "jest":
            return """You are an expert TypeScript/JavaScript test engineer. Generate Jest tests following best practices:
- Use describe/it blocks for organization
- Use beforeEach/afterEach for setup/teardown
- Use proper mocking with jest.mock
- Follow AAA pattern (Arrange, Act, Assert)
- Include descriptive test names
- Use expect assertions

Return files in this format:
```typescript:tests/<module>.test.ts
// test content
```
"""
        else:
            return "You are a test engineer. Generate comprehensive tests."

    def _parse_generated_tests(self, content: str, framework: str) -> dict[str, str]:
        """Parse generated test content into files."""
        import re

        files = {}

        # Match code blocks with file paths
        # Format: ```language:path/to/file.ext
        pattern = r"```(?:\w+):([^\n]+)\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)

        for filepath, code in matches:
            filepath = filepath.strip()
            code = code.strip()
            if filepath and code:
                files[filepath] = code

        # If no files found, try to create default test file
        if not files and content.strip():
            if framework == "pytest":
                files["tests/test_generated.py"] = content
            elif framework == "jest":
                files["tests/generated.test.ts"] = content

        return files

    def _generate_from_templates(
        self,
        code_files: dict[str, str],
        test_cases: list[dict[str, Any]],
        framework: str,
    ) -> dict[str, str]:
        """Generate tests using templates (fallback when no LLM)."""
        generated = {}

        for filepath, content in code_files.items():
            if framework == "pytest":
                test_content = self._generate_pytest_template(filepath, content, test_cases)
                test_path = self._get_test_path(filepath, "pytest")
                if test_content:
                    generated[test_path] = test_content
            elif framework == "jest":
                test_content = self._generate_jest_template(filepath, content, test_cases)
                test_path = self._get_test_path(filepath, "jest")
                if test_content:
                    generated[test_path] = test_content

        return generated

    def _get_test_path(self, source_path: str, framework: str) -> str:
        """Get test file path from source path."""
        from pathlib import Path
        p = Path(source_path)

        if framework == "pytest":
            return f"tests/test_{p.stem}.py"
        elif framework == "jest":
            return f"tests/{p.stem}.test.ts"
        return f"tests/test_{p.stem}"

    def _generate_pytest_template(
        self,
        filepath: str,
        content: str,
        test_cases: list[dict[str, Any]],
    ) -> str:
        """Generate pytest test template."""
        import re
        from pathlib import Path

        module_name = Path(filepath).stem
        lines = [
            f'"""Tests for {module_name}."""',
            "",
            "import pytest",
            f"from unittest.mock import Mock, patch",
            "",
            "",
        ]

        # Extract function names from content
        functions = re.findall(r"def\s+(\w+)\s*\(", content)
        classes = re.findall(r"class\s+(\w+)\s*[:\(]", content)

        # Add test cases from spec
        for tc in test_cases:
            if tc["type"] == "unit":
                test_name = f"test_{tc['id'].lower().replace('-', '_')}"
                lines.append(f"def {test_name}():")
                lines.append(f'    """Test: {tc["description"]}."""')
                lines.append("    # Arrange")
                if tc.get("setup"):
                    lines.append(f"    # Setup: {tc['setup']}")
                lines.append(f"    # Input: {tc.get('input', 'N/A')}")
                lines.append("    ")
                lines.append("    # Act")
                lines.append("    # TODO: Call function under test")
                lines.append("    result = None")
                lines.append("    ")
                lines.append("    # Assert")
                lines.append(f"    # Expected: {tc.get('expected', 'N/A')}")
                lines.append("    assert result is not None")
                if tc.get("teardown"):
                    lines.append(f"    # Teardown: {tc['teardown']}")
                lines.append("")
                lines.append("")

        # Add basic tests for functions
        for func in functions:
            if not func.startswith("_"):
                lines.append(f"def test_{func}_happy_path():")
                lines.append(f'    """Test {func} with valid input."""')
                lines.append("    # Arrange")
                lines.append("    # TODO: Set up test data")
                lines.append("    ")
                lines.append("    # Act")
                lines.append(f"    # result = {func}(...)")
                lines.append("    ")
                lines.append("    # Assert")
                lines.append("    # assert result == expected")
                lines.append("    pass")
                lines.append("")
                lines.append("")

        return "\n".join(lines)

    def _generate_jest_template(
        self,
        filepath: str,
        content: str,
        test_cases: list[dict[str, Any]],
    ) -> str:
        """Generate Jest test template."""
        import re
        from pathlib import Path

        module_name = Path(filepath).stem
        lines = [
            f"// Tests for {module_name}",
            "",
            f"import {{ /* imports */ }} from '../{filepath.replace('.ts', '')}';",
            "",
            f"describe('{module_name}', () => {{",
        ]

        # Add test cases from spec
        for tc in test_cases:
            if tc["type"] == "unit":
                test_name = tc["description"]
                lines.append(f"  it('{test_name}', () => {{")
                lines.append("    // Arrange")
                if tc.get("setup"):
                    lines.append(f"    // Setup: {tc['setup']}")
                lines.append(f"    // Input: {tc.get('input', 'N/A')}")
                lines.append("    ")
                lines.append("    // Act")
                lines.append("    // const result = functionUnderTest(...);")
                lines.append("    ")
                lines.append("    // Assert")
                lines.append(f"    // Expected: {tc.get('expected', 'N/A')}")
                lines.append("    expect(true).toBe(true);")
                lines.append("  });")
                lines.append("")

        lines.append("});")

        return "\n".join(lines)

    def _count_tests(self, test_files: dict[str, str]) -> int:
        """Count number of tests in generated files."""
        import re
        count = 0

        for content in test_files.values():
            # Count pytest tests
            count += len(re.findall(r"def\s+test_", content))
            # Count jest tests
            count += len(re.findall(r"\bit\s*\(", content))
            count += len(re.findall(r"\btest\s*\(", content))

        return count

    def run_tests(self, context: AgentContext, framework: str = "pytest") -> AgentResult:
        """Run generated tests.

        Args:
            context: Agent context.
            framework: Test framework to use.

        Returns:
            AgentResult with test run results.
        """
        import subprocess

        try:
            if framework == "pytest":
                result = subprocess.run(
                    ["pytest", "-v", "--tb=short", str(context.project_root / "tests")],
                    capture_output=True,
                    text=True,
                    cwd=str(context.project_root),
                    timeout=300,
                )
            elif framework == "jest":
                result = subprocess.run(
                    ["npm", "test"],
                    capture_output=True,
                    text=True,
                    cwd=str(context.project_root),
                    timeout=300,
                )
            else:
                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=f"Unsupported test framework: {framework}",
                    errors=[f"Framework {framework} is not supported"],
                )

            success = result.returncode == 0

            return AgentResult(
                status=AgentStatus.SUCCESS if success else AgentStatus.FAILED,
                message="Tests passed" if success else "Tests failed",
                data={
                    "exit_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "passed": success,
                },
                errors=[] if success else [result.stderr or "Tests failed"],
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                status=AgentStatus.FAILED,
                message="Test execution timed out",
                errors=["Test execution exceeded 5 minute timeout"],
            )
        except FileNotFoundError as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Test runner not found: {e}",
                errors=[str(e)],
            )
        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=f"Test execution failed: {e}",
                errors=[str(e)],
            )
