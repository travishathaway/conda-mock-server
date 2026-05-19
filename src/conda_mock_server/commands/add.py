import click

from conda_mock_server.core import manifest

DEFAULT_CHANNELS = ("conda-forge",)
DEFAULT_PLATFORMS = ("linux-64", "win-64", "osx-arm64", "linux-aarch64")


@click.command("add")
@click.argument("specs", nargs=-1, required=True)
@click.option(
    "--channel",
    "channels",
    multiple=True,
    default=DEFAULT_CHANNELS,
    show_default=True,
    help="Channel to add (may be repeated). Defaults to conda-forge.",
)
@click.option(
    "--platform",
    "platforms",
    multiple=True,
    default=DEFAULT_PLATFORMS,
    show_default=True,
    help="Platform subdir to include (may be repeated).",
)
@click.option(
    "--config",
    envvar="CONDA_MOCK_SERVER_MANIFEST",
    default=None,
    help="Path to manifest.json.",
)
def add_command(
    specs: tuple[str, ...],
    channels: tuple[str, ...],
    platforms: tuple[str, ...],
    config: str | None,
) -> None:
    """Add a dependency group to the manifest."""
    channels_list = list(channels)
    specs_list = list(specs)
    platforms_list = list(platforms)

    data = manifest.load_manifest(config)
    dep_groups = data["dep_groups"]

    if manifest.find_group(dep_groups, channels_list, specs_list, platforms_list):
        raise click.ClickException(
            "An identical dependency group (same specs, channels, and platforms) "
            "already exists in the manifest."
        )

    group = {
        "channels": channels_list,
        "specs": specs_list,
        "platforms": platforms_list,
    }
    dep_groups.append(group)
    manifest.save_manifest(data, config)

    click.echo(f"Added dependency group (index {len(dep_groups) - 1}):")
    click.echo(f"  specs:     {', '.join(specs_list)}")
    click.echo(f"  channels:  {', '.join(channels_list)}")
    click.echo(f"  platforms: {', '.join(platforms_list)}")
