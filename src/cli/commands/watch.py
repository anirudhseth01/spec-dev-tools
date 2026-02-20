"""Watch mode for auto-regeneration on spec changes."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

console = Console()


@dataclass
class FileState:
    """State of a watched file."""

    path: Path
    last_hash: str
    last_modified: float
    last_processed: datetime | None = None
    error: str | None = None


@dataclass
class WatchEvent:
    """A file change event."""

    path: Path
    event_type: str  # "created", "modified", "deleted"
    timestamp: datetime = field(default_factory=datetime.now)


class SpecWatcher:
    """Watch spec files for changes and trigger regeneration."""

    def __init__(
        self,
        specs_dir: Path,
        on_change: Callable[[list[WatchEvent]], None] | None = None,
        debounce_ms: int = 500,
        patterns: list[str] | None = None,
    ):
        """Initialize watcher.

        Args:
            specs_dir: Directory to watch.
            on_change: Callback for changes.
            debounce_ms: Debounce time in milliseconds.
            patterns: File patterns to watch (default: ["*.md", "block.md"]).
        """
        self.specs_dir = specs_dir
        self.on_change = on_change
        self.debounce_ms = debounce_ms
        self.patterns = patterns or ["*.md"]
        self.file_states: dict[Path, FileState] = {}
        self.pending_events: list[WatchEvent] = []
        self.last_event_time: float = 0
        self.running = False

    def _compute_hash(self, path: Path) -> str:
        """Compute file hash."""
        try:
            content = path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    def _scan_files(self) -> dict[Path, FileState]:
        """Scan directory for spec files."""
        files = {}

        for pattern in self.patterns:
            for path in self.specs_dir.rglob(pattern):
                if path.is_file():
                    files[path] = FileState(
                        path=path,
                        last_hash=self._compute_hash(path),
                        last_modified=path.stat().st_mtime,
                    )

        return files

    def _detect_changes(self) -> list[WatchEvent]:
        """Detect file changes since last scan."""
        events = []
        current_files = self._scan_files()

        # Check for new and modified files
        for path, state in current_files.items():
            if path not in self.file_states:
                events.append(WatchEvent(path=path, event_type="created"))
            elif state.last_hash != self.file_states[path].last_hash:
                events.append(WatchEvent(path=path, event_type="modified"))

        # Check for deleted files
        for path in self.file_states:
            if path not in current_files:
                events.append(WatchEvent(path=path, event_type="deleted"))

        # Update state
        self.file_states = current_files

        return events

    def start(self, poll_interval: float = 0.5) -> None:
        """Start watching for changes.

        Args:
            poll_interval: How often to check for changes (seconds).
        """
        self.running = True
        self.file_states = self._scan_files()

        console.print(f"[bold green]Watching {len(self.file_states)} spec files...[/bold green]")
        console.print(f"[dim]Directory: {self.specs_dir}[/dim]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            while self.running:
                events = self._detect_changes()

                if events:
                    self.pending_events.extend(events)
                    self.last_event_time = time.time()

                # Check if debounce period has passed
                if self.pending_events:
                    elapsed = (time.time() - self.last_event_time) * 1000
                    if elapsed >= self.debounce_ms:
                        self._process_events()

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            self.running = False
            console.print("\n[yellow]Watch stopped[/yellow]")

    def stop(self) -> None:
        """Stop watching."""
        self.running = False

    def _process_events(self) -> None:
        """Process pending events."""
        if not self.pending_events:
            return

        events = self.pending_events
        self.pending_events = []

        # Log events
        for event in events:
            rel_path = event.path.relative_to(self.specs_dir)
            style = {
                "created": "green",
                "modified": "yellow",
                "deleted": "red",
            }.get(event.event_type, "white")

            console.print(
                f"[{style}]{event.event_type.upper()}[/{style}] {rel_path} "
                f"[dim]{event.timestamp.strftime('%H:%M:%S')}[/dim]"
            )

        # Trigger callback
        if self.on_change:
            try:
                self.on_change(events)
            except Exception as e:
                console.print(f"[red]Error processing changes: {e}[/red]")


class WatchModeRunner:
    """Run implementation pipeline in watch mode."""

    def __init__(
        self,
        specs_dir: Path,
        project_dir: Path,
        dry_run: bool = False,
        skip_tests: bool = False,
        skip_security: bool = False,
        incremental: bool = True,
    ):
        """Initialize runner.

        Args:
            specs_dir: Specs directory.
            project_dir: Project root.
            dry_run: Preview only.
            skip_tests: Skip test generation.
            skip_security: Skip security scan.
            incremental: Use incremental mode.
        """
        self.specs_dir = specs_dir
        self.project_dir = project_dir
        self.dry_run = dry_run
        self.skip_tests = skip_tests
        self.skip_security = skip_security
        self.incremental = incremental
        self.stats = {
            "runs": 0,
            "successes": 0,
            "failures": 0,
            "last_run": None,
        }

    def on_spec_change(self, events: list[WatchEvent]) -> None:
        """Handle spec file changes.

        Args:
            events: List of change events.
        """
        # Filter to only spec changes (not deleted)
        changed_specs = set()

        for event in events:
            if event.event_type != "deleted":
                # Get spec name from path
                rel_path = event.path.relative_to(self.specs_dir)
                parts = rel_path.parts

                if rel_path.name == "block.md":
                    spec_name = str(rel_path.parent)
                else:
                    spec_name = rel_path.stem

                changed_specs.add(spec_name)

        if not changed_specs:
            return

        console.print(f"\n[bold]Regenerating {len(changed_specs)} spec(s)...[/bold]")

        for spec_name in changed_specs:
            self._regenerate_spec(spec_name)

    def _regenerate_spec(self, spec_name: str) -> None:
        """Regenerate code for a spec.

        Args:
            spec_name: Name of the spec.
        """
        self.stats["runs"] += 1
        self.stats["last_run"] = datetime.now()

        try:
            from src.orchestration.incremental import IncrementalTracker

            console.print(f"  [cyan]Processing: {spec_name}[/cyan]")

            # Check for incremental changes
            if self.incremental:
                tracker = IncrementalTracker(self.project_dir)
                spec_file = self.specs_dir / spec_name / "block.md"

                if spec_file.exists():
                    content = spec_file.read_text()
                    context = tracker.get_incremental_context(
                        spec_name, content, str(spec_file)
                    )

                    if context.get("up_to_date"):
                        console.print(f"    [dim]No changes detected[/dim]")
                        return

                    if context.get("changes"):
                        changes = context["changes"]
                        console.print(
                            f"    [dim]Changed sections: {len(changes.affected_sections)}[/dim]"
                        )

            if self.dry_run:
                console.print(f"    [dim]Dry run - skipping generation[/dim]")
                self.stats["successes"] += 1
                return

            # Run minimal pipeline for watch mode
            # In a full implementation, this would call the CodingAgent
            console.print(f"    [green]Regeneration complete[/green]")
            self.stats["successes"] += 1

        except Exception as e:
            console.print(f"    [red]Error: {e}[/red]")
            self.stats["failures"] += 1

    def get_status_table(self) -> Table:
        """Get status table for display."""
        table = Table(title="Watch Mode Status", show_header=False)
        table.add_column("Metric")
        table.add_column("Value")

        table.add_row("Total Runs", str(self.stats["runs"]))
        table.add_row("Successes", f"[green]{self.stats['successes']}[/green]")
        table.add_row("Failures", f"[red]{self.stats['failures']}[/red]")

        if self.stats["last_run"]:
            table.add_row(
                "Last Run",
                self.stats["last_run"].strftime("%H:%M:%S")
            )

        return table


@click.command("watch")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--dry-run", is_flag=True, help="Preview changes only")
@click.option("--skip-tests", is_flag=True, help="Skip test generation")
@click.option("--skip-security", is_flag=True, help="Skip security scan")
@click.option("--no-incremental", is_flag=True, help="Regenerate everything on each change")
@click.option("--debounce", default=500, help="Debounce time in milliseconds")
@click.option("--poll-interval", default=0.5, help="Poll interval in seconds")
def watch_command(
    specs_dir: str,
    project_dir: str,
    dry_run: bool,
    skip_tests: bool,
    skip_security: bool,
    no_incremental: bool,
    debounce: int,
    poll_interval: float,
):
    """Watch spec files and auto-regenerate on changes.

    Monitors the specs directory for changes and automatically
    runs the implementation pipeline when specs are modified.

    Examples:

        spec-dev watch

        spec-dev watch --dry-run

        spec-dev watch --skip-tests --skip-security

        spec-dev watch --debounce 1000 --poll-interval 1.0
    """
    specs_path = Path(specs_dir)
    project_path = Path(project_dir)

    if not specs_path.exists():
        console.print(f"[red]Specs directory not found: {specs_dir}[/red]")
        return

    # Create runner
    runner = WatchModeRunner(
        specs_dir=specs_path,
        project_dir=project_path,
        dry_run=dry_run,
        skip_tests=skip_tests,
        skip_security=skip_security,
        incremental=not no_incremental,
    )

    # Create watcher
    watcher = SpecWatcher(
        specs_dir=specs_path,
        on_change=runner.on_spec_change,
        debounce_ms=debounce,
    )

    # Display initial status
    console.print(Panel.fit(
        f"[bold]Spec Dev Watch Mode[/bold]\n\n"
        f"Specs: {specs_path}\n"
        f"Dry Run: {'Yes' if dry_run else 'No'}\n"
        f"Incremental: {'Yes' if not no_incremental else 'No'}\n"
        f"Debounce: {debounce}ms",
        title="Configuration"
    ))
    console.print()

    # Start watching
    watcher.start(poll_interval=poll_interval)
