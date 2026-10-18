"""Unit tests for the local, fail-closed image verification contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.ci.openxflow_verify_image import (
    VerificationError,
    build_copy_command,
    build_trivy_command,
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
    assert trivy[trivy.index("--ignorefile") + 1] == "/dev/null"


def test_trivy_summary_counts_findings(tmp_path: Path) -> None:
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps({"Results": [{"Vulnerabilities": [{"VulnerabilityID": "CVE-test"}]}]}), encoding="utf-8"
    )
    summary = summarize_trivy(report, "vuln")
    assert summary["finding_count"] == 1
