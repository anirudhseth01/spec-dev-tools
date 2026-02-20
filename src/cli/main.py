"""Main CLI entry point for spec-dev-tools."""

import click

from src.cli.commands.init import init
from src.cli.commands.validate import validate
from src.cli.commands.list_specs import list_specs
from src.cli.commands.status import status
from src.cli.commands.block import block
from src.cli.commands.rules import rules
from src.cli.commands.implement import implement
from src.cli.commands.security import security
from src.cli.commands.test import test
from src.cli.commands.review import review

# New commands
from src.cli.commands.version import version_group
from src.cli.commands.diff import diff_command
from src.cli.commands.lint import lint_command, lint_rules_command
from src.cli.commands.templates import template_group
from src.cli.commands.docs import docs_command
from src.cli.commands.graph import graph_command, validate_cross_command
from src.cli.commands.coverage import coverage_group


@click.group()
@click.version_option(version="0.2.0")
def cli() -> None:
    """Spec Dev Tools - Specification-Driven Development CLI.

    A tool for managing and implementing feature specifications
    using a hierarchical block structure with validation rules.

    \b
    GETTING STARTED:
      spec-dev init my-feature           Initialize a new specification
      spec-dev template create api-service my-api  Create from template
      spec-dev validate my-feature       Validate a specification
      spec-dev implement my-feature      Run the full implementation pipeline

    \b
    AGENT COMMANDS:
      spec-dev implement <spec>          Run full pipeline (code -> security -> tests -> review)
      spec-dev implement <spec> --incremental  Only regenerate changed sections
      spec-dev implement <spec> --create-pr    Create GitHub PR with generated code
      spec-dev security scan [path]      Run security scan
      spec-dev test generate <spec>      Generate tests from spec
      spec-dev review <path>             Review code against spec
      spec-dev docs <spec>               Generate documentation from spec

    \b
    SPEC MANAGEMENT:
      spec-dev list                      List all specifications
      spec-dev block tree                Show block hierarchy
      spec-dev version list <spec>       List spec versions
      spec-dev diff <old> <new>          Compare specs or versions

    \b
    VALIDATION:
      spec-dev lint <spec>               Check spec style and consistency
      spec-dev validate-cross            Validate cross-block interfaces
      spec-dev rules list                List validation rules
      spec-dev coverage analyze <spec>   Check implementation coverage

    \b
    VISUALIZATION:
      spec-dev graph                     Show dependency graph
      spec-dev coverage report           Generate coverage report
    """
    pass


# Register individual commands
cli.add_command(init)
cli.add_command(validate)
cli.add_command(list_specs)
cli.add_command(status)
cli.add_command(implement)
cli.add_command(review)

# Register command groups
cli.add_command(block)
cli.add_command(rules)
cli.add_command(security)
cli.add_command(test)

# New commands
cli.add_command(version_group, name="version")
cli.add_command(diff_command, name="diff")
cli.add_command(lint_command, name="lint")
cli.add_command(lint_rules_command, name="lint-rules")
cli.add_command(template_group, name="template")
cli.add_command(docs_command, name="docs")
cli.add_command(graph_command, name="graph")
cli.add_command(validate_cross_command, name="validate-cross")
cli.add_command(coverage_group, name="coverage")


if __name__ == "__main__":
    cli()
