"""CLI commands for Spec Builder Mode.

Provides interactive, AI-guided spec hierarchy design and implementation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.builder.session import (
    BuilderSession,
    SessionPhase,
    ResearchDepth,
    DISCUSSION_TOPICS,
)
from src.builder.persistence import SessionPersistence
from src.builder.discussion import DiscussionEngine, DiscussionAction
from src.builder.research import ResearchAgent
from src.builder.designer import BlockDesigner
from src.builder.generator import SpecGenerator
from src.builder.executor import ExecutionOrchestrator
from src.builder.dashboard import create_dashboard, ExecutionStatus, BlockStatus

console = Console()


@click.group()
def build() -> None:
    """Spec Builder Mode - Interactive system design and implementation.

    \b
    Three-phase workflow:
    1. Discussion - Interactive Q&A to gather requirements
    2. Review - Review and approve generated hierarchy
    3. Execution - Parallel build/test/deploy

    \b
    Getting started:
      spec-dev build ui                      # Launch web UI
      spec-dev build start --name "my-system"
      spec-dev build resume [session-id]
      spec-dev build list
    """
    pass


@build.command()
@click.option("--port", "-p", default=8501, help="Port to run the UI on")
@click.option("--project-dir", default=".", help="Project root directory")
def ui(port: int, project_dir: str) -> None:
    """Launch the Spec Builder web UI.

    Opens a Streamlit-based web interface for interactive system design.

    Example:
        spec-dev build ui
        spec-dev build ui --port 8080
    """
    import subprocess
    import sys
    from pathlib import Path

    # Get the path to the UI app
    ui_app_path = Path(__file__).parent.parent.parent / "ui" / "app.py"

    if not ui_app_path.exists():
        console.print(f"[red]UI app not found at:[/red] {ui_app_path}")
        raise SystemExit(1)

    console.print(f"\n[bold green]Launching Spec Builder UI...[/bold green]")
    console.print(f"  Port: {port}")
    console.print(f"  Project: {project_dir}")
    console.print(f"\n[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        # Launch streamlit
        subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ui_app_path),
                "--server.port",
                str(port),
                "--server.headless",
                "false",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=project_dir,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to start UI:[/red] {e}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]UI stopped.[/yellow]")


@build.command()
@click.option("--name", "-n", required=True, help="Name for the new system")
@click.option(
    "--research-depth",
    type=click.Choice(["light", "medium", "deep"]),
    default="medium",
    help="Depth of research for tech choices",
)
@click.option("--description", "-d", default="", help="Initial system description")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--specs-dir", default="specs", help="Specs directory")
def start(
    name: str,
    research_depth: str,
    description: str,
    project_dir: str,
    specs_dir: str,
) -> None:
    """Start a new builder session.

    Begins the interactive discussion phase to gather requirements
    and design the system architecture.

    Example:
        spec-dev build start --name "payment-system"
        spec-dev build start -n "auth-service" -d "User authentication service"
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    # Create new session
    session = BuilderSession(
        name=name,
        research_depth=ResearchDepth(research_depth),
        initial_description=description,
        project_root=str(project_path),
        specs_dir=specs_dir,
    )

    # Save session
    persistence.save(session)

    console.print(f"\n[bold green]Created builder session:[/bold green] {session.id}")
    console.print(f"  Name: {name}")
    console.print(f"  Research depth: {research_depth}")
    console.print(f"  Phase: {session.phase.value}")

    if description:
        console.print(f"  Description: {description}")

    console.print(f"\nSession saved. Resume with:")
    console.print(f"  [cyan]spec-dev build resume {session.id}[/cyan]")

    # Start discussion immediately
    if Confirm.ask("\nStart discussion now?", default=True):
        _run_discussion(session, persistence, project_path)


@build.command()
@click.argument("session_id", required=False)
@click.option("--project-dir", default=".", help="Project root directory")
def resume(session_id: Optional[str], project_dir: str) -> None:
    """Resume an existing builder session.

    If no session ID is provided, resumes the most recent session.

    Example:
        spec-dev build resume bs-abc123
        spec-dev build resume  # Resumes latest
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    if session_id:
        session = persistence.load(session_id)
        if not session:
            console.print(f"[red]Session not found:[/red] {session_id}")
            raise SystemExit(1)
    else:
        session = persistence.get_latest_session()
        if not session:
            console.print("[yellow]No sessions found.[/yellow]")
            console.print("Start a new session with: spec-dev build start --name <name>")
            raise SystemExit(1)

    console.print(f"\n[bold]Resuming session:[/bold] {session.id}")
    console.print(f"  Name: {session.name}")
    console.print(f"  Phase: {session.phase.value}")
    console.print(f"  Updated: {session.updated_at}")

    _handle_session_phase(session, persistence, project_path)


@build.command("list")
@click.option("--project-dir", default=".", help="Project root directory")
def list_sessions(project_dir: str) -> None:
    """List all builder sessions."""
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    sessions = persistence.list_sessions()

    if not sessions:
        console.print("[yellow]No builder sessions found.[/yellow]")
        console.print("Start a new session with: spec-dev build start --name <name>")
        return

    table = Table(title="Builder Sessions", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Phase")
    table.add_column("Updated")

    for s in sessions:
        phase_style = {
            "discussion": "yellow",
            "design": "blue",
            "review": "magenta",
            "execution": "cyan",
            "completed": "green",
            "paused": "red",
        }.get(s["phase"], "white")

        table.add_row(
            s["id"],
            s["name"],
            f"[{phase_style}]{s['phase']}[/{phase_style}]",
            s["updated_at"][:19] if s["updated_at"] else "-",
        )

    console.print(table)


@build.command()
@click.argument("session_id")
@click.option("--project-dir", default=".", help="Project root directory")
def status(session_id: str, project_dir: str) -> None:
    """Show detailed status of a session."""
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    session = persistence.load(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    _display_session_status(session)


@build.command()
@click.argument("session_id")
@click.option("--project-dir", default=".", help="Project root directory")
def approve(session_id: str, project_dir: str) -> None:
    """Approve the hierarchy design and proceed to execution.

    Reviews the generated hierarchy and, upon approval, generates
    spec files and prepares for execution.
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    session = persistence.load(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    if session.phase not in [SessionPhase.REVIEW, SessionPhase.DESIGN]:
        console.print(
            f"[yellow]Session is in {session.phase.value} phase, not ready for approval.[/yellow]"
        )
        raise SystemExit(1)

    if not session.hierarchy_design:
        console.print("[red]No hierarchy design found. Complete the discussion first.[/red]")
        raise SystemExit(1)

    # Show hierarchy for review
    _display_hierarchy(session)

    if not Confirm.ask("\nApprove this design and generate specs?", default=True):
        console.print("[yellow]Approval cancelled.[/yellow]")
        return

    # Generate specs
    console.print("\n[bold]Generating specifications...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating specs...", total=None)

        generator = SpecGenerator()
        specs = asyncio.run(
            generator.generate_all_specs(session.hierarchy_design, session)
        )

        # Write specs to disk
        created_files = asyncio.run(generator.write_specs(specs, project_path))

        progress.update(task, completed=True)

    console.print(f"\n[green]Generated {len(specs)} spec files:[/green]")
    for f in created_files[:10]:
        console.print(f"  - {f}")
    if len(created_files) > 10:
        console.print(f"  ... and {len(created_files) - 10} more")

    # Transition to ready for execution
    session.transition_to(SessionPhase.EXECUTION)
    persistence.save(session)

    console.print(f"\n[bold green]Design approved![/bold green]")
    console.print(f"Execute with: spec-dev build execute {session.id}")


@build.command()
@click.argument("session_id")
@click.option("--dry-run", is_flag=True, help="Preview without writing files")
@click.option("--skip-tests", is_flag=True, help="Skip test generation")
@click.option("--project-dir", default=".", help="Project root directory")
def execute(
    session_id: str,
    dry_run: bool,
    skip_tests: bool,
    project_dir: str,
) -> None:
    """Execute the implementation for all blocks.

    Runs the coding, testing, and security agents for each block
    in the hierarchy, respecting dependencies.

    Example:
        spec-dev build execute bs-abc123
        spec-dev build execute bs-abc123 --dry-run
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    session = persistence.load(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    if not session.hierarchy_design:
        console.print("[red]No hierarchy design found.[/red]")
        raise SystemExit(1)

    # Check if specs exist
    specs_dir = project_path / session.specs_dir
    if not specs_dir.exists():
        console.print(f"[red]Specs directory not found:[/red] {specs_dir}")
        console.print("Run 'spec-dev build approve' first to generate specs.")
        raise SystemExit(1)

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be written[/yellow]")

    # Get LLM client
    llm_client = _get_llm_client()

    # Create orchestrator
    orchestrator = ExecutionOrchestrator(
        session=session,
        project_root=project_path,
        llm_client=llm_client,
    )

    # Create dashboard
    dashboard = create_dashboard()

    # Set up callbacks
    execution_status = ExecutionStatus(
        total_blocks=len(session.hierarchy_design.blocks),
        blocks=[
            BlockStatus(path=b.path, name=b.name)
            for b in session.hierarchy_design.blocks
        ],
    )

    def on_block_start(block_path: str) -> None:
        for b in execution_status.blocks:
            if b.path == block_path:
                b.status = "running"
                break
        dashboard.update(execution_status)

    def on_block_complete(block_path: str, result) -> None:
        for b in execution_status.blocks:
            if b.path == block_path:
                b.status = "completed" if result.success else "failed"
                b.message = result.message
                if result.success:
                    execution_status.completed_blocks += 1
                else:
                    execution_status.failed_blocks += 1
                break
        dashboard.update(execution_status)

    orchestrator.set_callbacks(
        on_block_start=on_block_start,
        on_block_complete=on_block_complete,
    )

    # Execute
    console.print("\n[bold]Starting execution...[/bold]\n")
    dashboard.start()

    try:
        result = asyncio.run(orchestrator.execute(dry_run=dry_run))
    finally:
        dashboard.stop()

    # Save session
    persistence.save(session)

    # Display results
    console.print("\n" + "=" * 60)
    if result.success:
        console.print("[bold green]Execution completed successfully![/bold green]")
    else:
        console.print("[bold red]Execution completed with errors[/bold red]")

    console.print(f"  Total blocks: {result.total_blocks}")
    console.print(f"  Successful: {result.successful_blocks}")
    console.print(f"  Failed: {result.failed_blocks}")
    console.print(f"  Duration: {result.total_duration_seconds:.1f}s")

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for error in result.errors[:5]:
            console.print(f"  - {error}")


@build.command()
@click.argument("session_id")
@click.option("--force", is_flag=True, help="Delete without confirmation")
@click.option("--project-dir", default=".", help="Project root directory")
def delete(session_id: str, force: bool, project_dir: str) -> None:
    """Delete a builder session."""
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    if not persistence.exists(session_id):
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    if not force:
        if not Confirm.ask(f"Delete session {session_id}?", default=False):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    persistence.delete(session_id)
    console.print(f"[green]Deleted session:[/green] {session_id}")


@build.command("analyze-repo")
@click.argument("session_id")
@click.argument("repo_url")
@click.option("--project-dir", default=".", help="Project root directory")
def analyze_repo(session_id: str, repo_url: str, project_dir: str) -> None:
    """Analyze a GitHub repository for reusable patterns.

    Analyzes the given GitHub repository to find architecture patterns,
    reusable components, and code that could be adapted for your project.

    Example:
        spec-dev build analyze-repo bs-abc123 https://github.com/fastapi/fastapi
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    session = persistence.load(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    # Note: We use llm_client=None for repo analysis to keep it fast
    # The basic analysis still provides repo metadata and key files
    research_agent = ResearchAgent(None, session.research_depth)
    engine = DiscussionEngine(session, None, research_agent)

    console.print(f"\n[bold]Analyzing repository:[/bold] {repo_url}")
    console.print("[dim]Fetching repository data...[/dim]")

    result = asyncio.run(engine.add_reference_repo(repo_url))

    console.print("[dim]Analysis complete.[/dim]")

    # Display results
    if result.action == DiscussionAction.ANALYZE_REPO:
        console.print(Panel(
            result.message,
            title=f"Repository Analysis",
            border_style="green",
        ))

        if result.repo_analysis:
            components = result.repo_analysis.get("reusable_components", [])
            if components:
                console.print(f"\n[bold]Found {len(components)} reusable components.[/bold]")
                console.print("These will be considered when generating specs.")
    else:
        console.print(f"[yellow]{result.message}[/yellow]")

    # Save session
    persistence.save(session)

    console.print(f"\n[green]Repository added to session.[/green]")
    console.print(f"Total reference repos: {len(session.reference_repos)}")


@build.command("list-repos")
@click.argument("session_id")
@click.option("--project-dir", default=".", help="Project root directory")
def list_repos(session_id: str, project_dir: str) -> None:
    """List reference repositories for a session.

    Example:
        spec-dev build list-repos bs-abc123
    """
    project_path = Path(project_dir)
    persistence = SessionPersistence(project_path)

    session = persistence.load(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise SystemExit(1)

    if not session.reference_repos:
        console.print("[yellow]No reference repositories added yet.[/yellow]")
        console.print(f"\nAdd one with: spec-dev build analyze-repo {session_id} <github-url>")
        return

    table = Table(title="Reference Repositories", show_header=True)
    table.add_column("Repository")
    table.add_column("Language")
    table.add_column("Components")
    table.add_column("Patterns")

    for repo in session.reference_repos:
        components = repo.get("reusable_components", [])
        patterns = repo.get("architecture_patterns", [])
        table.add_row(
            repo.get("repo_name", "Unknown"),
            repo.get("primary_language", "-"),
            str(len(components)),
            ", ".join(patterns[:2]) if patterns else "-",
        )

    console.print(table)

    # Show component details
    for repo in session.reference_repos:
        components = repo.get("reusable_components", [])
        if components:
            console.print(f"\n[bold]{repo.get('repo_name', 'Unknown')}[/bold] components:")
            for comp in components[:5]:
                score = comp.get("relevance_score", 0)
                score_style = "green" if score > 0.7 else "yellow" if score > 0.4 else "dim"
                console.print(
                    f"  - [{score_style}]{comp.get('name', 'Unknown')}[/{score_style}] "
                    f"({comp.get('component_type', '-')}): {comp.get('description', '')[:50]}"
                )


def _run_discussion(
    session: BuilderSession,
    persistence: SessionPersistence,
    project_path: Path,
) -> None:
    """Run the interactive discussion phase."""
    llm_client = _get_llm_client()
    research_agent = ResearchAgent(llm_client, session.research_depth)
    engine = DiscussionEngine(session, llm_client, research_agent)

    console.print("\n" + "=" * 60)
    console.print("[bold]Interactive Design Session[/bold]")
    console.print("=" * 60)
    console.print("\nI'll ask you questions about your system design.")
    console.print("Type your answer, select an option number, or type 'quit' to pause.")
    console.print("[dim]Tip: Type 'repo <url>' to analyze a GitHub repo for patterns.[/dim]\n")

    # Get initial question
    question = asyncio.run(engine.start_discussion())
    console.print(question)

    while not engine.is_complete():
        try:
            response = Prompt.ask("\n[bold]Your answer[/bold]")

            if response.lower() in ["quit", "exit", "q"]:
                console.print("\n[yellow]Session paused.[/yellow]")
                session.transition_to(SessionPhase.PAUSED)
                persistence.save(session)
                console.print(f"Resume with: spec-dev build resume {session.id}")
                return

            # Check for repo command
            if response.lower().startswith("repo "):
                repo_url = response[5:].strip()
                if repo_url:
                    console.print(f"\n[bold]Analyzing repository:[/bold] {repo_url}")
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Fetching repository...", total=None)
                        repo_result = asyncio.run(engine.add_reference_repo(repo_url))
                        progress.update(task, completed=True)

                    if repo_result.action == DiscussionAction.ANALYZE_REPO:
                        console.print(Panel(repo_result.message, border_style="green"))
                    else:
                        console.print(f"[yellow]{repo_result.message}[/yellow]")
                    persistence.save(session)
                    continue
                else:
                    console.print("[yellow]Usage: repo <github-url>[/yellow]")
                    continue

            # Process response
            result = asyncio.run(engine.process_response(response))

            # Save after each decision
            persistence.save(session)

            if result.action == DiscussionAction.COMPLETE:
                console.print(f"\n[green]{result.message}[/green]")
                break
            elif result.action == DiscussionAction.CLARIFY:
                console.print(f"\n[yellow]{result.message}[/yellow]")
                continue
            elif result.action == DiscussionAction.NEXT_TOPIC:
                console.print(f"\n[dim]{result.message}[/dim]")

            if result.question:
                console.print(
                    _format_question_display(
                        session.current_topic["name"] if session.current_topic else "",
                        result.question,
                        result.options,
                    )
                )

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Session paused.[/yellow]")
            session.transition_to(SessionPhase.PAUSED)
            persistence.save(session)
            return

    # Discussion complete, move to design phase
    console.print("\n[bold]Designing block hierarchy...[/bold]")

    designer = BlockDesigner(llm_client)
    hierarchy = asyncio.run(designer.design_hierarchy(session))
    session.hierarchy_design = hierarchy
    session.transition_to(SessionPhase.REVIEW)
    persistence.save(session)

    _display_hierarchy(session)

    console.print(f"\n[green]Design complete![/green]")
    console.print(f"Approve with: spec-dev build approve {session.id}")


def _handle_session_phase(
    session: BuilderSession,
    persistence: SessionPersistence,
    project_path: Path,
) -> None:
    """Handle resumption based on session phase."""
    if session.phase in [SessionPhase.DISCUSSION, SessionPhase.PAUSED]:
        if session.phase == SessionPhase.PAUSED:
            session.transition_to(SessionPhase.DISCUSSION)
        _run_discussion(session, persistence, project_path)

    elif session.phase == SessionPhase.DESIGN:
        console.print("\nDesigning hierarchy...")
        llm_client = _get_llm_client()
        designer = BlockDesigner(llm_client)
        hierarchy = asyncio.run(designer.design_hierarchy(session))
        session.hierarchy_design = hierarchy
        session.transition_to(SessionPhase.REVIEW)
        persistence.save(session)
        _display_hierarchy(session)

    elif session.phase == SessionPhase.REVIEW:
        _display_hierarchy(session)
        console.print(f"\nApprove with: spec-dev build approve {session.id}")

    elif session.phase == SessionPhase.EXECUTION:
        console.print("\nSession is ready for execution.")
        console.print(f"Execute with: spec-dev build execute {session.id}")

    elif session.phase == SessionPhase.COMPLETED:
        console.print("\n[green]Session is complete.[/green]")
        _display_session_status(session)


def _display_session_status(session: BuilderSession) -> None:
    """Display detailed session status."""
    console.print(Panel(
        f"[bold]{session.name}[/bold]\n\n"
        f"ID: {session.id}\n"
        f"Phase: {session.phase.value}\n"
        f"Created: {session.created_at}\n"
        f"Updated: {session.updated_at}\n"
        f"Research depth: {session.research_depth.value}",
        title="Session Status",
    ))

    # Show decisions
    if session.decisions:
        table = Table(title="Decisions", show_header=True)
        table.add_column("Topic")
        table.add_column("Choice")
        table.add_column("Notes")

        for d in session.decisions:
            if d.is_decided:
                opt = d.selected_option
                choice = opt.label if opt else d.user_notes
                notes = d.user_notes if opt else ""
                table.add_row(d.topic, choice, notes[:30])

        console.print(table)

    # Show reference repos if any
    if session.reference_repos:
        console.print(f"\n[bold]Reference Repos:[/bold] {len(session.reference_repos)}")
        for repo in session.reference_repos:
            components = repo.get("reusable_components", [])
            console.print(
                f"  - {repo.get('repo_name', 'Unknown')} "
                f"({repo.get('primary_language', '-')}) - "
                f"{len(components)} components"
            )

    # Show hierarchy if available
    if session.hierarchy_design:
        console.print(f"\n[bold]Hierarchy:[/bold] {len(session.hierarchy_design.blocks)} blocks")
        for block in session.hierarchy_design.blocks[:5]:
            indent = "  " * block.path.count("/")
            console.print(f"  {indent}{block.name} ({block.block_type})")

    # Show execution progress if applicable
    if session.execution_progress.total_blocks > 0:
        prog = session.execution_progress
        console.print(
            f"\n[bold]Execution:[/bold] {prog.completed_blocks}/{prog.total_blocks} blocks"
        )


def _display_hierarchy(session: BuilderSession) -> None:
    """Display the hierarchy design."""
    if not session.hierarchy_design:
        console.print("[yellow]No hierarchy design.[/yellow]")
        return

    hierarchy = session.hierarchy_design

    console.print(Panel(
        f"[bold]Root:[/bold] {hierarchy.root_name}\n"
        f"[bold]Blocks:[/bold] {len(hierarchy.blocks)}",
        title="Hierarchy Design",
    ))

    # Build tree display
    table = Table(show_header=True)
    table.add_column("Block")
    table.add_column("Type")
    table.add_column("Description")

    for block in hierarchy.blocks:
        depth = block.path.count("/")
        indent = "  " * depth + ("├─ " if depth > 0 else "")
        name = f"{indent}{block.name}"

        type_style = {
            "root": "bold cyan",
            "component": "green",
            "module": "yellow",
            "leaf": "dim",
        }.get(block.block_type, "white")

        table.add_row(
            name,
            f"[{type_style}]{block.block_type}[/{type_style}]",
            block.description[:40] + "..." if len(block.description) > 40 else block.description,
        )

    console.print(table)


def _format_question_display(topic: str, question: str, options: list) -> str:
    """Format a question for display."""
    lines = [f"\n## {topic}\n", question, "\nOptions:"]
    for i, opt in enumerate(options, 1):
        lines.append(f"\n{i}. [bold]{opt.label}[/bold]")
        lines.append(f"   {opt.description}")
        if opt.pros:
            lines.append(f"   [green]+ {', '.join(opt.pros)}[/green]")
        if opt.cons:
            lines.append(f"   [red]- {', '.join(opt.cons)}[/red]")
    return "\n".join(lines)


def _get_llm_client():
    """Get the LLM client."""
    try:
        from src.llm.client import get_llm_client
        return get_llm_client(prefer_claude_code=True)
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not initialize LLM: {e}")
        return None
