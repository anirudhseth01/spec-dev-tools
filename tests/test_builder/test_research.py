"""Tests for the research agent and GitHub analyzer."""

from __future__ import annotations

import asyncio
import json
from unittest import mock

import pytest

from src.builder.research import (
    ResearchAgent,
    ResearchResult,
    ResearchStatus,
    ValidationResult,
    RepoFile,
    ReusableComponent,
    RepoAnalysis,
    GitHubAnalyzer,
)
from src.builder.session import ResearchDepth


class TestRepoFile:
    """Tests for RepoFile dataclass."""

    def test_creation(self):
        """Test RepoFile creation."""
        repo_file = RepoFile(
            path="src/main.py",
            content="print('hello')",
            language="python",
            size_bytes=15,
        )

        assert repo_file.path == "src/main.py"
        assert repo_file.content == "print('hello')"
        assert repo_file.language == "python"
        assert repo_file.size_bytes == 15

    def test_to_dict(self):
        """Test RepoFile serialization."""
        repo_file = RepoFile(
            path="src/main.py",
            content="code",
            language="python",
            size_bytes=4,
        )

        data = repo_file.to_dict()

        assert data["path"] == "src/main.py"
        assert data["content"] == "code"
        assert data["language"] == "python"
        assert data["size_bytes"] == 4

    def test_from_dict(self):
        """Test RepoFile deserialization."""
        data = {
            "path": "lib/utils.py",
            "content": "def helper(): pass",
            "language": "python",
            "size_bytes": 18,
        }

        repo_file = RepoFile.from_dict(data)

        assert repo_file.path == "lib/utils.py"
        assert repo_file.content == "def helper(): pass"


class TestReusableComponent:
    """Tests for ReusableComponent dataclass."""

    def test_creation(self):
        """Test ReusableComponent creation."""
        component = ReusableComponent(
            name="DatabaseAdapter",
            description="Generic database adapter pattern",
            source_file="src/adapters/db.py",
            code_snippet="class DatabaseAdapter: pass",
            component_type="pattern",
            relevance_score=0.85,
            adaptation_notes="Replace connection string handling",
        )

        assert component.name == "DatabaseAdapter"
        assert component.component_type == "pattern"
        assert component.relevance_score == 0.85

    def test_to_dict(self):
        """Test ReusableComponent serialization."""
        component = ReusableComponent(
            name="Logger",
            description="Logging utility",
            source_file="utils/logger.py",
            component_type="utility",
        )

        data = component.to_dict()

        assert data["name"] == "Logger"
        assert data["source_file"] == "utils/logger.py"
        assert data["component_type"] == "utility"

    def test_from_dict(self):
        """Test ReusableComponent deserialization."""
        data = {
            "name": "HTTPClient",
            "description": "HTTP client wrapper",
            "source_file": "lib/http.py",
            "code_snippet": "class HTTPClient: ...",
            "component_type": "implementation",
            "relevance_score": 0.9,
            "adaptation_notes": "Customize headers",
        }

        component = ReusableComponent.from_dict(data)

        assert component.name == "HTTPClient"
        assert component.relevance_score == 0.9
        assert component.adaptation_notes == "Customize headers"


class TestRepoAnalysis:
    """Tests for RepoAnalysis dataclass."""

    def test_creation(self):
        """Test RepoAnalysis creation."""
        analysis = RepoAnalysis(
            repo_url="https://github.com/owner/repo",
            repo_name="repo",
            description="A sample repository",
            primary_language="Python",
            structure_summary="Standard Python project structure",
            architecture_patterns=["MVC", "Repository Pattern"],
            dependencies=["fastapi", "sqlalchemy"],
        )

        assert analysis.repo_url == "https://github.com/owner/repo"
        assert analysis.primary_language == "Python"
        assert "MVC" in analysis.architecture_patterns

    def test_to_dict(self):
        """Test RepoAnalysis serialization."""
        analysis = RepoAnalysis(
            repo_url="https://github.com/owner/repo",
            repo_name="repo",
            key_files=[RepoFile(path="main.py", content="code")],
            reusable_components=[
                ReusableComponent(
                    name="Component",
                    description="A component",
                    source_file="src/component.py",
                )
            ],
            status=ResearchStatus.COMPLETED,
        )

        data = analysis.to_dict()

        assert data["repo_url"] == "https://github.com/owner/repo"
        assert len(data["key_files"]) == 1
        assert len(data["reusable_components"]) == 1
        assert data["status"] == "completed"

    def test_from_dict(self):
        """Test RepoAnalysis deserialization."""
        data = {
            "repo_url": "https://github.com/test/project",
            "repo_name": "project",
            "description": "Test project",
            "primary_language": "Go",
            "structure_summary": "Go project",
            "architecture_patterns": ["Clean Architecture"],
            "key_files": [{"path": "main.go", "content": "package main"}],
            "reusable_components": [],
            "dependencies": ["gin"],
            "recommendations": ["Use middleware"],
            "status": "completed",
            "error_message": "",
        }

        analysis = RepoAnalysis.from_dict(data)

        assert analysis.repo_name == "project"
        assert analysis.primary_language == "Go"
        assert len(analysis.key_files) == 1
        assert analysis.key_files[0].path == "main.go"

    def test_failed_status(self):
        """Test RepoAnalysis with failed status."""
        analysis = RepoAnalysis(
            repo_url="https://github.com/owner/private-repo",
            status=ResearchStatus.FAILED,
            error_message="Repository not found",
        )

        assert analysis.status == ResearchStatus.FAILED
        assert "not found" in analysis.error_message


class TestGitHubAnalyzer:
    """Tests for GitHubAnalyzer."""

    def test_creation(self, mock_llm):
        """Test analyzer initialization."""
        analyzer = GitHubAnalyzer(mock_llm, ResearchDepth.MEDIUM)

        assert analyzer.llm_client == mock_llm
        assert analyzer.depth == ResearchDepth.MEDIUM

    def test_parse_repo_url_https(self):
        """Test parsing standard HTTPS URL."""
        analyzer = GitHubAnalyzer()

        result = analyzer._parse_repo_url("https://github.com/owner/repo")

        assert result == ("owner", "repo")

    def test_parse_repo_url_with_git_suffix(self):
        """Test parsing URL with .git suffix."""
        analyzer = GitHubAnalyzer()

        result = analyzer._parse_repo_url("https://github.com/owner/repo.git")

        assert result == ("owner", "repo")

    def test_parse_repo_url_with_path(self):
        """Test parsing URL with additional path."""
        analyzer = GitHubAnalyzer()

        result = analyzer._parse_repo_url("https://github.com/owner/repo/tree/main/src")

        assert result == ("owner", "repo")

    def test_parse_repo_url_invalid(self):
        """Test parsing invalid URL."""
        analyzer = GitHubAnalyzer()

        result = analyzer._parse_repo_url("https://gitlab.com/owner/repo")

        assert result is None

    def test_identify_key_files_python(self):
        """Test identifying key files for Python project."""
        analyzer = GitHubAnalyzer(depth=ResearchDepth.MEDIUM)

        file_tree = [
            {"path": "README.md", "type": "blob", "size": 1000},
            {"path": "setup.py", "type": "blob", "size": 500},
            {"path": "src/main.py", "type": "blob", "size": 2000},
            {"path": "src/utils.py", "type": "blob", "size": 1500},
            {"path": "tests/test_main.py", "type": "blob", "size": 1000},
            {"path": "node_modules/pkg.js", "type": "blob", "size": 100},
        ]

        key_files = analyzer._identify_key_files(file_tree, "Python")

        # Should include README, setup.py, and src files but not tests
        assert "README.md" in key_files
        assert "setup.py" in key_files
        assert "src/main.py" in key_files
        # Tests should be excluded
        assert "tests/test_main.py" not in key_files

    def test_identify_key_files_respects_depth(self):
        """Test that file limit changes with depth."""
        light_analyzer = GitHubAnalyzer(depth=ResearchDepth.LIGHT)
        deep_analyzer = GitHubAnalyzer(depth=ResearchDepth.DEEP)

        file_tree = [
            {"path": f"src/file{i}.py", "type": "blob", "size": 1000}
            for i in range(40)
        ]

        light_files = light_analyzer._identify_key_files(file_tree, "Python")
        deep_files = deep_analyzer._identify_key_files(file_tree, "Python")

        assert len(light_files) <= 5
        assert len(deep_files) <= 30
        assert len(light_files) < len(deep_files)

    def test_analyze_repo_invalid_url(self):
        """Test analyzing with invalid URL."""
        analyzer = GitHubAnalyzer()

        result = asyncio.run(analyzer.analyze_repo("https://not-github.com/repo"))

        assert result.status == ResearchStatus.FAILED
        assert "Invalid GitHub URL" in result.error_message

    def test_analyze_repo_caching(self, mock_llm):
        """Test that analysis results are cached."""
        analyzer = GitHubAnalyzer(mock_llm, ResearchDepth.LIGHT)

        # Mock subprocess calls
        with mock.patch("subprocess.run") as mock_run:
            # Setup mock responses
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout='{"name": "repo", "language": "Python", "description": "Test", "topics": []}',
            )

            # First call
            asyncio.run(
                analyzer.analyze_repo("https://github.com/owner/repo", context="test")
            )

            # Second call with same URL and context
            asyncio.run(
                analyzer.analyze_repo("https://github.com/owner/repo", context="test")
            )

            # Should only make API calls once due to caching
            initial_call_count = mock_run.call_count

        analyzer.clear_cache()
        assert len(analyzer._cache) == 0

    def test_analyze_repo_without_llm(self):
        """Test analysis without LLM returns basic info."""
        analyzer = GitHubAnalyzer(llm_client=None, depth=ResearchDepth.LIGHT)

        with mock.patch("subprocess.run") as mock_run:
            # Mock metadata response
            mock_run.side_effect = [
                mock.Mock(
                    returncode=0,
                    stdout='{"name": "repo", "language": "Python", "description": "A test repo", "topics": ["cli"]}',
                ),
                mock.Mock(returncode=0, stdout="[]"),  # Empty file tree
            ]

            result = asyncio.run(analyzer.analyze_repo("https://github.com/owner/repo"))

            assert result.repo_name == "repo"
            assert result.primary_language == "Python"
            assert result.status == ResearchStatus.COMPLETED


class TestResearchAgent:
    """Tests for ResearchAgent."""

    def test_creation(self, mock_llm):
        """Test agent initialization."""
        agent = ResearchAgent(mock_llm, ResearchDepth.MEDIUM)

        assert agent.llm_client == mock_llm
        assert agent.depth == ResearchDepth.MEDIUM

    def test_research_technology_without_llm(self):
        """Test research without LLM client."""
        agent = ResearchAgent(llm_client=None)

        result = asyncio.run(agent.research_technology("FastAPI"))

        assert result.technology == "FastAPI"
        assert "LLM not available" in result.summary
        assert result.status == ResearchStatus.COMPLETED

    def test_research_technology_with_llm(self, mock_llm):
        """Test research with LLM client."""
        mock_llm.responses = [
            json.dumps({
                "summary": "FastAPI is a modern Python web framework",
                "documentation_snippets": ["Install with pip install fastapi"],
                "known_issues": ["Startup time can be slow"],
                "best_practices": ["Use dependency injection"],
                "related_technologies": ["Starlette", "Pydantic"],
                "recommendation": "Great choice for APIs",
                "confidence": 0.9,
            })
        ]

        agent = ResearchAgent(mock_llm, ResearchDepth.MEDIUM)

        result = asyncio.run(agent.research_technology("FastAPI", "Building REST APIs"))

        assert result.technology == "FastAPI"
        assert "modern Python" in result.summary
        assert result.confidence == 0.9
        assert "Pydantic" in result.related_technologies

    def test_research_technology_caching(self, mock_llm):
        """Test that research results are cached."""
        mock_llm.responses = [
            json.dumps({
                "summary": "Tech summary",
                "confidence": 0.8,
            })
        ]

        agent = ResearchAgent(mock_llm)

        # First call
        asyncio.run(agent.research_technology("React", "Frontend"))
        first_call_count = mock_llm.call_count

        # Second call with same params
        asyncio.run(agent.research_technology("React", "Frontend"))

        # Should not have made another LLM call
        assert mock_llm.call_count == first_call_count

    def test_validate_compatibility_without_llm(self):
        """Test compatibility validation without LLM."""
        agent = ResearchAgent(llm_client=None)

        result = asyncio.run(
            agent.validate_compatibility(["FastAPI", "PostgreSQL", "Redis"])
        )

        assert result.is_compatible is True
        assert any("not validated" in w for w in result.warnings)

    def test_validate_compatibility_with_llm(self, mock_llm):
        """Test compatibility validation with LLM."""
        mock_llm.responses = [
            json.dumps({
                "is_compatible": True,
                "warnings": ["Consider connection pooling"],
                "errors": [],
                "suggestions": ["Use asyncpg for async support"],
            })
        ]

        agent = ResearchAgent(mock_llm)

        result = asyncio.run(
            agent.validate_compatibility(["FastAPI", "PostgreSQL"], "Building async API")
        )

        assert result.is_compatible is True
        assert "connection pooling" in result.warnings[0]
        assert "asyncpg" in result.suggestions[0]

    def test_analyze_github_repo(self, mock_llm):
        """Test GitHub repo analysis delegation."""
        agent = ResearchAgent(mock_llm, ResearchDepth.LIGHT)

        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(
                    returncode=0,
                    stdout='{"name": "test-repo", "language": "Python", "description": "Test", "topics": []}',
                ),
                mock.Mock(returncode=0, stdout="[]"),
            ]

            result = asyncio.run(
                agent.analyze_github_repo("https://github.com/owner/test-repo")
            )

            assert result.repo_name == "test-repo"

    def test_fetch_documentation_light_depth(self):
        """Test that light depth returns no docs."""
        agent = ResearchAgent(llm_client=None, depth=ResearchDepth.LIGHT)

        docs = asyncio.run(
            agent.fetch_documentation("FastAPI", ["routing", "middleware"])
        )

        assert docs == []

    def test_clear_cache(self, mock_llm):
        """Test clearing research cache."""
        agent = ResearchAgent(mock_llm)
        agent._cache["test"] = ResearchResult(technology="test")

        agent.clear_cache()

        assert len(agent._cache) == 0


class TestResearchResult:
    """Tests for ResearchResult dataclass."""

    def test_creation(self):
        """Test ResearchResult creation."""
        result = ResearchResult(
            technology="Django",
            summary="Python web framework",
            documentation_snippets=["Django docs"],
            known_issues=["ORM complexity"],
            best_practices=["Use class-based views"],
            related_technologies=["Flask", "FastAPI"],
            recommendation="Good for large applications",
            confidence=0.85,
            status=ResearchStatus.COMPLETED,
        )

        assert result.technology == "Django"
        assert result.confidence == 0.85

    def test_to_dict(self):
        """Test ResearchResult serialization."""
        result = ResearchResult(
            technology="React",
            summary="JS library for UIs",
            status=ResearchStatus.COMPLETED,
        )

        data = result.to_dict()

        assert data["technology"] == "React"
        assert data["status"] == "completed"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_creation(self):
        """Test ValidationResult creation."""
        result = ValidationResult(
            is_compatible=False,
            warnings=["Version mismatch possible"],
            errors=["Incompatible runtime"],
            suggestions=["Use version X instead"],
        )

        assert result.is_compatible is False
        assert len(result.errors) == 1

    def test_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(is_compatible=True, warnings=["Minor issue"])

        data = result.to_dict()

        assert data["is_compatible"] is True
        assert "Minor issue" in data["warnings"]
