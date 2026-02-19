"""Main CLI entry point for spec-dev-tools."""

import click

from src.cli.commands.init import init
from src.cli.commands.validate import validate
from src.cli.commands.list_specs import list_specs
from src.cli.commands.status import status
from src.cli.commands.block import block
from src.cli.commands.rules import rules


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """Spec Dev Tools - Specification-Driven Development CLI.

    A tool for managing and implementing feature specifications
    using a hierarchical block structure with validation rules.
    """
    pass


# Register commands
cli.add_command(init)
cli.add_command(validate)
cli.add_command(list_specs)
cli.add_command(status)
cli.add_command(block)
cli.add_command(rules)


if __name__ == "__main__":
    cli()
