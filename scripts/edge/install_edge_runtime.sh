#!/usr/bin/env sh
set -eu

usage() {
    cat <<'EOF'
Usage:
  install_edge_runtime.sh \
    [--release-dir /path/to/release/vX.Y.Z] \
    [--wheel /path/to/seavision-<version>.whl] \
    [--artifact-dir /path/to/artifact] \
    [--release-version v0.1.0] \
    [--runtime-root /opt/seavision] \
    [--python python3]

Recommended:
    --release-dir      Path to a prepared release directory containing:
                       wheels/, artifacts/, scripts/, checksums/.

Advanced:
    --wheel            Path to the SeaVision package file (.whl) to install.
    --artifact-dir     Path to the exported model folder (artifact), or a parent
                       folder containing artifact/.

Optional:
    --release-version  Version label to save under the runtime root for rollback.
                       If omitted and --release-dir is supplied, the installer
                       uses the release directory name.
    --runtime-root     Runtime base directory for versioned installs and current
                       paths. Default: /opt/seavision
    --python           Python executable to use. Default: python3
EOF
}

WHEEL_PATH=""
ARTIFACT_DIR=""
RELEASE_DIR=""
RELEASE_VERSION=""
RUNTIME_ROOT="/opt/seavision"
PYTHON_BIN="python3"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --release-dir)
            RELEASE_DIR="$2"
            shift 2
            ;;
        --wheel)
            WHEEL_PATH="$2"
            shift 2
            ;;
        --artifact-dir)
            ARTIFACT_DIR="$2"
            shift 2
            ;;
        --release-version)
            RELEASE_VERSION="$2"
            shift 2
            ;;
        --runtime-root)
            RUNTIME_ROOT="$2"
            shift 2
            ;;
        --python)
            PYTHON_BIN="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
    exit 1
fi

resolve_artifact_dir() {
    base_dir="$1"
    if [ -f "$base_dir/manifest.json" ]; then
        printf '%s\n' "$base_dir"
        return
    fi

    if [ -f "$base_dir/artifact/manifest.json" ]; then
        printf '%s\n' "$base_dir/artifact"
        return
    fi

    printf '%s\n' ""
}

find_release_wheel() {
    release_dir="$1"
    find "$release_dir/wheels" -maxdepth 1 -type f -name 'seavision-*.whl' | sort | head -n 1
}

find_release_artifact_dir() {
    release_dir="$1"

    if [ -f "$release_dir/artifacts/artifact/manifest.json" ]; then
        printf '%s\n' "$release_dir/artifacts/artifact"
        return
    fi

    manifest_path="$(find "$release_dir/artifacts" -maxdepth 2 -type f -name 'manifest.json' | sort | head -n 1 || true)"
    if [ -n "$manifest_path" ]; then
        dirname "$manifest_path"
        return
    fi

    printf '%s\n' ""
}

wheel_uri() {
    wheel_path="$1"
    "$PYTHON_BIN" - "$wheel_path" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_uri())
PY
}

if [ -n "$RELEASE_DIR" ]; then
    if [ ! -d "$RELEASE_DIR" ]; then
        echo "ERROR: Release directory not found: $RELEASE_DIR" >&2
        exit 1
    fi

    if [ -z "$WHEEL_PATH" ]; then
        WHEEL_PATH="$(find_release_wheel "$RELEASE_DIR")"
    fi

    if [ -z "$ARTIFACT_DIR" ]; then
        ARTIFACT_DIR="$(find_release_artifact_dir "$RELEASE_DIR")"
    fi

    if [ -z "$RELEASE_VERSION" ]; then
        RELEASE_VERSION="$(basename "$RELEASE_DIR")"
    fi
fi

if [ -z "$WHEEL_PATH" ] || [ -z "$ARTIFACT_DIR" ]; then
    echo "ERROR: Could not determine both the wheel path and artifact directory." >&2
    echo "Use --release-dir for the simple path, or provide --wheel and --artifact-dir explicitly." >&2
    usage
    exit 1
fi

if [ ! -f "$WHEEL_PATH" ]; then
    echo "ERROR: Wheel not found: $WHEEL_PATH" >&2
    exit 1
fi

if [ ! -d "$ARTIFACT_DIR" ]; then
    echo "ERROR: Artifact directory not found: $ARTIFACT_DIR" >&2
    exit 1
fi

RESOLVED_ARTIFACT_DIR="$(resolve_artifact_dir "$ARTIFACT_DIR")"
if [ -z "$RESOLVED_ARTIFACT_DIR" ]; then
    echo "ERROR: manifest.json not found in the exported model folder or nested artifact/ directory." >&2
    echo "Checked: $ARTIFACT_DIR" >&2
    exit 1
fi

WHEEL_URI="$(wheel_uri "$WHEEL_PATH")"

echo "[1/4] Installing SeaVision edge runtime from the wheel..."
"$PYTHON_BIN" -m pip install --upgrade "seavision[edge] @ ${WHEEL_URI}"

echo "[2/4] Checking that the seavision-edge command is available..."
if ! command -v seavision-edge >/dev/null 2>&1; then
    echo "ERROR: seavision-edge is not available on PATH after install." >&2
    echo "Try running in the same environment as pip install, or use: $PYTHON_BIN -m seavision.run_edge --help" >&2
    exit 1
fi

echo "[3/4] Checking the exported model folder..."
if [ ! -f "$RESOLVED_ARTIFACT_DIR/manifest.json" ]; then
    echo "ERROR: manifest.json missing: $RESOLVED_ARTIFACT_DIR/manifest.json" >&2
    exit 1
fi

mkdir -p "$RUNTIME_ROOT/releases/wheels" "$RUNTIME_ROOT/releases/artifacts"

ACTIVE_ARTIFACT_DIR="$RESOLVED_ARTIFACT_DIR"

if [ -n "$RELEASE_VERSION" ]; then
    echo "[4/4] Saving this version for rollback and updating current paths..."

    VERSION_WHEEL_DIR="$RUNTIME_ROOT/releases/wheels/$RELEASE_VERSION"
    VERSION_ARTIFACT_DIR="$RUNTIME_ROOT/releases/artifacts/$RELEASE_VERSION"

    mkdir -p "$VERSION_WHEEL_DIR"
    rm -rf "$VERSION_ARTIFACT_DIR"

    cp -f "$WHEEL_PATH" "$VERSION_WHEEL_DIR/"
    cp -a "$RESOLVED_ARTIFACT_DIR" "$VERSION_ARTIFACT_DIR"

    ln -sfn "$VERSION_WHEEL_DIR" "$RUNTIME_ROOT/current-wheel"
    ln -sfn "$VERSION_ARTIFACT_DIR" "$RUNTIME_ROOT/current-artifact"

    ACTIVE_ARTIFACT_DIR="$RUNTIME_ROOT/current-artifact"
else
    echo "[4/4] Updating the current artifact path without rollback storage..."
    ln -sfn "$RESOLVED_ARTIFACT_DIR" "$RUNTIME_ROOT/current-artifact"
    ACTIVE_ARTIFACT_DIR="$RUNTIME_ROOT/current-artifact"
fi

echo ""
echo "SeaVision edge runtime installation complete."
echo "Installed wheel: $WHEEL_PATH"
echo "Using artifact directory: $RESOLVED_ARTIFACT_DIR"
if [ -n "$RELEASE_VERSION" ]; then
    echo "Saved release version: $RELEASE_VERSION"
    echo "Current paths now point to this saved version under $RUNTIME_ROOT"
else
    echo "No release version was supplied, so only the current artifact path was updated."
fi
echo ""
echo "Launch command:"
echo "  seavision-edge --artifact-dir $ACTIVE_ARTIFACT_DIR"
