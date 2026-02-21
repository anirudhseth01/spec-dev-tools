"""TestGeneratorAgent generates tests from spec test cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus
from src.agents.testing.generators import (
    GeneratorRegistry,
    BaseTestGenerator,
    GeneratedTest,
    TestGenerationResult,
    TestGeneratorContext,
)
from src.llm.client import LLMClient


@dataclass
class TestGenerationConfig:
    """Configuration for test generation."""

    min_unit_tests: int = 3
    min_integration_tests: int = 1
    generate_edge_case_tests: bool = True
    mock_external_services: bool = True
    include_coverage_targets: bool = True
    max_retries: int = 2
    # Coverage feedback loop settings
    target_coverage: float = 80.0
    focus_on_low_coverage: bool = True


@dataclass
class TestGenerationState:
    """Tracks state across test generation phases."""

    unit_tests: list[GeneratedTest] = field(default_factory=list)
    edge_case_tests: list[GeneratedTest] = field(default_factory=list)
    coverage_tests: list[GeneratedTest] = field(default_factory=list)
    fixtures: dict[str, str] = field(default_factory=dict)
    mocks: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    is_feedback_run: bool = False

    @property
    def all_tests(self) -> list[GeneratedTest]:
        """Get all generated tests."""
        return self.unit_tests + self.edge_case_tests + self.coverage_tests

    @property
    def total_test_count(self) -> int:
        """Total number of tests across all files."""
        return sum(t.test_count for t in self.all_tests)


class TestGeneratorAgent(BaseAgent):
    """Generates tests from specifications using LLM.

    Flow:
    1. Get code from coding_agent artifacts
    2. Parse spec test_cases and edge_cases sections
    3. Generate unit tests for each test case
    4. Generate edge case tests from edge_cases section
    5. Generate fixtures and mocks
    6. Validate all generated tests
    7. Return test files

    Design Decisions:
    - Depends on coding_agent (needs generated code to write tests for)
    - Uses language-specific generators (pytest for Python, Jest for TypeScript)
    - Validates generated tests compile/parse correctly
    - Generates fixtures and mocks alongside tests
    """

    name = "testing_agent"
    description = "Test generator from spec test cases"
    requires = ["coding_agent"]  # Needs generated code to test

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        generator_registry: Optional[GeneratorRegistry] = None,
        config: Optional[TestGenerationConfig] = None,
        dry_run: bool = False,
    ):
        """Initialize TestGeneratorAgent.

        Args:
            llm_client: LLM client for test generation.
            generator_registry: Test generator registry.
            config: Test generation configuration.
            dry_run: If True, don't write files.
        """
        self.llm = llm_client
        self.generators = generator_registry or GeneratorRegistry()
        self.config = config or TestGenerationConfig()
        self.dry_run = dry_run
        self.state = TestGenerationState()

    def execute(self, context: AgentContext) -> AgentResult:
        """Execute test generation."""
        try:
            # Reset state
            self.state = TestGenerationState()

            # Check for feedback context (coverage improvement mode)
            feedback_context = self._get_feedback_context(context)
            if feedback_context:
                self.state.is_feedback_run = True
                return self._execute_coverage_improvement(context, feedback_context)

            # Detect or get language
            language = self._get_language(context)
            generator = self.generators.get(language)

            # Get code from coding agent
            code_files = self._get_code_files(context)

            if not code_files:
                return AgentResult(
                    status=AgentStatus.SKIPPED,
                    message="No code files to generate tests for",
                )

            # Build test generator context
            test_context = self._build_test_context(context, code_files)

            if not test_context.has_test_cases and not test_context.has_edge_cases:
                # Still generate basic tests from code analysis
                if not self.llm:
                    return AgentResult(
                        status=AgentStatus.SKIPPED,
                        message="No test cases or edge cases defined in spec",
                    )

            # Phase 1: Generate fixtures (if LLM available and inputs/outputs defined)
            if self.llm and (test_context.inputs or test_context.outputs):
                fixtures = self._generate_fixtures(generator, test_context)
                self.state.fixtures = fixtures

            # Phase 2: Generate unit tests
            if test_context.has_test_cases:
                if self.llm:
                    unit_tests = self._generate_unit_tests_llm(
                        generator, test_context, context
                    )
                else:
                    unit_tests = self._generate_unit_tests_template(
                        generator, test_context, context
                    )
                self.state.unit_tests = unit_tests

            # Phase 3: Generate edge case tests
            if self.config.generate_edge_case_tests and test_context.has_edge_cases:
                if self.llm:
                    edge_tests = self._generate_edge_case_tests(
                        generator, test_context, context
                    )
                    self.state.edge_case_tests = edge_tests

            # Validate all tests
            all_tests = self.state.all_tests
            invalid_tests = [t for t in all_tests if not t.is_valid]

            if invalid_tests:
                self.state.errors = []
                for test in invalid_tests:
                    for err in test.validation_errors:
                        self.state.errors.append(f"{test.file_path}: {err}")

                return AgentResult(
                    status=AgentStatus.FAILED,
                    message=f"Test validation failed: {len(invalid_tests)} test files have errors",
                    errors=self.state.errors,
                    data={
                        "tests": {t.file_path: t.content for t in all_tests},
                        "fixtures": self.state.fixtures,
                        "language": language,
                        "test_framework": generator.test_framework,
                    },
                )

            # Write files (unless dry run)
            files_created = []
            test_files = {}

            for test in all_tests:
                test_files[test.file_path] = test.content
                if not self.dry_run:
                    full_path = context.project_root / test.file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(test.content)
                    files_created.append(test.file_path)

            for fixture_path, fixture_content in self.state.fixtures.items():
                test_files[fixture_path] = fixture_content
                if not self.dry_run:
                    full_path = context.project_root / fixture_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(fixture_content)
                    files_created.append(fixture_path)

            return AgentResult(
                status=AgentStatus.SUCCESS,
                message=f"Generated {len(all_tests)} test files with {self.state.total_test_count} tests",
                data={
                    "tests": test_files,
                    "files_created": files_created if files_created else list(test_files.keys()),
                    "unit_test_count": len(self.state.unit_tests),
                    "edge_case_test_count": len(self.state.edge_case_tests),
                    "total_test_count": self.state.total_test_count,
                    "fixtures": self.state.fixtures,
                    "language": language,
                    "test_framework": generator.test_framework,
                },
                files_created=files_created,
            )

        except Exception as e:
            return AgentResult(
                status=AgentStatus.FAILED,
                message=str(e),
                errors=[str(e)],
            )

    def _get_feedback_context(self, context: AgentContext) -> Optional[dict]:
        """Check for coverage feedback context from code review agent.

        The orchestrator passes feedback when coverage is below threshold.
        The feedback is stored as feedback_{agent_name} in artifacts.
        """
        if "artifacts" not in context.parent_context:
            return None

        artifacts = context.parent_context["artifacts"]

        # Check for feedback artifact (set by orchestrator)
        # Support both naming conventions
        feedback_keys = [
            f"feedback_{self.name}",
            "feedback_testing_agent",
            "feedback_test_generator_agent",
        ]

        for key in feedback_keys:
            if key in artifacts:
                feedback = artifacts[key]
                if isinstance(feedback, dict) and "value" in feedback:
                    return feedback["value"]
                return feedback

        return None

    def _execute_coverage_improvement(
        self,
        context: AgentContext,
        feedback: dict,
    ) -> AgentResult:
        """Execute test generation focused on improving coverage.

        Args:
            context: Agent context.
            feedback: Feedback dict with low_coverage_files and target_coverage.
        """
        low_coverage_files = feedback.get("low_coverage_files", [])
        target_coverage = feedback.get("target_coverage", self.config.target_coverage)
        current_coverage = feedback.get("current_coverage", 0)

        if not low_coverage_files:
            return AgentResult(
                status=AgentStatus.SKIPPED,
                message="No low coverage files to improve",
            )

        # Detect language
        language = self._get_language(context)
        generator = self.generators.get(language)

        # Get all code files
        code_files = self._get_code_files(context)

        # Focus on low coverage files
        coverage_tests = []

        for file_info in low_coverage_files:
            file_path = file_info.get("file_path", "")
            missing_lines = file_info.get("missing_lines", [])
            file_coverage = file_info.get("coverage", 0)

            if not file_path or not missing_lines:
                continue

            # Get the source code for this file
            source_code = None
            for code_path, content in code_files.items():
                if code_path.endswith(file_path) or file_path.endswith(code_path):
                    source_code = content
                    break

            if not source_code:
                # Try to read from disk
                full_path = context.project_root / file_path
                if full_path.exists():
                    try:
                        source_code = full_path.read_text()
                    except Exception:
                        continue

            if not source_code:
                continue

            # Generate tests for uncovered lines
            tests = self._generate_coverage_tests(
                generator=generator,
                file_path=file_path,
                source_code=source_code,
                missing_lines=missing_lines,
                file_coverage=file_coverage,
                target_coverage=target_coverage,
                context=context,
            )
            coverage_tests.extend(tests)

        self.state.coverage_tests = coverage_tests

        # Validate generated tests
        invalid_tests = [t for t in coverage_tests if not t.is_valid]
        if invalid_tests:
            for test in invalid_tests:
                for err in test.validation_errors:
                    self.state.errors.append(f"{test.file_path}: {err}")

        # Write files (unless dry run)
        files_created = []
        test_files = {}

        for test in coverage_tests:
            test_files[test.file_path] = test.content
            if not self.dry_run:
                full_path = context.project_root / test.file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(test.content)
                files_created.append(test.file_path)

        return AgentResult(
            status=AgentStatus.SUCCESS,
            message=(
                f"Generated {len(coverage_tests)} test files to improve coverage "
                f"(current: {current_coverage:.1f}%, target: {target_coverage}%)"
            ),
            data={
                "tests": test_files,
                "files_created": files_created if files_created else list(test_files.keys()),
                "coverage_test_count": len(coverage_tests),
                "total_test_count": self.state.total_test_count,
                "is_feedback_run": True,
                "low_coverage_files_addressed": [f["file_path"] for f in low_coverage_files],
                "language": language,
                "test_framework": generator.test_framework,
            },
            files_created=files_created,
        )

    def _generate_coverage_tests(
        self,
        generator: BaseTestGenerator,
        file_path: str,
        source_code: str,
        missing_lines: list[int],
        file_coverage: float,
        target_coverage: float,
        context: AgentContext,
    ) -> list[GeneratedTest]:
        """Generate tests targeting specific uncovered lines."""
        tests = []

        if not self.llm:
            # Template-based fallback
            test_path = self._get_test_path(file_path, generator)
            test_content = self._create_coverage_test_template(
                file_path, missing_lines, generator
            )
            errors = generator.validate_test(test_content)
            test_count = test_content.count("def test_") if generator.language == "python" else test_content.count("it(")

            return [GeneratedTest(
                file_path=test_path,
                content=test_content,
                test_framework=generator.test_framework,
                language=generator.language,
                test_count=test_count,
                is_valid=len(errors) == 0,
                validation_errors=errors,
            )]

        # Extract relevant code sections around missing lines
        code_sections = self._extract_uncovered_sections(source_code, missing_lines)

        prompt = f"""Generate {generator.test_framework} tests to improve code coverage.

## Target File
{file_path}

## Current Coverage
{file_coverage:.1f}% (target: {target_coverage}%)

## Uncovered Lines
Lines that need test coverage: {missing_lines[:20]}{'...' if len(missing_lines) > 20 else ''}

## Code Sections Needing Coverage
{code_sections}

## Full Source Code
```
{source_code}
```

## Requirements
- Focus on testing the uncovered lines
- Test all code paths that lead to the uncovered lines
- Include edge cases that exercise the uncovered branches
- Use descriptive test names: test_<function>_<scenario>
- Mock external dependencies
- Ensure tests are independent

Generate test file(s) to cover these lines:
"""

        system_prompt = generator.get_system_prompt()

        for attempt in range(self.config.max_retries + 1):
            response = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            generated_tests = generator.parse_generated_tests(response.content)

            if all(t.is_valid for t in generated_tests):
                tests.extend(generated_tests)
                break

            if attempt < self.config.max_retries:
                invalid_errors = []
                for t in generated_tests:
                    invalid_errors.extend(t.validation_errors)
                prompt = f"""The previous test generation had syntax errors:
{chr(10).join(invalid_errors)}

Please regenerate with correct syntax:
{prompt}
"""
            else:
                tests.extend(generated_tests)

        return tests

    def _extract_uncovered_sections(
        self,
        source_code: str,
        missing_lines: list[int],
    ) -> str:
        """Extract code sections around uncovered lines."""
        lines = source_code.splitlines()
        sections = []
        context_lines = 3  # Lines before/after for context

        # Group consecutive missing lines
        groups = []
        current_group = []

        for line_num in sorted(missing_lines):
            if not current_group or line_num <= current_group[-1] + 2:
                current_group.append(line_num)
            else:
                groups.append(current_group)
                current_group = [line_num]

        if current_group:
            groups.append(current_group)

        # Extract each group with context
        for group in groups[:5]:  # Limit to 5 groups
            start = max(0, group[0] - context_lines - 1)
            end = min(len(lines), group[-1] + context_lines)

            section_lines = []
            for i in range(start, end):
                line_num = i + 1
                marker = ">>> " if line_num in missing_lines else "    "
                section_lines.append(f"{marker}{line_num:4d}: {lines[i]}")

            sections.append("\n".join(section_lines))

        return "\n\n---\n\n".join(sections)

    def _create_coverage_test_template(
        self,
        file_path: str,
        missing_lines: list[int],
        generator: BaseTestGenerator,
    ) -> str:
        """Create a template for coverage tests (no LLM)."""
        module_name = Path(file_path).stem

        if generator.language == "python":
            lines = [
                f'"""Tests for improving coverage of {module_name}."""',
                "",
                "import pytest",
                "from unittest.mock import MagicMock, patch",
                "",
                "",
                f"class TestCoverage{module_name.title().replace('_', '')}:",
                f'    """Tests targeting uncovered lines in {file_path}."""',
                "",
                f"    # Target lines: {missing_lines[:10]}{'...' if len(missing_lines) > 10 else ''}",
                "",
                "    def test_uncovered_branch_1(self):",
                '        """Test for uncovered branch."""',
                "        # TODO: Implement test for uncovered code",
                "        pass",
                "",
                "    def test_uncovered_branch_2(self):",
                '        """Test for another uncovered branch."""',
                "        # TODO: Implement test for uncovered code",
                "        pass",
                "",
            ]
            return "\n".join(lines)
        else:
            return f"""// Tests for improving coverage of {module_name}
// Target lines: {missing_lines[:10]}

describe('{module_name} coverage', () => {{
  it('covers uncovered branch 1', () => {{
    // TODO: Implement test
    expect(true).toBe(true);
  }});

  it('covers uncovered branch 2', () => {{
    // TODO: Implement test
    expect(true).toBe(true);
  }});
}});
"""

    def _get_language(self, context: AgentContext) -> str:
        """Determine target language."""
        # From spec metadata
        if context.spec and context.spec.metadata:
            tech_stack = context.spec.metadata.tech_stack
            if tech_stack:
                detected = self.generators.detect_from_tech_stack(tech_stack)
                if detected:
                    return detected

        # From coding agent result
        coding_result = context.get_result("coding_agent")
        if coding_result and "language" in coding_result.data:
            lang = coding_result.data["language"]
            if self.generators.has(lang):
                return lang

        # Auto-detect from project
        return self.generators.detect_language(context.project_root)

    def _get_code_files(self, context: AgentContext) -> dict[str, str]:
        """Get code files from coding agent artifacts."""
        files = {}

        # From previous results
        coding_result = context.get_result("coding_agent")
        if coding_result and coding_result.is_success:
            if "code" in coding_result.data:
                code = coding_result.data["code"]
                if isinstance(code, dict):
                    files.update(code)

        # From parent context artifacts
        if "artifacts" in context.parent_context:
            artifacts = context.parent_context["artifacts"]
            if "code" in artifacts:
                code_artifact = artifacts["code"]
                if isinstance(code_artifact, dict) and "value" in code_artifact:
                    code_files = code_artifact["value"]
                    if isinstance(code_files, dict):
                        files.update(code_files)

        return files

    def _build_test_context(
        self,
        context: AgentContext,
        code_files: dict[str, str],
    ) -> TestGeneratorContext:
        """Build test generator context from spec."""
        test_context = TestGeneratorContext(code_under_test=code_files)

        if context.spec:
            # Extract test cases
            if context.spec.test_cases:
                test_context.test_cases = (
                    context.spec.test_cases.unit_tests +
                    context.spec.test_cases.integration_tests
                )

            # Extract edge cases
            if context.spec.edge_cases:
                test_context.edge_cases = context.spec.edge_cases

            # Extract inputs/outputs for fixtures
            if context.spec.inputs:
                inputs = {}
                for inp in context.spec.inputs.user_inputs:
                    inputs[inp.name] = {
                        "type": inp.type,
                        "required": inp.required,
                        "description": inp.description,
                    }
                for inp in context.spec.inputs.system_inputs:
                    inputs[inp.name] = {
                        "type": inp.type,
                        "required": inp.required,
                        "description": inp.description,
                    }
                test_context.inputs = inputs

            if context.spec.outputs:
                outputs = {
                    "return_values": context.spec.outputs.return_values,
                    "side_effects": context.spec.outputs.side_effects,
                    "events": context.spec.outputs.events,
                }
                test_context.outputs = outputs

            # Build spec context string
            test_context.spec_context = self._spec_to_context(context.spec)

        # Check for routed spec
        if "routed_spec" in context.parent_context:
            routed = context.parent_context["routed_spec"]
            if hasattr(routed, "to_prompt_context"):
                test_context.spec_context = routed.to_prompt_context()

        return test_context

    def _spec_to_context(self, spec: Any) -> str:
        """Convert spec to context string for prompts."""
        lines = []

        if hasattr(spec, "name") and spec.name:
            lines.append(f"# {spec.name}")

        if hasattr(spec, "overview") and spec.overview:
            lines.append("## Overview")
            if spec.overview.summary:
                lines.append(f"Summary: {spec.overview.summary}")

        if hasattr(spec, "api_contract") and spec.api_contract:
            lines.append("## API Contract")
            for endpoint in spec.api_contract.endpoints:
                lines.append(f"- {endpoint.method} {endpoint.path}")

        if hasattr(spec, "error_handling") and spec.error_handling:
            lines.append("## Error Types")
            for err in spec.error_handling.error_types:
                lines.append(f"- {err}")

        return "\n".join(lines)

    def _generate_fixtures(
        self,
        generator: BaseTestGenerator,
        test_context: TestGeneratorContext,
    ) -> dict[str, str]:
        """Generate test fixtures using LLM."""
        fixtures = {}

        prompt = generator.generate_fixture_prompt(
            inputs=test_context.inputs,
            outputs=test_context.outputs,
        )
        system_prompt = generator.get_fixture_system_prompt()

        response = self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=prompt,
        )

        # Parse fixtures from response
        generated_tests = generator.parse_generated_tests(response.content)
        for test in generated_tests:
            fixtures[test.file_path] = test.content

        return fixtures

    def _generate_unit_tests_llm(
        self,
        generator: BaseTestGenerator,
        test_context: TestGeneratorContext,
        context: AgentContext,
    ) -> list[GeneratedTest]:
        """Generate unit tests using LLM."""
        all_tests: list[GeneratedTest] = []

        # Combine code context
        code_context = self._build_code_context(test_context.code_under_test)

        # Generate tests for all test cases at once for efficiency
        if test_context.test_cases:
            test_cases_text = self._format_test_cases(test_context.test_cases)

            prompt = f"""Generate {generator.test_framework} unit tests based on the following test case specifications.

## Test Cases
{test_cases_text}

## Code Under Test
{code_context}

## Additional Context
{test_context.spec_context}

## Requirements
- Generate one test function per test case
- Use descriptive test names: test_<unit>_<scenario>
- Include proper assertions with helpful error messages
- Mock any external dependencies
- Add docstrings and comments
- Ensure all tests are independent and can run in any order

Generate the test files:
"""

            system_prompt = generator.get_system_prompt()

            for attempt in range(self.config.max_retries + 1):
                response = self.llm.generate(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                )

                tests = generator.parse_generated_tests(response.content)

                # Check if tests are valid
                if all(t.is_valid for t in tests):
                    all_tests.extend(tests)
                    break

                # If not valid and we have retries left, try again
                if attempt < self.config.max_retries:
                    invalid_errors = []
                    for t in tests:
                        invalid_errors.extend(t.validation_errors)
                    prompt = f"""The previous test generation had syntax errors:
{chr(10).join(invalid_errors)}

Please regenerate with correct syntax:
{prompt}
"""
                else:
                    # Last attempt, include tests with errors
                    all_tests.extend(tests)

        return all_tests

    def _generate_unit_tests_template(
        self,
        generator: BaseTestGenerator,
        test_context: TestGeneratorContext,
        context: AgentContext,
    ) -> list[GeneratedTest]:
        """Generate unit tests from templates (no LLM)."""
        tests = []

        # Group test cases by target module (heuristic based on code files)
        for filepath in test_context.code_under_test.keys():
            test_path = self._get_test_path(filepath, generator)
            test_content = self._create_test_template(
                filepath, test_context.test_cases, generator
            )

            # Validate the template
            errors = generator.validate_test(test_content)
            test_count = test_content.count("def test_") if generator.language == "python" else test_content.count("it(")

            tests.append(GeneratedTest(
                file_path=test_path,
                content=test_content,
                test_framework=generator.test_framework,
                language=generator.language,
                test_count=test_count,
                is_valid=len(errors) == 0,
                validation_errors=errors,
            ))

        return tests

    def _generate_edge_case_tests(
        self,
        generator: BaseTestGenerator,
        test_context: TestGeneratorContext,
        context: AgentContext,
    ) -> list[GeneratedTest]:
        """Generate edge case tests."""
        if not test_context.edge_cases:
            return []

        code_context = self._build_code_context(test_context.code_under_test)

        prompt = generator.generate_edge_case_prompt(
            edge_cases=test_context.edge_cases,
            code_context=code_context,
        )
        system_prompt = generator.get_system_prompt()

        tests = []
        for attempt in range(self.config.max_retries + 1):
            response = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
            )

            tests = generator.parse_generated_tests(response.content)

            if all(t.is_valid for t in tests):
                return tests

            if attempt < self.config.max_retries:
                invalid_errors = []
                for t in tests:
                    invalid_errors.extend(t.validation_errors)
                prompt = f"""The previous test generation had syntax errors:
{chr(10).join(invalid_errors)}

Please regenerate with correct syntax:
{prompt}
"""

        return tests

    def _build_code_context(self, code_files: dict[str, str]) -> str:
        """Build code context string from files."""
        parts = []
        for filepath, content in code_files.items():
            parts.append(f"### {filepath}\n```\n{content}\n```")
        return "\n\n".join(parts)

    def _format_test_cases(self, test_cases: list) -> str:
        """Format test cases for the prompt."""
        lines = []
        for tc in test_cases:
            lines.append(f"### {tc.test_id}: {tc.description}")
            lines.append(f"- Input: {tc.input}")
            lines.append(f"- Expected Output: {tc.expected_output}")
            if tc.setup:
                lines.append(f"- Setup: {tc.setup}")
            if tc.teardown:
                lines.append(f"- Teardown: {tc.teardown}")
            lines.append("")
        return "\n".join(lines)

    def _get_test_path(self, source_path: str, generator: BaseTestGenerator) -> str:
        """Get test file path from source path."""
        path = Path(source_path)

        if generator.language == "python":
            # Python: src/module.py -> tests/test_module.py
            name = f"test_{path.stem}.py"
            return f"tests/{name}"
        elif generator.language == "typescript":
            # TS: src/module.ts -> src/__tests__/module.test.ts
            name = f"{path.stem}.test.ts"
            return f"{path.parent}/__tests__/{name}"
        else:
            return f"tests/test_{path.stem}.py"

    def _create_test_template(
        self,
        source_path: str,
        test_cases: list,
        generator: BaseTestGenerator,
    ) -> str:
        """Create a basic test template."""
        module_name = Path(source_path).stem

        if generator.language == "python":
            return self._create_pytest_template(module_name, test_cases)
        elif generator.language == "typescript":
            return self._create_jest_template(module_name, test_cases)
        else:
            return self._create_pytest_template(module_name, test_cases)

    def _create_pytest_template(self, module_name: str, test_cases: list) -> str:
        """Create pytest test template."""
        lines = [
            f'"""Tests for {module_name}."""',
            "",
            "import pytest",
            "from unittest.mock import MagicMock, patch",
            "",
            "",
        ]

        # Add test class
        class_name = "".join(word.title() for word in module_name.split("_"))
        lines.append(f"class Test{class_name}:")
        lines.append(f'    """Test cases for {module_name}."""')
        lines.append("")

        # Add tests from spec
        for tc in test_cases:
            test_id = tc.test_id.lower().replace("-", "_")
            description = tc.description
            lines.append(f"    def test_{test_id}(self):")
            lines.append(f'        """{description}."""')
            lines.append(f"        # Input: {tc.input}")
            lines.append(f"        # Expected: {tc.expected_output}")
            lines.append("        # TODO: Implement test")
            lines.append("        pass")
            lines.append("")

        # Add placeholder if no tests
        if not test_cases:
            lines.append("    def test_placeholder(self):")
            lines.append('        """Placeholder test."""')
            lines.append("        # TODO: Implement tests")
            lines.append("        pass")
            lines.append("")

        return "\n".join(lines)

    def _create_jest_template(self, module_name: str, test_cases: list) -> str:
        """Create Jest test template."""
        lines = [
            f"// Tests for {module_name}",
            "",
            f"describe('{module_name}', () => {{",
        ]

        for tc in test_cases:
            description = tc.description
            lines.append(f"  it('{description}', () => {{")
            lines.append(f"    // Input: {tc.input}")
            lines.append(f"    // Expected: {tc.expected_output}")
            lines.append("    // TODO: Implement test")
            lines.append("    expect(true).toBe(true);")
            lines.append("  });")
            lines.append("")

        if not test_cases:
            lines.append("  it('placeholder test', () => {")
            lines.append("    // TODO: Implement tests")
            lines.append("    expect(true).toBe(true);")
            lines.append("  });")

        lines.append("});")
        return "\n".join(lines)

    def generate_tests_for_code(
        self,
        code: dict[str, str],
        test_cases: list,
        language: str = "python",
    ) -> TestGenerationResult:
        """Generate tests for specific code (direct API usage).

        Args:
            code: Dict of file path -> code content.
            test_cases: List of TestCase objects.
            language: Target language.

        Returns:
            TestGenerationResult with generated tests.
        """
        if not self.llm:
            raise ValueError("LLM client required for generate_tests_for_code")

        generator = self.generators.get(language)

        test_context = TestGeneratorContext(
            test_cases=test_cases,
            code_under_test=code,
        )

        code_context = self._build_code_context(code)
        test_cases_text = self._format_test_cases(test_cases)

        prompt = f"""Generate {generator.test_framework} unit tests.

## Test Cases
{test_cases_text}

## Code Under Test
{code_context}
"""

        response = self.llm.generate(
            system_prompt=generator.get_system_prompt(),
            user_prompt=prompt,
        )

        tests = generator.parse_generated_tests(response.content)

        return TestGenerationResult(
            tests=tests,
            summary=f"Generated {len(tests)} test files",
        )
