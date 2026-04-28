#!/usr/bin/env python
"""Assemble a versioned SeaVision edge deployment bundle."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_SOURCE = REPO_ROOT / "scripts" / "edge" / "install_edge_runtime.sh"
OPERATOR_DOC_SOURCE = REPO_ROOT / "docs" / "edge" / "Operator Quickstart.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="assemble_edge_release",
        description="Create a versioned SeaVision edge deployment bundle.",
    )
    parser.add_argument(
        "--wheel",
        required=True,
        help="Path to the built SeaVision wheel.",
    )
    parser.add_argument(
        "--artifact-dir",
        required=True,
        help=(
            "Path to the exported artifact directory, or a parent directory "
            "containing artifact/."
        ),
    )
    parser.add_argument(
        "--version",
        default="",
        help=(
            "Package version without a leading v, for example 0.1.0. "
            "If omitted, the version is inferred from the wheel filename."
        ),
    )
    parser.add_argument(
        "--output-root",
        default="release",
        help="Directory where the versioned release folder should be created.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Also create a zip archive in dist/.",
    )
    return parser.parse_args()


def sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_version_from_wheel(wheel_path: Path) -> str:
    parts = wheel_path.name.split("-")
    if len(parts) < 2:
        raise ValueError(f"Could not infer version from wheel name: {wheel_path}")
    return parts[1]


def resolve_artifact_dir(path: Path) -> Path:
    if (path / "manifest.json").exists():
        return path

    nested = path / "artifact"
    if (nested / "manifest.json").exists():
        return nested

    raise FileNotFoundError(
        "Could not find manifest.json in the provided artifact directory or "
        f"in a nested artifact/ directory: {path}"
    )


def write_install_wrapper(release_dir: Path) -> None:
    wrapper = release_dir / "install.sh"
    wrapper.write_text(
        """#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec sh "$SCRIPT_DIR/scripts/install_edge_runtime.sh" --release-dir "$SCRIPT_DIR" "$@"
""",
        encoding="utf-8",
    )


def write_checksums(release_dir: Path) -> None:
    checksum_dir = release_dir / "checksums"
    checksum_dir.mkdir(parents=True, exist_ok=True)

    files_to_hash = []
    for path in sorted(release_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.parent == checksum_dir:
            continue
        files_to_hash.append(path)

    lines = []
    for file_path in files_to_hash:
        relative = file_path.relative_to(release_dir).as_posix()
        lines.append(f"{sha256_for_file(file_path)} *{relative}")

    (checksum_dir / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def create_zip_archive(release_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zip_file:
        for path in sorted(release_dir.rglob("*")):
            if path.is_file():
                arcname = release_dir.name + "/" + path.relative_to(release_dir).as_posix()
                zip_file.write(path, arcname)


def main() -> int:
    args = parse_args()

    wheel_path = Path(args.wheel).resolve()
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    artifact_dir = resolve_artifact_dir(Path(args.artifact_dir).resolve())
    version = args.version or infer_version_from_wheel(wheel_path)
    release_version = version if version.startswith("v") else f"v{version}"

    release_dir = Path(args.output_root).resolve() / release_version
    if release_dir.exists():
        shutil.rmtree(release_dir)

    (release_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (release_dir / "wheels").mkdir(parents=True, exist_ok=True)
    (release_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    shutil.copy2(wheel_path, release_dir / "wheels" / wheel_path.name)
    shutil.copy2(INSTALLER_SOURCE, release_dir / "scripts" / INSTALLER_SOURCE.name)
    shutil.copy2(OPERATOR_DOC_SOURCE, release_dir / "OPERATOR_QUICKSTART.md")
    shutil.copytree(artifact_dir, release_dir / "artifacts" / "artifact")

    write_install_wrapper(release_dir)
    write_checksums(release_dir)

    print(f"Created release directory: {release_dir}")

    if args.zip:
        archive_path = Path("dist").resolve() / f"seavision-edge-{release_version}.zip"
        create_zip_archive(release_dir, archive_path)
        print(f"Created zip archive: {archive_path}")

    print("Next steps:")
    print(f"  1. Copy {release_dir} to the Raspberry Pi, or upload the zip archive.")
    print(f"  2. On the Pi, run: bash ~/seavision-release/{release_version}/install.sh")
    print("  3. Launch: seavision-edge --artifact-dir /opt/seavision/current-artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())