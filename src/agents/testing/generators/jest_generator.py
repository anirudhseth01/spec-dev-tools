"""Jest test generator for TypeScript code."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from src.agents.testing.generators.base import (
    BaseTestGenerator,
    GeneratedTest,
)

if TYPE_CHECKING:
    from src.spec.schemas import TestCase, EdgeCases


class JestGenerator(BaseTestGenerator):
    """TypeScript/Jest test generator."""

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def test_framework(self) -> str:
        return "jest"

    @property
    def file_extension(self) -> str:
        return ".test.ts"

    def generate_unit_test_prompt(
        self,
        test_case: TestCase,
        code_context: str,
    ) -> str:
        """Generate prompt for unit test creation."""
        return f"""Generate a Jest unit test based on the following specification.

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
- Use Jest conventions (describe, it, expect)
- Use TypeScript with proper type annotations
- Follow naming pattern: describe('<Module>') > it('should <behavior>')
- Include beforeEach/afterEach when needed
- Mock external dependencies using jest.mock()
- Add JSDoc comments for complex tests

Generate the test file:
```typescript
// FILE: src/__tests__/<module>.test.ts
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

        return f"""Generate Jest tests for edge cases based on the following specification.

## Edge Cases to Test
{chr(10).join(edge_case_text)}

## Code Under Test
{code_context}

## Requirements
- Test each edge case in a separate it() block
- Use expect().toThrow() for expected exceptions
- Use describe.each() or test.each() for related boundary conditions
- Include proper beforeEach/afterEach for async tests
- Mock external dependencies to simulate failures
- Use descriptive names: describe('<Module> Edge Cases') > it('should handle <scenario>')

Generate the test file:
```typescript
// FILE: src/__tests__/<module>.edge.test.ts
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

        return f"""Generate Jest test utilities and fixtures based on the following input/output specifications.

## Inputs
{input_text}

## Outputs
{output_text}

## Requirements
- Create a testUtils.ts with reusable test helpers
- Use TypeScript interfaces for mock data types
- Create factory functions for test data
- Include mock implementations for common dependencies
- Export all utilities for use in tests

Generate the utilities file:
```typescript
// FILE: src/__tests__/testUtils.ts
<fixture code>
```
"""

    def parse_generated_tests(self, llm_response: str) -> list[GeneratedTest]:
        """Parse LLM response into generated test objects."""
        tests = []

        # Pattern to match code blocks with FILE: header
        pattern = r"```typescript\s*\n//\s*FILE:\s*(.+?)\n(.*?)```"
        matches = re.findall(pattern, llm_response, re.DOTALL)

        for filepath, content in matches:
            filepath = filepath.strip()
            content = content.strip()

            # Count test functions (it, test, or test.each)
            test_count = len(re.findall(r"\b(?:it|test)\s*\(", content))

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

        # Fallback: if no FILE: headers, try to extract any typescript blocks
        if not tests:
            pattern = r"```typescript\s*\n(.*?)```"
            matches = re.findall(pattern, llm_response, re.DOTALL)
            for i, content in enumerate(matches):
                content = content.strip()
                test_count = len(re.findall(r"\b(?:it|test)\s*\(", content))
                errors = self.validate_test(content)

                tests.append(GeneratedTest(
                    file_path=f"src/__tests__/generated_{i}.test.ts",
                    content=content,
                    test_framework=self.test_framework,
                    language=self.language,
                    test_count=test_count,
                    is_valid=len(errors) == 0,
                    validation_errors=errors,
                ))

        return tests

    def validate_test(self, code: str) -> list[str]:
        """Validate TypeScript test syntax (basic checks)."""
        errors = []

        # Check for balanced braces
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            errors.append(
                f"Mismatched braces: {open_braces} open, {close_braces} close"
            )

        # Check for balanced parentheses
        open_parens = code.count("(")
        close_parens = code.count(")")
        if open_parens != close_parens:
            errors.append(
                f"Mismatched parentheses: {open_parens} open, {close_parens} close"
            )

        # Check for basic Jest structure
        if not re.search(r"\bdescribe\s*\(", code) and not re.search(r"\btest\s*\(", code):
            errors.append("Missing Jest test structure (describe/test blocks)")

        return errors

    def generate_mock_template(self, dependency: str, methods: list[str]) -> str:
        """Generate a mock template for a dependency."""
        mock_methods = "\n  ".join([
            f"{method}: jest.fn()," for method in methods
        ])

        return f'''
const mock{dependency} = {{
  {mock_methods}
}};

jest.mock('../{dependency.lower()}', () => ({{
  {dependency}: jest.fn(() => mock{dependency}),
}}));
'''

    def generate_test_each_template(
        self,
        test_name: str,
        params: list[tuple[str, Any, Any]],
    ) -> str:
        """Generate a test.each template.

        Args:
            test_name: Name of the test
            params: List of (description, input, expected) tuples
        """
        cases = []
        for desc, inp, expected in params:
            cases.append(f'    ["{desc}", {inp!r}, {expected!r}]')

        cases_str = ",\n".join(cases)

        return f'''
describe('{test_name}', () => {{
  test.each([
{cases_str}
  ])('%s: input=%s -> expected=%s', (description, input, expected) => {{
    const result = functionUnderTest(input);
    expect(result).toBe(expected);
  }});
}});
'''

    def generate_async_test_template(
        self,
        test_name: str,
        setup_code: str = "",
    ) -> str:
        """Generate an async test template."""
        return f'''
describe('{test_name}', () => {{
  beforeEach(async () => {{
    {setup_code if setup_code else "// Setup code here"}
  }});

  afterEach(async () => {{
    jest.clearAllMocks();
  }});

  it('should handle async operation', async () => {{
    // Arrange
    const input = {{}};

    // Act
    const result = await asyncFunctionUnderTest(input);

    // Assert
    expect(result).toBeDefined();
  }});

  it('should handle async errors', async () => {{
    // Arrange
    mockDependency.mockRejectedValueOnce(new Error('Test error'));

    // Act & Assert
    await expect(asyncFunctionUnderTest({{}})).rejects.toThrow('Test error');
  }});
}});
'''
