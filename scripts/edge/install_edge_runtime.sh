#!/usr/bin/env sh
set -eu

# Install or upgrade SeaVision edge runtime on Raspberry Pi, validate artifact
# manifest, configure stable current pointers, and print exact launch command.

usage() {
    cat <<'EOF'
Usage:
  install_edge_runtime.sh \
    --wheel /path/to/seavision-<version>.whl \
    --artifact-dir /path/to/artifact \
    [--release-version v0.1.0] \
    [--runtime-root /opt/seavision] \
    [--python python3]

Required:
  --wheel            Path to SeaVision wheel file.
  --artifact-dir     Path to edge artifact directory (or parent containing artifact/).

Optional:
  --release-version  Version label for versioned storage under runtime root.
                     Example: v0.1.0
  --runtime-root     Runtime base directory for versioned artifacts and stable pointers.
                     Default: /opt/seavision
  --python           Python executable to use. Default: python3
EOF
}

WHEEL_PATH=""
ARTIFACT_DIR=""
RELEASE_VERSION=""
RUNTIME_ROOT="/opt/seavision"
PYTHON_BIN="python3"

while [ "$#" -gt 0 ]; do
    case "$1" in
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

if [ -z "$WHEEL_PATH" ] || [ -z "$ARTIFACT_DIR" ]; then
    echo "ERROR: --wheel and --artifact-dir are required." >&2
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

RESOLVED_ARTIFACT_DIR="$(resolve_artifact_dir "$ARTIFACT_DIR")"
if [ -z "$RESOLVED_ARTIFACT_DIR" ]; then
    echo "ERROR: manifest.json not found in artifact path or nested artifact/ directory." >&2
    echo "Checked: $ARTIFACT_DIR" >&2
    exit 1
fi

echo "[1/4] Installing or upgrading SeaVision edge runtime..."
"$PYTHON_BIN" -m pip install --upgrade "${WHEEL_PATH}[edge]"

echo "[2/4] Verifying seavision-edge command availability..."
if ! command -v seavision-edge >/dev/null 2>&1; then
    echo "ERROR: seavision-edge is not available on PATH after install." >&2
    echo "Try running in the same environment as pip install, or use: $PYTHON_BIN -m seavision.run_edge --help" >&2
    exit 1
fi

echo "[3/4] Validating artifact manifest presence..."
if [ ! -f "$RESOLVED_ARTIFACT_DIR/manifest.json" ]; then
    echo "ERROR: manifest.json missing: $RESOLVED_ARTIFACT_DIR/manifest.json" >&2
    exit 1
fi

mkdir -p "$RUNTIME_ROOT/releases/wheels" "$RUNTIME_ROOT/releases/artifacts"

ACTIVE_ARTIFACT_DIR="$RESOLVED_ARTIFACT_DIR"

if [ -n "$RELEASE_VERSION" ]; then
    echo "[4/4] Storing versioned runtime assets for rollback..."

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
    ln -sfn "$RESOLVED_ARTIFACT_DIR" "$RUNTIME_ROOT/current-artifact"
    ACTIVE_ARTIFACT_DIR="$RUNTIME_ROOT/current-artifact"
fi

echo ""
echo "SeaVision edge runtime installation complete."
echo "Wheel: $WHEEL_PATH"
echo "Artifact: $RESOLVED_ARTIFACT_DIR"
if [ -n "$RELEASE_VERSION" ]; then
    echo "Release version: $RELEASE_VERSION"
fi
echo ""
echo "Launch command:"
echo "  seavision-edge --artifact-dir $ACTIVE_ARTIFACT_DIR"
