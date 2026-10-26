"""Static contract checks for the OpenXFlow production image."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "docker" / "build_and_push.Dockerfile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "openxflow-production-release.yml"


def test_product_version_is_independent_and_strictly_seeded() -> None:
    value = (REPO_ROOT / "deploy" / "IMAGE_VERSION").read_text(encoding="utf-8")
    assert re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\n", value)


def test_runtime_image_has_openxflow_provenance_and_upstream_attribution() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    for label in (
        "org.opencontainers.image.title",
        "org.opencontainers.image.description",
        "org.opencontainers.image.version",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.created",
        "org.opencontainers.image.source",
        "org.opencontainers.image.url",
    ):
        assert label in dockerfile
    assert 'org.opencontainers.image.title="OpenXFlow"' in dockerfile
    assert 'com.openxflow.upstream.source="https://github.com/langflow-ai/langflow"' in dockerfile
    assert "USER user" in dockerfile
    assert "FROM runtime AS full" in dockerfile


def test_all_image_targets_inherit_exposed_http_port_from_runtime() -> None:
    """Docker inspect must report 7860/tcp for base, full and bundle images."""
    runtime = _stage("runtime")
    assert "LANGFLOW_HOST=0.0.0.0" in runtime
    assert "LANGFLOW_PORT=7860" in runtime
    assert re.search(r"(?m)^EXPOSE 7860/tcp$", runtime)
    for target in ("base", "full", "full-bundles"):
        assert f"FROM runtime AS {target}" in DOCKERFILE.read_text(encoding="utf-8")


def test_production_workflow_never_emits_latest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert ":latest" not in workflow.lower()
    assert "type=raw,value=latest" not in workflow.lower()


def _stage(name: str) -> str:
    source = DOCKERFILE.read_text(encoding="utf-8")
    return re.split(r"(?m)^FROM ", source.split(f" AS {name}\n", 1)[1], maxsplit=1)[0]


@pytest.mark.parametrize("stage", ["full-dependencies", "full-builder", "full-bundles-builder"])
def test_full_distribution_installs_shared_vector_backend(stage: str) -> None:
    commands = re.findall(r"uv sync\b(.*?)(?:&&|\n\n)", _stage(stage), flags=re.DOTALL)
    assert commands, f"{stage} no longer resolves the full dependency environment"
    for command in commands:
        assert "--extra postgresql" in command
        assert "--extra pgvector" in command
        assert "--frozen" in command


def test_frontend_dependency_cache_precedes_source_copy() -> None:
    stage = _stage("frontend-builder")
    metadata_copy = re.search(r"COPY[^\n]*package\.json[^\n]*package-lock\.json", stage)
    assert metadata_copy is not None
    install = stage.index("npm ci")
    source_copy = stage.index("COPY ./src/frontend /tmp/src/frontend")
    assert metadata_copy.start() < install < source_copy < stage.index("npm run build")


def test_runtime_retains_the_actual_upstream_license() -> None:
    assert "Copyright (c) 2024 Langflow" in (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "COPY ./LICENSE /usr/share/licenses/openxflow/LICENSE" in _stage("runtime")


def test_base_image_is_immutable_and_node_download_is_checked() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        r"ARG PYTHON_IMAGE=registry\.access\.redhat\.com/ubi10/python-314-minimal@sha256:[a-f0-9]{64}", source
    )
    builder = _stage("builder-base")
    assert "sha256sum --check" in builder
    assert builder.index("sha256sum --check") < builder.index("tar -xJf /tmp/node.tar.xz")
    for arch in ("x64", "arm64"):
        assert re.search(rf"{arch}\).*?NODE_SHA256=[a-f0-9]{{64}}", builder)


def test_runtime_node_images_include_the_brotli_security_fix() -> None:
    for name in (
        "build_and_push.Dockerfile",
        "build_and_push_backend.Dockerfile",
        "build_and_push_ep.Dockerfile",
    ):
        source = (REPO_ROOT / "docker" / name).read_text(encoding="utf-8")
        match = re.search(r"(?m)^ARG NODE_VERSION=(\d+)\.(\d+)\.(\d+)$", source)
        assert match is not None, name
        assert tuple(map(int, match.groups())) >= (24, 22, 1), name


def test_runtime_node_checksum_printf_uses_a_real_newline() -> None:
    for name in (
        "build_and_push.Dockerfile",
        "build_and_push_backend.Dockerfile",
        "build_and_push_ep.Dockerfile",
    ):
        source = (REPO_ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "printf '%s  /tmp/node.tar.xz\\n' \"$NODE_SHA256\"" in source, name
        assert "printf '%s  /tmp/node.tar.xz\\\\n' \"$NODE_SHA256\"" not in source, name


def test_final_virtualenvs_apply_the_pip_vendor_patch_after_copy() -> None:
    targets = {
        "build_and_push.Dockerfile": ("base", "full-bundles", "full"),
        "build_and_push_backend.Dockerfile": ("runtime",),
        "build_and_push_ep.Dockerfile": ("runtime",),
    }
    for name, stage_names in targets.items():
        source = (REPO_ROOT / "docker" / name).read_text(encoding="utf-8")
        for stage_name in stage_names:
            stage = _stage(stage_name) if name == "build_and_push.Dockerfile" else source.split(" AS runtime\n", 1)[1]
            copy_match = re.search(r"(?m)^COPY --from=.* /app/\.venv /app/\.venv$", stage)
            assert copy_match is not None, (name, stage_name)
            copy = copy_match.start()
            patch = stage.index("COPY ./docker/patch_hardened_pip_vendor.sh", copy_match.end())
            run = stage.index("sh /tmp/patch_hardened_pip_vendor.sh", patch)
            assert copy < patch < run
            assert "find /app/.venv -type d -path '*/pip/_vendor' -exec chown -R 1000:0 {} +" in stage[run:]


def test_brotli_lock_constraints_include_the_security_fix() -> None:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    overrides = project["tool"]["uv"]["override-dependencies"]
    assert "brotli>=1.2.1,<2.0.0; platform_python_implementation == 'CPython'" in overrides
    assert "brotlicffi>=1.2.1.0,<2.0.0; platform_python_implementation != 'CPython'" in overrides

    base = tomllib.loads((REPO_ROOT / "src/backend/base/pyproject.toml").read_text(encoding="utf-8"))
    assert "ddgs>=9.0.0" in base["project"]["optional-dependencies"]["duckduckgo"]
    assert (
        "brotli>=1.2.1,<2.0.0; platform_python_implementation == 'CPython'"
        in base["project"]["optional-dependencies"]["duckduckgo"]
    )
    assert (
        "brotlicffi>=1.2.1.0,<2.0.0; platform_python_implementation != 'CPython'"
        in base["project"]["optional-dependencies"]["duckduckgo"]
    )

    bundle = tomllib.loads((REPO_ROOT / "src/bundles/duckduckgo/pyproject.toml").read_text(encoding="utf-8"))
    assert "brotli>=1.2.1,<2.0.0; platform_python_implementation == 'CPython'" in bundle["project"]["dependencies"]
    assert (
        "brotlicffi>=1.2.1.0,<2.0.0; platform_python_implementation != 'CPython'" in bundle["project"]["dependencies"]
    )

    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    httpx = next(package for package in lock["package"] if package["name"] == "httpx")
    assert {
        dependency["name"]: dependency.get("marker") for dependency in httpx["optional-dependencies"]["brotli"]
    } == {
        "brotli": "platform_python_implementation == 'CPython'",
        "brotlicffi": "platform_python_implementation != 'CPython'",
    }
    assert {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"] in {"brotli", "brotlicffi"}
    } == {"brotli": "1.2.1", "brotlicffi": "1.2.1.0"}


def test_context_excludes_local_state_and_secret_files() -> None:
    patterns = set((REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {
        "**/.git",
        "**/.venv*",
        "**/.cache",
        "**/.env",
        "**/.env.*",
        "**/*.env",
        "**/node_modules",
        "**/*.pem",
        "**/*.key",
        "**/.npmrc",
        "**/.pypirc",
        "**/*.db",
        "**/*.sqlite*",
    } <= patterns
    # Ordinary source builds still need the checked-in artifact directory and LICENSE.
    assert ".release-artifacts" not in patterns
    assert "LICENSE" not in patterns
