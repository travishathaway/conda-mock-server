import click

from conda_mock_server.core import manifest


@click.command("remove")
@click.argument("index", type=int)
@click.option(
    "--config",
    envvar="CONDA_MOCK_SERVER_MANIFEST",
    default=None,
    help="Path to manifest.json.",
)
def remove_command(index: int, config: str | None) -> None:
    """Remove a dependency group from the manifest by index (0-based)."""
    data = manifest.load_manifest(config)
    dep_groups = data["dep_groups"]

    if not dep_groups:
        raise click.ClickException("No dependency groups in manifest.")

    if index < 0 or index >= len(dep_groups):
        raise click.ClickException(
            f"Index {index} is out of range. "
            f"Valid indices are 0–{len(dep_groups) - 1}."
        )

    group = dep_groups[index]
    click.echo(f"Removing dependency group at index {index}:")
    click.echo(f"  specs:     {', '.join(group.get('specs', []))}")
    click.echo(f"  channels:  {', '.join(group.get('channels', []))}")
    click.echo(f"  platforms: {', '.join(group.get('platforms', []))}")

    dep_groups.pop(index)
    manifest.save_manifest(data, config)

    click.echo("Removed. Run 'cms download' to refresh the channel data.")
