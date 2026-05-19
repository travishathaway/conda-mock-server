# Tasks: conda-mock-server

## 1. Project scaffold

- [x] Create `pyproject.toml` with project metadata, dependencies (`click`, `flask`, `py-rattler`, `conda-index`), hatchling build config, entry point `cms = conda_mock_server.cli:main`, and pixi workspace config including `conda-index` in `[tool.pixi.dependencies]`
- [x] Create `src/conda_mock_server/__init__.py`
- [x] Create `src/conda_mock_server/commands/__init__.py`
- [x] Create `src/conda_mock_server/core/__init__.py`
- [x] Create `manifest.json` with a single base dep_group: `{"dep_groups": [{"channels": ["conda-forge"], "specs": ["python=3.14"], "platforms": ["linux-64", "win-64", "osx-arm64", "osx-64", "linux-aarch64"]}]}`
- [x] Add `.gitignore` excluding channel data directories and `.conda` files

## 2. Implement `core/manifest.py`

Functions:
- `get_manifest_path(config: str | None) -> Path`: returns `Path(config)` or `./manifest.json`
- `load_manifest(config: str | None) -> dict`: reads and parses `manifest.json`; returns `{"dep_groups": []}` if missing
- `save_manifest(data: dict, config: str | None) -> None`: writes pretty-printed JSON
- `find_group(dep_groups: list[dict], channels: list, specs: list, platforms: list) -> dict | None`: find exact-match group (for duplicate detection in `add`)

## 3. Implement `core/conda.py`

Async functions using py-rattler:
- `solve_group(group: dict) -> list[RepoDataRecord]`: calls `rattler.solve()` (with `sources=` param) per platform + noarch, deduplicates records by `file_name`, returns merged list; supplies per-platform virtual packages (glibc 2.17, osx 10.13, etc.) for hermetic cross-platform solving
- `download_records(records: list[RepoDataRecord], channel_dir: Path) -> None`: downloads each record's `.conda` file to `channel_dir / subdir / filename`; skips if file already exists; uses `asyncio.gather()` for parallel downloads
- `run_conda_index(channel_dir: Path) -> None`: calls `ChannelIndex` from `conda_index.index` directly (Python API, not subprocess) with `write_shards=True`, `write_zst=True`, `write_monolithic=True`

## 4. Implement `commands/add.py`

```
cms add <spec> [<spec>...] [--channel <ch>...] [--platform <plat>...] [--config PATH]
```

- Accept one or more specs as `click.argument("specs", nargs=-1, required=True)`
- `--channel` defaults to `["conda-forge"]` if not provided; allow multiple via `multiple=True`
- `--platform` defaults to `["linux-64", "win-64", "osx-arm64", "linux-aarch64"]` if not provided; allow multiple via `multiple=True`
- Load manifest, append new dep_group dict, save manifest
- Print summary of what was added (specs, channels, platforms)

## 5. Implement `commands/remove.py`

```
cms remove <index> [--config PATH]
```

- `<index>` is a 0-based integer index into `dep_groups`
- Load manifest, print summary of the group being removed, remove it, save manifest
- Error clearly if index is out of range
- Print confirmation of removal

## 6. Implement `commands/download.py`

```
cms download [-d/--directory DIR] [--config PATH]
```

- Load manifest; error if `dep_groups` is empty (instruct user to run `cms add` first)
- Resolve `channel_dir` from `--directory` or current directory; create if needed
- For each dep_group: call `asyncio.run(solve_and_download(group, channel_dir))`
  - `solve_and_download` calls `solve_group()` then `download_records()`
  - Print progress: group specs and platform count before solving, record count after
- After all groups are downloaded, call `run_conda_index(channel_dir)`
- Print completion message with channel directory path

## 7. Implement `core/server.py`

Flask application factory:
- `create_app(data_root: Path) -> Flask`
- Single route `GET /<path:filepath>`: resolves `data_root / filepath`, path-traversal guard via `.relative_to()`, returns file with correct MIME type or 404
- MIME type map: `.conda` → `application/x-conda-package`, `.json` → `application/json`, `.zst` → `application/zstd`, `.bz2` → `application/x-bz2`, `.txt` → `text/plain`; fallback `application/octet-stream`

## 8. Implement `commands/serve.py`

```
cms serve [--port 8080] [--host 127.0.0.1] [--root-dir PATH]
```

- `--root-dir` / `$CONDA_MOCK_SERVER_ROOT_DIR`: path to the indexed channel directory
- Warn to stderr if directory is empty or does not exist
- Use `werkzeug.serving.make_server()` instead of `app.run()` so the actual bound port can be read before printing the startup URL (supports `--port 0` for OS-assigned ports)
- Print startup URL with the real bound port before serving

## 9. Implement `cli.py`

- Click group `cli` with `--version`
- Register all four subcommands: `add_command`, `remove_command`, `download_command`, `serve_command`
- `main()` entrypoint

## 10. Create `recipe/`

- [x] Write `recipe/recipe.yaml` (noarch python, rattler-build v1 schema, `conda-index` in `run` requirements)
- [x] Write `recipe/build.sh`:
  - `pip install -e .`
  - `cms add python=3.14 --channel conda-forge --platform linux-64 --platform win-64 --platform osx-arm64 --platform osx-64 --platform linux-aarch64`
  - `cms download --directory "$PREFIX/local/share/conda-mock-server"`
  - `mv ./manifest.json "$PREFIX/local/share/conda-mock-server/manifest.json"`
  - Write `$PREFIX/etc/conda/env_vars.d/conda-mock-server.json` with `CONDA_MOCK_SERVER_ROOT_DIR` and `CONDA_MOCK_SERVER_MANIFEST`

## 11. Verify end-to-end

- [x] `pip install -e .` succeeds (or `pixi install`)
- [x] `cms --help` lists all four commands
- [x] `cms add numpy scipy --channel conda-forge --platform linux-64` → manifest updated
- [x] `cms remove 1` → second dep_group removed
- [x] `cms download` → `.conda` files present in subdirs; `repodata.json` and shard files generated (verified in build environment; not runnable in offline CI)
- [x] `cms serve` → `curl localhost:8080/linux-64/repodata.json` returns 200 with JSON
- [x] `curl localhost:8080/linux-64/<numpy-package>.conda` returns 200
- [x] Missing path returns 404
