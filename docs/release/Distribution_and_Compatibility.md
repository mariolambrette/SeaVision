# Distribution and Compatibility Policy (Phases 1 and 2)

This document defines the release contract and packaging profile for SeaVision.

## 1. Distribution Contract

### 1.1 Current Channel

SeaVision is distributed via GitHub Releases as versioned release assets.

Each release publishes:

1. Python wheel(s) and source distribution.
2. Release notes with install and launch commands.
3. Edge deployment guidance linking to edge runtime docs.

### 1.2 Planned Public Channel

PyPI is the planned public channel.

To keep migration low-risk, release engineering must keep build outputs identical across channels:

1. Build artifacts generated once from a tag.
2. Publish step separated from build/test step.
3. Identical CLI entry points regardless of source.

### 1.3 Versioning and Branch Policy

1. Semantic versioning is used: MAJOR.MINOR.PATCH.
2. Releases are cut from tagged commits on Main.
3. PATCH: bug fixes and doc updates only.
4. MINOR: backward-compatible feature additions.
5. MAJOR: breaking changes in API, CLI, config, or artifact contract.

## 2. Access Modes and Install Profiles

SeaVision supports these user access modes.

1. Programmatic detection pipeline API.
2. CLI detection pipeline: seavision.
3. CLI model export: seavision-export.
4. CLI edge runtime: seavision-edge.
5. CLI GUI launcher: seavision-gui.

Install profiles are mapped to extras:

1. Core mode: pip install seavision
2. S3 mode: pip install "seavision[s3]"
3. GUI mode (includes S3 support): pip install "seavision[gui]"
4. Export mode: pip install "seavision[export]"
5. Edge mode: pip install "seavision[edge]"
6. SAM3 mode: pip install "seavision[sam3]"
7. Full workstation mode: pip install "seavision[all]"

Profiles can be combined, for example:

pip install "seavision[gui,s3]"

## 3. Compatibility Policy

### 3.1 Python Support

Tier 1 support target:

1. Python 3.10
2. Python 3.11
3. Python 3.12

### 3.2 Platform Support by Mode

1. Detection and export CLIs: Windows x64, Linux x64, macOS x64/arm64.
2. GUI launcher: Windows x64, Linux x64, macOS x64/arm64.
3. Edge runtime: Linux on Raspberry Pi OS 64-bit (aarch64) as first-class target.

### 3.3 Support Tiers

1. Tier 1: tested in CI and release smoke checks.
2. Tier 2: best effort, not blocking release.

## 4. Release Readiness Gates for Phases 1 and 2

A release candidate for this phase is ready when:

1. Packaging metadata defines core deps and access-mode extras.
2. Core import path works without optional heavy dependencies.
3. CLI entry points remain stable.
4. Packaging/build artifacts are ignored by VCS rules.
5. This policy is linked from top-level docs.

## 5. PyPI Migration Readiness

When public release is approved:

1. Add TestPyPI publish from tags.
2. Add PyPI trusted publishing.
3. Run dual-publish for at least two releases.
4. Switch docs default install command to PyPI.
