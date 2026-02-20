"""Spec diff CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command("diff")
@click.argument("old_spec")
@click.argument("new_spec")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--version", "-v", is_flag=True, help="Compare versions instead of files")
@click.option("--unified", "-u", is_flag=True, help="Show unified diff")
@click.option("--no-color", is_flag=True, help="Disable colors")
def diff_command(old_spec: str, new_spec: str, specs_dir: str, version: bool, unified: bool, no_color: bool):
    """Compare two specs or spec versions.

    Examples:

        spec-dev diff spec-v1.md spec-v2.md

        spec-dev diff my-spec@1.0.0 my-spec@2.0.0 --version
    """
    from src.spec.diff import SpecDiffer, format_diff_for_terminal

    differ = SpecDiffer()
    specs_path = Path(specs_dir)

    if version:
        # Compare versions
        if "@" not in old_spec or "@" not in new_spec:
            console.print("[red]Version format: spec-name@version[/red]")
            return

        old_name, old_version = old_spec.rsplit("@", 1)
        new_name, new_version = new_spec.rsplit("@", 1)

        if old_name != new_name:
            console.print("[red]Can only compare versions of the same spec[/red]")
            return

        try:
            diff = differ.diff_versions(specs_path, old_name, old_version, new_version)
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return
    else:
        # Compare files
        old_path = Path(old_spec)
        new_path = Path(new_spec)

        # Try relative to specs dir if not found
        if not old_path.exists():
            old_path = specs_path / old_spec / "block.md"
        if not new_path.exists():
            new_path = specs_path / new_spec / "block.md"

        if not old_path.exists():
            console.print(f"[red]File not found: {old_spec}[/red]")
            return
        if not new_path.exists():
            console.print(f"[red]File not found: {new_spec}[/red]")
            return

        diff = differ.diff_files(old_path, new_path)

    # Output
    if not diff.has_changes:
        console.print("[green]No differences found[/green]")
        return

    if unified:
        console.print(diff.unified_diff)
    else:
        output = format_diff_for_terminal(diff, color=not no_color)
        console.print(output)
