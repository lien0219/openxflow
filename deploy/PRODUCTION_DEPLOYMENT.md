# OpenXFlow production deployment

`production.env.example` is the application configuration baseline for long-term
production. Initial single-instance tests use that same baseline with local
dependency endpoints and HTTP access overrides. Replica count is a deployment
choice, separate from this environment contract.

The current `docker-compose.prod.yml` and deployment helper start one OpenXFlow
API container with one worker and external PostgreSQL, pgVector, Redis, and
S3-compatible storage. This is the initial deployment path; it does not define
the final production replica count.
Compose does not create or publish those stateful services. Put TLS and public
authentication in a reverse proxy; the application binds to `127.0.0.1:7860`.
The host needs Docker Compose v2 and Python 3.10+ for the verification helper.
For dependencies running in Docker on the same host, follow
[SINGLE_NODE_DOCKER.md](SINGLE_NODE_DOCKER.md).

## Host preparation

```bash
cd deploy
cp -n production.env.example .env
chmod 600 .env
sudo install -d -o 1000 -g 0 -m 0700 data data/config
```

The application runs as UID 1000. These directory commands assume the default
`OPENXFLOW_DATA_DIR=./data`; use the configured host path if you change it.
`cp -n` preserves an existing `.env`; review that file before reusing it.

Replace every `replace-*` value (or remove both AWS credential values when the
host provides an approved workload identity). Use one stable URL-safe 32-byte Fernet key in
`LANGFLOW_SECRET_KEY` and one stable `LANGFLOW_CACHE_SIGNING_KEY` across future
restarts. Set `LANGFLOW_AUTO_LOGIN=false`, `LANGFLOW_DEPLOYMENT_PROFILE=prod`,
and use external service endpoints. Cache, queue, and rate-limit Redis URLs all
use database `0`; managed Redis Cluster services that do not support logical DBs
need separate endpoints or a provider-specific compatible URL.

Set `LANGFLOW_SUPERUSER` and `LANGFLOW_SUPERUSER_PASSWORD` for the initial admin
account; public signup is disabled in the template. HTTPS cookies are enabled;
set `LANGFLOW_CORS_ORIGINS` to the exact browser origin(s). For HTTP access through
an SSH tunnel, explicitly override both `LANGFLOW_ACCESS_SECURE` and
`LANGFLOW_REFRESH_SECURE` to `false`.

With a reverse proxy or load balancer, enable `LANGFLOW_RATE_LIMIT_TRUST_PROXY`
only after it overwrites forwarded client headers and direct API access is
restricted. Otherwise requests share the proxy's IP rate-limit bucket.

For S3-compatible storage that requires path-style requests, install the AWS
configuration file and uncomment `AWS_CONFIG_FILE` in `.env`:

```bash
sudo install -o 1000 -g 0 -m 0600 aws-config.example data/config/aws-config
```

The AWS SDK reads `s3.addressing_style=path` from this file;
`AWS_S3_FORCE_PATH_STYLE` is not an application setting.

The preflight checks require PostgreSQL, the `vector` extension, S3, and the
selected Redis services to be reachable. The current branch has no standalone
`langflow worker` command: `LANGFLOW_JOB_QUEUE_TYPE=redis` is still validated by
the application, while the background execution implementation falls back to
the in-process executor. This is a documented cluster limitation, not a claim
of Kubernetes readiness.

## Multiple API instances

One worker **per replica** is compatible with a future fleet of API replicas.
Increasing workers inside a container and increasing the number of containers
are separate choices. Adding `LANGFLOW_WORKERS` to `.env` does not override the
current Compose command or the deployment helper's one-worker check.

The application configuration contract for that fleet is:

| Configuration | Across API replicas |
| --- | --- |
| Application DB and vector store | Reach the same application database and vector dataset |
| Cache, build-event queue and rate limits | Use the same respective Redis stores; keep the queue in Redis mode on every replica |
| Object storage | Use the same bucket and namespace with consistent credentials or workload identities |
| Encryption and cache signing | Keep `LANGFLOW_SECRET_KEY` and `LANGFLOW_CACHE_SIGNING_KEY` identical and stable |
| Browser access | Use the public HTTPS origin(s) and the same cookie policy |
| Local directories, ports and container identity | Configure separately for each host/replica |

`LANGFLOW_DB_CONNECTION_SETTINGS` is per process. The application-engine
connection budget is approximately `replicas * workers * (pool_size + max_overflow)`;
reserve additional connections for vector queries, telemetry, listeners and
migrations. The template exposes the current defaults, not a measured capacity
target. `LANGFLOW_BACKGROUND_MAX_CONCURRENCY` is also per API worker on this branch.
Job retention defaults to keeping history; a positive retention window deletes
terminal jobs and ends their idempotency protection, so choose that policy explicitly.

Before deploying multiple API containers, the deployment implementation still
needs these changes and acceptance checks:

- Replace the fixed container name and host port mapping with replica identities,
  service discovery and an internal load balancer/ingress that supports streaming.
- Coordinate migrations, version rollout, health admission and application rollback
  across replicas. The current host-local deployment lock and `.deployed-image`
  record manage one container; they are not a fleet-wide rollout controller.
- Account for API-local background execution. Redis-backed build-event delivery
  does not provide the standalone background worker modules absent on this branch.
  Validate cross-replica event reads, cancellation, reattachment and recovery when
  an executing replica stops before treating the background path as cluster-ready.
- If Track B triggers are used, deploy `langflow listeners` separately with shared
  database, keys and OAuth registrations; see [listeners/README.md](listeners/README.md).
- Arrange shared infrastructure backup/restore and private metrics collection.
  Enabling `LANGFLOW_PROMETHEUS_ENABLED` alone does not provision a monitoring stack.

The single-instance test configuration preserves this shared-service contract;
passing its checks does not establish multi-instance acceptance.

When promoting the same-host test, use the production baseline with real shared
service endpoints and the public HTTPS origin. The test's `postgres`, `redis`
and `objectstore` names resolve only on its local Docker network. Make those
stores reachable through the private production network, or migrate their data
to the selected shared services, while preserving the encryption/signing keys.
Replace the test HTTP overrides when preparing the production environment.

Model-provider credentials, connection OAuth registrations and SSO/authorization
plugins need their own configuration when those features are used; this template
defines the common application baseline.

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
