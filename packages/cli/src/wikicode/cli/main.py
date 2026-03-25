"""WikiCode CLI — Click group and command registration."""

from __future__ import annotations

import click

from wikicode.cli import __version__
from wikicode.cli.commands.dead_code_cmd import dead_code_command
from wikicode.cli.commands.decision_cmd import decision_group
from wikicode.cli.commands.doctor_cmd import doctor_command
from wikicode.cli.commands.export_cmd import export_command
from wikicode.cli.commands.init_cmd import init_command
from wikicode.cli.commands.mcp_cmd import mcp_command
from wikicode.cli.commands.reindex_cmd import reindex_command
from wikicode.cli.commands.search_cmd import search_command
from wikicode.cli.commands.serve_cmd import serve_command
from wikicode.cli.commands.status_cmd import status_command
from wikicode.cli.commands.update_cmd import update_command
from wikicode.cli.commands.watch_cmd import watch_command


@click.group()
@click.version_option(version=__version__, prog_name="wikicode")
def cli() -> None:
    """WikiCode -- AI-powered codebase documentation engine."""


cli.add_command(init_command)
cli.add_command(update_command)
cli.add_command(dead_code_command)
cli.add_command(decision_group)
cli.add_command(search_command)
cli.add_command(export_command)
cli.add_command(status_command)
cli.add_command(doctor_command)
cli.add_command(watch_command)
cli.add_command(serve_command)
cli.add_command(mcp_command)
cli.add_command(reindex_command)
