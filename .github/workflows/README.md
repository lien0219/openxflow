# OpenXFlow publication boundary

The sole OpenXFlow production publication entry point is
`openxflow-production-release.yml`, following a successful PR merge into `main`.
Legacy Langflow writers require `github.repository == 'langflow-ai/langflow'`
at the job boundary. Dispatch inputs, tag pushes, `always()` and reusable
workflow calls cannot override this repository condition in a fork. Both the
caller and reusable image writer carry their own guards.

| Legacy workflow | Write capability isolated to the upstream repository |
| --- | --- |
| `release.yml` | PyPI, draft/final GitHub Release, and Docker build calls |
| `create-release.yml` | Git tag and GitHub Release |
| `prepare-release-tag.yml` | Git tag creation and candidate tag replacement |
| `docker-build-v2.yml` | Docker Hub/GHCR images and multiarch manifests |
| `docker-nightly-build.yml` | Nightly image calls and registry manifests |
| `docker-nightly-build-arch.yml` | Both registry build/push attempts |
| `nightly_build.yml` | Nightly tag deletion/creation and release workflow call |
| `release_nightly.yml` | Nightly PyPI and Docker workflow calls |
| `release-lfx.yml` | Prepared source tag, PyPI, Docker Hub/GHCR, GitHub Release |
| `release_bundles.yml` | Bundle publication to PyPI |
| `desktop-release.yml` | GitHub Release publication, including tag/manual triggers |

Artifact-only package builds and standalone bundle smoke tests retain their
existing behavior. Desktop builds use `contents: read`, build with
`--publish never`, and upload Actions artifacts. Only the upstream-only desktop
publish job requests `contents: write`. Ordinary CI and localization/autofix
branch writers are retained; they are not production tag, package, or image
publishers.

Run `scripts/ci/test_openxflow_workflow_isolation.py` to parse workflows, simulate
fork/upstream admission, check reusable callers, and inventory release writers
across the workflow directory. Keep these checks when merging upstream changes:
new or renamed writer jobs must be audited and receive repository guards.
Configure required Code Owner reviews for the release/deploy surfaces in
`.github/CODEOWNERS`; workflow code does not configure GitHub branch protection.

## Upstream reusable Docker workflows

The deprecated `docker-build.yml` reusable workflow has been removed. Callers
in the upstream repository must use the workflow matching the publication contract:

- Use `docker-build-v2.yml` for normal releases (`release`, `base`,
  `main`, `main-all`, `ep`, and `nightly-bundle`).
- Use `docker-nightly-build.yml` for nightly base and main image builds. It
  retries a failed architecture once on a fresh runner and publishes manifests
  only after every architecture succeeds.

External callers should pin a commit or tag instead of following a mutable
branch so interface changes can be adopted deliberately.
