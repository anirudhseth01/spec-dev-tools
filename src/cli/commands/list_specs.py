"""List specs command for displaying available specifications."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from src.spec.parser import SpecParser, BlockParser

console = Console()


@click.command("list")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--blocks/--no-blocks", default=False, help="List block specifications")
@click.option("--all", "show_all", is_flag=True, help="Show all specs (features and blocks)")
def list_specs(specs_dir: str, blocks: bool, show_all: bool) -> None:
    """List available specifications."""
    specs_path = Path(specs_dir)

    if not specs_path.exists():
        console.print(f"[yellow]No specifications directory found at '{specs_dir}'[/yellow]")
        return

    if blocks or show_all:
        _list_blocks(specs_path)

    if not blocks or show_all:
        _list_feature_specs(specs_path)


def _list_feature_specs(specs_path: Path) -> None:
    """List feature specifications."""
    parser = SpecParser(specs_path)
    specs = parser.list_specs()

    if not specs:
        console.print("[yellow]No feature specifications found[/yellow]")
        return

    console.print("\n[bold]Feature Specifications:[/bold]")
    table = Table(show_header=True)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Version")

    for spec_name in specs:
        try:
            spec = parser.parse_by_name(spec_name)
            table.add_row(
                spec_name,
                spec.metadata.status.value,
                spec.metadata.version,
            )
        except Exception:
            table.add_row(spec_name, "[red]parse error[/red]", "-")

    console.print(table)


def _list_blocks(specs_path: Path) -> None:
    """List block specifications."""
    parser = BlockParser(specs_path)
    block_paths = parser.discover_blocks()

    if not block_paths:
        console.print("[yellow]No block specifications found[/yellow]")
        return

    console.print("\n[bold]Block Specifications:[/bold]")
    table = Table(show_header=True)
    table.add_column("Path")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Children")

    for block_path in block_paths:
        try:
            block = parser.parse_block(block_path)
            # Count children (directories with block.md)
            children_count = sum(
                1 for p in block.directory.iterdir()
                if p.is_dir() and (p / "block.md").exists()
            )
            table.add_row(
                block.path,
                block.block_type.value,
                block.spec.metadata.status.value,
                str(children_count) if children_count > 0 else "-",
            )
        except Exception as e:
            rel_path = str(block_path.parent.relative_to(specs_path))
            table.add_row(rel_path, "-", f"[red]error: {e}[/red]", "-")

    console.print(table)
