"""Deployment failure tests use a Docker boundary fake; no production services are contacted."""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "ghcr.io/lien0219/openxflow"
OLD = REPOSITORY + "@sha256:" + "a" * 64
NEW = REPOSITORY + "@sha256:" + "b" * 64
OLD_REVISION = "1" * 40
NEW_REVISION = "2" * 40


def load_deployer():
    path = ROOT / "deploy" / "deploy_main.py"
    assert path.is_file(), "The deployment safety helper must be implemented"
    spec = importlib.util.spec_from_file_location("openxflow_deploy_main", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def environment():
    return {
        "LANGFLOW_DEPLOYMENT_PROFILE": "prod",
        "LANGFLOW_AUTO_LOGIN": "false",
        "LANGFLOW_NEW_USER_IS_ACTIVE": "false",
        "LANGFLOW_SECRET_KEY": base64.urlsafe_b64encode(b"x" * 32).decode(),
        "LANGFLOW_CACHE_SIGNING_KEY": "test-cache-signing-key-at-least-32-characters",
        # pragma: allowlist nextline secret
        "LANGFLOW_DATABASE_URL": "postgresql+psycopg://app:fixture@database.invalid/app",
        # pragma: allowlist nextline secret
        "PGVECTOR_CONNECTION_STRING": "postgresql+psycopg://app:fixture@vector.invalid/app",
        "LANGFLOW_STORAGE_TYPE": "s3",
        "LANGFLOW_OBJECT_STORAGE_BUCKET_NAME": "fixture-bucket",
        "LANGFLOW_CACHE_TYPE": "redis",
        "LANGFLOW_JOB_QUEUE_TYPE": "redis",
        "LANGFLOW_REDIS_URL": "rediss://:fixture@cache.invalid/0",
        "LANGFLOW_REDIS_QUEUE_URL": "rediss://:fixture@queue.invalid/0",
        "LANGFLOW_RATE_LIMIT_STORAGE_URI": "rediss://:fixture@limits.invalid/0",
        "AWS_DEFAULT_REGION": "us-east-1",
    }


def fingerprint(digest="c" * 64):
    return {"schema": 1, "uid": 1000, "alembic_sha256": digest, "models_sha256": "d" * 64, "heads": ["head1"]}


class FakeDocker:
    """Stateful Docker boundary: implements the commands the real deployer executes."""

    def __init__(self):
        self.calls = []
        self.image = None
        self.fail_up = False
        self.target_health = "healthy"
        self.old_health = "healthy"
        self.stop_fails = False
        self.image_source = "https://github.com/lien0219/openxflow"
        self.architecture = "amd64"
        self.fingerprints = {OLD: fingerprint(), NEW: fingerprint()}
        self.env = environment()

    def run(self, args, *, env=None, input_text=None):
        self.calls.append((args, (env or {}).get("OPENXFLOW_IMAGE")))
        if args[:2] == ["compose", "version"]:
            return "Docker Compose version v2.35.1"
        if args == ["info", "--format", "{{json .}}"]:
            return json.dumps({"OSType": "linux", "Architecture": "x86_64"})
        if args[0] == "pull":
            return "pulled"
        if args[:2] == ["image", "inspect"]:
            ref = args[2]
            digest = OLD if ref == OLD else NEW
            return json.dumps(
                [
                    {
                        "Id": "sha256:" + ("e" if digest == OLD else "f") * 64,
                        "RepoDigests": [digest],
                        "Architecture": self.architecture,
                        "Os": "linux",
                        "Config": {
                            "User": "user",
                            "Labels": {
                                "org.opencontainers.image.source": self.image_source,
                                "org.opencontainers.image.revision": OLD_REVISION if digest == OLD else NEW_REVISION,
                                "org.opencontainers.image.version": "0.1.0" if digest == OLD else "0.1.1",
                            },
                        },
                    }
                ]
            )
        if args[0] == "run":
            assert "--network=none" in args
            assert "--read-only" in args
            assert "--env-file" not in args
            assert input_text
            return json.dumps(self.fingerprints[args[-2]])
        if args[0] == "compose":
            if "config" in args:
                return json.dumps(
                    {
                        "services": {
                            "openxflow": {
                                "image": env["OPENXFLOW_IMAGE"],
                                "command": ["langflow", "run", "--workers", "1"],
                                "environment": self.env,
                                "user": "1000:0",
                            }
                        }
                    }
                )
            if "ps" in args:
                return "container1" if self.image else ""
            if "stop" in args:
                if self.stop_fails:
                    raise RuntimeError("mock stop failed")
                self.image = None
                return ""
            if "up" in args:
                assert "--pull" in args and args[args.index("--pull") + 1] == "never"
                self.image = env["OPENXFLOW_IMAGE"]
                if self.fail_up and self.image == NEW:
                    raise RuntimeError("mock up failed after partial startup")
                return ""
        if args[0] == "inspect":
            health = self.old_health if self.image == OLD else self.target_health
            return json.dumps(
                [
                    {
                        "Config": {"Image": self.image},
                        "Image": "sha256:" + ("e" if self.image == OLD else "f") * 64,
                        "State": {"Status": "running", "Health": {"Status": health}},
                    }
                ]
            )
        raise AssertionError(f"Unexpected Docker command: {args}")


def setup_deployment(tmp_path, *, previous=False):
    module = load_deployer()
    (tmp_path / ".env").write_text("# secrets supplied only to mocked compose\n", encoding="utf-8")
    (tmp_path / ".env").chmod(0o600)
    (tmp_path / "docker-compose.prod.yml").write_text("services: {}\n", encoding="utf-8")
    docker = FakeDocker()
    deployer = module.Deployer(tmp_path, docker, health_timeout=0.01, poll_interval=0)
    plan = deployer.inspect(NEW)
    if previous:
        old = deployer.inspect(OLD)["target"]
        (tmp_path / ".deployed-image").write_text(json.dumps(old), encoding="utf-8")
        docker.image = OLD
        plan = deployer.inspect(NEW)
    gate = {
        "schema": 1,
        "target_digest": NEW,
        "previous_digest": OLD if previous else None,
        "revision": NEW_REVISION,
        "version": "0.1.1",
        "configuration_sha256": plan["target"]["configuration_sha256"],
        "migration": plan["target"]["migration"],
        "backup_reference": "test-backup-123",
        "restore_drill_reference": "test-restore-drill-123",
        "migration_reviewed": True,
        "application_rollback_safe": True,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    gate_path = tmp_path / ".upgrade-gate.json"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    return module, deployer, docker, gate_path


def test_version_tag_is_resolved_to_digest_and_only_healthy_state_is_persisted(tmp_path):
    _, deployer, docker, gate_path = setup_deployment(tmp_path)
    deployer.deploy(REPOSITORY + ":main-v0.1.1", gate_path)
    state = json.loads((tmp_path / ".deployed-image").read_text())
    assert state["digest"] == NEW
    assert state["revision"] == NEW_REVISION
    assert all(image == NEW for command, image in docker.calls if "up" in command)


@pytest.mark.parametrize("failure", ["up", "health", "running"])
def test_startup_failure_recovers_only_last_verified_healthy_digest(tmp_path, failure):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    docker.fail_up = failure == "up"
    docker.target_health = "running" if failure == "running" else "unhealthy"
    with pytest.raises(module.DeployError, match="rollback completed"):
        deployer.deploy(NEW, gate_path)
    assert docker.image == OLD
    assert json.loads((tmp_path / ".deployed-image").read_text())["digest"] == OLD


def test_changed_migration_graph_blocks_automatic_rollback_after_failed_upgrade(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    docker.fingerprints[NEW] = fingerprint("9" * 64)
    gate = json.loads(gate_path.read_text())
    gate["migration"] = docker.fingerprints[NEW]
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    docker.target_health = "unhealthy"
    with pytest.raises(module.DeployError, match="automatic rollback blocked"):
        deployer.deploy(NEW, gate_path)
    assert docker.image is None
    assert [image for command, image in docker.calls if "up" in command] == [NEW]
    assert json.loads((tmp_path / ".deployed-image").read_text())["digest"] == OLD


def test_failed_stop_blocks_rollback_to_avoid_concurrent_migrations(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    docker.target_health = "unhealthy"
    docker.stop_fails = True
    with pytest.raises(module.DeployError, match="stop"):
        deployer.deploy(NEW, gate_path)
    assert not any("up" in command for command, _ in docker.calls)


def test_missing_backup_gate_prevents_stopping_current_container(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    gate = json.loads(gate_path.read_text())
    gate["backup_reference"] = ""
    gate_path.write_text(json.dumps(gate))
    with pytest.raises(module.DeployError, match="backup"):
        deployer.deploy(NEW, gate_path)
    assert docker.image == OLD
    assert not any("stop" in command or "up" in command for command, _ in docker.calls)


@pytest.mark.parametrize("ref", [REPOSITORY + ":main", REPOSITORY + ":latest", "evil.invalid/x@sha256:" + "a" * 64])
def test_mutable_or_foreign_target_is_rejected_before_docker(tmp_path, ref):
    module = load_deployer()
    docker = FakeDocker()
    with pytest.raises(module.DeployError, match="immutable"):
        module.Deployer(tmp_path, docker).inspect(ref)
    assert not docker.calls


@pytest.mark.parametrize("mutation", ["source", "revision", "architecture", "version"])
def test_inconsistent_image_metadata_is_rejected(tmp_path, mutation):
    module, deployer, docker, _ = setup_deployment(tmp_path)
    target = NEW
    if mutation == "source":
        docker.image_source = "https://github.com/another/repository"
    if mutation == "revision":
        target = REPOSITORY + ":sha-" + OLD_REVISION
    if mutation == "version":
        target = REPOSITORY + ":main-v0.2.0"
    if mutation == "architecture":
        docker.architecture = "arm64"
    with pytest.raises(module.DeployError):
        deployer.inspect(target)


def test_tampered_previous_reference_cannot_be_used_for_rollback(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    state_path = tmp_path / ".deployed-image"
    state = json.loads(state_path.read_text())
    state["digest"] = "evil.invalid/image@sha256:" + "a" * 64
    state_path.write_text(json.dumps(state))
    with pytest.raises(module.DeployError):
        deployer.deploy(NEW, gate_path)
    assert not any("stop" in command or "up" in command for command, _ in docker.calls)


def test_stale_atomic_state_file_blocks_before_stopping_current_container(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    (tmp_path / ".deployed-image.tmp").write_text("stale", encoding="utf-8")
    with pytest.raises(module.DeployError, match="stale temporary"):
        deployer.deploy(NEW, gate_path)
    assert not any("stop" in command or "up" in command for command, _ in docker.calls)


def test_second_deployment_cannot_acquire_the_same_host_lock(tmp_path):
    module = load_deployer()
    with module.deployment_lock(tmp_path / ".deploy.lock"):
        with pytest.raises(module.DeployError, match="another deployment"):
            with module.deployment_lock(tmp_path / ".deploy.lock"):
                pytest.fail("concurrent deployment acquired lock")


def test_configuration_change_disables_automatic_rollback(tmp_path):
    module, deployer, docker, gate_path = setup_deployment(tmp_path, previous=True)
    # pragma: allowlist nextline secret
    docker.env["LANGFLOW_DATABASE_URL"] = "postgresql+psycopg://app:fixture@other.invalid/app"
    gate = json.loads(gate_path.read_text())
    gate["configuration_sha256"] = deployer.inspect(NEW)["target"]["configuration_sha256"]
    gate_path.write_text(json.dumps(gate))
    docker.target_health = "unhealthy"
    with pytest.raises(module.DeployError, match="automatic rollback blocked"):
        deployer.deploy(NEW, gate_path)
    assert docker.image is None


def test_production_config_rejects_nonzero_redis_database_and_invalid_fernet(tmp_path):
    module, deployer, docker, _ = setup_deployment(tmp_path)
    docker.env["LANGFLOW_REDIS_QUEUE_URL"] = "rediss://cache.invalid/1"
    with pytest.raises(module.DeployError, match="Redis"):
        deployer.inspect(NEW)
    docker.env["LANGFLOW_REDIS_QUEUE_URL"] = "rediss://cache.invalid/0"
    docker.env["LANGFLOW_SECRET_KEY"] = "not-a-fernet-key"  # pragma: allowlist secret -- fake test credential
    with pytest.raises(module.DeployError, match="Fernet"):
        deployer.inspect(NEW)


def test_production_config_rejects_template_placeholders(tmp_path):
    module, deployer, docker, _ = setup_deployment(tmp_path)
    # pragma: allowlist nextline secret
    docker.env["LANGFLOW_DATABASE_URL"] = "postgresql+psycopg://app:replace-me@db.example.invalid/app"
    with pytest.raises(module.DeployError, match="placeholder"):
        deployer.inspect(NEW)
