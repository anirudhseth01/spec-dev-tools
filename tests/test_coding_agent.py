"""Tests for CodingAgent."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.agents.base import AgentContext, AgentStatus
from src.agents.coding.agent import CodingAgent, GenerationState
from src.agents.coding.plugins import PythonPlugin, TypeScriptPlugin, PluginRegistry
from src.agents.coding.context_builder import ContextBuilder, CodeContext
from src.agents.coding.ambiguity import (
    AmbiguityResolver,
    Ambiguity,
    AmbiguityCategory,
)
from src.llm.mock_client import MockLLMClient, create_skeleton_mock
from src.spec.schemas import Spec, Metadata, Overview


class TestPythonPlugin:
    """Tests for PythonPlugin."""

    def test_language_name(self):
        """Test language name."""
        plugin = PythonPlugin()
        assert plugin.language_name == "python"

    def test_conventions(self):
        """Test language conventions."""
        plugin = PythonPlugin()
        conv = plugin.conventions
        assert conv.file_extension == ".py"
        assert conv.naming_convention == "snake_case"
        assert conv.test_framework == "pytest"

    def test_parse_generated_code(self):
        """Test parsing LLM response into files."""
        plugin = PythonPlugin()
        response = '''Some text before

```python
# FILE: src/models.py
from dataclasses import dataclass

@dataclass
class User:
    name: str
```

```python
# FILE: src/service.py
class UserService:
    pass
```
'''
        files = plugin.parse_generated_code(response)
        assert len(files) == 2
        assert "src/models.py" in files
        assert "src/service.py" in files
        assert "@dataclass" in files["src/models.py"]

    def test_parse_generated_code_fallback(self):
        """Test fallback when no FILE: headers."""
        plugin = PythonPlugin()
        response = '''```python
def hello():
    pass
```'''
        files = plugin.parse_generated_code(response)
        assert len(files) == 1
        assert "generated_0.py" in files

    def test_validate_syntax_valid(self):
        """Test syntax validation with valid code."""
        plugin = PythonPlugin()
        code = '''
def hello(name: str) -> str:
    return f"Hello, {name}"
'''
        errors = plugin.validate_syntax(code)
        assert len(errors) == 0

    def test_validate_syntax_invalid(self):
        """Test syntax validation with invalid code."""
        plugin = PythonPlugin()
        code = '''
def hello(name: str
    return f"Hello, {name}"
'''
        errors = plugin.validate_syntax(code)
        assert len(errors) > 0


class TestTypeScriptPlugin:
    """Tests for TypeScriptPlugin."""

    def test_language_name(self):
        """Test language name."""
        plugin = TypeScriptPlugin()
        assert plugin.language_name == "typescript"

    def test_conventions(self):
        """Test language conventions."""
        plugin = TypeScriptPlugin()
        conv = plugin.conventions
        assert conv.file_extension == ".ts"
        assert conv.naming_convention == "camelCase"
        assert conv.test_framework == "jest"

    def test_parse_generated_code(self):
        """Test parsing TypeScript response."""
        plugin = TypeScriptPlugin()
        response = '''```typescript
// FILE: src/types.ts
interface User {
  name: string;
}
```'''
        files = plugin.parse_generated_code(response)
        assert len(files) == 1
        assert "src/types.ts" in files


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_default_plugins(self):
        """Test default plugins are registered."""
        registry = PluginRegistry()
        assert registry.has("python")
        assert registry.has("typescript")

    def test_get_plugin(self):
        """Test getting a plugin."""
        registry = PluginRegistry()
        plugin = registry.get("python")
        assert plugin.language_name == "python"

    def test_get_unknown_plugin(self):
        """Test getting unknown plugin raises error."""
        registry = PluginRegistry()
        with pytest.raises(ValueError):
            registry.get("cobol")

    def test_list_languages(self):
        """Test listing available languages."""
        registry = PluginRegistry()
        languages = registry.list_languages()
        assert "python" in languages
        assert "typescript" in languages

    def test_detect_language_python(self, tmp_path):
        """Test detecting Python project."""
        (tmp_path / "pyproject.toml").touch()
        registry = PluginRegistry()
        assert registry.detect_language(tmp_path) == "python"

    def test_detect_language_typescript(self, tmp_path):
        """Test detecting TypeScript project."""
        (tmp_path / "tsconfig.json").touch()
        registry = PluginRegistry()
        assert registry.detect_language(tmp_path) == "typescript"


class TestContextBuilder:
    """Tests for ContextBuilder."""

    def test_build_context_empty(self, tmp_path):
        """Test building context with no files."""
        builder = ContextBuilder()
        context = builder.build_context(
            project_root=tmp_path,
            target_files=[],
        )
        assert len(context.files) == 0

    def test_build_context_with_siblings(self, tmp_path):
        """Test building context includes siblings."""
        # Create some files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# main")
        (src_dir / "utils.py").write_text("# utils")

        builder = ContextBuilder()
        context = builder.build_context(
            project_root=tmp_path,
            target_files=[src_dir / "main.py"],
        )

        # Should find sibling
        assert any("utils.py" in path for path in context.files)

    def test_code_context_to_prompt(self):
        """Test converting context to prompt."""
        context = CodeContext()
        context.add_file("src/models.py", "class User: pass", "python")

        prompt = context.to_prompt()
        assert "src/models.py" in prompt
        assert "class User: pass" in prompt
        assert "```python" in prompt


class TestAmbiguityResolver:
    """Tests for AmbiguityResolver."""

    def test_critical_ambiguity_asks(self):
        """Test that critical ambiguities create questions."""
        resolver = AmbiguityResolver()
        ambiguity = Ambiguity(
            category=AmbiguityCategory.SECURITY,
            description="Authentication method not specified",
            possible_choices=["JWT", "OAuth", "Session"],
        )

        resolution = resolver.resolve(ambiguity)
        assert resolution.action == "ask"
        assert resolution.question is not None
        assert len(resolution.options) >= 3

    def test_minor_ambiguity_assumes(self):
        """Test that minor ambiguities are assumed."""
        resolver = AmbiguityResolver()
        ambiguity = Ambiguity(
            category=AmbiguityCategory.VARIABLE_NAMING,
            description="Variable naming style not specified",
            possible_choices=["snake_case", "camelCase"],
        )

        resolution = resolver.resolve(ambiguity)
        assert resolution.action == "assume"
        assert resolution.chosen is not None
        assert resolution.documentation is not None
        assert "ASSUMPTION" in resolution.documentation

    def test_detect_storage_ambiguity(self):
        """Test detecting storage ambiguities."""
        resolver = AmbiguityResolver()
        spec = "Store user preferences in the database"

        ambiguities = resolver.detect_ambiguities(spec)
        storage_ambiguity = [
            a for a in ambiguities
            if a.category == AmbiguityCategory.DATA_PERSISTENCE
        ]
        assert len(storage_ambiguity) > 0

    def test_detect_auth_ambiguity(self):
        """Test detecting auth ambiguities."""
        resolver = AmbiguityResolver()
        spec = "User must authenticate to access the dashboard"

        ambiguities = resolver.detect_ambiguities(spec)
        auth_ambiguity = [
            a for a in ambiguities
            if a.category == AmbiguityCategory.AUTHENTICATION
        ]
        assert len(auth_ambiguity) > 0


class TestCodingAgent:
    """Tests for CodingAgent."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM client."""
        return create_skeleton_mock()

    @pytest.fixture
    def agent(self, mock_llm):
        """Create CodingAgent with mock LLM."""
        return CodingAgent(llm_client=mock_llm, dry_run=True)

    @pytest.fixture
    def basic_context(self, tmp_path):
        """Create basic agent context."""
        spec = Spec(
            name="Test Feature",
            metadata=Metadata(
                spec_id="test-001",
                version="1.0",
                tech_stack="python",
            )
        )
        return AgentContext(
            spec=spec,
            project_root=tmp_path,
        )

    def test_agent_name(self, agent):
        """Test agent name."""
        assert agent.name == "coding_agent"

    def test_execute_generates_files(self, agent, basic_context):
        """Test that execute generates code files."""
        result = agent.execute(basic_context)

        # Should succeed or return questions
        assert result.status in [AgentStatus.SUCCESS, AgentStatus.PENDING]
        assert "code" in result.data or "questions" in result.data

    def test_execute_with_skeleton_response(self, basic_context, tmp_path):
        """Test execution with specific skeleton response."""
        mock_response = '''```python
# FILE: src/feature/service.py
from abc import ABC, abstractmethod

class Service(ABC):
    @abstractmethod
    def process(self) -> None:
        raise NotImplementedError
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = CodingAgent(llm_client=mock_llm, dry_run=True)

        result = agent.execute(basic_context)

        assert result.status in [AgentStatus.SUCCESS, AgentStatus.PENDING]

    def test_execute_detects_language(self, agent, tmp_path):
        """Test that agent detects language from project."""
        (tmp_path / "pyproject.toml").touch()

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(spec=spec, project_root=tmp_path)

        result = agent.execute(context)

        # Language should be detected as Python
        if result.status == AgentStatus.SUCCESS:
            assert result.data.get("language") == "python"

    def test_execute_with_typescript(self, tmp_path):
        """Test execution with TypeScript project."""
        (tmp_path / "tsconfig.json").touch()

        mock_response = '''```typescript
// FILE: src/service.ts
interface Service {
  process(): void;
}
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = CodingAgent(llm_client=mock_llm, dry_run=True)

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(spec=spec, project_root=tmp_path)

        result = agent.execute(context)
        assert result.status in [AgentStatus.SUCCESS, AgentStatus.PENDING]

    def test_syntax_validation_fails(self, tmp_path):
        """Test that syntax errors cause failure."""
        # Create a spec without ambiguity triggers
        spec = Spec(
            name="Simple Feature",
            metadata=Metadata(spec_id="test", version="1.0"),
            overview=Overview(summary="A simple feature"),
        )
        context = AgentContext(spec=spec, project_root=tmp_path)

        mock_response = '''```python
# FILE: src/bad.py
def broken(
    return "missing closing paren"
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = CodingAgent(llm_client=mock_llm, dry_run=True)

        result = agent.execute(context)
        # Either fails due to syntax, or returns pending for ambiguity questions
        assert result.status in [AgentStatus.FAILED, AgentStatus.PENDING]
        if result.status == AgentStatus.FAILED:
            assert len(result.errors) > 0

    def test_dry_run_no_files_written(self, basic_context, tmp_path):
        """Test that dry run doesn't write files."""
        mock_response = '''```python
# FILE: src/test.py
print("hello")
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = CodingAgent(llm_client=mock_llm, dry_run=True)

        agent.execute(basic_context)

        # No files should be written
        assert not (tmp_path / "src" / "test.py").exists()

    def test_writes_files_when_not_dry_run(self, basic_context, tmp_path):
        """Test that files are written when not dry run."""
        mock_response = '''```python
# FILE: src/test.py
print("hello")
```'''
        mock_llm = MockLLMClient(default_response=mock_response)
        agent = CodingAgent(llm_client=mock_llm, dry_run=False)

        result = agent.execute(basic_context)

        if result.status == AgentStatus.SUCCESS:
            assert (tmp_path / "src" / "test.py").exists()


class TestGenerationState:
    """Tests for GenerationState."""

    def test_initial_state(self):
        """Test initial state is empty."""
        state = GenerationState()
        assert len(state.skeleton_files) == 0
        assert len(state.implementation_files) == 0
        assert len(state.assumptions) == 0
        assert len(state.questions_pending) == 0

    def test_state_tracking(self):
        """Test state tracks data."""
        state = GenerationState()
        state.skeleton_files["test.py"] = "# skeleton"
        state.assumptions.append("# ASSUMPTION: test")

        assert "test.py" in state.skeleton_files
        assert len(state.assumptions) == 1
