# ruff: noqa: INP001, SIM108

"""Offline image migration fingerprint: parse/hash files without importing application code.

Executed through stdin with no network, secrets, or data mounts. It does not
connect to the database, initialize services, or run Alembic migrations.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def tree_hash(directory):
    files = sorted(directory.rglob("*.py"))
    if not files:
        message = "migration or model files are missing from this image"
        raise ValueError(message)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def fingerprint(package):
    revisions = set()
    parents = set()
    for path in sorted((package / "alembic" / "versions").glob("*.py")):
        if path.name == "__init__.py":
            continue
        values = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision", "depends_on"}:
                    values[target.id] = ast.literal_eval(node.value)
        revision = values.get("revision")
        if not isinstance(revision, str) or revision in revisions or "down_revision" not in values:
            message = "invalid or duplicate migration revision"
            raise ValueError(message)
        revisions.add(revision)
        for key in ("down_revision", "depends_on"):
            parent = values.get(key)
            if parent:
                parents.update([parent] if isinstance(parent, str) else parent)
    if not revisions or parents - revisions or len(revisions - parents) != 1:
        message = "migration graph is incomplete or has multiple heads"
        raise ValueError(message)
    uid = getattr(os, "getuid", None)
    if uid is None:
        uid = 1000
    else:
        uid = uid()
    return {
        "schema": 1,
        "uid": uid,
        "heads": sorted(revisions - parents),
        "alembic_sha256": tree_hash(package / "alembic"),
        "models_sha256": tree_hash(package / "services" / "database"),
    }


if __name__ == "__main__":
    spec = importlib.util.find_spec("langflow")
    if spec is None or not spec.submodule_search_locations:
        message = "langflow package is absent"
        raise ValueError(message)
    print(json.dumps(fingerprint(Path(next(iter(spec.submodule_search_locations))))))  # noqa: T201
