"""Tests for TestGeneratorAgent."""

import pytest
from pathlib import Path

from src.agents.base import AgentContext, AgentStatus, AgentResult
from src.agents.testing.agent import (
    TestGeneratorAgent,
    TestGenerationConfig,
    TestGenerationState,
)
from src.agents.testing.generators import (
    BaseTestGenerator,
    GeneratedTest,
    GeneratorRegistry,
    JestGenerator,
    PytestGenerator,
    TestGenerationResult,
    TestGeneratorContext,
)
from src.llm.mock_client import MockLLMClient
from src.spec.schemas import (
    Spec,
    Metadata,
    Overview,
    TestCase,
    TestCases,
    EdgeCases,
    Inputs,
    InputParam,
    Outputs,
)


class TestPytestGenerator:
    """Tests for PytestGenerator."""

    def test_language_name(self):
        """Test language name property."""
        generator = PytestGenerator()
        assert generator.language == "python"

    def test_test_framework(self):
        """Test test framework property."""
        generator = PytestGenerator()
        assert generator.test_framework == "pytest"

    def test_file_extension(self):
        """Test file extension property."""
        generator = PytestGenerator()
        assert generator.file_extension == ".py"

    def test_parse_generated_tests(self):
        """Test parsing LLM response into test files."""
        generator = PytestGenerator()
        response = '''Here are the generated tests:

```python
# FILE: tests/test_service.py
import pytest

def test_service_happy_path():
    """Test happy path."""
    assert True

def test_service_error_case():
    """Test error case."""
    assert True
```

```python
# FILE: tests/test_utils.py
import pytest

def test_utils_parse():
    """Test parse function."""
    assert True
```
'''
        tests = generator.parse_generated_tests(response)

        assert len(tests) == 2
        assert tests[0].file_path == "tests/test_service.py"
        assert tests[0].test_count == 2
        assert tests[0].is_valid is True
        assert tests[1].file_path == "tests/test_utils.py"
        assert tests[1].test_count == 1

    def test_parse_generated_tests_fallback(self):
        """Test fallback parsing when no FILE headers."""
        generator = PytestGenerator()
        response = '''```python
def test_something():
    assert True
```'''
        tests = generator.parse_generated_tests(response)

        assert len(tests) == 1
        assert "generated_0.py" in tests[0].file_path

    def test_validate_test_valid(self):
        """Test validation with valid Python code."""
        generator = PytestGenerator()
        code = '''
import pytest

def test_example():
    """Test example."""
    assert 1 + 1 == 2
'''
        errors = generator.validate_test(code)
        assert len(errors) == 0

    def test_validate_test_invalid(self):
        """Test validation with invalid Python code."""
        generator = PytestGenerator()
        code = '''
def test_broken(
    assert True
'''
        errors = generator.validate_test(code)
        assert len(errors) > 0
        assert "SyntaxError" in errors[0] or "Line" in errors[0]

    def test_generate_unit_test_prompt(self):
        """Test unit test prompt generation."""
        generator = PytestGenerator()
        test_case = TestCase(
            test_id="UT-001",
            description="Test happy path",
            input="valid input",
            expected_output="success",
            setup="create test data",
        )
        code_context = "def process(data): return data"

        prompt = generator.generate_unit_test_prompt(test_case, code_context)

        assert "UT-001" in prompt
        assert "Test happy path" in prompt
        assert "valid input" in prompt
        assert "success" in prompt
        assert "create test data" in prompt
        assert code_context in prompt

    def test_generate_edge_case_prompt(self):
        """Test edge case prompt generation."""
        generator = PytestGenerator()
        edge_cases = EdgeCases(
            boundary_conditions=["Empty input", "Max length input"],
            concurrency=["Concurrent writes"],
            failure_modes=["Network timeout"],
        )
        code_context = "def process(data): return data"

        prompt = generator.generate_edge_case_prompt(edge_cases, code_context)

        assert "Empty input" in prompt
        assert "Max length input" in prompt
        assert "Concurrent writes" in prompt
        assert "Network timeout" in prompt

    def test_get_system_prompt(self):
        """Test system prompt generation."""
        generator = PytestGenerator()
        prompt = generator.get_system_prompt()

        assert "python" in prompt.lower()
        assert "pytest" in prompt.lower()
        assert "FILE:" in prompt


class TestJestGenerator:
    """Tests for JestGenerator."""

    def test_language_name(self):
        """Test language name property."""
        generator = JestGenerator()
        assert generator.language == "typescript"

    def test_test_framework(self):
        """Test test framework property."""
        generator = JestGenerator()
        assert generator.test_framework == "jest"

    def test_file_extension(self):
        """Test file extension property."""
        generator = JestGenerator()
        assert generator.file_extension == ".test.ts"

    def test_parse_generated_tests(self):
        """Test parsing TypeScript test response."""
        generator = JestGenerator()
        response = '''```typescript
// FILE: src/__tests__/service.test.ts
describe('Service', () => {
  it('should handle request', () => {
    expect(true).toBe(true);
  });

  it('should handle error', () => {
    expect(true).toBe(true);
  });
});
```'''
        tests = generator.parse_generated_tests(response)

        assert len(tests) == 1
        assert tests[0].file_path == "src/__tests__/service.test.ts"
        assert tests[0].test_count == 2

    def test_validate_test_valid(self):
        """Test validation with valid TypeScript code."""
        generator = JestGenerator()
        code = '''
describe('Module', () => {
  it('should work', () => {
    expect(1 + 1).toBe(2);
  });
});
'''
        errors = generator.validate_test(code)
        assert len(errors) == 0

    def test_validate_test_mismatched_braces(self):
        """Test validation with mismatched braces."""
        generator = JestGenerator()
        code = '''
describe('Module', () => {
  it('should work', () => {
    expect(1).toBe(1);
  };
});
'''
        errors = generator.validate_test(code)
        assert len(errors) > 0

    def test_validate_test_missing_structure(self):
        """Test validation with missing Jest structure."""
        generator = JestGenerator()
        code = '''
function helper() {
  return true;
}
'''
        errors = generator.validate_test(code)
        assert len(errors) > 0
        assert any("Jest" in e for e in errors)


class TestGeneratorRegistry:
    """Tests for GeneratorRegistry."""

    def test_default_generators(self):
        """Test default generators are registered."""
        registry = GeneratorRegistry()
        assert registry.has("python")
        assert registry.has("typescript")

    def test_get_generator(self):
        """Test getting a generator."""
        registry = GeneratorRegistry()
        generator = registry.get("python")
        assert generator.language == "python"
        assert generator.test_framework == "pytest"

    def test_get_unknown_generator(self):
        """Test getting unknown generator raises error."""
        registry = GeneratorRegistry()
        with pytest.raises(ValueError) as exc_info:
            registry.get("rust")
        assert "No generator for language" in str(exc_info.value)

    def test_list_languages(self):
        """Test listing available languages."""
        registry = GeneratorRegistry()
        languages = registry.list_languages()
        assert "python" in languages
        assert "typescript" in languages

    def test_detect_language_python(self, tmp_path):
        """Test detecting Python project."""
        (tmp_path / "pyproject.toml").touch()
        registry = GeneratorRegistry()
        assert registry.detect_language(tmp_path) == "python"

    def test_detect_language_typescript(self, tmp_path):
        """Test detecting TypeScript project."""
        (tmp_path / "tsconfig.json").touch()
        registry = GeneratorRegistry()
        assert registry.detect_language(tmp_path) == "typescript"

    def test_detect_language_from_pytest_ini(self, tmp_path):
        """Test detecting Python from pytest.ini."""
        (tmp_path / "pytest.ini").touch()
        registry = GeneratorRegistry()
        assert registry.detect_language(tmp_path) == "python"

    def test_detect_language_from_jest_config(self, tmp_path):
        """Test detecting TypeScript from jest.config.ts."""
        (tmp_path / "jest.config.ts").touch()
        registry = GeneratorRegistry()
        assert registry.detect_language(tmp_path) == "typescript"

    def test_detect_from_tech_stack_python(self):
        """Test detecting Python from tech stack."""
        registry = GeneratorRegistry()
        assert registry.detect_from_tech_stack("Python, FastAPI") == "python"
        assert registry.detect_from_tech_stack("pytest, django") == "python"

    def test_detect_from_tech_stack_typescript(self):
        """Test detecting TypeScript from tech stack."""
        registry = GeneratorRegistry()
        assert registry.detect_from_tech_stack("TypeScript, NestJS") == "typescript"
        assert registry.detect_from_tech_stack("Jest, React") == "typescript"

    def test_get_test_framework(self):
        """Test getting test framework for language."""
        registry = GeneratorRegistry()
        assert registry.get_test_framework("python") == "pytest"
        assert registry.get_test_framework("typescript") == "jest"


class TestTestGeneratorContext:
    """Tests for TestGeneratorContext."""

    def test_empty_context(self):
        """Test empty context properties."""
        context = TestGeneratorContext()
        assert context.has_test_cases is False
        assert context.has_edge_cases is False

    def test_context_with_test_cases(self):
        """Test context with test cases."""
        test_case = TestCase(
            test_id="UT-001",
            description="Test",
            input="input",
            expected_output="output",
        )
        context = TestGeneratorContext(test_cases=[test_case])
        assert context.has_test_cases is True

    def test_context_with_edge_cases(self):
        """Test context with edge cases."""
        edge_cases = EdgeCases(
            boundary_conditions=["Edge 1"],
            concurrency=[],
            failure_modes=[],
        )
        context = TestGeneratorContext(edge_cases=edge_cases)
        assert context.has_edge_cases is True

    def test_context_with_empty_edge_cases(self):
        """Test context with empty edge cases."""
        edge_cases = EdgeCases(
            boundary_conditions=[],
            concurrency=[],
            failure_modes=[],
        )
        context = TestGeneratorContext(edge_cases=edge_cases)
        assert context.has_edge_cases is False


class TestGeneratedTest:
    """Tests for GeneratedTest."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        test = GeneratedTest(
            file_path="tests/test_example.py",
            content="def test_example(): pass",
            test_framework="pytest",
            language="python",
            test_count=1,
            is_valid=True,
        )
        data = test.to_dict()

        assert data["file_path"] == "tests/test_example.py"
        assert data["test_framework"] == "pytest"
        assert data["language"] == "python"
        assert data["test_count"] == 1
        assert data["is_valid"] is True

    def test_with_validation_errors(self):
        """Test with validation errors."""
        test = GeneratedTest(
            file_path="tests/test_bad.py",
            content="def broken(",
            test_framework="pytest",
            language="python",
            is_valid=False,
            validation_errors=["Syntax error at line 1"],
        )
        assert test.is_valid is False
        assert len(test.validation_errors) == 1


class TestTestGenerationResult:
    """Tests for TestGenerationResult."""

    def test_empty_result(self):
        """Test empty result properties."""
        result = TestGenerationResult()
        assert result.total_tests == 0
        assert result.all_valid is True
        assert len(result.validation_errors) == 0

    def test_result_with_tests(self):
        """Test result with tests."""
        tests = [
            GeneratedTest(
                file_path="tests/test_a.py",
                content="",
                test_framework="pytest",
                language="python",
                test_count=3,
                is_valid=True,
            ),
            GeneratedTest(
                file_path="tests/test_b.py",
                content="",
                test_framework="pytest",
                language="python",
                test_count=2,
                is_valid=True,
            ),
        ]
        result = TestGenerationResult(tests=tests)
        assert result.total_tests == 5
        assert result.all_valid is True

    def test_result_with_invalid_tests(self):
        """Test result with invalid tests."""
        tests = [
            GeneratedTest(
                file_path="tests/test_good.py",
                content="",
                test_framework="pytest",
                language="python",
                is_valid=True,
            ),
            GeneratedTest(
                file_path="tests/test_bad.py",
                content="",
                test_framework="pytest",
                language="python",
                is_valid=False,
                validation_errors=["Error 1", "Error 2"],
            ),
        ]
        result = TestGenerationResult(tests=tests)
        assert result.all_valid is False
        assert len(result.validation_errors) == 2


class TestTestGenerationState:
    """Tests for TestGenerationState."""

    def test_initial_state(self):
        """Test initial state is empty."""
        state = TestGenerationState()
        assert len(state.all_tests) == 0
        assert state.total_test_count == 0

    def test_all_tests_combines_lists(self):
        """Test all_tests combines unit and edge case tests."""
        unit_test = GeneratedTest(
            file_path="test_unit.py",
            content="",
            test_framework="pytest",
            language="python",
            test_count=2,
        )
        edge_test = GeneratedTest(
            file_path="test_edge.py",
            content="",
            test_framework="pytest",
            language="python",
            test_count=3,
        )
        state = TestGenerationState(
            unit_tests=[unit_test],
            edge_case_tests=[edge_test],
        )
        assert len(state.all_tests) == 2
        assert state.total_test_count == 5


class TestTestGenerationConfig:
    """Tests for TestGenerationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TestGenerationConfig()
        assert config.min_unit_tests == 3
        assert config.min_integration_tests == 1
        assert config.generate_edge_case_tests is True
        assert config.mock_external_services is True
        assert config.max_retries == 2

    def test_custom_config(self):
        """Test custom configuration."""
        config = TestGenerationConfig(
            min_unit_tests=5,
            generate_edge_case_tests=False,
            max_retries=3,
        )
        assert config.min_unit_tests == 5
        assert config.generate_edge_case_tests is False
        assert config.max_retries == 3


class TestTestGeneratorAgent:
    """Tests for TestGeneratorAgent."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""
        response = '''```python
# FILE: tests/test_service.py
import pytest

def test_service_process():
    """Test process function."""
    assert True

def test_service_error():
    """Test error handling."""
    assert True
```'''
        return MockLLMClient(default_response=response)

    @pytest.fixture
    def agent(self, mock_llm):
        """Create TestGeneratorAgent with mock LLM."""
        return TestGeneratorAgent(llm_client=mock_llm, dry_run=True)

    @pytest.fixture
    def basic_spec(self):
        """Create a basic spec with test cases."""
        return Spec(
            name="Test Feature",
            metadata=Metadata(
                spec_id="test-feature",
                version="1.0",
                tech_stack="Python",
            ),
            overview=Overview(summary="A test feature"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(
                        test_id="UT-001",
                        description="Test happy path",
                        input="valid input",
                        expected_output="success",
                    ),
                    TestCase(
                        test_id="UT-002",
                        description="Test error case",
                        input="invalid input",
                        expected_output="error",
                    ),
                ],
            ),
        )

    @pytest.fixture
    def basic_context(self, basic_spec, tmp_path):
        """Create basic agent context."""
        return AgentContext(
            spec=basic_spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={
                        "code": {
                            "src/service.py": "def process(data): return data",
                        },
                        "language": "python",
                    },
                ),
            },
        )

    def test_agent_name(self, agent):
        """Test agent name."""
        assert agent.name == "testing_agent"

    def test_agent_requires(self, agent):
        """Test agent dependencies."""
        assert "coding_agent" in agent.requires

    def test_execute_generates_tests(self, agent, basic_context):
        """Test that execute generates test files."""
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.SUCCESS
        assert "tests" in result.data
        assert result.data["total_test_count"] >= 1

    def test_execute_skips_without_code(self, agent, basic_spec, tmp_path):
        """Test that execute skips when no code files."""
        context = AgentContext(
            spec=basic_spec,
            project_root=tmp_path,
        )
        result = agent.execute(context)

        assert result.status == AgentStatus.SKIPPED
        assert "No code files" in result.message

    def test_execute_with_edge_cases(self, mock_llm, tmp_path):
        """Test execution with edge cases."""
        spec = Spec(
            name="Test Feature",
            metadata=Metadata(spec_id="test", version="1.0", tech_stack="Python"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(
                        test_id="UT-001",
                        description="Test",
                        input="input",
                        expected_output="output",
                    ),
                ],
            ),
            edge_cases=EdgeCases(
                boundary_conditions=["Empty input", "Max size"],
                failure_modes=["Network error"],
            ),
        )
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"code": {"src/module.py": "def func(): pass"}},
                ),
            },
        )

        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=True)
        result = agent.execute(context)

        assert result.status == AgentStatus.SUCCESS

    def test_execute_detects_language(self, mock_llm, tmp_path):
        """Test that agent detects language from project."""
        (tmp_path / "pyproject.toml").touch()

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"code": {"src/module.py": "pass"}},
                ),
            },
        )

        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=True)
        result = agent.execute(context)

        assert result.data.get("language") == "python"
        assert result.data.get("test_framework") == "pytest"

    def test_execute_with_typescript(self, tmp_path):
        """Test execution with TypeScript project."""
        (tmp_path / "tsconfig.json").touch()

        mock_response = '''```typescript
// FILE: src/__tests__/service.test.ts
describe('Service', () => {
  it('should process data', () => {
    expect(true).toBe(true);
  });
});
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=True)

        spec = Spec(
            name="Test",
            metadata=Metadata(spec_id="test", version="1.0", tech_stack="TypeScript"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(test_id="UT-001", description="Test", input="", expected_output=""),
                ],
            ),
        )
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"code": {"src/service.ts": "export function process() {}"}},
                ),
            },
        )

        result = agent.execute(context)

        assert result.status == AgentStatus.SUCCESS
        assert result.data.get("language") == "typescript"
        assert result.data.get("test_framework") == "jest"

    def test_syntax_validation_fails(self, tmp_path):
        """Test that syntax errors cause failure."""
        mock_response = '''```python
# FILE: tests/test_bad.py
def test_broken(
    assert True
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=True)

        spec = Spec(
            name="Test",
            metadata=Metadata(spec_id="test", version="1.0"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(test_id="UT-001", description="Test", input="", expected_output=""),
                ],
            ),
        )
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"code": {"src/module.py": "pass"}},
                ),
            },
        )

        result = agent.execute(context)

        assert result.status == AgentStatus.FAILED
        assert len(result.errors) > 0

    def test_dry_run_no_files_written(self, agent, basic_context, tmp_path):
        """Test that dry run doesn't write files."""
        agent.execute(basic_context)

        # No files should be written
        assert not (tmp_path / "tests").exists()

    def test_writes_files_when_not_dry_run(self, mock_llm, basic_context, tmp_path):
        """Test that files are written when not dry run."""
        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=False)
        basic_context.project_root = tmp_path

        result = agent.execute(basic_context)

        if result.status == AgentStatus.SUCCESS:
            # Check that at least one test file was created
            test_files = list(tmp_path.rglob("test_*.py"))
            assert len(test_files) >= 1

    def test_template_generation_without_llm(self, tmp_path):
        """Test template generation without LLM client."""
        agent = TestGeneratorAgent(llm_client=None, dry_run=True)

        spec = Spec(
            name="Test",
            metadata=Metadata(spec_id="test", version="1.0", tech_stack="Python"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(
                        test_id="UT-001",
                        description="Test happy path",
                        input="input",
                        expected_output="output",
                    ),
                ],
            ),
        )
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={"code": {"src/service.py": "def process(): pass"}},
                ),
            },
        )

        result = agent.execute(context)

        assert result.status == AgentStatus.SUCCESS
        assert "tests" in result.data
        # Template tests should include the test case ID
        test_content = list(result.data["tests"].values())[0]
        assert "ut_001" in test_content.lower() or "UT-001" in test_content

    def test_can_run_checks_dependencies(self, agent, basic_context):
        """Test can_run checks for coding_agent dependency."""
        # With coding_agent result
        can_run, reason = agent.can_run(basic_context)
        assert can_run is True

        # Without coding_agent result
        context_no_dep = AgentContext(
            spec=basic_context.spec,
            project_root=basic_context.project_root,
        )
        can_run, reason = agent.can_run(context_no_dep)
        assert can_run is False
        assert "coding_agent" in reason

    def test_generate_tests_for_code_api(self, mock_llm):
        """Test direct API for generating tests."""
        agent = TestGeneratorAgent(llm_client=mock_llm)

        code = {"src/module.py": "def example(): pass"}
        test_cases = [
            TestCase(
                test_id="UT-001",
                description="Test example function",
                input="none",
                expected_output="none",
            ),
        ]

        result = agent.generate_tests_for_code(code, test_cases, language="python")

        assert isinstance(result, TestGenerationResult)
        assert len(result.tests) >= 1

    def test_generate_tests_for_code_requires_llm(self):
        """Test that generate_tests_for_code requires LLM."""
        agent = TestGeneratorAgent(llm_client=None)

        with pytest.raises(ValueError) as exc_info:
            agent.generate_tests_for_code({}, [], language="python")
        assert "LLM client required" in str(exc_info.value)


class TestTestGeneratorAgentIntegration:
    """Integration tests for TestGeneratorAgent."""

    def test_full_test_generation_flow(self, tmp_path):
        """Test complete test generation flow."""
        # Create project structure
        (tmp_path / "pyproject.toml").touch()
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create mock LLM with realistic response
        mock_response = '''Here are the generated tests:

```python
# FILE: tests/test_user_service.py
"""Tests for user service."""

import pytest
from unittest.mock import MagicMock, patch

class TestUserService:
    """Test cases for UserService."""

    def test_create_user_happy_path(self):
        """Test creating a user with valid data."""
        # Arrange
        user_data = {"name": "John", "email": "john@example.com"}

        # Act
        result = create_user(user_data)

        # Assert
        assert result["success"] is True
        assert result["user"]["name"] == "John"

    def test_create_user_invalid_email(self):
        """Test error when email is invalid."""
        # Arrange
        user_data = {"name": "John", "email": "invalid"}

        # Act & Assert
        with pytest.raises(ValidationError):
            create_user(user_data)

    def test_create_user_missing_name(self):
        """Test error when name is missing."""
        # Arrange
        user_data = {"email": "john@example.com"}

        # Act & Assert
        with pytest.raises(ValidationError):
            create_user(user_data)
```
'''
        mock_llm = MockLLMClient(default_response=mock_response)

        # Create spec with test cases
        spec = Spec(
            name="User Service",
            metadata=Metadata(
                spec_id="user-service",
                version="1.0",
                tech_stack="Python, FastAPI",
            ),
            overview=Overview(summary="User management service"),
            inputs=Inputs(
                user_inputs=[
                    InputParam(name="name", type="string", required=True),
                    InputParam(name="email", type="string", required=True),
                ],
            ),
            outputs=Outputs(
                return_values=["User object with id"],
                side_effects=["User saved to database"],
            ),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(
                        test_id="UT-001",
                        description="Create user with valid data",
                        input='{"name": "John", "email": "john@example.com"}',
                        expected_output='{"success": true}',
                    ),
                    TestCase(
                        test_id="UT-002",
                        description="Error on invalid email",
                        input='{"name": "John", "email": "invalid"}',
                        expected_output="ValidationError",
                    ),
                ],
            ),
            edge_cases=EdgeCases(
                boundary_conditions=["Empty name", "Very long name"],
                failure_modes=["Database connection error"],
            ),
        )

        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            previous_results={
                "coding_agent": AgentResult(
                    status=AgentStatus.SUCCESS,
                    data={
                        "code": {
                            "src/user_service.py": """
def create_user(user_data):
    validate(user_data)
    return save_user(user_data)
""",
                        },
                        "language": "python",
                    },
                ),
            },
        )

        # Execute
        agent = TestGeneratorAgent(llm_client=mock_llm, dry_run=True)
        result = agent.execute(context)

        # Verify
        assert result.status == AgentStatus.SUCCESS
        assert result.data["language"] == "python"
        assert result.data["test_framework"] == "pytest"
        assert result.data["total_test_count"] >= 1
        assert "tests/test_user_service.py" in result.data["tests"]
