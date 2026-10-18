"""Parse legacy release jobs and simulate their repository admission conditions."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
UPSTREAM = "langflow-ai/langflow"
FORK = "lien0219/openxflow"
WRITE_JOBS = {
    "release.yml": [
        "reserve-final-release",
        "publish-base",
        "publish-bundles",
        "publish-main",
        "publish-sdk",
        "publish-lfx",
        "call_docker_build_base",
        "call_docker_build_main",
        "call_docker_build_main_backend",
        "call_docker_build_main_frontend",
        "call_docker_build_main_ep",
        "call_docker_build_main_all",
        "create_release",
    ],
    "create-release.yml": ["create_release"],
    "prepare-release-tag.yml": ["prepare-tag"],
    "docker-build-v2.yml": [
        "build-base",
        "build-main",
        "build-main-backend",
        "build-main-frontend",
        "build-main-ep",
        "build-main-all",
        "create-manifest",
    ],
    "docker-nightly-build.yml": ["build-nightly", "create-manifest"],
    "docker-nightly-build-arch.yml": ["attempt-1", "attempt-2"],
    "nightly_build.yml": ["create-nightly-tag", "release-nightly-build"],
    "release_nightly.yml": [
        "publish-nightly-lfx",
        "publish-nightly-sdk",
        "publish-nightly-base",
        "publish-nightly-bundles",
        "publish-nightly-main",
        "call_docker_build_base",
        "call_docker_build_main",
    ],
    "release-lfx.yml": ["validate-version", "release-lfx", "build-docker", "create-release"],
    "release_bundles.yml": ["publish-bundles"],
    "desktop-release.yml": ["publish"],
}
CASES = [(filename, job) for filename, jobs in WRITE_JOBS.items() for job in jobs]


@cache
def load_workflow(filename: str) -> dict:
    return yaml.safe_load((WORKFLOWS / filename).read_text(encoding="utf-8"))


class Condition:
    """Small, fail-closed parser for the boolean subset used by legacy job gates.

    Values are supplied by tests. No workflow text is passed to eval, exec, a
    shell, or JavaScript; unsupported syntax and functions raise immediately.
    """

    TOKEN = re.compile(r"\s*(\&\&|\|\||==|!=|[!(),]|'(?:[^']|'')*'|[A-Za-z_][A-Za-z0-9_.-]*)")

    def __init__(self, expression: str, values: dict):
        expression = expression.strip()
        if expression.startswith("${{") and expression.endswith("}}"):
            expression = expression[3:-2].strip()
        self.tokens = []
        position = 0
        while position < len(expression):
            match = self.TOKEN.match(expression, position)
            if match is None:
                message = f"Unsupported condition near {expression[position:]!r}"
                raise ValueError(message)
            self.tokens.append(match[1])
            position = match.end()
        self.position = 0
        self.values = values

    def accept(self, symbol: str) -> bool:
        if self.position < len(self.tokens) and self.tokens[self.position] == symbol:
            self.position += 1
            return True
        return False

    def parse(self) -> bool:
        result = self.disjunction()
        assert self.position == len(self.tokens), self.tokens[self.position :]
        return bool(result)

    def disjunction(self):
        result = self.conjunction()
        while self.accept("||"):
            right = self.conjunction()
            result = result or right
        return result

    def conjunction(self):
        result = self.comparison()
        while self.accept("&&"):
            right = self.comparison()
            result = result and right
        return result

    def comparison(self):
        left = self.value()
        if self.accept("=="):
            return left == self.value()
        if self.accept("!="):
            return left != self.value()
        return left

    def value(self):
        if self.accept("!"):
            return not self.value()
        if self.accept("("):
            result = self.disjunction()
            assert self.accept(")")
            return result
        symbol = self.tokens[self.position]
        self.position += 1
        if symbol.startswith("'"):
            return symbol[1:-1].replace("''", "'")
        if symbol in {"true", "false"}:
            return symbol == "true"
        if self.accept("("):
            arguments = []
            if not self.accept(")"):
                arguments.append(self.disjunction())
                while self.accept(","):
                    arguments.append(self.disjunction())
                assert self.accept(")")
            if symbol == "always" and not arguments:
                return True
            if symbol == "cancelled" and not arguments:
                return False
            if symbol == "startsWith" and len(arguments) == 2:
                return arguments[0].startswith(arguments[1])
            message = f"Unsupported function {symbol}"
            raise ValueError(message)
        return self.values[symbol]


def passing_values(expression: str, repository: str, job: str, event: str) -> dict:
    values = {}
    for symbol in Condition.TOKEN.findall(expression):
        if not symbol.startswith(("github.", "inputs.", "needs.")):
            continue
        if symbol.endswith(".result"):
            values[symbol] = "success"
        elif symbol.endswith(".skipped"):
            values[symbol] = "false"
        elif symbol.endswith(".bundles-found"):
            values[symbol] = "1"
        elif symbol.endswith(".succeeded"):
            values[symbol] = "false"
        else:
            values[symbol] = True
    values.update(
        {
            "github.repository": repository,
            "github.event_name": event,
            "github.ref": "refs/tags/desktop-v1.2.3",
            "inputs.dry_run": False,
            "github.event.inputs.build_docker": "true",
            "github.event.inputs.create_github_release": "true",
            "inputs.release_type": job.removeprefix("build-") if job.startswith("build-") else "main",
        }
    )
    return values


@pytest.mark.parametrize(("filename", "job"), CASES)
@pytest.mark.parametrize("event", ["workflow_dispatch", "workflow_call", "push", "schedule", "pull_request_target"])
@pytest.mark.parametrize("repository", [FORK, "other-owner/langflow", "langflow-ai/langflow-fork"])
def test_legacy_writers_reject_forks_even_with_successful_needs_and_publish_inputs(filename, job, event, repository):
    expression = load_workflow(filename)["jobs"][job].get("if", "true")
    assert not Condition(expression, passing_values(expression, repository, job, event)).parse()


@pytest.mark.parametrize(("filename", "job"), CASES)
def test_legacy_writers_still_admit_the_upstream_contract(filename, job):
    expression = load_workflow(filename)["jobs"][job]["if"]
    assert Condition(expression, passing_values(expression, UPSTREAM, job, "workflow_dispatch")).parse()


def test_guard_parser_detects_an_always_or_bypass():
    expression = "github.repository == 'langflow-ai/langflow' || always()"
    assert Condition(expression, {"github.repository": FORK}).parse()
    with pytest.raises(ValueError, match="Unsupported function"):
        Condition("untrusted()", {}).parse()


def test_every_discovered_legacy_release_writer_has_an_inventory_entry():
    """Detect new writer jobs anywhere in workflows, including called workflows."""
    shell_writer = re.compile(
        r"\buv publish\b|\bmake sdk_publish\b|bundle_release_plan\.py publish|"
        r"docker (?:push|manifest push|buildx imagetools create)|"
        r"(?:createRelease|updateRelease|createRef|deleteRef)\s*\(|"
        r"^\s*(?:if\s+!?\s*)?git push[^\n]*(?:refs/tags|\$RELEASE_TAG|\$tag_ref|outputs\.release_tag)",
        re.MULTILINE,
    )
    discovered = set()
    for path in WORKFLOWS.glob("*.yml"):
        if path.name == "openxflow-production-release.yml":
            continue
        for name, job in load_workflow(path.name).get("jobs", {}).items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                action_writer = uses.startswith(("ncipollo/release-action@", "softprops/action-gh-release@"))
                image_writer = uses.startswith("docker/build-push-action@") and step.get("with", {}).get(
                    "push"
                ) not in {
                    None,
                    False,
                    "false",
                }
                commands = step.get("run", "") + step.get("with", {}).get("script", "")
                if action_writer or image_writer or shell_writer.search(commands):
                    discovered.add((path.name, name))
    assert discovered
    assert discovered <= set(CASES), discovered - set(CASES)


def test_reusable_production_calls_are_guarded_at_both_boundaries():
    called = set(WRITE_JOBS) - {"desktop-release.yml", "nightly_build.yml"}
    for path in WORKFLOWS.glob("*.yml"):
        for name, job in load_workflow(path.name).get("jobs", {}).items():
            uses = job.get("uses", "")
            if uses.startswith("./.github/workflows/") and uses.rsplit("/", 1)[-1] in called:
                assert (path.name, name) in CASES


def test_desktop_build_remains_read_only_and_artifact_only():
    workflow = load_workflow("desktop-release.yml")
    assert workflow["permissions"] == {"contents": "read"}
    build = workflow["jobs"]["build"]
    assert build.get("permissions", workflow["permissions"]) == {"contents": "read"}
    assert "if" not in build
    assert any(step.get("uses", "").startswith("actions/upload-artifact@") for step in build["steps"])
    installer = next(step for step in build["steps"] if step.get("name") == "Build installer")
    assert "--publish never" in installer["run"]
    assert workflow["jobs"]["publish"]["permissions"] == {"contents": "write"}


def test_standalone_bundle_smoke_tests_still_run_without_upstream_credentials():
    jobs = load_workflow("release_bundles.yml")["jobs"]
    assert "if" not in jobs["build-bundles"]
    assert "github.repository" not in jobs["test-install"]["if"]


def test_release_surfaces_have_explicit_fork_codeowners():
    owners = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    for pattern in [
        "/.github/workflows/",
        "/.github/CODEOWNERS",
        "/scripts/ci/openxflow_release.py",
        "/deploy/",
        "/docker/",
    ]:
        assert f"{pattern} @lien0219" in owners
