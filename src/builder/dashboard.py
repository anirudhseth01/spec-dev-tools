"""Live dashboard for execution progress display.

The LiveDashboard provides a Rich-based live display of execution
progress with progress bars, status indicators, and timing information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class BlockStatus:
    """Status of a single block during execution."""

    path: str
    name: str
    status: str = "pending"  # pending, running, completed, failed
    progress: float = 0.0  # 0-100
    message: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    blocked_by: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Get execution duration if available."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None


@dataclass
class ExecutionStatus:
    """Overall execution status for dashboard display."""

    total_blocks: int = 0
    completed_blocks: int = 0
    failed_blocks: int = 0
    blocks: list[BlockStatus] = field(default_factory=list)
    current_level: int = 0
    started_at: datetime | None = None
    total_tests_passed: int = 0
    total_tests_failed: int = 0

    @property
    def elapsed_time(self) -> str:
        """Get formatted elapsed time."""
        if not self.started_at:
            return "0s"
        elapsed = (datetime.now() - self.started_at).total_seconds()
        minutes, seconds = divmod(int(elapsed), 60)
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @property
    def progress_percent(self) -> float:
        """Get overall progress percentage."""
        if self.total_blocks == 0:
            return 0.0
        return (self.completed_blocks / self.total_blocks) * 100

    def get_blocks_by_status(self, status: str) -> list[BlockStatus]:
        """Get blocks with a specific status."""
        return [b for b in self.blocks if b.status == status]


class LiveDashboard:
    """Rich-based live dashboard for execution progress.

    Displays:
    - Overall progress bar
    - Per-block status with progress indicators
    - Timing information
    - Error summaries
    """

    def __init__(self):
        """Initialize the dashboard."""
        self._live: Live | None = None
        self._console = Console() if RICH_AVAILABLE else None
        self._status = ExecutionStatus()

    def start(self) -> None:
        """Start the live display."""
        if not RICH_AVAILABLE:
            print("Starting execution (Rich not available for live display)...")
            return

        self._status.started_at = datetime.now()
        self._live = Live(
            self._render(self._status),
            console=self._console,
            refresh_per_second=4,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()
            self._live = None

    def update(self, status: ExecutionStatus) -> None:
        """Update the display with new status.

        Args:
            status: Current execution status.
        """
        self._status = status
        if not self._status.started_at:
            self._status.started_at = datetime.now()

        if self._live:
            self._live.update(self._render(status))
        else:
            # Fallback to simple print
            self._print_status(status)

    def _render(self, status: ExecutionStatus) -> Panel:
        """Render the dashboard panel.

        Args:
            status: Current execution status.

        Returns:
            Rich Panel for display.
        """
        # Create main table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Content", ratio=1)

        # Progress section
        progress_text = self._render_progress_section(status)
        table.add_row(progress_text)
        table.add_row("")

        # Block status section
        blocks_text = self._render_blocks_section(status)
        table.add_row(blocks_text)

        # Stats section
        stats_text = self._render_stats_section(status)
        table.add_row("")
        table.add_row(stats_text)

        return Panel(
            table,
            title="[bold blue]Execution Progress[/bold blue]",
            border_style="blue",
        )

    def _render_progress_section(self, status: ExecutionStatus) -> Text:
        """Render the overall progress section."""
        text = Text()

        # Progress bar
        progress = status.progress_percent
        bar_width = 40
        filled = int(bar_width * progress / 100)
        empty = bar_width - filled

        text.append("  Overall: ")
        text.append("[" + "=" * filled + " " * empty + "]", style="cyan")
        text.append(f" {progress:.0f}%")
        text.append(f"  ({status.completed_blocks}/{status.total_blocks} blocks)")

        return text

    def _render_blocks_section(self, status: ExecutionStatus) -> Table:
        """Render the blocks status section."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Status", width=3)
        table.add_column("Block", width=30)
        table.add_column("Progress", width=20)
        table.add_column("Info", width=30)

        # Group blocks by status for display
        running = [b for b in status.blocks if b.status == "running"]
        pending = [b for b in status.blocks if b.status == "pending"]
        completed = [b for b in status.blocks if b.status == "completed"]
        failed = [b for b in status.blocks if b.status == "failed"]

        # Show running blocks first
        for block in running:
            progress_bar = self._render_block_progress(block.progress)
            duration = self._format_duration(block.duration_seconds)
            table.add_row(
                "[yellow]>[/yellow]",
                f"[yellow]{block.name}[/yellow]",
                progress_bar,
                f"[dim]{block.message or duration}[/dim]",
            )

        # Show pending blocks with blockers
        for block in pending[:3]:  # Limit pending display
            if block.blocked_by:
                info = f"Blocked by: {', '.join(block.blocked_by)}"
            else:
                info = "Waiting..."
            table.add_row(
                "[dim]○[/dim]",
                f"[dim]{block.name}[/dim]",
                "",
                f"[dim]{info}[/dim]",
            )

        if len(pending) > 3:
            table.add_row("", f"[dim]... and {len(pending) - 3} more[/dim]", "", "")

        # Show completed blocks (last few)
        for block in completed[-2:]:
            duration = self._format_duration(block.duration_seconds)
            table.add_row(
                "[green]✓[/green]",
                f"[green]{block.name}[/green]",
                "[green]Complete[/green]",
                f"[dim]({duration})[/dim]",
            )

        # Show failed blocks
        for block in failed:
            table.add_row(
                "[red]✗[/red]",
                f"[red]{block.name}[/red]",
                "[red]Failed[/red]",
                f"[red]{block.message}[/red]",
            )

        return table

    def _render_stats_section(self, status: ExecutionStatus) -> Text:
        """Render the statistics section."""
        text = Text()

        text.append(f"  Elapsed: {status.elapsed_time}", style="dim")
        text.append("  │  ", style="dim")
        text.append(f"Blocks: {status.completed_blocks}/{status.total_blocks}", style="dim")

        if status.total_tests_passed > 0 or status.total_tests_failed > 0:
            text.append("  │  ", style="dim")
            if status.total_tests_failed > 0:
                text.append(
                    f"Tests: {status.total_tests_passed}/{status.total_tests_passed + status.total_tests_failed}",
                    style="yellow",
                )
            else:
                text.append(f"Tests: {status.total_tests_passed} ✓", style="green")

        if status.failed_blocks > 0:
            text.append("  │  ", style="dim")
            text.append(f"Failed: {status.failed_blocks}", style="red")

        return text

    def _render_block_progress(self, progress: float) -> str:
        """Render a small progress bar for a block."""
        bar_width = 12
        filled = int(bar_width * progress / 100)
        empty = bar_width - filled
        return f"[cyan][{'█' * filled}{'░' * empty}][/cyan] {progress:.0f}%"

    def _format_duration(self, seconds: float | None) -> str:
        """Format duration in human readable form."""
        if seconds is None:
            return ""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}m {secs}s"

    def _print_status(self, status: ExecutionStatus) -> None:
        """Print status without Rich (fallback)."""
        print(f"\n--- Execution Progress ---")
        print(f"Progress: {status.completed_blocks}/{status.total_blocks} blocks")
        print(f"Elapsed: {status.elapsed_time}")

        running = [b for b in status.blocks if b.status == "running"]
        if running:
            print(f"Running: {', '.join(b.name for b in running)}")

        failed = [b for b in status.blocks if b.status == "failed"]
        if failed:
            print(f"Failed: {', '.join(b.name for b in failed)}")


class SimpleDashboard:
    """Simple non-interactive dashboard for environments without Rich."""

    def __init__(self):
        """Initialize simple dashboard."""
        self._last_update = datetime.now()
        self._status: ExecutionStatus | None = None

    def start(self) -> None:
        """Start tracking."""
        print("\n=== Starting Execution ===\n")

    def stop(self) -> None:
        """Stop tracking."""
        if self._status:
            print(f"\n=== Execution Complete ===")
            print(f"Total: {self._status.completed_blocks}/{self._status.total_blocks} blocks")
            if self._status.failed_blocks > 0:
                print(f"Failed: {self._status.failed_blocks} blocks")

    def update(self, status: ExecutionStatus) -> None:
        """Update with new status."""
        self._status = status

        # Only print updates every second
        now = datetime.now()
        if (now - self._last_update).total_seconds() < 1:
            return
        self._last_update = now

        running = [b for b in status.blocks if b.status == "running"]
        if running:
            names = ", ".join(b.name for b in running[:3])
            if len(running) > 3:
                names += f" +{len(running) - 3}"
            print(f"Running: {names} ({status.completed_blocks}/{status.total_blocks})")


def create_dashboard() -> LiveDashboard | SimpleDashboard:
    """Create the appropriate dashboard based on environment.

    Returns:
        LiveDashboard if Rich is available, SimpleDashboard otherwise.
    """
    if RICH_AVAILABLE:
        return LiveDashboard()
    return SimpleDashboard()
