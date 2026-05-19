import asyncio
from pathlib import Path

import click

from conda_mock_server.core import manifest


@click.command("download")
@click.option(
    "-d",
    "--directory",
    default=None,
    help="Directory to write the channel data to (default: current directory).",
)
@click.option(
    "--config",
    envvar="CONDA_MOCK_SERVER_MANIFEST",
    default=None,
    help="Path to manifest.json.",
)
def download_command(directory: str | None, config: str | None) -> None:
    """Resolve and download all dependency groups, then index the channel."""
    from conda_mock_server.core.conda import run_conda_index, solve_and_download
    data = manifest.load_manifest(config)
    dep_groups = data["dep_groups"]

    if not dep_groups:
        raise click.ClickException(
            "No dependency groups in manifest. Run 'cms add <spec>...' first."
        )

    channel_dir = Path(directory) if directory is not None else Path(".")
    channel_dir.mkdir(parents=True, exist_ok=True)

    for i, group in enumerate(dep_groups):
        specs_str = ", ".join(group["specs"])
        plat_count = len(group["platforms"])
        click.echo(
            f"\n[group {i}] solving: {specs_str} "
            f"({plat_count} platform{'s' if plat_count != 1 else ''})"
        )
        count = asyncio.run(solve_and_download(group, channel_dir))
        click.echo(f"  downloaded {count} package(s)")

    click.echo("\nIndexing channel...")
    run_conda_index(channel_dir)
    click.echo(f"Channel ready at: {channel_dir.resolve()}")
