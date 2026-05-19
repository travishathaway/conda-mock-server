import click

from conda_mock_server.commands.add import add_command
from conda_mock_server.commands.download import download_command
from conda_mock_server.commands.remove import remove_command
from conda_mock_server.commands.serve import serve_command
from conda_mock_server import __version__


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """conda-mock-server: serve a local conda channel for testing."""


cli.add_command(add_command)
cli.add_command(remove_command)
cli.add_command(download_command)
cli.add_command(serve_command)


def main() -> None:
    cli()
