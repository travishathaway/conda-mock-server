# Design: conda-mock-server

## Module Layout

```
src/conda_mock_server/
  __init__.py
  cli.py                    ← Click group; registers all subcommands
  commands/
    __init__.py
    add.py
    remove.py
    download.py
    serve.py
  core/
    __init__.py
    manifest.py             ← manifest.json CRUD
    conda.py                ← py-rattler solve + download logic
    server.py               ← Flask app
```

## Data Flow

```
Developer / build workflow:

  cms add python=3.14 --channel conda-forge \
      --platform linux-64 win-64 osx-arm64 osx-64 linux-aarch64
    └─▶ appends dep_group entry to manifest.json

  cms download --directory ./channel-data
    └─▶ reads manifest.json
    └─▶ for each dep_group:
          for each platform:
            records = await rattler.solve(
              channels=[...],
              specs=[...],
              platforms=[Platform(plat)],
              virtual_packages=[],   # conservative: no virtuals
            )
          deduplicate records across platforms
          for each unique record:
            await download_to_path(client, record.url,
              dest=channel_dir / record.subdir / record.filename)
    └─▶ rattler-index fs ./channel-data   (builds repodata + shards)

  cms serve --root-dir ./channel-data
    └─▶ Flask serves channel-data/ as a static conda channel

conda build workflow (recipe/build.sh):
  pip install -e .
  cms add python=3.14 --channel conda-forge \
      --platform linux-64 win-64 osx-arm64 osx-64 linux-aarch64
  cms download --directory "$PREFIX/local/share/conda-mock-server"
  mv manifest.json "$PREFIX/local/share/conda-mock-server/manifest.json"
  # write env_vars.d activation JSON
```

## manifest.json Schema

Stored at `./manifest.json`, committed to git (data directory is gitignored).

```json
{
  "dep_groups": [
    {
      "channels": ["conda-forge"],
      "specs": ["python=3.14"],
      "platforms": ["linux-64", "win-64", "osx-arm64", "osx-64", "linux-aarch64"]
    }
  ]
}
```

- Each entry in `dep_groups` represents a single solve: all specs are resolved together for each platform in the group.
- `channels`: ordered list of channel names/URLs; passed directly to `rattler.solve()`.
- `specs`: conda MatchSpec strings (e.g. `"numpy>=1.24"`, `"python=3.11"`).
- `platforms`: conda subdir strings; the solve is run independently per platform and results are merged.

## `cms add` Semantics

```
cms add <spec> [<spec>...] --channel <ch> [--channel <ch>...] --platform <plat> [--platform <plat>...]
```

- Appends a new dep_group object to `manifest.json["dep_groups"]`.
- No online validation at add time — validation happens at download time when the solver runs.
- Multiple specs in one invocation are treated as a single group (solved together).
- Default channel if `--channel` is omitted: `conda-forge`.
- Default platforms if `--platform` is omitted: `linux-64 win-64 osx-arm64 linux-aarch64`.

## `cms remove` Semantics

```
cms remove <index>
```

- Removes the dep_group at position `<index>` (0-based) from `manifest.json["dep_groups"]`.
- Does not touch downloaded files; a subsequent `cms download` will re-solve from scratch.
- Prints a summary of the removed group for confirmation.

## py-rattler Solve + Download

`core/conda.py` is the heart of the download step.

```python
import asyncio
from rattler import solve, Platform, RepoDataRecord
from rattler.networking import Client
from rattler.package_streaming import download_to_path
from rattler.virtual_package import GenericVirtualPackage
from rattler.package import PackageName
from rattler.version import Version

# Per-platform virtual packages using conda-forge minimum baseline versions.
# Must be supplied explicitly for cross-platform solves; passing [] causes the
# solver to fail for any package with __glibc >=2.17 constraints.
_PLATFORM_VIRTUAL_PACKAGES = {
    "linux-64":      [__unix=1, __linux=5.15, __glibc=2.17, __archspec=1=x86_64],
    "linux-aarch64": [__unix=1, __linux=5.15, __glibc=2.17, __archspec=1=aarch64],
    "osx-64":        [__unix=1, __osx=10.13, __archspec=1=x86_64],
    "osx-arm64":     [__unix=1, __osx=10.13, __archspec=1=m1],
    "win-64":        [__win=10, __archspec=1=x86_64],
    # ... (see source for full table)
}

async def solve_group(group: dict) -> list[RepoDataRecord]:
    """Solve a single dep_group across all platforms; return deduplicated records."""
    all_records: dict[str, RepoDataRecord] = {}
    for plat in group["platforms"]:
        # sources= is the correct kwarg (not channels=); noarch must be explicit
        records = await solve(
            sources=group["channels"],
            specs=group["specs"],
            platforms=[Platform(plat), Platform("noarch")],
            virtual_packages=_virtual_packages_for(plat),
        )
        for r in records:
            all_records[r.file_name] = r
    return list(all_records.values())

async def download_records(records: list[RepoDataRecord], channel_dir: Path) -> None:
    """Download .conda packages into the correct subdir of channel_dir."""
    client = Client()
    tasks = []
    for record in records:
        dest = channel_dir / record.subdir / record.file_name  # subdir is direct attr
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            tasks.append(download_to_path(client, str(record.url), dest))
    if tasks:
        await asyncio.gather(*tasks)
```

Key design decisions:
- **`sources=`** is the correct first parameter name for `rattler.solve()` (not `channels=`).
- **`noarch` must be listed explicitly** in the `platforms` list — py-rattler does not auto-add it when a platforms list is passed.
- **Per-platform virtual packages** with real conda-forge baseline versions are required. `version=0` does not satisfy `>=2.17`; baseline values are `__glibc=2.17` (CentOS 7), `__osx=10.13` (High Sierra), `__win=10`.
- **`record.subdir`** is a direct property (not `record.package_record.subdir`).
- Deduplication is by `file_name` — noarch packages are downloaded once regardless of how many platforms need them.
- Download is skipped if the file already exists on disk (idempotent re-runs).

## conda-index Invocation

After all packages are downloaded, the download command indexes the channel using
`conda-index`'s Python API directly — no subprocess, no external binary required:

```python
from conda_index.index import ChannelIndex

def run_conda_index(channel_dir: Path) -> None:
    idx = ChannelIndex(
        channel_root=channel_dir,
        channel_name=None,
        write_bz2=False,
        write_zst=True,
        write_monolithic=True,
        write_shards=True,     # produces repodata_shards.msgpack.zst
    )
    idx.index(patch_generator=None)
    idx.update_channeldata()
```

`update_index()` (the simpler top-level function) does not expose `write_shards`, so
`ChannelIndex` must be used directly. `conda-index` is listed as a regular Python
dependency in `pyproject.toml` alongside `py-rattler`.

## HTTP Server (Flask)

`core/server.py` is a minimal static file server. `commands/serve.py` uses
`werkzeug.serving.make_server()` instead of `app.run()` so that the actual OS-assigned
port can be read and printed before blocking — this enables `--port 0` (let the OS pick
a free port), which is useful for testing:

```python
from werkzeug.serving import make_server

server = make_server(host, port, app)
actual_port = server.socket.getsockname()[1]  # real port after OS assignment
click.echo(f"conda mock server running at http://{host}:{actual_port}/")
server.serve_forever()
```

MIME types served:

```python
CONTENT_TYPES = {
    ".conda":   "application/x-conda-package",
    ".json":    "application/json",
    ".zst":     "application/zstd",
    ".bz2":     "application/x-bz2",
    ".txt":     "text/plain",
}
```

## pyproject.toml

```toml
[project]
name = "conda-mock-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["click", "flask", "py-rattler", "conda-index"]

[project.scripts]
cms = "conda_mock_server.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/conda_mock_server"]

[tool.pixi.workspace]
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "win-64"]

[tool.pixi.dependencies]
python = ">=3.11"
click = "*"
flask = "*"
py-rattler = "*"
conda-index = "*"

[tool.pixi.pypi-dependencies]
conda-mock-server = { path = ".", editable = true }
```

## recipe/recipe.yaml

```yaml
schema_version: 1

context:
  name: conda-mock-server
  version: 0.1.0
  python_min: "3.11"

package:
  name: ${{ name|lower }}
  version: ${{ version }}

source:
  path: ../

build:
  number: 0
  noarch: python
  script:
    file: build.sh
    env:
      CONDA_MOCK_SERVER_ROOT_DIR: "local/share/conda-mock-server"
  python:
    entry_points:
      - cms = conda_mock_server.cli:main

requirements:
  host:
    - python >=${{ python_min }}
    - hatchling >=1.27.0
    - pip
    - click
    - flask
    - py-rattler
    - conda-index
  run:
    - python >=${{ python_min }}
    - click
    - flask
    - py-rattler
    - conda-index

tests:
  - python:
      pip_check: true
  - requirements:
      run:
        - python >=${{ python_min }}
    script:
      - cms --help
```

## recipe/build.sh

```bash
#!/bin/bash
set -euo pipefail

$PYTHON -m pip install . -vv --no-deps --no-build-isolation

# Register the base dependency group
cms add python=3.14 \
    --channel conda-forge \
    --platform linux-64 --platform win-64 --platform osx-arm64 \
    --platform osx-64 --platform linux-aarch64

# Resolve, download, and index
cms download --directory "$PREFIX/local/share/conda-mock-server"

# Move manifest to final home
mv ./manifest.json "$PREFIX/local/share/conda-mock-server/manifest.json"

# Create activation env vars
mkdir -p "$PREFIX/etc/conda/env_vars.d"
cat > "$PREFIX/etc/conda/env_vars.d/conda-mock-server.json" << EOF
{
  "CONDA_MOCK_SERVER_ROOT_DIR": "$PREFIX/local/share/conda-mock-server",
  "CONDA_MOCK_SERVER_MANIFEST": "$PREFIX/local/share/conda-mock-server/manifest.json"
}
EOF
```

## .gitignore Additions

```
# conda-mock-server downloaded channel data
channel-data/
*.conda
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `CONDA_MOCK_SERVER_ROOT_DIR` | Root directory of the indexed channel to serve |
| `CONDA_MOCK_SERVER_MANIFEST` | Path to `manifest.json` (default: `./manifest.json`) |

Both are set automatically when the conda package is activated via `env_vars.d`.
