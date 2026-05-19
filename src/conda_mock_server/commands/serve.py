from pathlib import Path

import click
from werkzeug.serving import make_server

from conda_mock_server.core.server import create_app


@click.command("serve")
@click.option(
    "--port",
    default=8080,
    show_default=True,
    help="Port to listen on. Use 0 to let the OS assign a free port.",
)
@click.option(
    "--host", default="127.0.0.1", show_default=True, help="Host to bind to."
)
@click.option(
    "--root-dir",
    envvar="CONDA_MOCK_SERVER_ROOT_DIR",
    default=None,
    help="Root directory of the indexed conda channel to serve.",
)
def serve_command(port: int, host: str, root_dir: str | None) -> None:
    """Serve the mock conda channel over HTTP."""
    if root_dir is None:
        raise click.ClickException(
            "No channel directory specified. "
            "Use --root-dir or set CONDA_MOCK_SERVER_ROOT_DIR."
        )

    data_root = Path(root_dir)

    if not data_root.exists():
        click.echo(
            f"Warning: channel directory '{data_root}' does not exist. "
            "Run 'cms download' first.",
            err=True,
        )
    elif not any(data_root.iterdir()):
        click.echo(
            f"Warning: channel directory '{data_root}' is empty. "
            "Run 'cms download' first.",
            err=True,
        )

    app = create_app(data_root)
    server = make_server(host, port, app)
    actual_port = server.socket.getsockname()[1]
    click.echo(f"conda mock server running at http://{host}:{actual_port}/")
    click.echo("Press Ctrl+C to stop.")
    server.serve_forever()
