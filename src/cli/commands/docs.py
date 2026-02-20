"""Documentation generation CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command("docs")
@click.argument("spec_name")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--output-dir", "-o", default="docs", help="Output directory")
@click.option("--format", "-f", "formats", multiple=True,
              type=click.Choice(["readme", "api", "openapi", "architecture", "all"]),
              default=["all"], help="Documentation formats to generate")
@click.option("--dry-run", is_flag=True, help="Show what would be generated")
def docs_command(spec_name: str, specs_dir: str, output_dir: str, formats: tuple, dry_run: bool):
    """Generate documentation from a specification.

    Examples:

        spec-dev docs my-feature

        spec-dev docs my-api --format api --format openapi

        spec-dev docs my-feature -o docs/generated
    """
    from src.agents.docs import DocsGeneratorAgent, DocFormat

    specs_path = Path(specs_dir)
    output_path = Path(output_dir)

    # Find spec file
    spec_file = specs_path / spec_name / "block.md"
    if not spec_file.exists():
        spec_file = specs_path / f"{spec_name}.md"

    if not spec_file.exists():
        console.print(f"[red]Spec not found: {spec_name}[/red]")
        return

    content = spec_file.read_text()

    # Generate docs
    agent = DocsGeneratorAgent(output_dir=output_path)
    result = agent.generate_docs(content, spec_name)

    if not result.success:
        console.print("[red]Documentation generation failed:[/red]")
        for error in result.errors:
            console.print(f"  - {error}")
        return

    # Filter by requested formats
    if "all" not in formats:
        format_map = {
            "readme": "README.md",
            "api": "api.md",
            "openapi": "openapi.json",
            "architecture": "architecture.md",
        }
        result.docs = [d for d in result.docs if any(
            format_map.get(f) == d.filename for f in formats
        )]

    if dry_run:
        console.print(f"[bold]Would generate {len(result.docs)} files:[/bold]")
        for doc in result.docs:
            console.print(f"  - {output_dir}/{doc.filename} ({doc.format.value})")
        return

    # Write files
    written = agent.write_docs(result, output_path / spec_name)

    console.print(f"[green]Generated {len(written)} documentation files:[/green]")
    for path in written:
        console.print(f"  - {path}")
