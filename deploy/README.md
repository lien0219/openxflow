# OpenXFlow deployment

`docker-compose.prod.yml` runs the OpenXFlow API against external PostgreSQL
(with pgVector), Redis, and S3. It does not start local stateful containers.
Copy `production.env.example` to `.env`, provide real credentials, and keep the
file mode `600`.

```bash
./deploy-main.sh ghcr.io/lien0219/openxflow:main-vX.Y.Z
```

Deploy only immutable version/SHA tags or a digest. The helper verifies image
source, revision, version, architecture, non-root execution, migration graph,
production configuration, and an operator-supplied backup/upgrade gate before
stopping the current API. It requires a real `healthy` status and records only
the last verified digest for recovery. See
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).
