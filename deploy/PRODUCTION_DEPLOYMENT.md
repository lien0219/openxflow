# OpenXFlow production deployment

This deployment shape runs one OpenXFlow API process with one application
worker and external PostgreSQL, pgVector, Redis, and S3-compatible storage.
Compose does not create or publish those stateful services. Put TLS and public
authentication in a reverse proxy; the application binds to `127.0.0.1:7860`.
The host needs Docker Compose v2 and Python 3.10+ for the verification helper.

## Host preparation

```bash
cd deploy
cp production.env.example .env
chmod 600 .env
mkdir -p data/config
chmod 700 data
```

Replace every `replace-me` value (or remove both AWS credential values when the
host provides an approved workload identity). Use one stable URL-safe 32-byte Fernet key in
`LANGFLOW_SECRET_KEY` and one stable `LANGFLOW_CACHE_SIGNING_KEY` across future
restarts. Set `LANGFLOW_AUTO_LOGIN=false`, `LANGFLOW_DEPLOYMENT_PROFILE=prod`,
and use external service endpoints. Cache, queue, and rate-limit Redis URLs all
use database `0`; managed Redis Cluster services that do not support logical DBs
need separate endpoints or a provider-specific compatible URL.

The preflight checks require PostgreSQL, the `vector` extension, S3, and the
selected Redis services to be reachable. The current branch has no standalone
`langflow worker` command: `LANGFLOW_JOB_QUEUE_TYPE=redis` is still validated by
the application, while the background execution implementation falls back to
the in-process executor. This is a documented cluster limitation, not a claim
of Kubernetes readiness.

## Upgrade gate

Before each deployment, an operator must create a local `.upgrade-gate.json`
(ignored by Git) that binds the target digest and migration fingerprint to an
approved backup and restore drill. The deployment helper rejects missing,
expired, mismatched, or placeholder gate records. For example:

```json
{
  "schema": 1,
  "target_digest": "ghcr.io/lien0219/openxflow@sha256:<64 hex>",
  "previous_digest": "ghcr.io/lien0219/openxflow@sha256:<64 hex>",
  "revision": "<40 hex source SHA>",
  "version": "0.1.1",
  "configuration_sha256": "<64 hex>",
  "migration": {"schema": 1, "uid": 1000, "heads": ["<migration head>"], "alembic_sha256": "<64 hex>", "models_sha256": "<64 hex>"},
  "backup_reference": "ticket-or-object-store-backup-id",
  "restore_drill_reference": "ticket-or-restore-test-id",
  "migration_reviewed": true,
  "application_rollback_safe": true,
  "approved_at": "2026-10-18T00:00:00Z"
}
```

For the first deployment, set `previous_digest` to JSON `null`; later gates
must contain the exact digest and metadata recorded by `.deployed-image`.

The image starts the application with `langflow run --workers 1`. Application
startup **does run Alembic migrations**; the script does not claim otherwise.
The script stops the old API before starting the new one so two containers never
run migrations concurrently. It never executes a database downgrade or restores
database state.

## Deploy and recover

Use a version tag, full source-SHA tag, or manifest digest. Mutable `main`,
`latest`, short SHAs, and other registries are rejected:

```bash
./deploy-main.sh ghcr.io/lien0219/openxflow:main-v0.1.1
./deploy-main.sh ghcr.io/lien0219/openxflow:sha-<40-character-merge-sha>
./deploy-main.sh ghcr.io/lien0219/openxflow@sha256:<64-hex-digest>
```

The helper resolves tags to a digest, verifies OCI source/revision/version,
host architecture, non-root user, offline migration fingerprint, Compose
configuration, and production environment. It waits for `healthy`; `running`
alone is never success. Only after health passes does it atomically replace
`.deployed-image`, which records the last verified digest and metadata.

On startup or health failure, automatic application rollback is allowed only
when the previous digest and full metadata record still verify, the migration
fingerprint and resolved configuration are unchanged, and the gate explicitly
marks rollback safe. Otherwise the helper fails closed and directs the operator
to the approved backup/migration recovery procedure. A successful application
rollback never rolls back PostgreSQL, Redis, or S3 data.

The helper uses `.deploy.lock` to serialize host operations. Never delete or
edit `.deployed-image` or `.upgrade-gate.json` while a deployment is running.

## Checks and limitations

Run the offline deployment tests without any production credentials:

```bash
uv run --no-project --with pytest pytest scripts/ci/test_openxflow_deployment.py -q
```

Real GHCR pulls, production database backups, migration upgrades, reverse-proxy
checks, and Kubernetes acceptance are intentionally **NOT RUN** in this change.
