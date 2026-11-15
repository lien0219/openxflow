# CI Stability Implementation Plan

**Goal:** Resolve the current branch's confirmed CI failures and validate the affected checks together before another push.

**Approach:** Audit GitHub jobs for the exact commit, reproduce independent failures, apply narrowly scoped fixes, and run the relevant complete suites. Preserve existing assertions, security checks, unrelated changes, and Git history.

**Baseline:** `5ca48feae4ed0a3fe51477ed8df2ebebd8de1bbd`, branch `sync/langflow-20261115`.

## Tasks

- [x] Read repository guidance and collect current-commit job conclusions and logs.
- [x] Reproduce the AuthModal timeout and subsequent interleaved input failure with a stricter local 2-second diagnostic budget. The unmodified suite fails both affected cases, matching CI.
- [x] Update `src/frontend/src/modals/authModal/__tests__/AuthModal.test.tsx` to enter long configuration values with real paste events. Keep short host/port typing and all save/synchronization assertions.
- [x] Run the same 2-second diagnostic command after the change, then run the complete Jest suite with coverage and TypeScript checks.
- [x] Wait for every baseline job to finish and inspect independent failures and retried failures, rather than counting downstream report failures twice.
- [x] Fix the manual-login reload redirect loop and wait for successful login plus authenticated content before cleanup. Remove the same init-script redirect bug from the other affected specs.
- [x] Reproduce and fix the authenticated ORM user expiring after a default-project race rollback; retain allow and deny behavior.
- [x] Reproduce and fix old-document requests delivered after navigation starts; preserve pending new-document requests, same-document navigation, aborted navigation, and observed server errors.
- [x] Run CI script tests, frontend utility/i18n checks, and relevant Playwright regressions where permitted. Record unavailable checks explicitly.
- [x] Refresh remote status and review the full patch. Do not stage, commit, push, or change CI gates.

## Verified So Far

- The unchanged AuthModal suite reproduced both CI symptoms with a 2-second diagnostic timeout; the fixed suite passes all 8 cases with the same stricter limit.
- Complete frontend Jest suite, including accessibility: **769 suites / 8280 tests passed**, with coverage. Focused auth regressions: **65 passed**. AuthModal also passes under Linux/Node 22 with coverage.
- TypeScript and the frontend production build pass. Biome passes for the changed frontend files; Ruff check and format check pass for the backend changes.
- Linux Python 3.13 CI script suite: 1681 passed, 1 skipped. Windows-only runs additionally encounter shell-path and CRLF test-harness limitations; use the Linux result for the CI workflow contract.
- Frontend utility tests: 63 passed. i18n checker tests: 12 passed; extraction and all 7 locale parity checks pass.
- Browser regressions for cleanup, document request lifecycle, and manual-login setup: **14 cases repeated three times / 42 passed**, using Chromium and 2 workers.
- Backend flow creation, folder integrity, concurrency, and route guard checks: **57 passed**. Complete authorization service tests plus the new real-session rollback regression: **363 passed** (overlapping sets; do not add the totals).
- Full local application UI startup was rejected by execution policy. The loopback browser regressions and backend tests do not substitute for a full application E2E rerun. No policy bypass attempted.
- All four remote Jest shard artifacts were inspected: only the AuthModal save test exceeds 3 seconds. The other reported Jest failures are downstream summaries.
- Previous backend performance failures followed cancellation of the old commit's tests and explicitly report missing/interrupted shards; they are not independent backend test failures.

## Completed Remote Audit

Run `43706693306` on baseline `5ca48fe` finished with **79 success, 6 skipped, 6 failure**. All **30 backend groups** passed, as did Docker, docs build and accessibility, integrations, CLI, LFX on the workflow Python versions, S3, starter templates, and 15/16 browser shards.

The six red checks collapse to two independent test failures (AuthModal and the normal-user getting-started scenario), plus four reporting/final gates. Reviewing successful jobs also found a retried flow-create 500 and two retried request-lifecycle errors; these were fixed in this patch rather than dismissed because retries passed.

Confirmed causes and regressions:

1. Sequential typing of long OAuth form values exceeded Jest's budget and continued into the next test. Use awaited paste events, retain all saved-value assertions.
2. An init script restored `testMockAutoLogin=true` on reload. Authenticated login/home guards then redirected to one another, producing thousands of successful refresh requests. Keep only the manual-login environment/endpoint setup persistent; remove the transient flag before submitting and await the authenticated home page.
3. Default-project creation can roll back a shared session after losing an insert race. Refresh an expired ORM user asynchronously before CREATE authorization, so the guard and route do not trigger `MissingGreenlet`. The real-session regression failed before the fix and passes for both allowed and denied requests afterwards.
4. An XHR can be reported after the navigation request but before document replacement. Include these late requests and freeze the abandoned set at frame commit; the replacement-document binding confirms cleanup without retiring the new document's requests. The forced event-order regression failed before the fix and passes with the other lifecycle invariants.

The changes remain local and uncommitted. The fixed patch has not been pushed, so this audit does **not** claim a green remote run for it. The 6 skipped baseline checks remain skipped; this work does not promise that future provider, runner, PR-context, or base-branch changes cannot fail.

## Commands

Run from `src/frontend`:

```powershell
$env:CI='true'
node node_modules/jest/bin/jest.js --runInBand --watchAll=false --coverage=false --testTimeout=2000 --runTestsByPath src/modals/authModal/__tests__/AuthModal.test.tsx
node node_modules/jest/bin/jest.js --ci --coverage --watchAll=false --maxWorkers=2
node node_modules/typescript/bin/tsc --noEmit --pretty false
npm run test:e2e-utilities
npm run check:i18n
npm run test:i18n-checker
```

Run from the repository root:

```powershell
$env:PYTHONPATH='scripts/ci'
uv run --no-sync python -m pytest scripts/ci/ -q --tb=short --no-header -o addopts=
git diff --check
```
