# No-Clone Distribution Path — Implementation Plan

**Goal:** Allow every user persona (workstation analyst, field operator, developer) to install SeaVision without cloning the repository — using only `pip install` from GitHub Releases or PyPI, with no local source tree required.

**Estimated effort:** 1–2 weeks for a GitHub Releases MVP; 3–6 weeks for full PyPI production path.

---

## Workstreams

### 1. Packaging correctness audit

Before publishing anywhere, verify the built wheel is actually self-contained and installs cleanly into a blank environment.

**Tasks:**
- [ ] Run `pip wheel . --no-deps -w dist/` and inspect the resulting `.whl` with `unzip -l` to confirm all expected files are included
- [ ] Create a throw-away venv and install the wheel with each extra in isolation (`pip install seavision[gui]`, `pip install seavision[edge]`, `pip install seavision[sam3]`) — verify the entry-point commands are present and importable
- [ ] Verify `seavision[all]` installs without dependency conflicts on Python 3.10, 3.11, and 3.12
- [ ] Check that optional heavy deps (torch, transformers, ultralytics) are **not** pulled in by core or `[gui]`
- [ ] Confirm `MANIFEST.in` (or `[tool.setuptools.package-data]`) includes all non-Python assets (e.g. `config/default.yaml`, any bundled model config files)
- [ ] Run the existing test suite against an installed wheel (not editable install) to catch any path assumptions

**Acceptance criteria:** `pip install <wheel>[all]` into a clean venv passes `pytest tests/` with no import errors.

---

### 2. GitHub Releases CI publish pipeline

Publish pre-built wheels to GitHub Releases so users can `pip install` directly from a release URL without cloning.

**Tasks:**
- [ ] Add a `.github/workflows/release.yml` workflow that:
  - Triggers on `git push --tags` matching `v*.*.*`
  - Runs on `ubuntu-latest`
  - Builds the wheel with `python -m build --wheel`
  - Computes `SHA256SUMS.txt` for all built artifacts
  - Uploads wheel + checksums as GitHub Release assets
- [ ] Verify the release URL pattern: `https://github.com/mariolambrette/SeaVision/releases/download/vX.Y.Z/seavision-X.Y.Z-py3-none-any.whl`
- [ ] Update `scripts/edge/install_edge_runtime.sh` to accept a GitHub Release URL as an alternative to a local path (add `--release-url` flag)
- [ ] Add a `build` job to an existing CI workflow (or a new `ci.yml`) that builds the wheel on every PR to catch packaging regressions early

**Acceptance criteria:** Pushing a `vX.Y.Z` tag triggers the workflow, produces a release with a wheel and `SHA256SUMS.txt`, and the wheel installs cleanly from the release URL.

---

### 3. PyPI trusted publishing

Publish to PyPI so users can install with `pip install seavision` (no URL required).

**Tasks:**
- [ ] Register the `seavision` package name on PyPI (or TestPyPI first)
- [ ] Configure PyPI Trusted Publishing (OIDC) for the `mariolambrette/SeaVision` repository — no API tokens needed
  - On PyPI: add a new publisher → GitHub Actions → repo `mariolambrette/SeaVision`, workflow `release.yml`, environment `pypi`
- [ ] Add a `publish` job to `release.yml` that runs after the GitHub Release upload job:
  ```yaml
  - uses: pypa/gh-action-pypi-publish@release/v1
    with:
      packages-dir: dist/
  ```
- [ ] Add a `publish-testpypi` job that runs on every push to `Main` (or on demand), publishing to TestPyPI for smoke-testing before a real release
- [ ] Update `pyproject.toml` with correct `[project.urls]` (Homepage, Documentation, Source) so the PyPI listing is complete
- [ ] Decide on a pre-release versioning scheme (`1.0.0a1`, `1.0.0rc1`) for TestPyPI smoke runs

**Suggested sequence:** TestPyPI smoke run → confirm install matrix passes → publish to PyPI proper.

**Acceptance criteria:** `pip install seavision` (and `pip install seavision[gui]`, `pip install seavision[edge]`) works from a clean environment on Windows and Linux.

---

### 4. Install matrix smoke tests per persona

Define one smoke test per user persona that runs against a published wheel (not a local editable install).

| Persona | Install command | Smoke test |
|---|---|---|
| Workstation analyst | `pip install seavision[gui]` | `seavision-gui --help` exits 0 |
| Edge operator | `pip install seavision[edge]` | `seavision-edge --help` exits 0 |
| CLI / API developer | `pip install seavision` | `seavision --help` exits 0 |
| Export workflow | `pip install seavision[export]` | `seavision-export --help` exits 0 |
| Full stack | `pip install seavision[all]` | All entry-point commands exit 0; `python -c "import seavision"` succeeds |

**Tasks:**
- [ ] Add a `smoke-test-wheel.yml` workflow that:
  - Runs on `workflow_dispatch` (manually triggered) and after the `release.yml` workflow completes
  - Matrix: `python-version: [3.10, 3.11, 3.12]`, `os: [ubuntu-latest, windows-latest]`
  - Installs the wheel from the latest GitHub Release (or a workflow input URL)
  - Runs each persona smoke test listed above
- [ ] For edge persona: add an `aarch64` runner or QEMU emulation step so the Pi target is covered in CI
- [ ] Record the smoke test matrix results in the release notes template

**Acceptance criteria:** All cells in the matrix pass on both Ubuntu and Windows before any PyPI publish.

---

### 5. Documentation migration

Replace all local-path install instructions with `pip install` from registry examples, while keeping the clone-based developer path clearly labelled.

**Tasks:**
- [ ] **README.md** — update install matrix:
  - Workstation analyst: `pip install seavision[gui]` (no clone)
  - Edge operator: link to Operator Quickstart (wheel URL from release)
  - Developer: keep `git clone` + `pip install -e .[dev]`
- [ ] **docs/edge/Operator Quickstart.md** — replace "download the release bundle from GitHub" step with a direct `pip install <release-url>` one-liner (keeping the bundle-download path as an alternative for air-gapped installs)
- [ ] **docs/edge/Deploy to Raspberry Pi.md** — add a "minimal online path" section: `pip install seavision[edge]==X.Y.Z` on the Pi directly, for operators with internet access
- [ ] **docs/edge/Wheel Runtime.md** — note that wheels are now published to GitHub Releases; update the "where to get the wheel" section
- [ ] **docs/release/Distribution_and_Compatibility.md** — add a "PyPI publishing" section noting OIDC trusted publishing and TestPyPI pre-release policy
- [ ] Remove any remaining `<path-to-wheel>` placeholders from all docs
- [ ] Add a `pip install seavision` badge to README.md once PyPI is live

**Acceptance criteria:** No doc still requires a user to clone the repo unless they are explicitly in the Developer persona section.

---

## Sequencing recommendation

```
Week 1:
  Day 1–2   Workstream 1 — packaging audit and wheel inspection
  Day 3–4   Workstream 2 — GitHub Releases CI workflow (build + upload)
  Day 5     Workstream 4 — smoke test workflow (GitHub Releases wheel)

Week 2:
  Day 1–2   Workstream 3 — TestPyPI trusted publishing, smoke-test pass
  Day 3     Workstream 3 — PyPI publish
  Day 4–5   Workstream 5 — documentation migration
```

---

## Open questions

1. **Package name:** Is `seavision` available on PyPI? Check at https://pypi.org/project/seavision/ before starting Workstream 3.
2. **Air-gapped edge deployments:** Should the GitHub Releases bundle (wheel + artifact files) be kept as an alternative even after PyPI is live? Likely yes — field operators may not have internet on the Pi.
3. **Version pinning for edge:** Should `seavision-edge` installs be pinned to exact versions (`==X.Y.Z`) to prevent unintended upgrades on deployed Pis?
4. **Extras on PyPI vs GitHub Releases:** PyPI supports extras natively; GitHub Release URLs do not. Confirm all edge operator docs use the PyPI path once it is live.
