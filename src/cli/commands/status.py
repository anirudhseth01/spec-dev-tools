"""Status command for checking specification status."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from src.spec.parser import SpecParser

console = Console()


@click.command()
@click.argument("name")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
def status(name: str, specs_dir: str) -> None:
    """Check the status of a specification.

    NAME is the name of the specification to check.
    """
    parser = SpecParser(specs_dir)

    try:
        spec = parser.parse_by_name(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Specification '{name}' not found")
        raise SystemExit(1)

    # Build status display
    status_text = f"""
[bold]Specification:[/bold] {spec.name}
[bold]ID:[/bold] {spec.metadata.spec_id}
[bold]Version:[/bold] {spec.metadata.version}
[bold]Status:[/bold] {spec.metadata.status.value}
[bold]Author:[/bold] {spec.metadata.author or 'N/A'}

[bold]Overview:[/bold]
{spec.overview.summary or 'No summary provided'}

[bold]Goals:[/bold] {len(spec.overview.goals)} defined
[bold]Test Cases:[/bold] {len(spec.test_cases.unit_tests)} unit, {len(spec.test_cases.integration_tests)} integration
[bold]API Endpoints:[/bold] {len(spec.api_contract.endpoints)}
"""

    console.print(Panel(status_text.strip(), title=f"Status: {name}"))
