# Proposal: conda-mock-server

## Problem

Testing conda-based tooling (solvers, installers, environment managers) requires fetching packages from real channels like `conda-forge`, which is slow, network-dependent, and produces non-reproducible test environments. There is no local mock that replicates a conda channel's HTTP interface — including shard-based repodata — for hermetic testing.

## Solution

Build a conda-installable CLI tool (`cms`) that:

1. Lets developers declare named dependency groups — sets of specs, channels, and platforms — in a committed manifest (`manifest.json`)
2. Resolves and downloads the full dependency closure for each group (using `py-rattler`) at package build time, not stored in git
3. Indexes the downloaded packages into a proper conda channel using `rattler-index` (with shards enabled)
4. Serves the channel over HTTP so existing conda tooling works with zero reconfiguration beyond pointing at `localhost`

The key capability is **per-group solve correctness**: each dependency group in the manifest represents an independently resolvable environment, letting tests verify that a given set of specs actually solves cleanly for all declared platforms before downloading.

## Goals

- `cms add <specs...> --channel <ch> --platform <plat...>`: register a dependency group in the manifest
- `cms remove <index>`: remove a dependency group from the manifest by index
- `cms download [--directory DIR]`: resolve all groups, download `.conda` packages, and run `rattler-index`
- `cms serve [--port N] [--root-dir DIR]`: serve the indexed channel over HTTP

## Non-Goals

- Storing downloaded `.conda` files in git
- Mocking PyPI or other non-conda package indices
- Generating or mutating synthetic package content (real packages from upstream channels are used)
- Partial/incremental re-downloads when the manifest changes (re-download is always full)

## Tech Stack

- Python ≥ 3.11, Click (CLI), Flask (HTTP server), py-rattler (solve + download), asyncio
- `rattler-index` binary (conda-forge) for channel indexing
- Pixi / rattler-build for packaging
- Data directory (`$PREFIX/local/share/conda-mock-server/`) populated at conda build time and activated via `etc/conda/env_vars.d/`
