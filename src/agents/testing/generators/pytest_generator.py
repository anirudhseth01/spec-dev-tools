"""Pytest test generator for Python code."""

from __future__ import annotations

import ast
import re
from typing import Any, TYPE_CHECKING

from src.agents.testing.generators.base import (
    BaseTestGenerator,
    GeneratedTest,
)

if TYPE_CHECKING:
    from src.spec.schemas import TestCase, EdgeCases


class PytestGenerator(BaseTestGenerator):
    """Python/pytest test generator."""

    @property
    def language(self) -> str:
        return "python"

    @property
    def test_framework(self) -> str:
        return "pytest"

    @property
    def file_extension(self) -> str:
        return ".py"

    def generate_unit_test_prompt(
        self,
        test_case: TestCase,
        code_context: str,
    ) -> str:
        """Generate prompt for unit test creation."""
        return f"""Generate a pytest unit test based on the following specification.

## Test Case
- Test ID: {test_case.test_id}
- Description: {test_case.description}
- Input: {test_case.input}
- Expected Output: {test_case.expected_output}
{f"- Setup: {test_case.setup}" if test_case.setup else ""}
{f"- Teardown: {test_case.teardown}" if test_case.teardown else ""}

## Code Under Test
{code_context}

## Requirements
- Use pytest conventions and fixtures
- Follow Google-style docstrings
- Use descriptive function names: test_<unit>_<scenario>
- Include proper assertions with helpful messages
- Mock any external dependencies (database, API, etc.)
- Add type hints to test functions

Generate the test file:
```python
# FILE: tests/test_<module>.py
<test code>
```
"""

    def generate_edge_case_prompt(
        self,
        edge_cases: EdgeCases,
        code_context: str,
    ) -> str:
        """Generate prompt for edge case tests."""
        edge_case_text = []

        if edge_cases.boundary_conditions:
            edge_case_text.append("### Boundary Conditions")
            for bc in edge_cases.boundary_conditions:
                edge_case_text.append(f"- {bc}")

        if edge_cases.concurrency:
            edge_case_text.append("### Concurrency Cases")
            for cc in edge_cases.concurrency:
                edge_case_text.append(f"- {cc}")

        if edge_cases.failure_modes:
            edge_case_text.append("### Failure Modes")
            for fm in edge_cases.failure_modes:
                edge_case_text.append(f"- {fm}")

        return f"""Generate pytest tests for edge cases based on the following specification.

## Edge Cases to Test
{chr(10).join(edge_case_text)}

## Code Under Test
{code_context}

## Requirements
- Test each edge case in a separate test function
- Use pytest.raises for expected exceptions
- Use pytest.mark.parametrize for related boundary conditions
- Include proper setup/teardown for concurrency tests
- Mock external dependencies to simulate failures
- Use descriptive names: test_<unit>_edge_<scenario>

Generate the test file:
```python
# FILE: tests/test_<module>_edge_cases.py
<test code>
```
"""

    def generate_fixture_prompt(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
    ) -> str:
        """Generate prompt for test fixtures/mocks."""
        input_text = "\n".join([
            f"- {name}: {details}" for name, details in inputs.items()
        ]) if inputs else "No specific inputs defined"

        output_text = "\n".join([
            f"- {name}: {details}" for name, details in outputs.items()
        ]) if outputs else "No specific outputs defined"

        return f"""Generate pytest fixtures and conftest.py based on the following input/output specifications.

## Inputs
{input_text}

## Outputs
{output_text}

## Requirements
- Create a conftest.py with reusable fixtures
- Use @pytest.fixture decorator with appropriate scope
- Include type hints
- Add docstrings explaining fixture purpose
- Create factory fixtures for complex objects
- Include cleanup logic where needed

Generate the conftest file:
```python
# FILE: tests/conftest.py
<fixture code>
```
"""

    def parse_generated_tests(self, llm_response: str) -> list[GeneratedTest]:
        """Parse LLM response into generated test objects."""
        tests = []

        # Pattern to match code blocks with FILE: header
        pattern = r"```python\s*\n#\s*FILE:\s*(.+?)\n(.*?)```"
        matches = re.findall(pattern, llm_response, re.DOTALL)

        for filepath, content in matches:
            filepath = filepath.strip()
            content = content.strip()

            # Count test functions
            test_count = len(re.findall(r"def test_", content))

            # Validate syntax
            errors = self.validate_test(content)

            tests.append(GeneratedTest(
                file_path=filepath,
                content=content,
                test_framework=self.test_framework,
                language=self.language,
                test_count=test_count,
                is_valid=len(errors) == 0,
                validation_errors=errors,
            ))

        # Fallback: if no FILE: headers, try to extract any python blocks
        if not tests:
            pattern = r"```python\s*\n(.*?)```"
            matches = re.findall(pattern, llm_response, re.DOTALL)
            for i, content in enumerate(matches):
                content = content.strip()
                test_count = len(re.findall(r"def test_", content))
                errors = self.validate_test(content)

                tests.append(GeneratedTest(
                    file_path=f"tests/test_generated_{i}.py",
                    content=content,
                    test_framework=self.test_framework,
                    language=self.language,
                    test_count=test_count,
                    is_valid=len(errors) == 0,
                    validation_errors=errors,
                ))

        return tests

    def validate_test(self, code: str) -> list[str]:
        """Validate Python test syntax using ast.parse."""
        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Line {e.lineno}: {e.msg}")
        return errors

    def generate_mock_template(self, dependency: str, methods: list[str]) -> str:
        """Generate a mock template for a dependency."""
        mock_methods = "\n    ".join([
            f"{method} = MagicMock()" for method in methods
        ])

        return f'''
@pytest.fixture
def mock_{dependency.lower()}():
    """Mock for {dependency}."""
    mock = MagicMock(spec={dependency})
    {mock_methods}
    return mock
'''

    def generate_parametrize_template(
        self,
        test_name: str,
        params: list[tuple[str, Any, Any]],
    ) -> str:
        """Generate a parametrized test template.

        Args:
            test_name: Name of the test function
            params: List of (description, input, expected) tuples
        """
        param_values = []
        for desc, inp, expected in params:
            param_values.append(f'    pytest.param({inp!r}, {expected!r}, id="{desc}")')

        params_str = ",\n".join(param_values)

        return f'''
@pytest.mark.parametrize("input_val,expected", [
{params_str}
])
def {test_name}(input_val, expected):
    """Test with various inputs."""
    result = function_under_test(input_val)
    assert result == expected
'''
