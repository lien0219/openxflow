# ruff: noqa: INP001, TRY003, EM101, EM102, PLR2004

"""Deploy one verified image with a host lock and an explicit migration/backup gate.

Only Docker subprocesses may contact infrastructure. The offline image probe has
no network, production environment, or data volume. Application startup itself
runs migrations; this tool never promises database rollback.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

REPOSITORY = "ghcr.io/lien0219/openxflow"
SOURCE = "https://github.com/lien0219/openxflow"
SEMVER = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
DIGEST = re.compile(re.escape(REPOSITORY) + r"@sha256:[0-9a-f]{64}")
REFERENCE = re.compile(re.escape(REPOSITORY) + rf"(?::main-v{SEMVER}|:sha-[0-9a-f]{{40}}|@sha256:[0-9a-f]{{64}})")
SHA256 = re.compile(r"[0-9a-f]{64}")
PROBE = Path(__file__).with_name("migration_fingerprint.py")
GATE_MAX_AGE_SECONDS = 24 * 60 * 60


class DeployError(RuntimeError):
    """A failed gate or deployment; messages must never contain credentials."""


def require(condition, message):
    if not condition:
        raise DeployError(message)


def read_json(path):
    require(path.is_file() and not path.is_symlink(), f"missing or unsafe file: {path.name}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeployError(f"invalid JSON file: {path.name}") from exc
    require(isinstance(result, dict), f"expected a JSON object in {path.name}")
    return result


@contextmanager
def deployment_lock(path):
    """Serialize host operations; an OS lock is released even after SIGKILL."""
    require(not path.is_symlink(), "deployment lock must not be a symlink")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            # Windows support is for local lock tests; production targets Linux.
            if not os.fstat(descriptor).st_size:
                os.write(descriptor, b"0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DeployError("another deployment holds the host lock") from exc
        else:
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DeployError("another deployment holds the host lock") from exc
        yield
    finally:
        os.close(descriptor)


class Docker:
    """Do not print command output: Compose output may include resolved secrets."""

    def __init__(self):
        self.executable = shutil.which("docker")
        require(self.executable, "Docker is required")

    def run(self, args, *, env=None, input_text=None):
        try:
            result = subprocess.run(  # noqa: S603 - argument vector, never a shell
                [self.executable, *args],
                env={**os.environ, **(env or {})},
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=1800,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeployError(f"Docker {args[0]} could not complete; inspect host logs privately") from exc
        require(result.returncode == 0, f"Docker {args[0]} failed; inspect host logs privately")
        return result.stdout


def validate_environment(environment):
    """Validate Compose's resolved environment without executing or echoing .env."""

    def configured(value, label):
        require(
            value and "replace" not in str(value).lower() and "example.invalid" not in str(value).lower(),
            f"replace the production placeholder for {label}",
        )

    fixed = {
        "LANGFLOW_DEPLOYMENT_PROFILE": "prod",
        "LANGFLOW_AUTO_LOGIN": "false",
        "LANGFLOW_NEW_USER_IS_ACTIVE": "false",
        "LANGFLOW_STORAGE_TYPE": "s3",
        "LANGFLOW_CACHE_TYPE": "redis",
        "LANGFLOW_JOB_QUEUE_TYPE": "redis",
    }
    for name, expected in fixed.items():
        require(str(environment.get(name, "")).lower() == expected, f"production setting required: {name}={expected}")
    for name in ("LANGFLOW_DATABASE_URL", "PGVECTOR_CONNECTION_STRING"):
        value = environment.get(name, "")
        configured(value, name)
        url = urlsplit(value)
        require(
            url.scheme in {"postgresql", "postgresql+psycopg", "postgresql+asyncpg"} and url.hostname,
            f"external PostgreSQL configuration required: {name}",
        )
    for name in ("LANGFLOW_REDIS_URL", "LANGFLOW_REDIS_QUEUE_URL", "LANGFLOW_RATE_LIMIT_STORAGE_URI"):
        value = environment.get(name, "")
        configured(value, name)
        url = urlsplit(value)
        require(
            url.scheme in {"redis", "rediss"} and url.hostname and url.path in {"", "/", "/0"},
            f"Redis endpoint must use redis/rediss and DB 0: {name}",
        )
    try:
        key = base64.b64decode(environment.get("LANGFLOW_SECRET_KEY", ""), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        key = b""
    require(len(key) == 32, "LANGFLOW_SECRET_KEY must be a fixed 32-byte Fernet key encoded as URL-safe base64")
    require(len(environment.get("LANGFLOW_CACHE_SIGNING_KEY", "")) >= 32, "a stable cache signing key is required")
    for name in ("LANGFLOW_OBJECT_STORAGE_BUCKET_NAME", "AWS_DEFAULT_REGION"):
        configured(environment.get(name), name)
    if environment.get("AWS_ENDPOINT_URL"):
        configured(environment["AWS_ENDPOINT_URL"], "AWS_ENDPOINT_URL")
        require(
            urlsplit(environment["AWS_ENDPOINT_URL"]).scheme in {"http", "https"}, "AWS_ENDPOINT_URL must use HTTP(S)"
        )
    if environment.get("AWS_ACCESS_KEY_ID") or environment.get("AWS_SECRET_ACCESS_KEY"):
        require(
            environment.get("AWS_ACCESS_KEY_ID") and environment.get("AWS_SECRET_ACCESS_KEY"),
            "provide both S3 credential fields or use the AWS workload credential chain",
        )
        configured(environment["AWS_ACCESS_KEY_ID"], "AWS_ACCESS_KEY_ID")
        configured(environment["AWS_SECRET_ACCESS_KEY"], "AWS_SECRET_ACCESS_KEY")
    require(environment.get("LANGFLOW_PREFLIGHT_COMPLETED") != "1", "production preflight cannot be bypassed")


class Deployer:
    def __init__(self, directory, docker, *, health_timeout=300, poll_interval=3):
        self.directory = directory.resolve()
        self.docker = docker
        self.state = self.directory / ".deployed-image"
        self.environment_file = self.directory / ".env"
        self.compose_file = self.directory / "docker-compose.prod.yml"
        self.health_timeout = health_timeout
        self.poll_interval = poll_interval

    def compose(self, image, *args):
        return self.docker.run(
            ["compose", "--env-file", str(self.environment_file), "-f", str(self.compose_file), *args],
            env={"OPENXFLOW_IMAGE": image, "OPENXFLOW_ENV_FILE": str(self.environment_file)},
        )

    def verify_image(self, reference):
        require(
            isinstance(reference, str) and REFERENCE.fullmatch(reference), "an immutable OpenXFlow image is required"
        )
        self.docker.run(["pull", reference])
        images = json.loads(self.docker.run(["image", "inspect", reference]))
        require(len(images) == 1, "image inspection did not identify exactly one image")
        metadata = images[0]
        matches = sorted({ref for ref in metadata.get("RepoDigests", []) if DIGEST.fullmatch(ref)})
        if "@" in reference:
            require(reference in matches, "pulled image digest does not match the requested digest")
            digest = reference
        else:
            require(len(matches) == 1, "image repository digest is missing or ambiguous; deploy an explicit digest")
            digest = matches[0]
        labels = metadata.get("Config", {}).get("Labels", {}) or {}
        revision = labels.get("org.opencontainers.image.revision", "")
        version = labels.get("org.opencontainers.image.version", "")
        require(labels.get("org.opencontainers.image.source") == SOURCE, "image source is not OpenXFlow")
        require(re.fullmatch(r"[0-9a-f]{40}", revision), "image revision must be a full source SHA")
        require(re.fullmatch(SEMVER, version), "image version must be strict OpenXFlow SemVer")
        if ":sha-" in reference:
            require(reference == f"{REPOSITORY}:sha-{revision}", "image revision does not match its SHA tag")
        if ":main-v" in reference:
            require(reference == f"{REPOSITORY}:main-v{version}", "image version does not match its version tag")
        daemon = json.loads(self.docker.run(["info", "--format", "{{json .}}"]))
        architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(daemon["Architecture"], daemon["Architecture"])
        require(daemon["OSType"] == metadata.get("Os") == "linux", "a Linux Docker daemon and image are required")
        require(
            architecture in {"amd64", "arm64"} and metadata.get("Architecture") == architecture,
            "image architecture does not match the host",
        )
        user = str(metadata.get("Config", {}).get("User", "")).split(":", maxsplit=1)[0]
        require(user not in {"", "0", "root"}, "image must run as a non-root user")
        probe = json.loads(
            self.docker.run(
                [
                    "run",
                    "--rm",
                    "-i",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--entrypoint",
                    "python",
                    digest,
                    "-",
                ],
                input_text=PROBE.read_text(encoding="utf-8"),
            )
        )
        require(probe.get("schema") == 1 and probe.get("uid") == 1000, "image must execute offline probe as uid 1000")
        require(
            all(SHA256.fullmatch(probe.get(name, "")) for name in ("alembic_sha256", "models_sha256")),
            "invalid migration fingerprint",
        )
        require(
            isinstance(probe.get("heads"), list) and len(probe["heads"]) == 1, "a single migration head is required"
        )
        return {
            "schema": 1,
            "digest": digest,
            "revision": revision,
            "version": version,
            "architecture": architecture,
            "image_id": metadata["Id"],
            "migration": probe,
        }

    def inspect(self, reference):
        require(
            isinstance(reference, str) and REFERENCE.fullmatch(reference), "an immutable OpenXFlow image is required"
        )
        for path in (self.environment_file, self.compose_file):
            require(path.is_file() and not path.is_symlink(), f"missing or unsafe file: {path.name}")
        if os.name != "nt":
            require(self.environment_file.stat().st_mode & 0o077 == 0, ".env permissions must be 600")
        self.docker.run(["compose", "version"])
        target = self.verify_image(reference)
        config = json.loads(self.compose(target["digest"], "config", "--format", "json"))
        require(set(config.get("services", {})) == {"openxflow"}, "this deployment supports one OpenXFlow service")
        service = config["services"]["openxflow"]
        require(service.get("command") == ["langflow", "run", "--workers", "1"], "a single API worker is required")
        require(
            service.get("image") == target["digest"] and service.get("user") == "1000:0", "Compose image/user mismatch"
        )
        validate_environment(service.get("environment", {}))
        # Bind rollback to the complete resolved service config, excluding image.
        stable_config = {key: value for key, value in service.items() if key != "image"}
        target["configuration_sha256"] = hashlib.sha256(json.dumps(stable_config, sort_keys=True).encode()).hexdigest()
        previous = None
        temporary = self.state.with_name(".deployed-image.tmp")
        require(
            not temporary.exists() and not temporary.is_symlink(),
            "stale temporary deployment state; inspect before retry",
        )
        if self.state.exists() or self.state.is_symlink():
            if os.name != "nt":
                require(self.state.stat().st_mode & 0o077 == 0, "deployment state permissions must be 600")
            previous = read_json(self.state)
            require(DIGEST.fullmatch(previous.get("digest", "")), "invalid previous image digest")
            verified = self.verify_image(previous["digest"])
            require(
                all(previous.get(key) == value for key, value in verified.items()),
                "previous image record does not match its verified image",
            )
            require(
                SHA256.fullmatch(previous.get("configuration_sha256", "")), "invalid previous configuration fingerprint"
            )
        return {
            "target": target,
            "previous": previous,
            "migration_files_changed": previous is None or previous["migration"] != target["migration"],
        }

    def container(self, image):
        identifiers = self.compose(image, "ps", "--all", "--quiet", "openxflow").split()
        require(len(identifiers) <= 1, "multiple API containers found; stop and review migration concurrency")
        if not identifiers:
            return None
        containers = json.loads(self.docker.run(["inspect", identifiers[0]]))
        require(len(containers) == 1, "container inspection is ambiguous")
        return containers[0]

    def wait_healthy(self, target):
        deadline = time.monotonic() + self.health_timeout
        while time.monotonic() < deadline:
            container = self.container(target["digest"])
            if container:
                require(
                    container.get("Config", {}).get("Image") == target["digest"]
                    and container.get("Image") == target["image_id"],
                    "running container does not use the verified image",
                )
                status = container.get("State", {})
                health = status.get("Health", {}).get("Status")
                if status.get("Status") == "running" and health == "healthy":
                    return
                require(
                    status.get("Status") not in {"exited", "dead"} and health != "unhealthy",
                    "application health check failed",
                )
            time.sleep(self.poll_interval)
        raise DeployError("application did not become healthy before timeout")

    def validate_gate(self, plan, path):
        if os.name != "nt":
            require(path.is_file() and path.stat().st_mode & 0o077 == 0, "upgrade gate permissions must be 600")
        gate = read_json(path)
        target, previous = plan["target"], plan["previous"]
        expected = {
            "schema": 1,
            "target_digest": target["digest"],
            "previous_digest": previous["digest"] if previous else None,
            "revision": target["revision"],
            "version": target["version"],
            "configuration_sha256": target["configuration_sha256"],
            "migration": target["migration"],
            "migration_reviewed": True,
        }
        require(
            all(gate.get(key) == value for key, value in expected.items()),
            "upgrade gate does not match this deployment",
        )
        for key in ("backup_reference", "restore_drill_reference"):
            value = gate.get(key)
            require(
                isinstance(value, str) and value.strip() and "replace" not in value.lower(),
                f"verified {key} is required",
            )
        try:
            approved = datetime.fromisoformat(gate.get("approved_at", "").replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - approved).total_seconds()
        except (TypeError, ValueError) as exc:
            raise DeployError("upgrade approval must include a timezone-aware approved_at") from exc
        require(0 <= age <= GATE_MAX_AGE_SECONDS, "upgrade approval is expired or future-dated")
        return gate

    def start(self, target):
        self.compose(
            target["digest"], "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "openxflow"
        )
        self.wait_healthy(target)

    def save(self, target):
        require(not self.state.is_symlink(), "deployment state must not be a symlink")
        temporary = self.state.with_name(".deployed-image.tmp")
        require(
            not temporary.exists() and not temporary.is_symlink(),
            "stale temporary deployment state; inspect before retry",
        )
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({**target, "healthy_at": datetime.now(timezone.utc).isoformat()}, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.state)
        finally:
            temporary.unlink(missing_ok=True)

    def deploy(self, reference, gate_path):
        with deployment_lock(self.directory / ".deploy.lock"):
            plan = self.inspect(reference)
            target, previous = plan["target"], plan["previous"]
            gate = self.validate_gate(plan, gate_path)
            current = self.container(target["digest"])
            if current:
                require(
                    previous
                    and current.get("Config", {}).get("Image") == previous["digest"]
                    and current.get("Image") == previous["image_id"],
                    "existing container has no matching verified healthy record",
                )
            # Stop the previous process before any new API process can migrate.
            try:
                self.compose(target["digest"], "stop", "openxflow")
            except (DeployError, RuntimeError) as exc:
                raise DeployError("failed to stop the current application; automatic rollback blocked") from exc
            try:
                self.start(target)
                self.save(target)
            except (DeployError, RuntimeError, OSError) as exc:
                # up may fail after partially starting; stop it before deciding rollback.
                try:
                    self.compose(target["digest"], "stop", "openxflow")
                except (DeployError, RuntimeError) as stop_exc:
                    raise DeployError("failed to stop the new application; automatic rollback blocked") from stop_exc
                safe = (
                    previous
                    and not plan["migration_files_changed"]
                    and previous["configuration_sha256"] == target["configuration_sha256"]
                    and gate.get("application_rollback_safe") is True
                )
                if not safe:
                    raise DeployError(
                        "deployment failed; automatic rollback blocked; review migrations and backup recovery"
                    ) from exc
                try:
                    self.start(previous)
                except (DeployError, RuntimeError) as rollback_exc:
                    raise DeployError(
                        "deployment failed and application rollback did not become healthy"
                    ) from rollback_exc
                raise DeployError(
                    "deployment failed; application rollback completed; database was not rolled back"
                ) from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument(
        "--inspect", action="store_true", help="pull and inspect without contacting production services"
    )
    parser.add_argument("--gate", type=Path, default=Path(".upgrade-gate.json"))
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    try:
        timeout = int(os.environ.get("HEALTH_TIMEOUT_SECONDS", "300"))
        require(1 <= timeout <= 3600, "HEALTH_TIMEOUT_SECONDS must be between 1 and 3600")
        deployer = Deployer(directory, Docker(), health_timeout=timeout)
        if args.inspect:
            with deployment_lock(directory / ".deploy.lock"):
                print(json.dumps(deployer.inspect(args.image), indent=2))  # noqa: T201 - redacted CLI output
        else:
            gate_path = args.gate if args.gate.is_absolute() else directory / args.gate
            deployer.deploy(args.image, gate_path)
            print("[openxflow-deploy] deployment healthy; verified digest recorded")  # noqa: T201
    except (DeployError, OSError, ValueError, KeyError, TypeError) as exception:
        # Unexpected parser/shape errors also fail closed without dumping secrets.
        message = (
            str(exception) if isinstance(exception, DeployError) else "invalid deployment input or Docker response"
        )
        print(f"[openxflow-deploy] ERROR: {message}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
