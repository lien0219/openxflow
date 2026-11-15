# How to contribute to Langflow

Thank you for your interest in contributing!

## How to Contribute

### OpenXFlow branches and PR preflight

For this OpenXFlow repository, target `develop` from feature, fix, and
`sync/**` branches. Promote validated changes from `develop` to `main` for
release. Keep `official` as an upstream mirror. The Langflow contribution
instructions below apply when contributing back to the upstream project.

Before requesting review:

1. Run the tests for the changed behavior and record the tested commit SHA.
2. For workflows, Dockerfiles, dependency pins, lockfiles, or component indexes,
   set `PYTHONPATH=scripts/ci` and run
   `uv run --no-sync python -m pytest scripts/ci/ -q`. In PowerShell use
   `$env:PYTHONPATH='scripts/ci'` before the command. The canonical
   CI-script environment is Linux with Python 3.13 and Node.js 22; report
   Windows-only harness limitations separately from product failures.
3. For component changes, regenerate with `make build_component_index` in the
   Linux CI environment and include the generated file. Dependency versions
   come from `uv.lock` so optional local installations cannot change them.
4. Run `git diff --check`. Keep dependency expectations and generated-file
   integrity checks enabled.
5. Check the PR's own required jobs on the current commit. List skipped and
   not-run checks separately; a green branch run alone is not merge approval.

Branch CI runs the shared CI-script tests before a PR exists. `sync/**`
branches also request the complete main CI job set instead of only checking
the last push. This catches more issues early without guaranteeing that
PR-only permissions, base-branch changes, or external services cannot fail.

For frontend changes, run the complete local checks from `src/frontend` before
the next push. In PowerShell:

```powershell
$env:CI='true'
npm run check:i18n
npm run test:i18n-checker
npm run test:e2e-utilities
npx --no-install tsc --noEmit --pretty false
npm test -- --ci --coverage --watchAll=false --maxWorkers=2
npm run build
```

This includes accessibility unit tests as well as the ordinary Jest suites.
Run affected Playwright scenarios separately against an isolated test database;
unit tests and a successful build do not replace browser integration checks.
Keep the CI run for the current commit running to completion before evaluating
its result: pushing another commit cancels the previous branch run, leaving
its shard reports incomplete.

For form tests, type short values when individual keystrokes are relevant.
Use awaited `user.paste()` after focusing or clearing the field for long URLs,
tokens, and configuration text. Keep the saved-value assertions. A timed-out
`user.type()` can continue dispatching keys into the following test, so fix the
input sequence before adding retries or increasing the suite timeout.

For manual-login browser tests, use `mockAutoLoginDisabled` and
`submitLoginAndRequireSuccess`, then wait for authenticated page content before
cleanup or navigation. Keep temporary forced-login flags out of init scripts:
those scripts rerun on every document and can reintroduce redirects after a
successful login. Cover reloads as well as the initial sign-in.

### Contributing to upstream Langflow

1. Fork the [Langflow GitHub repository](https://github.com/langflow-ai/langflow).
2. Create a new branch for your changes.
3. Open a GitHub pull request against the active `release-X.Y.Z` release candidate branch.
Do not target `main`.
For example, if the latest released version is `1.8.0`, your pull request should target the `release-1.9.0` branch.
Include a clear title and description.
Reference any issues fixed, for example `Fixes #1234`.
Ensure your PR title follows [semantic commit conventions](https://www.conventionalcommits.org/).
4. A maintainer will review your PR and may request changes.

## Development Environment Setup

For detailed instructions on setting up your local development environment, see [DEVELOPMENT.md](./DEVELOPMENT.md).

## Documentation Contributions

Langflow documentation is built with [Docusaurus](https://docusaurus.io/).
For setup instructions, see [DEVELOPMENT.md](./DEVELOPMENT.md).

## Additional Guides

- [Contribute Bundles](./docs/docs/Contributing/contributing-bundles.mdx)
- [Contribute Components](./docs/docs/Contributing/contributing-components.mdx)
- [Contribute Tests](./docs/docs/Contributing/contributing-component-tests.mdx)
- [Contribute Templates](./docs/docs/Contributing/contributing-templates.mdx)

Thank you for helping improve Langflow!
