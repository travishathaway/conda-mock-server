#!/bin/bash
set -euo pipefail

$PYTHON -m pip install . -vv --no-deps --no-build-isolation

# Register the base dependency group
cms add python=3.13 pip \
    --channel conda-forge \
    --platform linux-64 \
    --platform win-64 \
    --platform osx-arm64 \
    --platform osx-64 \
    --platform linux-aarch64

# Resolve, download all packages, and index the channel
cms download --directory "$PREFIX/local/share/conda-mock-server"

# Move the manifest to its final installed location
mv ./manifest.json "$PREFIX/local/share/conda-mock-server/manifest.json"

# Create activation environment variables
mkdir -p "$PREFIX/etc/conda/env_vars.d"
cat > "$PREFIX/etc/conda/env_vars.d/conda-mock-server.json" << EOF
{
  "CONDA_MOCK_SERVER_ROOT_DIR": "$PREFIX/local/share/conda-mock-server",
  "CONDA_MOCK_SERVER_MANIFEST": "$PREFIX/local/share/conda-mock-server/manifest.json"
}
EOF
