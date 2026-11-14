# OpenXFlow deployment

`production.env.example` is the application configuration baseline for production
and for initial testing. Shared PostgreSQL/pgVector, Redis, object storage and
stable keys remain required when starting with one API instance.

`docker-compose.prod.yml` runs the OpenXFlow API against external PostgreSQL
(with pgVector), Redis, and S3. It does not start local stateful containers.
Copy `production.env.example` to `.env`, provide real credentials, and keep the
file mode `600`.

For an early single Linux test host with all dependencies in Docker, see
[SINGLE_NODE_DOCKER.md](SINGLE_NODE_DOCKER.md). Its `single-node.env.example` is
an override fragment appended after the production template.

The current Compose/deployment helper operates one API container with one worker.
Multiple API replicas need deployment orchestration beyond this helper; their
shared configuration follows the same production baseline. See the
[multi-instance deployment requirements](PRODUCTION_DEPLOYMENT.md#multiple-api-instances).

```bash
./deploy-main.sh ghcr.io/lien0219/openxflow:main-vX.Y.Z
```

Deploy only immutable version/SHA tags or a digest. The helper verifies image
source, revision, version, architecture, non-root execution, migration graph,
production configuration, and an operator-supplied backup/upgrade gate before
stopping the current API. It requires a real `healthy` status and records only
the last verified digest for recovery. See
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).
