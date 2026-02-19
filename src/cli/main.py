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


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Spec Dev Tools - Specification-Driven Development CLI.

    A tool for managing and implementing feature specifications
    using a hierarchical block structure with validation rules.

    \b
    GETTING STARTED:
      spec-dev init my-feature           Initialize a new specification
      spec-dev validate my-feature       Validate a specification
      spec-dev implement my-feature      Run the full implementation pipeline

    \b
    AGENT COMMANDS:
      spec-dev implement <spec>          Run full pipeline (code -> security -> tests -> review)
      spec-dev security scan [path]      Run security scan
      spec-dev test generate <spec>      Generate tests from spec
      spec-dev test run                  Run project tests
      spec-dev review <path>             Review code against spec

    \b
    MANAGEMENT:
      spec-dev list                      List all specifications
      spec-dev block tree                Show block hierarchy
      spec-dev rules list                List validation rules
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


if __name__ == "__main__":
    cli()
