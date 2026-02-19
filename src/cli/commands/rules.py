"""Rules management commands."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from src.spec.parser import BlockParser
from src.rules.engine import RulesEngine, load_rules_from_yaml, save_rules_to_yaml
from src.rules.schemas import Rule, RuleCategory, RuleLevel, RuleSeverity

console = Console()


@click.group()
def rules() -> None:
    """Rules management commands."""
    pass


@rules.command("list")
@click.option(
    "--level",
    type=click.Choice(["global", "scoped", "all"]),
    default="all",
    help="Filter by rule level",
)
@click.option("--project-dir", default=".", help="Project root directory")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
def list_rules(level: str, project_dir: str, specs_dir: str) -> None:
    """List available rules."""
    project_path = Path(project_dir)
    specs_path = Path(specs_dir)

    all_rules: list[tuple[str, Rule]] = []

    # Load global rules
    if level in ("global", "all"):
        engine = RulesEngine(project_path)
        for rule in engine.global_rules:
            all_rules.append(("global", rule))

    # Load scoped rules from blocks
    if level in ("scoped", "all"):
        parser = BlockParser(specs_path)
        blocks = parser.parse_hierarchy()
        for block in blocks:
            for rule in block.scoped_rules:
                all_rules.append((f"scoped:{block.path}", rule))

    if not all_rules:
        console.print("[yellow]No rules found[/yellow]")
        return

    # Display rules
    table = Table(show_header=True, title="Rules")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Level")
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Sections")
    table.add_column("Enabled")

    for source, rule in all_rules:
        severity_style = {
            "error": "red",
            "warning": "yellow",
            "info": "blue",
        }.get(rule.severity.value, "white")

        table.add_row(
            rule.id,
            rule.name,
            source,
            rule.category.value,
            f"[{severity_style}]{rule.severity.value}[/{severity_style}]",
            ", ".join(rule.applies_to_sections[:3]) + ("..." if len(rule.applies_to_sections) > 3 else ""),
            "[green]yes[/green]" if rule.enabled else "[red]no[/red]",
        )

    console.print(table)


@rules.command("check")
@click.argument("block_path")
@click.option("--specs-dir", default="specs", help="Directory for specifications")
@click.option("--project-dir", default=".", help="Project root directory")
def check_rules(block_path: str, specs_dir: str, project_dir: str) -> None:
    """Check rules for a block specification.

    BLOCK_PATH is the path to the block to check.
    """
    project_path = Path(project_dir)
    specs_path = Path(specs_dir)
    block_file = specs_path / block_path / "block.md"

    if not block_file.exists():
        console.print(f"[red]Error:[/red] Block not found at '{block_path}'")
        raise SystemExit(1)

    # Parse block
    parser = BlockParser(specs_path)
    block = parser.parse_block(block_file)

    # Validate
    engine = RulesEngine(project_path)
    violations = engine.validate(block)

    if not violations:
        console.print(f"[green]No rule violations for '{block_path}'[/green]")
        return

    # Display violations
    table = Table(show_header=True, title=f"Rule Violations: {block_path}")
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("Section")
    table.add_column("Message")

    for v in violations:
        severity_style = {
            "error": "red",
            "warning": "yellow",
            "info": "blue",
        }.get(v.rule.severity.value, "white")

        table.add_row(
            f"[{severity_style}]{v.rule.severity.value.upper()}[/{severity_style}]",
            f"{v.rule.id}: {v.rule.name}",
            v.section,
            v.message,
        )

    console.print(table)

    # Summary
    errors = sum(1 for v in violations if v.rule.severity == RuleSeverity.ERROR)
    warnings = sum(1 for v in violations if v.rule.severity == RuleSeverity.WARNING)
    infos = sum(1 for v in violations if v.rule.severity == RuleSeverity.INFO)

    console.print(f"\n[bold]Summary:[/bold] {errors} error(s), {warnings} warning(s), {infos} info(s)")

    if errors > 0:
        raise SystemExit(1)


@rules.command("add-global")
@click.argument("rule_id")
@click.argument("name")
@click.option(
    "--category",
    type=click.Choice(["security", "testing", "api", "performance", "documentation", "code_quality"]),
    default="code_quality",
    help="Rule category",
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default="warning",
    help="Rule severity",
)
@click.option("--sections", default="all", help="Comma-separated list of sections")
@click.option("--validator", default="", help="Validator function name")
@click.option("--description", default="", help="Rule description")
@click.option("--project-dir", default=".", help="Project root directory")
def add_global_rule(
    rule_id: str,
    name: str,
    category: str,
    severity: str,
    sections: str,
    validator: str,
    description: str,
    project_dir: str,
) -> None:
    """Add a new global rule.

    RULE_ID is the unique identifier for the rule (e.g., SEC-001).
    NAME is the human-readable name for the rule.
    """
    project_path = Path(project_dir)
    rules_file = project_path / ".spec-dev" / "global-rules.yaml"

    # Load existing rules
    existing_rules = load_rules_from_yaml(rules_file) if rules_file.exists() else []

    # Check for duplicate ID
    if any(r.id == rule_id for r in existing_rules):
        console.print(f"[red]Error:[/red] Rule with ID '{rule_id}' already exists")
        raise SystemExit(1)

    # Create new rule
    new_rule = Rule(
        id=rule_id,
        name=name,
        level=RuleLevel.GLOBAL,
        category=RuleCategory(category),
        severity=RuleSeverity(severity),
        applies_to_sections=[s.strip() for s in sections.split(",") if s.strip()],
        validation_fn=validator,
        description=description,
        enabled=True,
    )

    # Add and save
    existing_rules.append(new_rule)
    save_rules_to_yaml(existing_rules, rules_file)

    console.print(f"[green]Added global rule:[/green] {rule_id} - {name}")


@rules.command("enable")
@click.argument("rule_id")
@click.option("--project-dir", default=".", help="Project root directory")
def enable_rule(rule_id: str, project_dir: str) -> None:
    """Enable a global rule.

    RULE_ID is the identifier of the rule to enable.
    """
    _toggle_rule(rule_id, project_dir, enabled=True)


@rules.command("disable")
@click.argument("rule_id")
@click.option("--project-dir", default=".", help="Project root directory")
def disable_rule(rule_id: str, project_dir: str) -> None:
    """Disable a global rule.

    RULE_ID is the identifier of the rule to disable.
    """
    _toggle_rule(rule_id, project_dir, enabled=False)


def _toggle_rule(rule_id: str, project_dir: str, enabled: bool) -> None:
    """Toggle a rule's enabled state."""
    project_path = Path(project_dir)
    rules_file = project_path / ".spec-dev" / "global-rules.yaml"

    if not rules_file.exists():
        console.print("[red]Error:[/red] No global rules file found")
        raise SystemExit(1)

    rules = load_rules_from_yaml(rules_file)

    found = False
    for rule in rules:
        if rule.id == rule_id:
            rule.enabled = enabled
            found = True
            break

    if not found:
        console.print(f"[red]Error:[/red] Rule '{rule_id}' not found")
        raise SystemExit(1)

    save_rules_to_yaml(rules, rules_file)

    action = "enabled" if enabled else "disabled"
    console.print(f"[green]Rule '{rule_id}' {action}[/green]")
