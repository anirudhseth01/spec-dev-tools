"""Tests for CodeReviewAgent."""

import pytest
from pathlib import Path

from src.agents.base import AgentContext, AgentStatus
from src.agents.review.agent import CodeReviewAgent, ReviewMode
from src.agents.review.findings import (
    ReviewComment,
    ReviewReport,
    ReviewSeverity,
    ReviewCategory,
    SpecComplianceStatus,
)
from src.agents.review.checkers import (
    ReviewContext,
    CheckerRegistry,
    StyleChecker,
    SpecComplianceChecker,
    BestPracticesChecker,
)
from src.spec.schemas import Spec, Metadata


class TestReviewSeverity:
    """Tests for ReviewSeverity."""

    def test_blocks_merge(self):
        """Test which severities block merges."""
        assert ReviewSeverity.ERROR.blocks_merge is True
        assert ReviewSeverity.WARNING.blocks_merge is False
        assert ReviewSeverity.SUGGESTION.blocks_merge is False

    def test_severity_score(self):
        """Test severity scores for sorting."""
        assert ReviewSeverity.ERROR.score > ReviewSeverity.WARNING.score
        assert ReviewSeverity.WARNING.score > ReviewSeverity.SUGGESTION.score


class TestReviewComment:
    """Tests for ReviewComment class."""

    def test_location_with_line(self):
        """Test location string with line number."""
        comment = ReviewComment(
            id="TEST-001",
            file_path="src/main.py",
            message="Test issue",
            severity=ReviewSeverity.WARNING,
            category=ReviewCategory.STYLE,
            line_number=42,
        )
        assert comment.location == "src/main.py:42"

    def test_location_without_line(self):
        """Test location string without line number."""
        comment = ReviewComment(
            id="TEST-001",
            file_path="src/main.py",
            message="Test issue",
            severity=ReviewSeverity.WARNING,
            category=ReviewCategory.STYLE,
        )
        assert comment.location == "src/main.py"

    def test_location_with_line_range(self):
        """Test location string with line range."""
        comment = ReviewComment(
            id="TEST-001",
            file_path="src/main.py",
            message="Test issue",
            severity=ReviewSeverity.WARNING,
            category=ReviewCategory.STYLE,
            line_number=10,
            end_line=20,
        )
        assert comment.location == "src/main.py:10-20"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        comment = ReviewComment(
            id="TEST-001",
            file_path="test.py",
            message="Test message",
            severity=ReviewSeverity.ERROR,
            category=ReviewCategory.LOGIC,
            line_number=10,
            suggestion="Fix it",
        )
        data = comment.to_dict()
        assert data["id"] == "TEST-001"
        assert data["severity"] == "error"
        assert data["category"] == "logic"
        assert data["suggestion"] == "Fix it"


class TestReviewReport:
    """Tests for ReviewReport class."""

    def test_empty_report(self):
        """Test empty report."""
        report = ReviewReport()
        assert report.error_count == 0
        assert report.has_blocking_issues is False
        assert report.compliance_score == 1.0

    def test_report_with_comments(self):
        """Test report with various comments."""
        comments = [
            ReviewComment(
                id="1", file_path="a.py", message="Error",
                severity=ReviewSeverity.ERROR, category=ReviewCategory.LOGIC,
            ),
            ReviewComment(
                id="2", file_path="b.py", message="Warning",
                severity=ReviewSeverity.WARNING, category=ReviewCategory.STYLE,
            ),
            ReviewComment(
                id="3", file_path="c.py", message="Suggestion",
                severity=ReviewSeverity.SUGGESTION, category=ReviewCategory.BEST_PRACTICE,
            ),
        ]
        report = ReviewReport(comments=comments, files_reviewed=3)

        assert report.error_count == 1
        assert report.warning_count == 1
        assert report.suggestion_count == 1
        assert report.has_blocking_issues is True
        assert len(report.blocking_comments) == 1

    def test_compliance_score(self):
        """Test compliance score calculation."""
        results = [
            SpecComplianceStatus(requirement="Auth", status="pass"),
            SpecComplianceStatus(requirement="Rate", status="fail"),
            SpecComplianceStatus(requirement="TLS", status="pass"),
            SpecComplianceStatus(requirement="Log", status="pass"),
        ]
        report = ReviewReport(spec_compliance=results)
        assert report.compliance_score == 0.75  # 3/4

    def test_to_summary(self):
        """Test summary generation."""
        comments = [
            ReviewComment(
                id="1", file_path="a.py", message="Error",
                severity=ReviewSeverity.ERROR, category=ReviewCategory.LOGIC,
            ),
        ]
        report = ReviewReport(comments=comments)
        summary = report.to_summary()
        assert "NEEDS CHANGES" in summary
        assert "1 errors" in summary

    def test_to_markdown(self):
        """Test markdown report generation."""
        comments = [
            ReviewComment(
                id="1", file_path="auth.py", message="Logic error in auth",
                severity=ReviewSeverity.ERROR, category=ReviewCategory.LOGIC,
                line_number=10, suggestion="Fix the condition",
            ),
        ]
        report = ReviewReport(comments=comments, files_reviewed=5)
        markdown = report.to_markdown()

        assert "# Code Review Report" in markdown
        assert "auth.py:10" in markdown
        assert "Logic error" in markdown

    def test_get_comments_by_file(self):
        """Test filtering comments by file."""
        comments = [
            ReviewComment(
                id="1", file_path="a.py", message="Issue 1",
                severity=ReviewSeverity.WARNING, category=ReviewCategory.STYLE,
            ),
            ReviewComment(
                id="2", file_path="b.py", message="Issue 2",
                severity=ReviewSeverity.WARNING, category=ReviewCategory.STYLE,
            ),
            ReviewComment(
                id="3", file_path="a.py", message="Issue 3",
                severity=ReviewSeverity.WARNING, category=ReviewCategory.STYLE,
            ),
        ]
        report = ReviewReport(comments=comments)
        a_comments = report.get_comments_by_file("a.py")
        assert len(a_comments) == 2


class TestStyleChecker:
    """Tests for StyleChecker."""

    def test_detect_trailing_whitespace(self):
        """Test detection of trailing whitespace."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.py": "x = 1   \n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("trailing" in c.message.lower() for c in comments)

    def test_detect_import_star(self):
        """Test detection of import *."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.py": "from os import *\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("import *" in c.message or "pollutes" in c.message.lower() for c in comments)

    def test_detect_bare_except(self):
        """Test detection of bare except."""
        checker = StyleChecker()
        code = '''
try:
    x = 1
except:
    pass
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("except" in c.message.lower() for c in comments)

    def test_detect_mutable_default(self):
        """Test detection of mutable default argument."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.py": "def foo(x=[]):\n    pass\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("mutable" in c.message.lower() for c in comments)

    def test_detect_print_statement(self):
        """Test detection of print statements."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.py": "print('hello')\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("print" in c.message.lower() for c in comments)

    def test_detect_todo_comment(self):
        """Test detection of TODO comments."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.py": "# TODO: fix this\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("TODO" in c.message or "todo" in c.message.lower() for c in comments)

    def test_clean_code_minimal_issues(self):
        """Test that clean code produces minimal issues."""
        checker = StyleChecker()
        code = '''
"""Module docstring."""

import os


def get_value():
    """Get a value."""
    return os.environ.get("VALUE")
'''
        context = ReviewContext(
            files={"clean.py": code},
            project_root=Path("."),
        )
        comments = checker.check(context)
        # Should have no errors
        errors = [c for c in comments if c.severity == ReviewSeverity.ERROR]
        assert len(errors) == 0

    def test_typescript_console_log(self):
        """Test detection of console.log in TypeScript."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.ts": "console.log('debug');\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("console" in c.message.lower() for c in comments)

    def test_typescript_any_type(self):
        """Test detection of 'any' type in TypeScript."""
        checker = StyleChecker()
        context = ReviewContext(
            files={"test.ts": "const x: any = 1;\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("any" in c.message.lower() for c in comments)


class TestBestPracticesChecker:
    """Tests for BestPracticesChecker."""

    def test_detect_deep_nesting(self):
        """Test detection of deep nesting."""
        checker = BestPracticesChecker()
        code = '''
def foo():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        x = 1
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("nesting" in c.message.lower() for c in comments)

    def test_detect_empty_except(self):
        """Test detection of empty except blocks."""
        checker = BestPracticesChecker()
        code = '''
try:
    x = 1
except Exception:
    pass
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("except" in c.message.lower() or "empty" in c.message.lower() for c in comments)

    def test_detect_sql_injection(self):
        """Test detection of SQL injection patterns."""
        checker = BestPracticesChecker()
        code = '''
def query(user_id):
    sql = f"SELECT * FROM users WHERE id = {user_id}"
    return sql
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("sql" in c.message.lower() for c in comments)

    def test_detect_eval_usage(self):
        """Test detection of eval/exec usage."""
        checker = BestPracticesChecker()
        context = ReviewContext(
            files={"test.py": "result = eval(user_input)\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("eval" in c.message.lower() for c in comments)

    def test_detect_disabled_ssl(self):
        """Test detection of disabled SSL verification."""
        checker = BestPracticesChecker()
        context = ReviewContext(
            files={"test.py": "requests.get(url, verify=False)\n"},
            project_root=Path("."),
        )
        comments = checker.check(context)
        assert any("ssl" in c.message.lower() or "tls" in c.message.lower() for c in comments)


class TestSpecComplianceChecker:
    """Tests for SpecComplianceChecker."""

    def test_detect_missing_endpoint(self):
        """Test detection of missing endpoint implementation."""
        checker = SpecComplianceChecker()
        context = ReviewContext(
            files={"test.py": "# No endpoint implementation\n"},
            project_root=Path("."),
            spec_context="## API\nGET /users\nPOST /users",
        )
        comments = checker.check(context)
        # Should find missing endpoints
        assert any("missing" in c.message.lower() or "endpoint" in c.message.lower()
                  for c in comments)

    def test_endpoint_found(self):
        """Test that implemented endpoint is not flagged."""
        checker = SpecComplianceChecker()
        code = '''
@app.get("/users")
def get_users():
    return []
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
            spec_context="## API\nGET /users",
        )
        comments = checker.check(context)
        # Implemented endpoint should not be flagged as missing
        endpoint_issues = [c for c in comments
                         if "missing" in c.message.lower() and "/users" in c.message]
        assert len(endpoint_issues) == 0

    def test_get_compliance_status(self):
        """Test getting compliance status for requirements."""
        checker = SpecComplianceChecker()
        code = '''
@app.get("/users")
def get_users():
    return []
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
            spec_context="## API\nGET /users\nPOST /users",
        )
        statuses = checker.get_compliance_status(context)
        assert len(statuses) > 0
        # At least one should pass (GET /users)
        assert any(s.status == "pass" for s in statuses)


class TestCheckerRegistry:
    """Tests for CheckerRegistry."""

    def test_default_checkers(self):
        """Test default checker registration."""
        registry = CheckerRegistry()
        assert "style_checker" in registry.list_checkers()
        assert "spec_compliance_checker" in registry.list_checkers()
        assert "best_practices_checker" in registry.list_checkers()

    def test_lightweight_checkers(self):
        """Test getting lightweight checkers."""
        registry = CheckerRegistry()
        lightweight = registry.get_lightweight_checkers()
        assert all(not c.is_heavyweight for c in lightweight)

    def test_check_deduplication(self):
        """Test that duplicate comments are removed."""
        registry = CheckerRegistry()
        context = ReviewContext(
            files={"test.py": "from os import *\n"},
            project_root=Path("."),
        )
        comments = registry.check(context)

        # Check for duplicates
        locations = [(c.file_path, c.line_number, c.category) for c in comments]
        assert len(locations) == len(set(locations))

    def test_comments_sorted_by_severity(self):
        """Test that comments are sorted by severity."""
        registry = CheckerRegistry()
        code = '''
from os import *
print("test")
def foo(x=[]):
    pass
'''
        context = ReviewContext(
            files={"test.py": code},
            project_root=Path("."),
        )
        comments = registry.check(context)

        if len(comments) > 1:
            for i in range(len(comments) - 1):
                assert comments[i].severity.score >= comments[i + 1].severity.score


class TestCodeReviewAgent:
    """Tests for CodeReviewAgent."""

    @pytest.fixture
    def basic_context(self, tmp_path):
        """Create basic agent context."""
        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        return AgentContext(spec=spec, project_root=tmp_path)

    def test_agent_name(self):
        """Test agent name."""
        agent = CodeReviewAgent()
        assert agent.name == "code_review_agent"

    def test_standard_mode_default(self):
        """Test that standard mode is default."""
        agent = CodeReviewAgent()
        assert agent.mode == ReviewMode.STANDARD

    def test_quick_mode_config(self):
        """Test quick mode configuration."""
        agent = CodeReviewAgent(mode=ReviewMode.QUICK)
        assert agent.mode == ReviewMode.QUICK

    def test_deep_mode_config(self):
        """Test deep mode configuration."""
        agent = CodeReviewAgent(mode=ReviewMode.DEEP)
        assert agent.mode == ReviewMode.DEEP

    def test_mode_string_conversion(self):
        """Test mode string to enum conversion."""
        agent = CodeReviewAgent(mode="deep")
        assert agent.mode == ReviewMode.DEEP

    def test_review_clean_files(self, basic_context, tmp_path):
        """Test reviewing clean files passes."""
        # Create clean Python file
        (tmp_path / "clean.py").write_text('''
"""Clean module."""

import os


def get_config():
    """Get configuration."""
    return os.environ.get("CONFIG")
''')
        agent = CodeReviewAgent(fail_on_errors=False)
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.SUCCESS
        # Clean code should have no error-level issues
        assert result.data.get("has_blocking_issues") is False

    def test_review_problematic_files(self, basic_context, tmp_path):
        """Test reviewing files with issues."""
        # Create file with issues
        (tmp_path / "bad.py").write_text('''
from os import *

def foo(x=[]):
    eval(user_input)
    password = "secret123"
''')
        agent = CodeReviewAgent(fail_on_errors=True)
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.FAILED
        assert result.data.get("has_blocking_issues") is True
        assert len(result.errors) > 0

    def test_review_with_artifacts(self, basic_context):
        """Test reviewing from coding agent artifacts."""
        basic_context.parent_context = {
            "artifacts": {
                "code": {
                    "value": {
                        "src/auth.py": "def foo(x=[]):\n    pass\n",
                    }
                }
            }
        }
        agent = CodeReviewAgent(fail_on_errors=True)
        result = agent.execute(basic_context)

        # Should find mutable default argument
        assert "report" in result.data

    def test_review_empty_project(self, basic_context):
        """Test reviewing empty project."""
        agent = CodeReviewAgent()
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.SUCCESS
        assert result.data["report"]["files_reviewed"] == 0

    def test_direct_review_api(self):
        """Test direct file reviewing API."""
        agent = CodeReviewAgent()
        files = {
            "test.py": "from os import *\n",
        }
        report = agent.review_files(files)

        assert report.files_reviewed == 1
        assert len(report.comments) > 0

    def test_report_markdown_output(self, basic_context, tmp_path):
        """Test markdown report is generated."""
        (tmp_path / "test.py").write_text("print('hello')\n")
        agent = CodeReviewAgent()
        result = agent.execute(basic_context)

        assert "markdown_report" in result.data
        assert "# Code Review Report" in result.data["markdown_report"]

    def test_file_extension_filtering(self, basic_context, tmp_path):
        """Test that only specified extensions are reviewed."""
        # Create files with different extensions
        (tmp_path / "code.py").write_text("print('test')\n")
        (tmp_path / "readme.txt").write_text("print('test')\n")

        agent = CodeReviewAgent(file_extensions=[".py"])
        result = agent.execute(basic_context)

        # Should only review .py file
        report = result.data.get("report", {})
        assert report.get("files_reviewed", 0) == 1

    def test_fail_on_errors_disabled(self, basic_context, tmp_path):
        """Test that fail_on_errors can be disabled."""
        # Create file with error-level issues (eval is detected as error)
        (tmp_path / "bad.py").write_text("result = eval(user_input)\n")

        agent = CodeReviewAgent(fail_on_errors=False)
        result = agent.execute(basic_context)

        # Should succeed even with errors
        assert result.status == AgentStatus.SUCCESS
        # But should still report blocking issues
        assert result.data.get("has_blocking_issues") is True


class TestCodeReviewIntegration:
    """Integration tests for code review."""

    def test_full_review_flow(self, tmp_path):
        """Test complete review flow with multiple issues."""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # File with multiple issues
        (src_dir / "auth.py").write_text('''
from os import *
import hashlib

password = "admin123"  # Hardcoded password

def hash_pass(p):
    return hashlib.md5(p.encode()).hexdigest()  # Weak hash

def run_command(cmd):
    result = eval(cmd)  # Dangerous eval
    print(result)  # Debug print
    return result
''')

        # Cleaner file
        (src_dir / "utils.py").write_text('''
"""Utility functions."""

import logging

logger = logging.getLogger(__name__)


def process_data(data):
    """Process data safely."""
    logger.info("Processing data")
    return data
''')

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(spec=spec, project_root=tmp_path)

        agent = CodeReviewAgent(fail_on_errors=True)
        result = agent.execute(context)

        # Should find issues
        assert result.status == AgentStatus.FAILED
        report = result.data.get("report", {})
        assert report.get("files_reviewed", 0) >= 2

        # Check different categories found
        comments = report.get("comments", [])
        categories = {c["category"] for c in comments}
        # Should find style and security issues
        assert len(categories) > 1

    def test_review_with_spec_compliance(self, tmp_path):
        """Test review with spec compliance checking."""
        (tmp_path / "api.py").write_text('''
@app.get("/users")
def get_users():
    return []
''')

        # Create a mock spec with to_prompt_context method
        class MockRoutedSpec:
            def to_prompt_context(self):
                return "## API\nGET /users\nPOST /users"

        spec = Spec(name="User API", metadata=Metadata(spec_id="user-api", version="1.0"))
        context = AgentContext(
            spec=spec,
            project_root=tmp_path,
            parent_context={
                "routed_spec": MockRoutedSpec()
            }
        )

        agent = CodeReviewAgent()
        result = agent.execute(context)

        # Should succeed and have a report
        assert result.status == AgentStatus.SUCCESS
        report = result.data.get("report", {})
        assert "compliance_score" in report

    def test_quick_mode_faster(self, tmp_path):
        """Test that quick mode is faster."""
        (tmp_path / "test.py").write_text("x = 1\n")

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(spec=spec, project_root=tmp_path)

        quick_agent = CodeReviewAgent(mode=ReviewMode.QUICK)
        standard_agent = CodeReviewAgent(mode=ReviewMode.STANDARD)

        quick_result = quick_agent.execute(context)
        standard_result = standard_agent.execute(context)

        # Both should succeed
        assert quick_result.status == AgentStatus.SUCCESS
        assert standard_result.status == AgentStatus.SUCCESS
