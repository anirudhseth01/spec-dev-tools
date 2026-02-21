"""Test command for generating and running tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@click.group()
def test() -> None:
    """Test generation and execution commands."""
    pass


@test.command("generate")
@click.argument("spec_path")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option(
    "--framework",
    type=click.Choice(["pytest", "jest", "auto"]),
    default="auto",
    help="Test framework to use",
)
@click.option("--output-dir", help="Output directory for tests (default: tests/)")
@click.option("--dry-run", is_flag=True, help="Preview tests without writing files")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--coverage-target", type=int, default=80, help="Target code coverage percentage")
def generate(
    spec_path: str,
    specs_dir: str,
    project_dir: str,
    framework: str,
    output_dir: Optional[str],
    dry_run: bool,
    verbose: bool,
    coverage_target: int,
) -> None:
    """Generate tests from a specification.

    SPEC_PATH is the path to the specification (e.g., 'payment-gateway').

    This command generates:
    - Unit tests based on spec test cases
    - Integration tests for API endpoints
    - Edge case tests from spec edge cases

    Examples:
        spec-dev test generate payment-gateway
        spec-dev test generate auth/login --framework pytest
        spec-dev test generate api/users --dry-run
    """
    specs_path = Path(specs_dir)
    project_path = Path(project_dir)

    # Load specification
    spec = _load_spec(spec_path, specs_path)
    if not spec:
        console.print(f"[red]Error:[/red] Specification not found: {spec_path}")
        raise SystemExit(1)

    console.print(f"\n[bold]Generating tests for:[/bold] {spec.name}")

    # Detect or use specified framework
    if framework == "auto":
        framework = _detect_framework(project_path)
        console.print(f"  Detected framework: {framework}")
    else:
        console.print(f"  Framework: {framework}")

    if dry_run:
        console.print("[yellow]DRY RUN - No files will be written[/yellow]")

    # Get LLM client
    llm_client = _get_llm_client(verbose)

    # Import test generator
    try:
        from src.agents.testing import TestGeneratorAgent, TestGenerationConfig
    except ImportError as e:
        console.print(f"[red]Error:[/red] Could not import TestGeneratorAgent: {e}")
        raise SystemExit(1)

    # Create config
    # Note: TestGenerationConfig doesn't accept framework/coverage_target directly
    # framework is passed to the agent and handled by language-specific generators
    # coverage_target maps to include_coverage_targets (bool)
    config = TestGenerationConfig(
        include_coverage_targets=(coverage_target > 0),
    )

    # Create agent
    agent = TestGeneratorAgent(
        llm_client=llm_client,
        config=config,
        dry_run=dry_run,
    )

    # Get existing code files
    code_files = _get_code_files(project_path)
    console.print(f"  Code files found: {len(code_files)}")

    # Create context
    from src.agents.base import AgentContext
    context = AgentContext(
        spec=spec,
        project_root=project_path,
        dry_run=dry_run,
        verbose=verbose,
    )

    # Add code files to context
    context.parent_context["artifacts"] = {
        "code": {"value": code_files},
    }

    # Generate tests
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Generating tests...", total=None)
        result = agent.execute(context)
        progress.update(task, completed=True)

    # Display results
    if result.is_success:
        test_files = result.data.get("tests", {})
        test_count = result.data.get("test_count", 0)

        console.print(f"\n[green]Generated {len(test_files)} test file(s) with {test_count} test(s)[/green]")

        if test_files:
            console.print("\n[bold]Generated files:[/bold]")
            for filepath in test_files.keys():
                console.print(f"  - {filepath}")

        if verbose and test_files:
            console.print("\n[bold]Test file contents:[/bold]")
            for filepath, content in test_files.items():
                console.print(Panel(
                    content[:1000] + ("..." if len(content) > 1000 else ""),
                    title=filepath,
                    border_style="dim",
                ))

        if dry_run:
            console.print("\n[yellow]No files written (dry run)[/yellow]")
    else:
        console.print(f"\n[red]Test generation failed:[/red] {result.message}")
        if result.errors:
            for error in result.errors:
                console.print(f"  - {error}")
        raise SystemExit(1)


@test.command("run")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option(
    "--framework",
    type=click.Choice(["pytest", "jest", "auto"]),
    default="auto",
    help="Test framework to use",
)
@click.option("--coverage", is_flag=True, help="Generate coverage report")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--filter", "test_filter", help="Filter tests by pattern")
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
def run(
    project_dir: str,
    framework: str,
    coverage: bool,
    verbose: bool,
    test_filter: Optional[str],
    fail_fast: bool,
) -> None:
    """Run tests in the project.

    Examples:
        spec-dev test run
        spec-dev test run --coverage
        spec-dev test run --framework pytest --filter test_auth
        spec-dev test run --verbose --fail-fast
    """
    project_path = Path(project_dir)

    # Detect framework
    if framework == "auto":
        framework = _detect_framework(project_path)

    console.print(f"\n[bold]Running tests[/bold]")
    console.print(f"  Framework: {framework}")
    console.print(f"  Project: {project_path.absolute()}")

    # Build command
    if framework == "pytest":
        cmd = ["pytest"]
        if verbose:
            cmd.append("-v")
        if coverage:
            cmd.extend(["--cov", "--cov-report=term-missing"])
        if test_filter:
            cmd.extend(["-k", test_filter])
        if fail_fast:
            cmd.append("-x")
        cmd.append(str(project_path / "tests"))
    elif framework == "jest":
        cmd = ["npm", "test"]
        if verbose:
            cmd.append("--", "--verbose")
        if coverage:
            cmd.append("--coverage")
        if test_filter:
            cmd.extend(["--testNamePattern", test_filter])
        if fail_fast:
            cmd.append("--bail")
    else:
        console.print(f"[red]Error:[/red] Unsupported framework: {framework}")
        raise SystemExit(1)

    console.print(f"  Command: {' '.join(cmd)}")
    console.print()

    # Run tests
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_path),
            timeout=600,  # 10 minute timeout
        )

        if result.returncode == 0:
            console.print("\n[green]All tests passed![/green]")
        else:
            console.print(f"\n[red]Tests failed (exit code: {result.returncode})[/red]")
            raise SystemExit(result.returncode)

    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Test execution timed out (10 minutes)")
        raise SystemExit(1)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] Test runner not found: {e}")
        console.print(f"  Make sure {framework} is installed")
        raise SystemExit(1)


@test.command("list")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option(
    "--framework",
    type=click.Choice(["pytest", "jest", "auto"]),
    default="auto",
    help="Test framework to use",
)
def list_tests(project_dir: str, framework: str) -> None:
    """List available tests in the project.

    Example:
        spec-dev test list
        spec-dev test list --framework pytest
    """
    project_path = Path(project_dir)

    # Detect framework
    if framework == "auto":
        framework = _detect_framework(project_path)

    console.print(f"\n[bold]Test files ({framework}):[/bold]")

    # Find test files
    if framework == "pytest":
        patterns = ["**/test_*.py", "**/*_test.py"]
    elif framework == "jest":
        patterns = ["**/*.test.ts", "**/*.test.js", "**/*.spec.ts", "**/*.spec.js"]
    else:
        patterns = ["**/test_*", "**/*_test*", "**/*.test.*", "**/*.spec.*"]

    test_files = []
    for pattern in patterns:
        test_files.extend(project_path.glob(pattern))

    # Filter out node_modules, __pycache__, etc.
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv"}
    test_files = [
        f for f in test_files
        if not any(d in f.parts for d in skip_dirs)
    ]

    if test_files:
        table = Table(show_header=True)
        table.add_column("Test File")
        table.add_column("Tests")

        for test_file in sorted(test_files):
            rel_path = test_file.relative_to(project_path)
            test_count = _count_tests_in_file(test_file, framework)
            table.add_row(str(rel_path), str(test_count))

        console.print(table)
        console.print(f"\nTotal: {len(test_files)} test file(s)")
    else:
        console.print("[yellow]No test files found[/yellow]")


@test.command("coverage")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option(
    "--framework",
    type=click.Choice(["pytest", "jest", "auto"]),
    default="auto",
    help="Test framework to use",
)
@click.option("--min-coverage", type=int, default=80, help="Minimum required coverage")
def coverage(project_dir: str, framework: str, min_coverage: int) -> None:
    """Check test coverage.

    Example:
        spec-dev test coverage
        spec-dev test coverage --min-coverage 90
    """
    project_path = Path(project_dir)

    # Detect framework
    if framework == "auto":
        framework = _detect_framework(project_path)

    console.print(f"\n[bold]Checking test coverage[/bold]")
    console.print(f"  Minimum required: {min_coverage}%")

    # Build command
    if framework == "pytest":
        cmd = ["pytest", "--cov", "--cov-report=term-missing", "--cov-fail-under", str(min_coverage)]
    elif framework == "jest":
        cmd = ["npm", "test", "--", "--coverage", f"--coverageThreshold={{\"global\":{{\"lines\":{min_coverage}}}}}"]
    else:
        console.print(f"[red]Error:[/red] Unsupported framework: {framework}")
        raise SystemExit(1)

    console.print(f"  Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_path),
            timeout=600,
        )

        if result.returncode == 0:
            console.print(f"\n[green]Coverage meets minimum requirement ({min_coverage}%)[/green]")
        else:
            console.print(f"\n[red]Coverage below minimum requirement ({min_coverage}%)[/red]")
            raise SystemExit(result.returncode)

    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Test execution timed out")
        raise SystemExit(1)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] Test runner not found: {e}")
        raise SystemExit(1)


def _load_spec(spec_path: str, specs_path: Path):
    """Load specification."""
    try:
        # Check if it's a block spec
        block_path = specs_path / spec_path / "block.md"
        if block_path.exists():
            from src.spec.parser import BlockParser
            parser = BlockParser(specs_path)
            block = parser.parse_block(block_path)
            return block.spec
        else:
            from src.spec.parser import SpecParser
            parser = SpecParser(specs_path)
            return parser.parse_by_name(spec_path)
    except Exception:
        return None


def _detect_framework(project_path: Path) -> str:
    """Detect test framework from project."""
    # Check for pytest
    if (project_path / "pytest.ini").exists():
        return "pytest"
    if (project_path / "pyproject.toml").exists():
        try:
            content = (project_path / "pyproject.toml").read_text()
            if "pytest" in content:
                return "pytest"
        except Exception:
            pass

    # Check for jest
    if (project_path / "jest.config.js").exists() or (project_path / "jest.config.ts").exists():
        return "jest"

    # Check package.json
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            import json
            pkg = json.loads(package_json.read_text())
            if "jest" in pkg.get("devDependencies", {}) or "jest" in pkg.get("dependencies", {}):
                return "jest"
        except Exception:
            pass

    # Check for Python files
    if list(project_path.glob("**/*.py")):
        return "pytest"

    # Check for TypeScript/JavaScript files
    if list(project_path.glob("**/*.ts")) or list(project_path.glob("**/*.js")):
        return "jest"

    return "pytest"  # Default


def _get_llm_client(verbose: bool):
    """Get LLM client.

    Prefers Claude Code CLI (uses your existing authentication) over API.
    """
    try:
        from src.llm.client import get_llm_client
        client = get_llm_client(prefer_claude_code=True)
        if verbose:
            client_type = type(client).__name__
            console.print(f"[dim]Using {client_type} for test generation...[/dim]")
        return client
    except Exception as e:
        if verbose:
            console.print(f"[yellow]Warning:[/yellow] LLM not available: {e}")
            console.print("  Using template-based generation")
        return None


def _get_code_files(project_path: Path) -> dict[str, str]:
    """Get code files from project."""
    files = {}

    # Common code directories
    code_dirs = ["src", "lib", "app"]
    extensions = [".py", ".ts", ".js", ".tsx", ".jsx"]

    # Skip directories
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", "tests", "test"}

    for code_dir in code_dirs:
        dir_path = project_path / code_dir
        if dir_path.exists():
            for ext in extensions:
                for file_path in dir_path.rglob(f"*{ext}"):
                    if not any(d in file_path.parts for d in skip_dirs):
                        try:
                            rel_path = str(file_path.relative_to(project_path))
                            files[rel_path] = file_path.read_text()
                        except Exception:
                            pass

    return files


def _count_tests_in_file(file_path: Path, framework: str) -> int:
    """Count tests in a file."""
    import re

    try:
        content = file_path.read_text()
        count = 0

        if framework == "pytest":
            count = len(re.findall(r"def\s+test_", content))
        elif framework == "jest":
            count = len(re.findall(r"\bit\s*\(", content))
            count += len(re.findall(r"\btest\s*\(", content))

        return count
    except Exception:
        return 0
