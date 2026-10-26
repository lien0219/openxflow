# ruff: noqa: TRY003,EM101,EM102,S603,S108

"""Fail-closed verification for a candidate OpenXFlow multi-arch OCI image.

This command performs local verification only. It never pushes to a registry
and never accepts a missing tool, missing attestation, or ambiguous image
metadata as a pass. A successful report is suitable for release assets after
the caller independently verifies the source commit and registry admission.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import secrets
import subprocess
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any

SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
PLATFORMS = ("amd64", "arm64")
SMOKE_MIN_PASSWORD_LENGTH = 32
# arm64 is emulated with QEMU on the AMD64 GitHub runner. Its Python startup
# and first database migration can take substantially longer than native AMD64.
SMOKE_STARTUP_TIMEOUT_S = {"amd64": 120, "arm64": 360}
SMOKE_POLL_INTERVAL_S = 2
PREDICATE_PROVENANCE = {
    "https://slsa.dev/provenance/v0.2",
    "https://slsa.dev/provenance/v1",
    "https://slsa.dev/provenance/v1.0",
}
PREDICATE_SBOM = {
    "https://spdx.dev/Document",
    "https://spdx.dev/Document/v2.3",
    "https://cyclonedx.org/bom",
}


class VerificationError(RuntimeError):
    """A required image verification invariant was not proven."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)


def _run_required(args: list[str]) -> str:
    result = _run(args)
    if result.returncode:
        raise VerificationError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr[-2000:]}")
    return result.stdout


def validate_plan(raw: dict[str, Any]) -> dict[str, str]:
    _require(isinstance(raw, dict), "plan must be a JSON object")
    source = raw.get("source")
    version = raw.get("version")
    created = raw.get("created")
    _require(
        isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source),
        "plan.source must be a lowercase 40-char commit SHA",
    )
    _require(isinstance(version, str) and SEMVER.fullmatch(version), "plan.version must be strict MAJOR.MINOR.PATCH")
    _require(isinstance(created, str) and created, "plan.created must be a non-empty ISO timestamp")
    try:
        dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VerificationError("plan.created must be an ISO timestamp") from exc
    return {"source": source, "version": version, "created": created}


def _descriptor_digest(descriptor: dict[str, Any]) -> str:
    digest = descriptor.get("digest")
    _require(isinstance(digest, str) and SHA256.fullmatch(digest), f"invalid OCI descriptor digest: {digest!r}")
    return digest


def _read_blob(files: dict[str, bytes], digest: str) -> bytes:
    _require(digest.startswith("sha256:"), f"unsupported blob digest: {digest}")
    key = f"blobs/sha256/{digest.removeprefix('sha256:')}"
    _require(key in files, f"OCI archive is missing {key}")
    blob = files[key]
    _require(hashlib.sha256(blob).hexdigest() == digest.removeprefix("sha256:"), f"OCI blob digest mismatch: {digest}")
    return blob


def read_oci_archive(archive: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    _require(archive.is_file(), f"OCI archive does not exist: {archive}")
    try:
        with tarfile.open(archive, "r:*") as stream:
            files = {
                member.name: stream.extractfile(member).read() for member in stream.getmembers() if member.isfile()
            }
    except (OSError, tarfile.TarError) as exc:
        raise VerificationError(f"unable to read OCI archive: {exc}") from exc
    _require("index.json" in files, "OCI archive is missing index.json")
    try:
        index = json.loads(files["index.json"])
    except json.JSONDecodeError as exc:
        raise VerificationError("OCI index.json is not valid JSON") from exc
    _require(isinstance(index.get("manifests"), list) and index["manifests"], "OCI index has no manifests")
    return index, files


def _predicate_from_layer(blob: bytes) -> tuple[str | None, dict[str, Any] | None]:
    try:
        data = gzip.decompress(blob) if blob[:2] == b"\x1f\x8b" else blob
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(value, dict):
        return None, None
    predicate = value.get("predicateType") or value.get("predicate", {}).get("predicateType")
    return predicate if isinstance(predicate, str) else None, value


def _manifest(files: dict[str, bytes], descriptor: dict[str, Any]) -> dict[str, Any]:
    raw = _read_blob(files, _descriptor_digest(descriptor))
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"OCI manifest is not valid JSON: {_descriptor_digest(descriptor)}") from exc
    _require(isinstance(value, dict), "OCI manifest must be an object")
    return value


def validate_oci_index(index: dict[str, Any], files: dict[str, bytes]) -> dict[str, Any]:
    descriptors = index.get("manifests", [])
    platforms: dict[str, dict[str, Any]] = {}
    attestations: dict[str, list[dict[str, Any]]] = {arch: [] for arch in PLATFORMS}
    for descriptor in descriptors:
        platform = descriptor.get("platform") or {}
        arch = platform.get("architecture")
        if platform.get("os") == "linux" and arch in PLATFORMS:
            _require(arch not in platforms, f"duplicate linux/{arch} image manifest")
            platforms[arch] = descriptor
    _require(set(platforms) == set(PLATFORMS), "OCI archive must contain linux/amd64 and linux/arm64 manifests")
    for descriptor in descriptors:
        annotations = descriptor.get("annotations") or {}
        target = annotations.get("vnd.docker.reference.digest")
        if annotations.get("vnd.docker.reference.type") != "attestation-manifest" or not target:
            continue
        for arch, image in platforms.items():
            if target == image.get("digest"):
                attestations[arch].append(descriptor)
    result: dict[str, Any] = {"platforms": {}, "attestations": {}}
    for arch, descriptor in platforms.items():
        digest = _descriptor_digest(descriptor)
        manifest = _manifest(files, descriptor)
        _require(manifest.get("config", {}).get("digest"), f"linux/{arch} manifest has no config")
        _require(manifest.get("layers"), f"linux/{arch} manifest has no filesystem layers")
        predicates: dict[str, dict[str, Any]] = {}
        for attestation in attestations[arch]:
            att_manifest = _manifest(files, attestation)
            for layer in att_manifest.get("layers", []):
                predicate, value = _predicate_from_layer(_read_blob(files, _descriptor_digest(layer)))
                if predicate in PREDICATE_PROVENANCE:
                    predicates["provenance"] = value
                elif predicate in PREDICATE_SBOM:
                    predicates["sbom"] = value
        _require(
            set(predicates) == {"provenance", "sbom"}, f"linux/{arch} is missing SBOM or in-toto provenance attestation"
        )
        result["platforms"][arch] = {"digest": digest, "manifest": manifest}
        result["attestations"][arch] = predicates
    return result


def resolve_inspected_oci_index(
    archive_index: dict[str, Any], files: dict[str, bytes], inspected: dict[str, Any], raw: bytes
) -> dict[str, Any]:
    """Match Skopeo's selected index to the exact image stored in the OCI layout.

    Buildx OCI exports may wrap the multi-platform image index in a single
    descriptor in index.json. Skopeo resolves that descriptor and prints the
    referenced index rather than the outer layout index. Prove the selected
    index is the SHA-256-addressed blob in the archive before accepting it.
    """
    _require(isinstance(inspected.get("manifests"), list), "skopeo raw inspection has no image manifests")
    if inspected == archive_index:
        return archive_index

    descriptors = archive_index.get("manifests") or []
    _require(len(descriptors) == 1, "ambiguous OCI layout index; expected a single image-index descriptor")
    descriptor = descriptors[0]
    _require(
        descriptor.get("mediaType")
        in {
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
        },
        "OCI layout descriptor is not a multi-platform image index",
    )
    selected_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    _require(
        _descriptor_digest(descriptor) == selected_digest,
        "skopeo raw index is not referenced by the OCI layout",
    )
    _require(_read_blob(files, selected_digest) == raw, "skopeo raw index bytes differ from OCI archive blob")
    return inspected


def skopeo_inspect_archive(archive: Path) -> tuple[dict[str, Any], bytes]:
    raw = _run_required(["skopeo", "inspect", "--raw", f"oci-archive:{archive}"])
    raw_bytes = raw.encode("utf-8")
    try:
        index = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerificationError("skopeo inspect --raw did not return JSON") from exc
    _require(isinstance(index, dict), "skopeo raw inspection must be an OCI index object")
    return index, raw_bytes


def build_copy_command(archive: Path, destination: Path, arch: str, tag: str) -> list[str]:
    return [
        "skopeo",
        "copy",
        "--override-os",
        "linux",
        "--override-arch",
        arch,
        f"oci-archive:{archive}",
        f"docker-archive:{destination}:{tag}",
    ]


def build_trivy_command(archive: Path, scanner: str, report: Path) -> list[str]:
    return [
        "trivy",
        "image",
        "--input",
        str(archive),
        "--scanners",
        scanner,
        "--severity",
        "HIGH,CRITICAL",
        "--ignore-unfixed=false",
        "--ignorefile",
        str(Path(__file__).resolve().parents[2] / ".trivyignore.yaml"),
        "--format",
        "json",
        "--output",
        str(report),
    ]


def summarize_trivy(report: Path, scanner: str) -> dict[str, Any]:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid Trivy {scanner} report: {report}") from exc
    findings = []
    for result in payload.get("Results", []):
        findings.extend(result.get("Vulnerabilities", []) if scanner == "vuln" else result.get("Secrets", []))
    return {"scanner": scanner, "report": str(report), "finding_count": len(findings), "findings": findings}


def _docker_inspect(tag: str) -> dict[str, Any]:
    raw = _run_required(["docker", "image", "inspect", tag])
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerificationError("docker image inspect did not return JSON") from exc
    _require(isinstance(values, list) and values, f"docker image inspect returned no image for {tag}")
    return values[0]


def _inspect_image(image: dict[str, Any], plan: dict[str, str]) -> None:
    config = image.get("Config") or {}
    labels = config.get("Labels") or {}
    for key, expected in {
        "org.opencontainers.image.source": "https://github.com/lien0219/openxflow",
        "org.opencontainers.image.revision": plan["source"],
        "org.opencontainers.image.version": plan["version"],
        "org.opencontainers.image.created": plan["created"],
    }.items():
        _require(labels.get(key) == expected, f"OCI label {key} does not match release plan")
    user = str(config.get("User") or "")
    _require(user not in {"", "0", "root", "0:0"}, "image does not declare a non-root runtime user")
    _require("7860/tcp" in (config.get("ExposedPorts") or {}), "image does not expose 7860/tcp")


def _probe(tag: str) -> None:
    probe = Path(__file__).with_name("openxflow_container_probe.py")
    _run_required(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "1000:0",
            "-v",
            f"{probe}:/tmp/openxflow_container_probe.py:ro",
            tag,
            "python",
            "/tmp/openxflow_container_probe.py",
        ]
    )


def build_smoke_run_command(tag: str, name: str, password: str) -> list[str]:
    """Run offline with an ephemeral superuser; never weaken image auth defaults."""
    _require(len(password) >= SMOKE_MIN_PASSWORD_LENGTH, "smoke-test password must be strong")
    return [
        "docker",
        "run",
        "--detach",
        "--network",
        "none",
        "--user",
        "1000:0",
        "--name",
        name,
        "--env",
        "LANGFLOW_DATABASE_URL=sqlite:////app/data/openxflow-verify.db",
        "--env",
        "LANGFLOW_CONFIG_DIR=/app/data/config",
        "--env",
        "LANGFLOW_AUTO_LOGIN=false",
        "--env",
        "LANGFLOW_SUPERUSER=langflow",
        "--env",
        f"LANGFLOW_SUPERUSER_PASSWORD={password}",
        "--env",
        "LANGFLOW_HOST=0.0.0.0",
        "--env",
        "LANGFLOW_PORT=7860",
        "--env",
        "LANGFLOW_SKIP_MCP_AUTO_INIT=true",
        "--env",
        "LANGFLOW_MODELS_DEV_REFRESH=false",
        "--env",
        "DO_NOT_TRACK=true",
        tag,
    ]


def smoke_startup_timeout(arch: str) -> int:
    """Allow QEMU-emulated ARM64 enough time without weakening readiness."""
    _require(arch in SMOKE_STARTUP_TIMEOUT_S, f"unsupported smoke-test architecture: {arch}")
    return SMOKE_STARTUP_TIMEOUT_S[arch]


def _smoke_diagnostics(name: str) -> str:
    """Include container exit state and *both* Docker log streams."""
    state = _run(["docker", "inspect", "--format", "{{.State.Status}} exit={{.State.ExitCode}}", name])
    state_summary = (state.stdout or state.stderr).strip() or "unavailable"
    logs = _run(["docker", "logs", "--tail", "100", name])
    output = "\n".join(part for part in (logs.stdout, logs.stderr) if part).strip()
    return f"container state: {state_summary}\ncontainer logs:\n{output[-4000:] or '(empty)'}"


def _smoke(tag: str, arch: str, names: list[str]) -> None:
    name = f"openxflow-verify-{uuid.uuid4().hex[:16]}-{arch}"
    names.append(name)
    # Credentials are unique to this isolated, disposable container. They are
    # never printed, committed, or embedded into the production image.
    password = secrets.token_urlsafe(32)
    try:
        result = _run(build_smoke_run_command(tag, name, password))
        if result.returncode:
            raise VerificationError(f"docker smoke container failed to start ({arch}): {result.stderr[-1000:]}")
        script = """\
import urllib.request
for path in ('/health_check', '/'):
    response = urllib.request.urlopen('http://127.0.0.1:7860' + path, timeout=3)
    body = response.read()
    assert response.status == 200 and body, path
print('smoke pass')
"""
        deadline = time.monotonic() + smoke_startup_timeout(arch)
        last_probe = ""
        while time.monotonic() < deadline:
            probe = _run(["docker", "exec", name, "python", "-c", script])
            if probe.returncode == 0:
                return
            last_probe = (probe.stderr or probe.stdout).strip()[-500:]
            running = _run(["docker", "inspect", "--format", "{{.State.Running}}", name])
            if running.returncode or running.stdout.strip().lower() != "true":
                diagnostics = _smoke_diagnostics(name)
                raise VerificationError(
                    f"docker smoke container exited before readiness ({arch})\n"
                    f"{diagnostics}\nlast readiness probe: {last_probe}"
                )
            time.sleep(SMOKE_POLL_INTERVAL_S)
        diagnostics = _smoke_diagnostics(name)
        raise VerificationError(
            f"docker smoke did not reach /health_check and / ({arch}) "
            f"within {smoke_startup_timeout(arch)}s\n"
            f"{diagnostics}\nlast readiness probe: {last_probe}"
        )
    finally:
        _run(["docker", "rm", "--force", name])


def verify(args: argparse.Namespace) -> dict[str, Any]:
    archive = Path(args.archive).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = validate_plan(json.loads(Path(args.plan).read_text(encoding="utf-8")))
    findings: list[dict[str, Any]] = []
    cleanup_names: list[str] = []
    identity: dict[str, Any] = {
        "schema": 1,
        "source": plan["source"],
        "version": plan["version"],
        "created": plan["created"],
        "platforms": list(PLATFORMS),
    }
    report: dict[str, Any] = {"identity": identity, "status": "BLOCKED", "findings": findings}
    try:
        inspected, raw = skopeo_inspect_archive(archive)
        identity["digest"] = "sha256:" + hashlib.sha256(raw.strip()).hexdigest()
        index, files = read_oci_archive(archive)
        selected_index = resolve_inspected_oci_index(index, files, inspected, raw)
        structure = validate_oci_index(selected_index, files)
        report["attestations"] = {}
        attestation_dir = output / "attestations"
        attestation_dir.mkdir(exist_ok=True)
        for arch, predicates in structure["attestations"].items():
            report["attestations"][arch] = {}
            for kind, value in predicates.items():
                path = attestation_dir / f"{arch}-{kind}.json"
                path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                report["attestations"][arch][kind] = str(path)
        for arch in PLATFORMS:
            archive_copy = output / f"openxflow-{arch}.docker.tar"
            tag = f"openxflow-verify-{plan['source'][:12]}-{arch}"
            _run_required(build_copy_command(archive, archive_copy, arch, tag))
            loaded = _run_required(["docker", "load", "--input", str(archive_copy)])
            _require(
                tag in loaded or _run(["docker", "image", "inspect", tag]).returncode == 0,
                f"docker load did not load expected tag {tag}",
            )
            image = _docker_inspect(tag)
            _inspect_image(image, plan)
            _probe(tag)
            _smoke(tag, arch, cleanup_names)
            arch_findings = {"platform": arch, "trivy": []}
            for scanner in ("vuln", "secret"):
                trivy_report = output / f"trivy-{arch}-{scanner}.json"
                _run_required(build_trivy_command(archive_copy, scanner, trivy_report))
                summary = summarize_trivy(trivy_report, scanner)
                arch_findings["trivy"].append(summary)
                _require(summary["finding_count"] == 0, f"Trivy {scanner} findings for linux/{arch}")
            findings.append(arch_findings)
            _run(["docker", "image", "rm", "--force", tag])
            archive_copy.unlink(missing_ok=True)
        report["status"] = "PASS"
    except (OSError, VerificationError, KeyError, json.JSONDecodeError) as exc:
        report["status"] = "BLOCKED" if isinstance(exc, (OSError, FileNotFoundError)) else "FAIL"
        report["error"] = str(exc)
    finally:
        for name in cleanup_names:
            _run(["docker", "rm", "--force", name])
    (output / "verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="candidate multi-arch OCI archive")
    parser.add_argument("--plan", required=True, help="release plan JSON with source/version/created")
    parser.add_argument(
        "--output-dir", required=True, help="directory for verification.json, reports, and attestations"
    )
    report = verify(parser.parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
