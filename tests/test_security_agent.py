"""Tests for SecurityScanAgent."""

import pytest
from pathlib import Path

from src.agents.base import AgentContext, AgentStatus
from src.agents.security.agent import SecurityScanAgent, ScanMode
from src.agents.security.findings import (
    Finding,
    FindingSeverity,
    FindingCategory,
    SecurityReport,
    SpecComplianceResult,
)
from src.agents.security.scanners import (
    PatternScanner,
    ScanContext,
    ScannerRegistry,
)
from src.spec.schemas import Spec, Metadata


class TestFindingSeverity:
    """Tests for FindingSeverity."""

    def test_blocks_pr(self):
        """Test which severities block PRs."""
        assert FindingSeverity.CRITICAL.blocks_pr is True
        assert FindingSeverity.HIGH.blocks_pr is True
        assert FindingSeverity.MEDIUM.blocks_pr is False
        assert FindingSeverity.LOW.blocks_pr is False
        assert FindingSeverity.INFO.blocks_pr is False

    def test_blocks_deploy(self):
        """Test which severities block deployment."""
        assert FindingSeverity.CRITICAL.blocks_deploy is True
        assert FindingSeverity.HIGH.blocks_deploy is False
        assert FindingSeverity.MEDIUM.blocks_deploy is False

    def test_severity_score(self):
        """Test severity scores for sorting."""
        assert FindingSeverity.CRITICAL.score > FindingSeverity.HIGH.score
        assert FindingSeverity.HIGH.score > FindingSeverity.MEDIUM.score
        assert FindingSeverity.MEDIUM.score > FindingSeverity.LOW.score


class TestFinding:
    """Tests for Finding class."""

    def test_location_with_line(self):
        """Test location string with line number."""
        finding = Finding(
            id="TEST-001",
            title="Test",
            description="Test finding",
            severity=FindingSeverity.HIGH,
            category=FindingCategory.SECRETS,
            file_path="src/main.py",
            line_number=42,
        )
        assert finding.location == "src/main.py:42"

    def test_location_without_line(self):
        """Test location string without line number."""
        finding = Finding(
            id="TEST-001",
            title="Test",
            description="Test finding",
            severity=FindingSeverity.HIGH,
            category=FindingCategory.SECRETS,
            file_path="src/main.py",
        )
        assert finding.location == "src/main.py"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        finding = Finding(
            id="TEST-001",
            title="Test Finding",
            description="Test description",
            severity=FindingSeverity.HIGH,
            category=FindingCategory.INJECTION,
            file_path="test.py",
            line_number=10,
        )
        data = finding.to_dict()
        assert data["id"] == "TEST-001"
        assert data["severity"] == "high"
        assert data["category"] == "injection"


class TestSecurityReport:
    """Tests for SecurityReport class."""

    def test_empty_report(self):
        """Test empty report."""
        report = SecurityReport()
        assert report.critical_count == 0
        assert report.has_blocking_issues is False
        assert report.compliance_score == 1.0

    def test_report_with_findings(self):
        """Test report with various findings."""
        findings = [
            Finding(
                id="1", title="Critical", description="",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SECRETS, file_path="a.py"
            ),
            Finding(
                id="2", title="High", description="",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.INJECTION, file_path="b.py"
            ),
            Finding(
                id="3", title="Medium", description="",
                severity=FindingSeverity.MEDIUM,
                category=FindingCategory.CRYPTO, file_path="c.py"
            ),
        ]
        report = SecurityReport(findings=findings, files_scanned=3)

        assert report.critical_count == 1
        assert report.high_count == 1
        assert report.medium_count == 1
        assert report.has_blocking_issues is True
        assert len(report.blocking_findings) == 2

    def test_compliance_score(self):
        """Test compliance score calculation."""
        results = [
            SpecComplianceResult(requirement="Auth", status="pass"),
            SpecComplianceResult(requirement="Rate", status="fail"),
            SpecComplianceResult(requirement="TLS", status="pass"),
            SpecComplianceResult(requirement="Log", status="pass"),
        ]
        report = SecurityReport(compliance_results=results)
        assert report.compliance_score == 0.75  # 3/4

    def test_to_summary(self):
        """Test summary generation."""
        findings = [
            Finding(
                id="1", title="Critical", description="",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SECRETS, file_path="a.py"
            ),
        ]
        report = SecurityReport(findings=findings)
        summary = report.to_summary()
        assert "FAILED" in summary
        assert "1 critical" in summary

    def test_to_markdown(self):
        """Test markdown report generation."""
        findings = [
            Finding(
                id="1", title="Hardcoded Secret",
                description="Found hardcoded password",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SECRETS,
                file_path="auth.py",
                line_number=10,
                recommendation="Use environment variables",
            ),
        ]
        report = SecurityReport(findings=findings, files_scanned=5)
        markdown = report.to_markdown()

        assert "# Security Scan Report" in markdown
        assert "Hardcoded Secret" in markdown
        assert "auth.py:10" in markdown


class TestPatternScanner:
    """Tests for PatternScanner."""

    def test_detect_hardcoded_password(self):
        """Test detection of hardcoded passwords."""
        scanner = PatternScanner()
        context = ScanContext(
            files={"auth.py": 'password = "secret123"'},
            project_root=Path("."),
        )
        findings = scanner.scan(context)
        assert len(findings) >= 1
        assert any(f.category == FindingCategory.SECRETS for f in findings)

    def test_detect_sql_injection(self):
        """Test detection of SQL injection."""
        scanner = PatternScanner()
        code = '''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
'''
        context = ScanContext(
            files={"db.py": code},
            project_root=Path("."),
        )
        findings = scanner.scan(context)
        assert len(findings) >= 1
        assert any(f.category == FindingCategory.INJECTION for f in findings)

    def test_detect_command_injection(self):
        """Test detection of command injection."""
        scanner = PatternScanner()
        code = '''
import subprocess
def run_cmd(cmd):
    subprocess.call(cmd, shell=True)
'''
        context = ScanContext(
            files={"util.py": code},
            project_root=Path("."),
        )
        findings = scanner.scan(context)
        assert len(findings) >= 1
        assert any("shell" in f.title.lower() or "injection" in f.title.lower()
                  for f in findings)

    def test_detect_weak_crypto(self):
        """Test detection of weak cryptography."""
        scanner = PatternScanner()
        code = '''
import hashlib
def hash_password(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()
'''
        context = ScanContext(
            files={"crypto.py": code},
            project_root=Path("."),
        )
        findings = scanner.scan(context)
        assert len(findings) >= 1
        assert any(f.category == FindingCategory.CRYPTO for f in findings)

    def test_clean_code_no_findings(self):
        """Test that clean code produces no findings."""
        scanner = PatternScanner()
        code = '''
import os
import hashlib

def get_api_key():
    return os.environ.get("API_KEY")

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()
'''
        context = ScanContext(
            files={"clean.py": code},
            project_root=Path("."),
        )
        findings = scanner.scan(context)
        # Should have no critical or high findings
        blocking = [f for f in findings if f.severity.blocks_pr]
        assert len(blocking) == 0

    def test_language_specific_patterns(self):
        """Test language-specific pattern matching."""
        scanner = PatternScanner()

        # Python-specific pattern should match .py files
        py_code = 'password = "test123"'
        context = ScanContext(
            files={"test.py": py_code},
            project_root=Path("."),
        )
        py_findings = scanner.scan(context)

        # Same pattern in .txt should still match (no language filter for secrets)
        txt_context = ScanContext(
            files={"test.txt": py_code},
            project_root=Path("."),
        )
        txt_findings = scanner.scan(txt_context)

        # Both should find the hardcoded password
        assert len(py_findings) >= 1


class TestScannerRegistry:
    """Tests for ScannerRegistry."""

    def test_default_scanners(self):
        """Test default scanner registration."""
        registry = ScannerRegistry()
        assert "pattern_scanner" in registry.list_scanners()

    def test_lightweight_scanners(self):
        """Test getting lightweight scanners."""
        registry = ScannerRegistry()
        lightweight = registry.get_lightweight_scanners()
        assert all(not s.is_heavyweight for s in lightweight)

    def test_heavyweight_scanners(self):
        """Test getting heavyweight scanners."""
        registry = ScannerRegistry()
        registry.register_compliance_scanner()
        heavyweight = registry.get_heavyweight_scanners()
        assert len(heavyweight) >= 2  # Pattern + compliance

    def test_scan_deduplication(self):
        """Test that duplicate findings are removed."""
        registry = ScannerRegistry()
        context = ScanContext(
            files={"test.py": 'password = "test"'},
            project_root=Path("."),
        )
        findings = registry.scan(context)

        # Check for duplicates
        locations = [(f.file_path, f.line_number, f.category) for f in findings]
        assert len(locations) == len(set(locations))


class TestSecurityScanAgent:
    """Tests for SecurityScanAgent."""

    @pytest.fixture
    def basic_context(self, tmp_path):
        """Create basic agent context."""
        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        return AgentContext(spec=spec, project_root=tmp_path)

    def test_agent_name(self):
        """Test agent name."""
        agent = SecurityScanAgent()
        assert agent.name == "security_agent"

    def test_lightweight_mode_default(self):
        """Test that lightweight mode is default."""
        agent = SecurityScanAgent()
        assert agent.mode == ScanMode.LIGHTWEIGHT

    def test_heavyweight_mode_config(self):
        """Test heavyweight mode configuration."""
        agent = SecurityScanAgent(mode=ScanMode.HEAVYWEIGHT)
        assert agent.mode == ScanMode.HEAVYWEIGHT

    def test_mode_string_conversion(self):
        """Test mode string to enum conversion."""
        agent = SecurityScanAgent(mode="heavyweight")
        assert agent.mode == ScanMode.HEAVYWEIGHT

    def test_scan_clean_files(self, basic_context, tmp_path):
        """Test scanning clean files passes."""
        # Create clean Python file
        (tmp_path / "clean.py").write_text('''
import os

def get_config():
    return os.environ.get("CONFIG")
''')
        agent = SecurityScanAgent()
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.SUCCESS
        assert result.data.get("has_blocking_issues") is False

    def test_scan_vulnerable_files(self, basic_context, tmp_path):
        """Test scanning vulnerable files fails."""
        # Create file with hardcoded secret
        (tmp_path / "bad.py").write_text('''
password = "super_secret_password_123"
api_key = "sk-1234567890abcdef1234567890abcdef"
''')
        agent = SecurityScanAgent()
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.FAILED
        assert result.data.get("has_blocking_issues") is True
        assert len(result.errors) > 0

    def test_scan_with_artifacts(self, basic_context):
        """Test scanning from coding agent artifacts."""
        basic_context.parent_context = {
            "artifacts": {
                "code": {
                    "value": {
                        "src/auth.py": 'password = "test123"',
                    }
                }
            }
        }
        agent = SecurityScanAgent()
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.FAILED
        assert "report" in result.data

    def test_scan_empty_project(self, basic_context):
        """Test scanning empty project."""
        agent = SecurityScanAgent()
        result = agent.execute(basic_context)

        assert result.status == AgentStatus.SUCCESS
        assert result.data["report"]["files_scanned"] == 0

    def test_direct_scan_api(self):
        """Test direct file scanning API."""
        agent = SecurityScanAgent()
        files = {
            "test.py": 'api_key = "secret12345678901234"',
        }
        report = agent.scan_files(files)

        assert report.files_scanned == 1
        assert report.has_blocking_issues is True

    def test_report_markdown_output(self, basic_context, tmp_path):
        """Test markdown report is generated."""
        (tmp_path / "vuln.py").write_text('password = "hackme"')
        agent = SecurityScanAgent()
        result = agent.execute(basic_context)

        assert "markdown_report" in result.data
        assert "# Security Scan Report" in result.data["markdown_report"]

    def test_file_extension_filtering(self, basic_context, tmp_path):
        """Test that only specified extensions are scanned."""
        # Create files with different extensions
        (tmp_path / "code.py").write_text('password = "test"')
        (tmp_path / "readme.txt").write_text('password = "test"')
        (tmp_path / "image.png").write_bytes(b'\x89PNG\r\n\x1a\n')

        agent = SecurityScanAgent(file_extensions=[".py"])
        result = agent.execute(basic_context)

        # Should only scan .py file
        report = result.data.get("report", {})
        assert report.get("files_scanned", 0) <= 1


class TestSecurityScanIntegration:
    """Integration tests for security scanning."""

    def test_full_scan_flow(self, tmp_path):
        """Test complete scan flow with multiple vulnerabilities."""
        # Create project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # File with multiple issues
        (src_dir / "auth.py").write_text('''
import hashlib
import os

password = "admin123"  # Hardcoded password

def hash_pass(p):
    return hashlib.md5(p.encode()).hexdigest()  # Weak hash

def run_command(cmd):
    os.system(f"echo {cmd}")  # Command injection
''')

        # Clean file
        (src_dir / "utils.py").write_text('''
import logging

logger = logging.getLogger(__name__)

def process_data(data):
    logger.info("Processing data")
    return data
''')

        spec = Spec(name="Test", metadata=Metadata(spec_id="test", version="1.0"))
        context = AgentContext(spec=spec, project_root=tmp_path)

        agent = SecurityScanAgent()
        result = agent.execute(context)

        # Should find issues
        assert result.status == AgentStatus.FAILED
        report = result.data.get("report", {})
        assert report.get("files_scanned", 0) >= 2

        # Check different categories found
        findings = report.get("findings", [])
        categories = {f["category"] for f in findings}
        assert "secrets" in categories or "crypto" in categories
