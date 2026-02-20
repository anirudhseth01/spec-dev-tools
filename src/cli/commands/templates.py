"""Template CLI commands."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("template")
def template_group():
    """Spec template commands."""
    pass


@template_group.command("list")
def list_templates():
    """List available spec templates."""
    from src.spec.templates import TemplateRegistry

    registry = TemplateRegistry()
    templates = registry.list()

    table = Table(title="Available Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="blue")
    table.add_column("Description")
    table.add_column("Variables")

    for t in templates:
        var_names = [v["name"] for v in t["variables"]]
        table.add_row(
            t["name"],
            t["category"],
            t["description"],
            ", ".join(var_names),
        )

    console.print(table)


@template_group.command("show")
@click.argument("template_name")
def show_template(template_name: str):
    """Show template details and variables."""
    from src.spec.templates import TemplateRegistry

    registry = TemplateRegistry()
    template = registry.get(template_name)

    if not template:
        console.print(f"[red]Template not found: {template_name}[/red]")
        console.print("Use 'spec-dev template list' to see available templates")
        return

    console.print(f"[bold]{template.name}[/bold]")
    console.print(f"[dim]{template.description}[/dim]")
    console.print(f"Category: {template.category}")
    console.print()

    if template.variables:
        console.print("[bold]Variables:[/bold]")
        for var in template.variables:
            required = "[red]*[/red]" if var.required else ""
            default = f" (default: {var.default})" if var.default else ""
            console.print(f"  {required}{var.name}: {var.description}{default}")


@template_group.command("create")
@click.argument("template_name")
@click.argument("spec_name")
@click.option("--var", "-v", multiple=True, help="Variable value (name=value)")
@click.option("--specs-dir", default="specs", help="Specs directory")
@click.option("--dry-run", is_flag=True, help="Show what would be created")
def create_from_template(template_name: str, spec_name: str, var: tuple, specs_dir: str, dry_run: bool):
    """Create a spec from a template.

    Examples:

        spec-dev template create api-service my-api --var name=my-api --var resource=user

        spec-dev template create cli-tool my-tool -v name=my-tool -v description="My CLI tool"
    """
    from src.spec.templates import TemplateRegistry

    registry = TemplateRegistry()
    template = registry.get(template_name)

    if not template:
        console.print(f"[red]Template not found: {template_name}[/red]")
        return

    # Parse variables
    variables = {"name": spec_name}
    for v in var:
        if "=" not in v:
            console.print(f"[red]Invalid variable format: {v} (use name=value)[/red]")
            return
        name, value = v.split("=", 1)
        variables[name] = value

    # Check required variables
    for tv in template.variables:
        if tv.required and tv.name not in variables and not tv.default:
            console.print(f"[red]Missing required variable: {tv.name}[/red]")
            return

    # Render template
    content = template.render(variables)

    if dry_run:
        console.print(f"[bold]Would create: {specs_dir}/{spec_name}/block.md[/bold]")
        console.print()
        console.print(content[:500] + "..." if len(content) > 500 else content)
        return

    # Create spec directory and file
    specs_path = Path(specs_dir)
    spec_dir = specs_path / spec_name
    spec_dir.mkdir(parents=True, exist_ok=True)

    spec_file = spec_dir / "block.md"
    spec_file.write_text(content)

    console.print(f"[green]Created: {spec_file}[/green]")
