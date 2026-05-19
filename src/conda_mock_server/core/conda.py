import asyncio
from pathlib import Path

from rattler import solve, Platform, RepoDataRecord
from rattler.networking import Client
from rattler.package_streaming import download_to_path
from rattler.virtual_package import GenericVirtualPackage
from rattler.package import PackageName
from rattler.version import Version

# ---------------------------------------------------------------------------
# Per-platform virtual packages for cross-platform solving
#
# When solving for a platform other than the current host, py-rattler cannot
# auto-detect virtual packages (e.g. __glibc on linux when building on macOS).
# Passing an empty list causes the solver to treat those virtual packages as
# absent, so any package with `__glibc >=2.17` constraints has no candidates.
#
# The fix: supply explicit virtual packages using the conda-forge minimum
# baseline versions. These are the same versions that CONDA_OVERRIDE_GLIBC
# and CONDA_OVERRIDE_OSX default to across the ecosystem:
#
#   __glibc  2.17  — CentOS 7 baseline (conda-forge minimum)
#   __osx    10.13 — macOS High Sierra (conda-forge minimum)
#   __linux  5.15  — conservative modern kernel
#   __unix   1     — always present on POSIX platforms
#   __win    10    — Windows 10 baseline
#   __archspec 1=<arch> — from rattler Archspec::from_platform()
#
# Note: version "0" does NOT satisfy ">= 2.17" — 0 < 2.17 in conda version
# ordering. Real minimum versions must be used.
# ---------------------------------------------------------------------------

def _gvp(name: str, version: str, build: str) -> GenericVirtualPackage:
    return GenericVirtualPackage(PackageName(name), Version(version), build)


# Virtual packages keyed by conda subdir string.
# Each entry is the minimal baseline set needed for a hermetic cross-platform solve.
_PLATFORM_VIRTUAL_PACKAGES: dict[str, list[GenericVirtualPackage]] = {
    "linux-64": [
        _gvp("__unix", "1", "0"),
        _gvp("__linux", "5.15", "0"),
        _gvp("__glibc", "2.17", "0"),
        _gvp("__archspec", "1", "x86_64"),
    ],
    "linux-aarch64": [
        _gvp("__unix", "1", "0"),
        _gvp("__linux", "5.15", "0"),
        _gvp("__glibc", "2.17", "0"),
        _gvp("__archspec", "1", "aarch64"),
    ],
    "linux-ppc64le": [
        _gvp("__unix", "1", "0"),
        _gvp("__linux", "5.15", "0"),
        _gvp("__glibc", "2.17", "0"),
        _gvp("__archspec", "1", "ppc64le"),
    ],
    "osx-64": [
        _gvp("__unix", "1", "0"),
        _gvp("__osx", "11.0", "0"),
        _gvp("__archspec", "1", "x86_64"),
    ],
    "osx-arm64": [
        _gvp("__unix", "1", "0"),
        _gvp("__osx", "11.0", "0"),
        _gvp("__archspec", "1", "m1"),
    ],
    "win-64": [
        _gvp("__win", "10", "0"),
        _gvp("__archspec", "1", "x86_64"),
    ],
    "win-arm64": [
        _gvp("__win", "10", "0"),
        _gvp("__archspec", "1", "aarch64"),
    ],
}


def _virtual_packages_for(platform: str) -> list[GenericVirtualPackage]:
    """Return cross-platform-safe virtual packages for a given subdir string.

    Falls back to an empty list for unknown/noarch platforms — the solver
    doesn't need virtual packages for those.
    """
    return _PLATFORM_VIRTUAL_PACKAGES.get(platform, [])


async def solve_group(group: dict) -> list[RepoDataRecord]:
    """Solve a single dep_group across all platforms; return deduplicated records.

    Records are deduplicated by file_name so that noarch packages shared across
    platforms are only downloaded once.

    Each platform is solved independently with noarch included, so that pure-Python
    packages (which land in noarch/) are correctly resolved alongside platform-specific
    packages.
    """
    all_records: dict[str, RepoDataRecord] = {}
    for plat in group["platforms"]:
        # Include "noarch" explicitly — when passing a platforms list, py-rattler
        # does NOT auto-add noarch, so we must include it ourselves.
        records = await solve(
            sources=group["channels"],
            specs=group["specs"],
            platforms=[Platform(plat), Platform("noarch")],
            virtual_packages=_virtual_packages_for(plat),
        )
        for r in records:
            all_records[r.file_name] = r
    return list(all_records.values())


async def download_records(
    records: list[RepoDataRecord], channel_dir: Path
) -> None:
    """Download .conda packages into the correct subdir of channel_dir.

    Skips files that already exist on disk. Downloads are run concurrently.
    """
    client = Client()
    tasks = []
    for record in records:
        # subdir is a direct property on RepoDataRecord (via PackageRecord)
        dest = channel_dir / record.subdir / record.file_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            tasks.append(
                download_to_path(client, str(record.url), dest)
            )
    if tasks:
        await asyncio.gather(*tasks)


async def solve_and_download(group: dict, channel_dir: Path) -> int:
    """Solve a dep_group and download all resolved packages. Returns count of records."""
    records = await solve_group(group)
    await download_records(records, channel_dir)
    return len(records)


def run_conda_index(channel_dir: Path) -> None:
    """Index the channel directory using conda-index with shards enabled.

    Uses the ChannelIndex Python API directly (no subprocess) so that
    conda-index is a regular Python dependency rather than an external binary.
    Shards are written alongside the standard repodata.json.
    """
    from conda_index.index import ChannelIndex

    idx = ChannelIndex(
        channel_root=channel_dir,
        channel_name=None,
        write_bz2=False,
        write_zst=True,
        write_monolithic=True,
        write_shards=True,
    )
    idx.index(patch_generator=None)
    idx.update_channeldata()
