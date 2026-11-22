# ModuRelay provider implementation plan

> Execute inline using the test-driven-development and verification-before-completion skills. Keep all work uncommitted in the authorized checkout.

**Goal:** Configure ModuRelay at `https://ai.zhihengxiangyu.com`, discover the account's live model IDs, and use them in workflows without a static model whitelist.

**Architecture:** Ship an independent `lfx-modurelay` extension with isolated credentials, live discovery and a gateway request component. Existing Language Model and Embedding Model components handle their respective protocols. A `gateway` model type and the request component handle media, reranking and custom JSON or multipart APIs, including asynchronous job retrieval. Model metadata selects an initial operation; users can select an explicit endpoint for aliases whose capabilities are not advertised.

**Constraints:** Preserve provider policy, per-user credential resolution, environment isolation, SSRF protection and redirect rejection. Validation uses GET `/v1/models` and does not create billable completions. Do not commit, push or deploy. Real gateway acceptance requires a user-provided gateway API key; browser session cookies are not API keys.

## 1. Provider discovery and runtime

- [x] Add `src/bundles/modurelay/tests/test_modurelay_provider.py` covering extension registration, root and `/v1` URLs, independent bearer credentials, unlisted names, model classification, malformed catalogs, authentication failures, chat/tools/streaming and string embeddings using real SDKs with HTTP test transports.
- [x] Observe the missing extension fail through `load_extension(bundle_root)` before creating the bundle.
- [x] Create the bundle manifest, package metadata, README and `discovery.py`. Implement `fetch_live_modurelay_models(user_id, model_type)` and `validate_modurelay_credentials(provider, variables, model_name=None)`.
- [x] Add `default_value` support for non-secret endpoint variables and normalize configured URLs consistently during runtime. Use metadata-controlled embedding kwargs to preserve plain string inputs.
- [x] Add the package to root dependencies and uv workspace, regenerate `uv.lock` with `uv lock`, then sync the full application and backend dev dependencies.

## 2. Arbitrary gateway model operations

- [x] Add `gateway` to persisted model-status and policy key types and the frontend `ModelType`; test that typed deny and enable decisions remain distinct from `llm` and `embeddings`.
- [x] Allow a provider to advertise discovery of all types in one request. Test that a media-only catalog is retained and does not enter language/embedding selectors.
- [x] Add `ModuRelayRequestComponent` to the bundle: live model dropdown, prompt, method, endpoint, JSON body, optional base64 multipart files, configurable timeout, JSON or base64 binary output. GET supports querying generation jobs and downloading results.
- [x] Test exact outgoing model IDs, endpoint resolution, JSON payloads, multipart bytes, binary results, policy denial before credential/network access, credential-host protection and upstream errors.

## 3. Settings and reliable model toggles

- [x] Add UI tests for the default endpoint placeholder and gateway model section, with translated help directing media/custom operations to ModuRelay Request.
- [x] Test explicit enable intent surviving static/live catalog default changes, then retain explicit status entries for every user-enabled model.
- [x] Reproduce duplicate refreshes with real TanStack Query requests, then remove the redundant toggle invalidation and ensure refresh joins in-flight requests.
- [x] Display gateway models in a separate section while preserving existing language/embedding filters and optimistic state across all types.

## 4. Verification and delivery

- [x] Run focused provider, model identity, policy and extension tests with `uv run --no-sync`.
- [x] Run focused Jest tests, TypeScript, i18n checks and frontend build.
- [x] Run CI script tests because workspace dependencies and the lockfile change. Regenerate component metadata and its integrity hash together in a supported Linux environment if the index includes the new bundle.
- [x] Run formatting/lint for changed files and `git diff --check`; inspect final diff for credential leakage and unrelated changes.
- [x] Report local checks and live acceptance limitations separately. Leave all changes uncommitted.

## Verification record (2026-11-17)

Tested the uncommitted working tree on `develop`, based on `a51ffb61b4`.

- Provider, request, OpenAI Compatible, model-status identity, live-only provider,
  model-policy, unified-model and model-utils regressions: **235 passed**.
  Command: `uv run --no-sync python -m pytest src/bundles/modurelay/tests src/bundles/openai-compatible/tests src/backend/tests/unit/api/v1/test_model_status_identity.py src/backend/tests/unit/api/v1/test_models_live_only_providers.py src/backend/tests/unit/api/v1/test_models_provider_policy.py src/backend/tests/unit/test_unified_models.py src/backend/tests/unit/base/models/test_model_utils.py -q -o addopts='' -o log_cli=false --tb=short`.
- LFX provider registry, credential policy, model-provider policy and extension
  manifest/schema/registration tests: **278 passed, 1 skipped**. These ran with
  `LFX_TEST_ALLOW_LANGFLOW=1`, the existing opt-in for the full application venv.
- Model-provider modal and shared model-refresh Jest suites: **222 passed** in
  12 suites. Command: `npm.cmd test -- src/modals/modelProviderModal/__tests__ src/hooks/__tests__/use-refresh-model-inputs.test.ts --watchAll=false --maxWorkers=2`
  from `src/frontend`.
- Frontend TypeScript (`npx.cmd --no-install tsc --noEmit --pretty false`),
  i18n parity (`npm.cmd run check:i18n`), i18n checker (**12 passed**),
  E2E utilities (**63 passed**) and `npm.cmd run build`: passed. The utility
  tests are not browser acceptance. Build emitted chunk-size and locale-import warnings.
- Release inventory and bundle-profile tests: **26 passed**. Command:
  `uv run --no-sync python -m pytest scripts/ci/test_release_inventory.py scripts/ci/test_bundle_profiles.py -q -o addopts='' -o log_cli=false --tb=short`.
- Full CI-script suite: **1619 passed, 62 skipped, 7 failed** on Windows.
  Four coverage-advisor shell cases and two Docker Compose startup cases fail
  around shell execution (`bash` / `/bin/sh`); the release-auth archive assertion
  fails on CRLF versus LF bytes. These test and product files were not changed.
  Linux CI was not run. The complete output is in `.tmp/modurelay-ci-scripts.log`.
- `uv lock --check`: passed; existing third-party dependency versions and platform
  markers were preserved. The enterprise profile lock was regenerated with the
  repository tool.
- `uv build --package lfx-modurelay --out-dir .tmp/modurelay-dist`: passed for
  the final sdist and wheel. All six packaged source files match the working
  tree byte-for-byte and the wheel includes the extension entry point.
  Installed-distribution discovery registers ModuRelay and builds the Request
  component template successfully.
- Targeted Ruff formatting/lint and `git diff --check`: passed. No changes are
  staged, committed, pushed or deployed.

The component-index builder scans `lfx.components`. This component is supplied
through an installed extension and loaded by `import_extension_components`, so
it does not enter the core static index; no generated index/hash change was made.

## Acceptance boundaries

- All model IDs returned by the API key's `/v1/models` catalog are retained,
  including aliases absent from a static model list. Capabilities guide the
  initial endpoint; aliases without metadata may need an explicit endpoint
  and native JSON parameters in ModuRelay Request.
- SDK and gateway tests use HTTP test transports. No valid gateway API key was
  available for live discovery, inference, media generation or billing checks.
  Browser session cookies were not used. One early test with a dummy key reached
  an invalid gateway route and returned 404; request-test fixtures now reject
  network access unless an HTTP test transport is installed.
- Real calls still require permission from the key's group and support from the
  gateway and upstream API. The Request component covers HTTP JSON, multipart,
  binary output and asynchronous job retrieval. Realtime WebSocket sessions
  are not implemented.
- No real-browser acceptance or production deployment was performed.
