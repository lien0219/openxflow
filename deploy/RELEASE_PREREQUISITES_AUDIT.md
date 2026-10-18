# OpenXFlow production release prerequisites: read-only audit

Audit snapshot completed: 2026-10-18T09:27:43Z (17:27:43 Asia/Shanghai); API probes preceded that completion time. This is a current remote-state snapshot, not an executed release or proof of CI token write access. Only this report was written by this audit; no GitHub settings, workflows, tags, packages, releases, or production services were changed.

## Decision

**BLOCKED for the first production release.** Main already has an effective PR-only ruleset, but required CI and CODEOWNERS enforcement are missing; formal version tags have no ruleset; remotely installed legacy publishing workflows remain active; complete GHCR version history cannot be read with the available credential. These are separate from local implementation/test completion.

`0.1.0` is a reasonable **provisional** independent OpenXFlow IMAGE_VERSION: no OpenXFlow tags/releases or committed IMAGE_VERSION history were found. It is **not yet certified collision-free** because authorized GHCR enumeration was denied. Do not increase the version automatically to bypass that uncertainty. An authorized package-history read and repeat collision checks immediately before publication are required.

## Git and product version history

- Current feature branch: `feature/openxflow-release-pipeline`, based at `9b1858dfa0ab98b2334e70b724f0f2f22762532d` (`refactor: rebrand Langflow as OpenXFlow`). Other agents' release implementation files were already dirty and were preserved.
- Live `git ls-remote origin`: develop is the same `9b1858dfa0ab98b2334e70b724f0f2f22762532d`; main is `17122e4d76baf51a687e19b418d36d0ab1cbea02`.
- `git tag --list`, `git ls-remote origin 'refs/tags/*'`, and `git log --all -- deploy/IMAGE_VERSION` returned no entries.
- `GET /repos/lien0219/openxflow/tags?per_page=100`: HTTP 200, `[]` (public and authenticated).
- `GET /repos/lien0219/openxflow/releases?per_page=100`: HTTP 200, `[]` (public and authenticated; authenticated read includes otherwise visible drafts).
- Worktree `deploy/IMAGE_VERSION` currently contains `0.1.0` and is untracked; it is a new independent product-version source.
- At the verified remote main commit, root `pyproject.toml` and `src/frontend/package.json` use Langflow `1.12.5`. These are inherited package versions, not evidence of an OpenXFlow `v1.12.5` product release. Keep Langflow/LFX/SDK package versions separate.

## GHCR evidence and remaining uncertainty

Read requests used an existing Git Credential Manager credential only in process memory. No credential was printed, saved in the report, or used to write remotely. No `gh` executable was found in PATH or the checked Program Files/LocalAppData locations; no tool installation was needed.

| Read endpoint | HTTP result | Interpretation |
| --- | --- | --- |
| Unauthenticated `GET /users/lien0219/packages?package_type=container` | 401 | Authentication required. |
| Authenticated `GET /users/lien0219/packages?package_type=container&per_page=100` | 403, `You need at least read:packages scope to list packages.` | Available repo credential cannot enumerate complete package history. |
| Authenticated `GET /users/lien0219/packages/container/openxflow` | 404, `Package not found.` | Cannot establish absence given missing package scope. |
| Authenticated `GET /users/lien0219/packages/container/openxflow/versions?per_page=100` | 404, `Package not found.` | Cannot certify no private/otherwise inaccessible versions. |
| Anonymous `GET https://ghcr.io/v2/lien0219/openxflow/tags/list` | 401 | Anonymous registry access requires authorization. |
| Anonymous `GET https://ghcr.io/token?service=ghcr.io&scope=repository:lien0219/openxflow:pull` | 403, `DENIED` | No anonymous pull token was issued; not proof that the package is absent. |

Before first publication, an account/CI context with package read access must inventory all versions/tags of `ghcr.io/lien0219/openxflow`, check `main-v0.1.0` and all intended version aliases, and preserve the resulting digest/source evidence. CI must fail closed on 401/403 or ambiguous 404 results rather than treating them as an unused version.

## Effective main and tag protection

Authenticated `GET /repos/lien0219/openxflow` returned 200, public repository, default branch main. The personal credential reports repository admin/push permissions; this does **not** establish `GITHUB_TOKEN` permissions or bypass ability.

| Read endpoint | HTTP result | Observed configuration |
| --- | --- | --- |
| `/repos/lien0219/openxflow/branches/main/protection` | 404, `Branch not protected` | No classic branch-protection record; rulesets must also be checked. |
| `/repos/lien0219/openxflow/rules/branches/main` | 200 | Effective deletion, non-fast-forward, and pull-request rules from ruleset 18865751. |
| `/repos/lien0219/openxflow/rulesets?includes_parents=true` | 200 | Exactly one ruleset: active branch ruleset `Protect main branch`; no tag ruleset. |
| `/repos/lien0219/openxflow/rulesets/18865751` | 200 | Targets `~DEFAULT_BRANCH`; no excludes; `bypass_actors: []`; `current_user_can_bypass: never`. |
| `/repos/lien0219/openxflow/branches?per_page=100` | 200 | Main `protected: true`; develop and other returned branches unprotected. |

Effective PR parameters: `required_approving_review_count: 0`, `require_code_owner_review: false`, `require_last_push_approval: false`, `required_review_thread_resolution: true`, `allowed_merge_methods: [merge]`. No `required_status_checks` rule exists. Repository merge/squash/rebase settings are all enabled, but this main ruleset currently permits only merge commits.

Required administrator work before the first production merge:

1. Add required CI/status checks for release policy tests and relevant build/test/security validation, using actual stable check context names from successful runs.
2. Add and enforce CODEOWNERS review for production workflow, release policy scripts, Dockerfile, deployment files, and ownership policy. Main currently has no `.github/CODEOWNERS` at the audited SHA. Review thresholds should meet the chosen governance policy.
3. Add an active tag ruleset covering `refs/tags/v*` that prevents update and deletion. Define narrowly scoped creation authorization without granting tag mutation bypass; verify the release workflow's real token can create the tag while updates/deletions remain denied.
4. Retain main's no-deletion/no-force-push/PR requirement and empty bypass list. Verify the new workflow reads the effective rules, including rulesets; a classic-protection-only probe would incorrectly report main as unprotected.

`/rules/tags/v*` returned 404, but this is not used as tag-protection evidence: there is no analogous supported wildcard endpoint. The complete ruleset listing is the evidence that no tag ruleset is configured.

## Actions configuration and CI-only proof boundary

- `GET /repos/lien0219/openxflow/actions/permissions`: HTTP 200, `enabled: true`, `allowed_actions: all`, `sha_pinning_required: false`.
- `GET /repos/lien0219/openxflow/actions/permissions/workflow`: HTTP 200, `default_workflow_permissions: write`, `can_approve_pull_request_reviews: false`.
- `GET /repos/lien0219/openxflow/actions/permissions/selected-actions`: HTTP 409, all actions and workflows are allowed.
- `GET /repos/lien0219/openxflow/actions/permissions/fork-pr-contributor-approval`: HTTP 200, `first_time_contributors`.

Change the repository default workflow permission to read and require explicit minimum job permissions for publication. Consider an allowed-actions policy and immutable action pins; this audit did not change settings. A personal admin API read cannot prove GHCR package ownership/linkage, package inheritance, a future event's token permission, or whether configured tag protection will permit `github-actions` tag creation. Real controlled CI must establish build/push/digest/tag/release behavior; no actual push or release was attempted here.

## Installed legacy publishing entry points and other refs

`GET /repos/lien0219/openxflow/actions/workflows?per_page=100&page=1` returned 200 with 100 records; page 2 returned 200 with 19 records; total 119. All listed publishing workflows below have `state: active` in the remote workflow catalog. Active catalog entries can outlive removal from current source, so inventory must be checked against actual current main/ref content.

Verified at remote main `17122e4d76baf51a687e19b418d36d0ab1cbea02` using `git show origin/main:.github/workflows/<file>`:

| File / workflow id | Existing entry or write behavior | Required disposition |
| --- | --- | --- |
| `release.yml` / 337944318 | Manual dispatch; selectable dry-run off; `uv publish` at lines 1393/1485/1552; calls Docker publication; `contents: write` release job at 1667; release action at 1734. No OpenXFlow main-PR-only gate. | Isolate/disable external publishing in the fork. |
| `create-release.yml` / 337944292 | Manual dispatch; release action line 28 takes user-controlled tag/ref. | Disable/isolate write entry. |
| `docker-build-v2.yml` / 337944298 | `workflow_call` and manual dispatch; user-selectable registry push; official `langflow-ai`/Docker Hub targets. | Disable/isolate registry publication. |
| `docker-nightly-build.yml` / 337944301 | Reusable/manual; `push_to_registry`; official registry targets. | Disable/isolate registry publication. |
| `docker-nightly-build-arch.yml` / 337944300 | Reusable architecture publisher used by nightly workflow. | Isolate registry publication, preserve build-only behavior if needed. |
| `nightly_build.yml` / 312697569 | Schedule/manual; existing `github.repository == 'langflow-ai/langflow'` job guards mean the guarded upstream jobs already skip in OpenXFlow. | Preserve/strengthen fork isolation; do not call this an observed successful fork publication. |
| `release_nightly.yml` / 337944323 | Reusable PyPI/Docker publication. | Isolate writes even if callers are currently guarded. |
| `release-lfx.yml` / 337944317 | Manual; global contents/packages write; `uv publish` line 203; GitHub release action line 340. | Disable/isolate writes. |
| `release_bundles.yml` / 337944320 | Manual bundle publishing. | Disable/isolate writes. |
| `desktop-release.yml` / 315534386 | Manual and desktop tag push; contents write; `inputs.publish_release` can create release. | Disable/isolate writes under strict single production release entrance. |

Current remote refs also contain `.github/workflows/prepare-release-tag.yml`: GitHub contents API returned 200 on develop, official, and sync/langflow-latest, but 404 on main. Those versions contain manual dispatch, contents write, `git push origin`, and optional `git push --force-with-lease` of a tag. Verified current official SHA `972d56c47d3830d17060ee85cfaad152df823041` and sync/langflow-latest SHA `7becf26cf6d5838d75cd6dcf07b4c883a07e63cf`; the latter differs from the local stale tracking ref and was inspected through the live API.

Local changes to a new workflow cannot update existing remote main or other branch workflow definitions. Do not claim the remote bypass surface is closed before the intended branch changes are merged and the remote inventory/repository controls are reviewed. Workflow source isolation, tag protections, minimum default token permissions, credential/environment restrictions, and administrator disabling of retired release workflows form the cutover boundary. No legacy secret value or presence was inspected, so whether PyPI/Docker credentials currently permit those paths is NOT PROVEN.

## ModuRelay comparison

- Read local `D:/project/modurelay/.goreleaser.yaml`: GoReleaser v2 builds Go executables for linux/windows/darwin amd64/arm64 (windows arm64 omitted), injects version/commit/date/build/deployment values, archives deploy files, and emits `checksums.txt`. It explicitly delegates container publication to `publish-main-image.yml`.
- Read local ModuRelay `publish-main-image.yml` and `release.yml`: independent `deploy/IMAGE_VERSION`, immutable version tags, OCI source-revision checks, exact-source validation, image-first release, GHCR auth with `GITHUB_TOKEN`, and rollback documentation are useful patterns. Its existing push-main and tag/manual release triggers are **not** compliant with this OpenXFlow user's stricter PR-merged-main-only trigger requirement; do not copy those triggers.
- Live `GET /repos/lien0219/modurelay/releases/tags/v0.4.6`: HTTP 200; `ModuRelay 0.4.6`, published `2026-10-17T18:06:35Z`, target main. Body identifies main commit `6b5035a29ad308e71334be819ff15e9d9521c856` and image `ghcr.io/lien0219/modurelay:main-v0.4.6`.
- Release assets are `checksums.txt`, darwin amd64/arm64, linux amd64/arm64 tarballs, and windows amd64 zip. Body explicitly states image rollback does not restore the database. This is reference evidence, not a live validation of OpenXFlow or the ModuRelay image.

## Read-only audit limitations

No image was built or pulled, no package/tag/release was created, no production endpoint/database was contacted, and no Actions setting was changed. No actual `GITHUB_TOKEN` token was available to this local audit. The GHCR history, protected-tag token path, real CI build/scan/smoke, architecture manifests, write permissions, and real retry behavior remain NOT RUN or BLOCKED as described above.

## Docker build input availability (read-only)

Checked at `2026-10-18T09:27:05Z` through `09:27:43Z` (UTC). Current Dockerfile defaults are `UV_VERSION=0.10.4`, `PYTHON_IMAGE=registry.access.redhat.com/ubi10/python-314-minimal`, and `NODE_VERSION=24.21.0`. These are input-reachability checks only, not a successful image build, vulnerability scan, or runtime test.

| Input / read command | Result |
| --- | --- |
| `docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.10.4` | Exit 0; OCI index digest `sha256:4cac394b6b72846f8a85a7a0e577c6d61d4e17fe2ccee65d9451a8b3c9efb4ac`; linux/amd64 and linux/arm64 manifests present. |
| `docker buildx imagetools inspect registry.access.redhat.com/ubi10/python-314-minimal:latest` | Exit 0; OCI index digest `sha256:3754d6dacac3177e62637420cadf7dcf438e390f664c527b0457a79653a47488`; linux/amd64 and linux/arm64/v8 manifests present (also s390x and ppc64le). |
| HEAD `https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-x64.tar.xz` | HTTP 200; content length 31890184. |
| HEAD `https://nodejs.org/dist/v24.21.0/node-v24.21.0-linux-arm64.tar.xz` | HTTP 200; content length 30843004. |
| `docker buildx version` / Docker server version | buildx `v0.36.1-desktop.1`; server `29.7.2`. |

The UBI Dockerfile argument omits an explicit tag, therefore resolves mutable `latest`. Pin approved base indexes by digest for reproducible builds and record the actual build provenance. Package repositories, all locked wheels/provider dependencies, `microdnf` package availability, Node checksum verification, actual frontend build, and runtime startup were not verified by these metadata-only checks. No image layers were pulled by this audit.
