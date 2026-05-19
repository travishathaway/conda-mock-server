import json
from pathlib import Path


def get_manifest_path(config: str | None = None) -> Path:
    if config is not None:
        return Path(config)
    return Path(".") / "manifest.json"


def load_manifest(config: str | None = None) -> dict:
    path = get_manifest_path(config)
    if not path.exists():
        return {"dep_groups": []}
    return json.loads(path.read_text())


def save_manifest(data: dict, config: str | None = None) -> None:
    path = get_manifest_path(config)
    path.write_text(json.dumps(data, indent=2) + "\n")


def find_group(
    dep_groups: list[dict],
    channels: list[str],
    specs: list[str],
    platforms: list[str],
) -> dict | None:
    """Find a dep_group with an exact match on channels, specs, and platforms (order-insensitive)."""
    for group in dep_groups:
        if (
            sorted(group.get("channels", [])) == sorted(channels)
            and sorted(group.get("specs", [])) == sorted(specs)
            and sorted(group.get("platforms", [])) == sorted(platforms)
        ):
            return group
    return None
