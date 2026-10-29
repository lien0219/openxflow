"""Unit tests for the local, fail-closed image verification contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.ci.openxflow_verify_image import (
    VerificationError,
    build_copy_command,
    build_smoke_run_command,
    build_trivy_command,
    probe_smoke_endpoints,
    resolve_inspected_oci_index,
    smoke_startup_timeout,
    summarize_trivy,
    validate_oci_index,
    validate_plan,
)

PLAN = {"source": "a" * 40, "version": "0.1.0", "created": "2026-10-18T09:00:00Z"}


def _blob(value: bytes) -> tuple[str, bytes]:
    return "sha256:" + hashlib.sha256(value).hexdigest(), value


def _archive_files() -> tuple[dict, dict[str, bytes]]:
    layer_digest, layer = _blob(b"layer")
    config_digest, config = _blob(b"{}")
    attest_layer_digest, attest_layer = _blob(
        json.dumps({"predicateType": "https://slsa.dev/provenance/v1", "predicate": {}}).encode()
    )
    sbom_layer_digest, sbom_layer = _blob(
        json.dumps({"predicateType": "https://spdx.dev/Document", "predicate": {}}).encode()
    )
    files = {
        f"blobs/sha256/{layer_digest[7:]}": layer,
        f"blobs/sha256/{config_digest[7:]}": config,
        f"blobs/sha256/{attest_layer_digest[7:]}": attest_layer,
        f"blobs/sha256/{sbom_layer_digest[7:]}": sbom_layer,
    }
    manifests = []
    for arch in ("amd64", "arm64"):
        manifest = json.dumps(
            {"schemaVersion": 2, "config": {"digest": config_digest}, "layers": [{"digest": layer_digest}]}
        ).encode()
        digest, raw = _blob(manifest)
        files[f"blobs/sha256/{digest[7:]}"] = raw
        image = {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": digest,
            "platform": {"os": "linux", "architecture": arch},
        }
        manifests.append(image)
        att_manifest = json.dumps(
            {
                "schemaVersion": 2,
                "config": {"digest": config_digest},
                "layers": [{"digest": attest_layer_digest}, {"digest": sbom_layer_digest}],
            }
        ).encode()
        att_digest, att_raw = _blob(att_manifest)
        files[f"blobs/sha256/{att_digest[7:]}"] = att_raw
        manifests.append(
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": att_digest,
                "annotations": {
                    "vnd.docker.reference.type": "attestation-manifest",
                    "vnd.docker.reference.digest": digest,
                },
            }
        )
    return {"schemaVersion": 2, "manifests": manifests}, files


@pytest.mark.parametrize("value", ["", "v0.1.0", "0.1", "01.0.0", "a" * 40 + "0"])
def test_plan_rejects_unsafe_identity(value: str) -> None:
    plan = dict(PLAN, version=value) if value != "a" * 40 + "0" else dict(PLAN, source=value)
    with pytest.raises(VerificationError):
        validate_plan(plan)


def test_oci_index_requires_both_architectures_and_attestations() -> None:
    index, files = _archive_files()
    result = validate_oci_index(index, files)
    assert set(result["platforms"]) == {"amd64", "arm64"}
    assert set(result["attestations"]["amd64"]) == {"provenance", "sbom"}
    broken = dict(index, manifests=index["manifests"][:-2])
    with pytest.raises(VerificationError, match="arm64"):
        validate_oci_index(broken, files)


def test_commands_pin_overrides_and_strict_trivy_policy(tmp_path: Path) -> None:
    copy = build_copy_command(Path("candidate.oci.tar"), tmp_path / "amd64.tar", "amd64", "local:amd64")
    assert "--override-os" in copy
    assert "linux" in copy
    assert "--override-arch" in copy
    assert "amd64" in copy
    trivy = build_trivy_command(tmp_path / "amd64.tar", "vuln", tmp_path / "vuln.json")
    assert "--ignore-unfixed=false" in trivy
    assert Path(trivy[trivy.index("--ignorefile") + 1]).name == ".trivyignore.yaml"


def test_trivy_summary_counts_findings(tmp_path: Path) -> None:
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps({"Results": [{"Vulnerabilities": [{"VulnerabilityID": "CVE-test"}]}]}), encoding="utf-8"
    )
    summary = summarize_trivy(report, "vuln")
    assert summary["finding_count"] == 1


def test_skopeo_selected_index_matches_single_sha256_addressed_oci_layout_blob() -> None:
    """An OCI layout wrapper is legitimate only when its selected digest matches."""
    selected, files = _archive_files()
    raw = json.dumps(selected, separators=(",", ":")).encode("utf-8")
    digest, _ = _blob(raw)
    files[f"blobs/sha256/{digest[7:]}"] = raw
    layout = {
        "schemaVersion": 2,
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "digest": digest,
                "size": len(raw),
                "annotations": {"org.opencontainers.image.ref.name": "openxflow"},
            }
        ],
    }
    verified = resolve_inspected_oci_index(layout, files, selected, raw)
    assert set(validate_oci_index(verified, files)["platforms"]) == {"amd64", "arm64"}


def test_skopeo_index_identity_fails_closed_on_foreign_or_tampered_blobs() -> None:
    selected, files = _archive_files()
    raw = json.dumps(selected).encode("utf-8")
    digest, _ = _blob(raw)
    files[f"blobs/sha256/{digest[7:]}"] = raw
    layout = {
        "schemaVersion": 2,
        "manifests": [{"mediaType": "application/vnd.oci.image.index.v1+json", "digest": digest}],
    }
    assert resolve_inspected_oci_index(selected, files, selected, raw) == selected
    with pytest.raises(VerificationError, match="not referenced"):
        resolve_inspected_oci_index(layout, files, selected, raw + b" ")
    files[f"blobs/sha256/{digest[7:]}"] = b"tampered"
    with pytest.raises(VerificationError, match="digest mismatch"):
        resolve_inspected_oci_index(layout, files, selected, raw)
    layout["manifests"].append(dict(layout["manifests"][0]))
    with pytest.raises(VerificationError, match="ambiguous"):
        resolve_inspected_oci_index(layout, files, selected, raw)


def test_authenticated_offline_smoke_requires_ephemeral_superuser_credentials() -> None:
    """CI must supply credentials while preserving production's no-auto-login default."""
    password = "x" * 48  # Synthetic input, not a real credential.
    command = build_smoke_run_command("image:test", "smoke-one", password)
    assert command[:4] == ["docker", "run", "--detach", "--network"]
    assert command[4] == "none"
    assert command[-1] == "image:test"
    envs = [command[pos + 1] for pos, item in enumerate(command[:-1]) if item == "--env"]
    assert "LANGFLOW_AUTO_LOGIN=false" in envs
    assert "LANGFLOW_SUPERUSER=langflow" in envs
    assert f"LANGFLOW_SUPERUSER_PASSWORD={password}" in envs
    assert "LANGFLOW_DATABASE_URL=sqlite:////app/data/openxflow-verify.db" in envs
    assert "LANGFLOW_CONFIG_DIR=/app/data/config" in envs
    assert "--user" in command
    assert command[command.index("--user") + 1] == "1000:0"
    with pytest.raises(VerificationError, match="must be strong"):
        build_smoke_run_command("image:test", "smoke-one", "short")


def test_emulated_arm64_smoke_has_bounded_longer_startup_window() -> None:
    assert smoke_startup_timeout("arm64") > smoke_startup_timeout("amd64") > 0
    with pytest.raises(VerificationError, match="unsupported"):
        smoke_startup_timeout("other")


def test_failed_smoke_reports_stderr_and_exits_early(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.ci import openxflow_verify_image as verifier

    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(args, 1, "", "connection refused")
        if args[:3] == ["docker", "inspect", "--format"]:
            return subprocess.CompletedProcess(args, 0, "false\n", "")
        if args[:2] == ["docker", "logs"]:
            return subprocess.CompletedProcess(args, 0, "", "Startup failed: missing database")
        return subprocess.CompletedProcess(args, 0, "container-id", "")

    monkeypatch.setattr(verifier, "_run", fake_run)
    names: list[str] = []
    with pytest.raises(VerificationError, match="Startup failed: missing database"):
        verifier.smoke_image("image:test", "arm64", names)
    assert len(names) == 1
    assert any(command[:2] == ["docker", "rm"] for command in calls)
    assert not any(command[:2] == ["docker", "exec"] for command in calls[2:])


def test_smoke_environment_skips_network_refresh_but_keeps_authentication() -> None:
    command = build_smoke_run_command("image:test", "smoke-two", "x" * 48)
    variables = [command[i + 1] for i, part in enumerate(command[:-1]) if part == "--env"]
    assert "LANGFLOW_AUTO_LOGIN=false" in variables
    assert "LANGFLOW_SKIP_MCP_AUTO_INIT=true" in variables
    assert "LANGFLOW_MODELS_DEV_REFRESH=false" in variables
    assert "LANGFLOW_WORKERS=1" in variables
    assert "LITELLM_LOCAL_MODEL_COST_MAP=true" in variables
    assert "LITELLM_OFFLINE_MODE=true" in variables
    assert "DO_NOT_TRACK=true" in variables


def test_curl_smoke_probe_requires_both_real_http_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.ci import openxflow_verify_image as verifier

    requests: list[list[str]] = []

    def successful_http(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        requests.append(args)
        return subprocess.CompletedProcess(args, 0, "healthy", "")

    monkeypatch.setattr(verifier, "_run", successful_http)
    assert probe_smoke_endpoints("test-container") == (True, "")
    assert len(requests) == 2
    assert requests[0][-1] == "http://127.0.0.1:7860/health_check"
    assert requests[1][-1] == "http://127.0.0.1:7860/"
    for command in requests:
        assert command[:4] == ["docker", "exec", "test-container", "curl"]
        assert "--fail" in command
        assert "--max-time" in command

    requests.clear()

    def failed_http(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        requests.append(args)
        return subprocess.CompletedProcess(args, 22, "", "HTTP 503")

    monkeypatch.setattr(verifier, "_run", failed_http)
    ready, reason = probe_smoke_endpoints("test-container")
    assert not ready
    assert "503" in reason
    assert len(requests) == 1


def test_curl_smoke_probe_rejects_empty_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.ci import openxflow_verify_image as verifier

    monkeypatch.setattr(
        verifier,
        "_run",
        lambda args: subprocess.CompletedProcess(args, 0, "", ""),
    )
    ready, reason = probe_smoke_endpoints("test-container")
    assert not ready
    assert "/health_check" in reason
