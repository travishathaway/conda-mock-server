# conda-mock-server

A CLI tool for creating and serving a local conda channel for testing. It resolves
package dependencies with [py-rattler](https://github.com/conda/rattler), downloads
the resolved `.conda` packages, indexes the channel with
[conda-index](https://github.com/conda/conda-index) (including sharded repodata), and
serves it over HTTP — so your tests can point at `localhost` instead of `conda-forge`.

## Installation

To install, use my personal conda channel, "thath":

```bash
pixi add conda-mock-server
# or
conda install thath::conda-mock-server
```

## Usage

```
Usage: cms [OPTIONS] COMMAND [ARGS]...

  conda-mock-server: serve a local conda channel for testing.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  add       Add a dependency group to the manifest.
  download  Resolve and download all dependency groups, then index the channel.
  remove    Remove a dependency group from the manifest by index (0-based).
  serve     Serve the mock conda channel over HTTP.
```

### `cms add`

```
Usage: cms add [OPTIONS] SPECS...

  Add a dependency group to the manifest.

Options:
  --channel TEXT   Channel to add (may be repeated). Defaults to conda-forge.
                   [default: conda-forge]
  --platform TEXT  Platform subdir to include (may be repeated).
                   [default: linux-64, win-64, osx-arm64, linux-aarch64]
  --config TEXT    Path to manifest.json.
  --help           Show this message and exit.
```

### `cms remove`

```
Usage: cms remove [OPTIONS] INDEX

  Remove a dependency group from the manifest by index (0-based).

Options:
  --config TEXT  Path to manifest.json.
  --help         Show this message and exit.
```

### `cms download`

```
Usage: cms download [OPTIONS]

  Resolve and download all dependency groups, then index the channel.

Options:
  -d, --directory TEXT  Directory to write the channel data to (default:
                        current directory).
  --config TEXT         Path to manifest.json.
  --help                Show this message and exit.
```

### `cms serve`

```
Usage: cms serve [OPTIONS]

  Serve the mock conda channel over HTTP.

Options:
  --port INTEGER   Port to listen on. Use 0 to let the OS assign a free port.
                   [default: 8080]
  --host TEXT      Host to bind to.  [default: 127.0.0.1]
  --root-dir TEXT  Root directory of the indexed conda channel to serve.
  --help           Show this message and exit.
```

## Getting started

This walkthrough shows how to build a local conda channel, extend it with additional
packages, and point a test suite at it.

### 1. Install the package

```bash
conda install -c thath conda-mock-server
```

The conda package ships with a pre-built channel containing a base set of packages
(Python 3.14 and its dependencies for all major platforms). After installation, the
`CONDA_MOCK_SERVER_ROOT_DIR` (`$CONDA_PREFIX/local/share/conda-mock-server`) 
environment variable is set automatically whenever the
conda environment is active, so `cms serve` will find the channel without any extra
configuration.

Additionally, the `CONDA_MOCK_SERVER_CONFIG` variable will be set to the default
`manifest.json` (`$CONDA_PREFIX/local/share/conda-mock-server/manifest.json`).

### 2. Serve the pre-built channel

Start the server pointing at the bundled channel data:

```bash
cms serve
# conda mock server running at http://127.0.0.1:8080/
# Press Ctrl+C to stop.
```

Verify it responds:

```bash
curl http://127.0.0.1:8080/linux-64/repodata.json | python3 -m json.tool | head -20
```

### 3. Add packages to the manifest

Each call to `cms add` registers a *dependency group* — a set of specs that should
be solvable together. All specs in one invocation are resolved in a single solve,
so you can verify that the combination is satisfiable before committing to it.

```bash
# Add numpy and scipy together for two platforms
cms add numpy scipy --platform linux-64 --platform osx-arm64

# Add pandas on its own (separate group, separate solve)
cms add pandas --platform linux-64 --platform win-64 --platform osx-arm64

# Add a pinned version from a non-default channel
cms add "pytorch>=2.3" --channel pytorch --channel conda-forge \
    --platform linux-64 --platform osx-arm64
```

After each `cms add`, `manifest.json` is updated immediately. Nothing is downloaded
yet — that happens in the next step.

### 4. Review the manifest

`manifest.json` tracks every dependency group in order:

```json
{
  "dep_groups": [
    {
      "channels": ["conda-forge"],
      "specs": ["python=3.14"],
      "platforms": ["linux-64", "win-64", "osx-arm64", "osx-64", "linux-aarch64"]
    },
    {
      "channels": ["conda-forge"],
      "specs": ["numpy", "scipy"],
      "platforms": ["linux-64", "osx-arm64"]
    },
    {
      "channels": ["conda-forge"],
      "specs": ["pandas"],
      "platforms": ["linux-64", "win-64", "osx-arm64"]
    }
  ]
}
```

To remove a group you no longer need, use its 0-based index:

```bash
cms remove 2   # removes the pandas group
```

### 5. Download and index the channel

```bash
cms download
```

This command:

1. Reads every dependency group from `manifest.json`
2. Runs a solver for each group × platform combination using py-rattler
3. Downloads the resolved `.conda` packages into the correct platform subdirectory
4. Skips files that already exist on disk (re-runs are safe and incremental)
5. Runs `conda-index` to generate `repodata.json`, `repodata.json.zst`, and
   sharded repodata (`repodata_shards.msgpack.zst`) for each subdir

Output looks like:

```
[group 0] solving: python=3.14 (5 platforms)
  downloaded 8 package(s)

[group 1] solving: numpy, scipy (2 platforms)
  downloaded 24 package(s)

Indexing channel...
Channel ready at: /home/user/my-channel
```

### 6. Serve the channel

```bash
cms serve 
# conda mock server running at http://127.0.0.1:8080/
```

Pass `--port 0` to let the OS pick a free port — useful in CI or when running
multiple servers at once:

```bash
cms serve --port 0
# conda mock server running at http://127.0.0.1:54321/
```

### 7. Use the channel in tests

Point conda or pixi at `http://127.0.0.1:8080` as a channel:

```bash
# conda
conda install -c http://127.0.0.1:8080 numpy

# pixi (in pixi.toml)
# [project]
# channels = ["http://127.0.0.1:8080", "conda-forge"]
```

In a pytest fixture you can start the server as a subprocess and tear it down after
the test session. Use `--port 0` so the OS picks a free port, then read the actual
URL from the first line of stdout:

```python
import re
import subprocess
import pytest

@pytest.fixture(scope="session")
def conda_channel(channel_data_dir):
    proc = subprocess.Popen(
        ["cms", "serve", "--root-dir", str(channel_data_dir), "--port", "0"],
        stdout=subprocess.PIPE,
        text=True,
    )
    # cms prints "conda mock server running at http://<host>:<port>/" as its
    # first line, so we can read the real OS-assigned port directly from it.
    first_line = proc.stdout.readline()
    match = re.search(r"(http://\S+)", first_line)
    url = match.group(1).rstrip("/")
    yield url
    proc.terminate()
```

## How it works

```
cms add numpy scipy --platform linux-64 osx-arm64
  └─▶ appends dep_group to manifest.json

cms download
  └─▶ for each dep_group:
        for each platform:
          py-rattler solves specs → list of RepoDataRecords
        deduplicate records (noarch packages appear once)
        download .conda files in parallel
  └─▶ conda-index builds repodata.json + shards

cms serve
  └─▶ Flask serves ./channel as a static conda channel
```

## Environment variables

| Variable | Purpose |
|---|---|
| `CONDA_MOCK_SERVER_ROOT_DIR` | Default `--root-dir` for `cms serve` |
| `CONDA_MOCK_SERVER_MANIFEST` | Default `--config` path for all commands |

Both are set automatically when the conda package's environment is activated.
