"""Version management CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("version")
def version_group():
    """Spec version management commands."""
    pass


@version_group.command("list")
@click.argument("spec_name")
@click.option("--specs-dir", default="specs", help="Specs directory")
def list_versions(spec_name: str, specs_dir: str):
    """List all versions of a specification."""
    from src.spec.versioning import SpecVersionManager

    specs_path = Path(specs_dir)
    manager = SpecVersionManager(specs_path)

    versions = manager.list_versions(spec_name)

    if not versions:
        console.print(f"[yellow]No versions found for {spec_name}[/yellow]")
        return

    table = Table(title=f"Versions: {spec_name}")
    table.add_column("Version", style="cyan")
    table.add_column("Schema", style="blue")
    table.add_column("Created", style="green")
    table.add_column("Hash", style="dim")

    for v in versions:
        table.add_row(
            v["spec_version"],
            v["schema_version"],
            v["created_at"][:10],
            v["content_hash"][:8],
        )

    console.print(table)


@version_group.command("save")
@click.argument("spec_name")
@click.argument("version")
@click.option("--message", "-m", default="", help="Version message")
@click.option("--specs-dir", default="specs", help="Specs directory")
def save_version(spec_name: str, version: str, message: str, specs_dir: str):
    """Save current spec as a new version."""
    from src.spec.versioning import SpecVersionManager

    specs_path = Path(specs_dir)
    manager = SpecVersionManager(specs_path)

    # Find spec file
    spec_file = specs_path / spec_name / "block.md"
    if not spec_file.exists():
        spec_file = specs_path / f"{spec_name}.md"

    if not spec_file.exists():
        console.print(f"[red]Spec not found: {spec_name}[/red]")
        return

    content = spec_file.read_text()
    version_info = manager.save_version(spec_name, content, version, message)

    console.print(f"[green]Saved version {version} for {spec_name}[/green]")
    console.print(f"  Schema: {version_info.schema_version.value}")
    console.print(f"  Hash: {version_info.content_hash}")


@version_group.command("show")
@click.argument("spec_name")
@click.argument("version")
@click.option("--specs-dir", default="specs", help="Specs directory")
def show_version(spec_name: str, version: str, specs_dir: str):
    """Show content of a specific version."""
    from src.spec.versioning import SpecVersionManager

    specs_path = Path(specs_dir)
    manager = SpecVersionManager(specs_path)

    content = manager.get_version(spec_name, version)

    if content is None:
        console.print(f"[red]Version {version} not found for {spec_name}[/red]")
        return

    console.print(content)


@version_group.command("migrate")
@click.argument("spec_name")
@click.option("--to-version", default=None, help="Target schema version")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated")
def migrate_spec(spec_name: str, to_version: str | None, specs_dir: str, dry_run: bool):
    """Migrate spec to newer schema version."""
    from src.spec.versioning import SpecVersionManager, SchemaVersion

    specs_path = Path(specs_dir)
    manager = SpecVersionManager(specs_path)

    # Find spec file
    spec_file = specs_path / spec_name / "block.md"
    if not spec_file.exists():
        spec_file = specs_path / f"{spec_name}.md"

    if not spec_file.exists():
        console.print(f"[red]Spec not found: {spec_name}[/red]")
        return

    content = spec_file.read_text()
    current_version = manager.detect_schema_version(content)

    target_version = SchemaVersion.from_string(to_version) if to_version else SchemaVersion.latest()

    if current_version == target_version:
        console.print(f"[green]Spec is already at schema version {target_version.value}[/green]")
        return

    console.print(f"Migrating from {current_version.value} to {target_version.value}")

    # This would need spec parsing to dict - simplified for now
    if dry_run:
        migrations = manager.get_migration_path(current_version, target_version)
        console.print("\n[bold]Migration steps:[/bold]")
        for m in migrations:
            console.print(f"  - {m.description}")
    else:
        console.print("[yellow]Migration requires manual review for markdown specs[/yellow]")
        console.print("Use spec-dev diff to compare versions after editing")
