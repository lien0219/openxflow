# ruff: noqa: TRY003,EM101,EM102

"""Runtime probe used by the OpenXFlow image verifier.

The probe is intentionally a small stdlib program executed inside an image
with ``--network none``. It checks the import and filesystem contract without
contacting a provider, database, or production endpoint.
"""

from __future__ import annotations

import importlib
import importlib.util
import stat
from pathlib import Path


class ProbeError(RuntimeError):
    """Image runtime probe failed."""


REQUIRED_MODULES = (
    "psycopg",
    "redis",
    "aiobotocore",
    "pgvector",
    "langflow",
    "langflow.custom",
    "langflow.api",
    "langflow.services.database",
    "lfx",
    "lfx.components",
)


def _check_writable_data() -> None:
    data = Path("/app/data")
    data.mkdir(parents=True, exist_ok=True)
    marker = data / ".openxflow-image-verification"
    marker.write_text("verified", encoding="utf-8")
    marker.unlink()


def _check_frontend() -> None:
    spec = importlib.util.find_spec("langflow")
    if spec is None or spec.origin is None:
        raise ProbeError("langflow package is not importable")
    frontend = Path(spec.origin).parent / "frontend"
    index = frontend / "index.html"
    if not index.is_file() or index.stat().st_size == 0:
        raise ProbeError(f"frontend index missing or empty: {index}")
    assets = frontend / "assets"
    if not assets.is_dir() or not any(path.is_file() for path in assets.rglob("*")):
        raise ProbeError(f"frontend assets missing or empty: {assets}")


def _check_package_permissions() -> None:
    spec = importlib.util.find_spec("langflow")
    roots = []
    if spec and spec.origin:
        roots.append(Path(spec.origin).parent)
    roots.append(Path("/app/.venv/lib"))
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                mode = path.stat().st_mode
            except OSError as exc:
                raise ProbeError(f"cannot inspect package path {path}: {exc}") from exc
            if mode & stat.S_IWOTH:
                raise ProbeError(f"package path is world writable: {path}")


def main() -> None:
    for module in REQUIRED_MODULES:
        importlib.import_module(module)
    _check_frontend()
    _check_writable_data()
    _check_package_permissions()
    print("openxflow container probe: PASS")


if __name__ == "__main__":
    main()
