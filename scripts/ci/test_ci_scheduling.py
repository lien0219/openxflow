"""Regression coverage for branch admission and bounded CI test scheduling."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from test_openxflow_workflow_isolation import Condition

ROOT = Path(__file__).resolve().parents[2]


def _workflow(filename: str) -> dict:
    # BaseLoader constructs scalars only and preserves Actions' YAML 1.2 `on`.
    return yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,  # noqa: S506
    )


def _node(*args: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node, "Node.js is required to validate the actual CI planning scripts"
    return subprocess.run([node, *args], cwd=ROOT, check=False, capture_output=True, text=True)  # noqa: S603


def _bash() -> str:
    # Windows' system32/bash.exe launches WSL and drops ordinary Windows env
    # variables. Use Git Bash when these tests run in a Windows Python process.
    if os.name == "nt" and (git := shutil.which("git")):
        candidate = Path(git).parent.parent / "bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    bash = shutil.which("bash")
    assert bash, "Bash is required to exercise the workflow shell steps"
    return bash


def test_branch_push_and_pr_lifecycle_are_covered() -> None:
    branch = _workflow("branch-ci.yml")
    assert branch["on"]["push"]["branches"] == ["**"]
    assert branch["concurrency"]["cancel-in-progress"] == "true"
    assert branch["jobs"]["ci"]["uses"] == "./.github/workflows/ci.yml"
    events = _workflow("ci.yml")["on"]["pull_request"]["types"]
    assert {"opened", "synchronize", "reopened", "ready_for_review", "labeled", "unlabeled"} <= set(events)


@pytest.mark.parametrize(
    ("draft", "head", "run_ci"),
    [
        (False, "current", False),
        (True, "current", True),
        (False, "old", True),
        (False, "no-pr", True),
    ],
)
def test_open_pr_owns_validation_for_its_exact_head(*, draft: bool, head: str, run_ci: bool) -> None:
    steps = _workflow("branch-ci.yml")["jobs"]["plan"]["steps"]
    script = next(step["with"]["script"] for step in steps if step.get("id") == "pr-ci")
    fixture = {
        "draft": draft,
        "head": head,
    }
    harness = """
const fixture = JSON.parse(process.argv[2]);
const outputs = {};
const context = {repo: {owner: 'example', repo: 'app'}, ref: 'refs/heads/develop', sha: 'current'};
const github = {
  paginate: async () => fixture.head === 'no-pr' ? [] : [{number: 7, draft: fixture.draft,
    head: {sha: fixture.head, repo: {full_name: 'example/app'}}}],
  rest: {pulls: {list: {}}}
};
const summary = {addHeading() {return this}, addRaw() {return this}, async write() {}};
const core = {setOutput: (name, value) => outputs[name] = String(value), summary, info() {}};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
new AsyncFunction('github', 'context', 'core', process.argv[1])(github, context, core)
  .then(() => console.log(JSON.stringify(outputs))).catch(error => {console.error(error); process.exitCode = 1});
"""
    result = _node("-e", harness, script, json.dumps(fixture))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run-ci"] == str(run_ci).lower()


@pytest.mark.parametrize(("event", "draft", "expected"), [("push", False, True), ("pull_request", True, False)])
def test_ci_admits_branch_calls_without_running_draft_prs(event: str, *, draft: bool, expected: bool) -> None:
    condition = _workflow("ci.yml")["jobs"]["set-ci-condition"]["outputs"]["should-run-ci"]
    assert (
        Condition(condition, {"github.event_name": event, "github.event.pull_request.draft": draft}).parse() is expected
    )


@pytest.mark.parametrize(
    ("workflow", "job", "step_id"),
    [("ci.yml", "path-filter", "filter"), ("typescript_test.yml", "determine-test-suite", "filter")],
)
def test_push_path_filter_compares_to_the_previous_head(workflow: str, job: str, step_id: str) -> None:
    steps = _workflow(workflow)["jobs"][job]["steps"]
    inputs = next(step["with"] for step in steps if step.get("id") == step_id)
    context = {
        "github.event_name": "push",
        "github.ref": "refs/heads/develop",
        "github.sha": "current-sha",
        "inputs.ref": "current-sha",
        "github.event.pull_request.base.sha": "",
        "github.event.pull_request.head.sha": "",
    }
    # paths-filter uses push.before only when its base and head INPUTS name
    # the same branch. An explicit head SHA with a branch base compares the
    # current head to itself and silently skips all dependent tests.
    for name in ("base", "ref"):
        parser = Condition(inputs[name], context)
        assert parser.disjunction() == "refs/heads/develop"
        assert parser.position == len(parser.tokens)


@pytest.mark.parametrize(
    ("test_count", "limit", "expected"), [(1, 16, 1), (20, 16, 1), (21, 16, 2), (350, 16, 16), (1400, 70, 70)]
)
def test_playwright_matrix_bounds_jobs_and_assigns_every_shard(test_count: int, limit: int, expected: int) -> None:
    result = _node("scripts/ci/playwright_matrix.mjs", str(test_count), str(limit))
    assert result.returncode == 0, result.stderr
    outputs = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert int(outputs["shard_count"]) == expected
    assert json.loads(outputs["matrix"])["include"] == [
        {"shardIndex": index, "shardTotal": expected} for index in range(1, expected + 1)
    ]


@pytest.mark.parametrize(("count", "limit"), [("0", "16"), ("oops", "16"), ("10", "0"), ("10", "71")])
def test_playwright_matrix_rejects_empty_tests_and_invalid_limits(count: str, limit: str) -> None:
    result = _node("scripts/ci/playwright_matrix.mjs", count, limit)
    assert result.returncode != 0
    assert not result.stdout


@pytest.mark.parametrize(
    ("path", "required", "excluded"),
    [
        ("src/frontend/src/pages/LandingPage/index.tsx", {"frontend", "browser"}, {"templates"}),
        ("src/backend/base/langflow/api/v1/projects.py", {"python", "browser"}, {"frontend"}),
        ("src/langflow-core/pyproject.toml", {"python", "browser", "docker"}, {"frontend"}),
        ("Makefile.frontend", {"frontend", "browser"}, {"templates"}),
        ("src/backend/base/langflow/initial_setup/starter_projects/a.json", {"templates", "python"}, {"frontend"}),
        (".github/changes-filter.yaml", {"python", "frontend", "browser", "templates"}, set()),
        ("docs/docs/intro.mdx", {"docs"}, {"python", "frontend", "browser", "templates"}),
    ],
)
def test_change_filters_cover_runtime_and_ci_dependencies(path: str, required: set[str], excluded: set[str]) -> None:
    filters = yaml.safe_load((ROOT / ".github/changes-filter.yaml").read_text(encoding="utf-8"))
    selected = {name for name, patterns in filters.items() if any(fnmatch.fnmatchcase(path, p) for p in patterns)}
    assert required <= selected
    assert not excluded & selected


def test_backend_only_changes_do_not_run_jest_but_still_run_browser_tests() -> None:
    jobs = _workflow("ci.yml")["jobs"]
    values = {
        "inputs.run-all-tests": False,
        "needs.set-ci-condition.outputs.should-run-tests": "true",
        "needs.path-filter.result": "success",
        "needs.path-filter.outputs.docs-only": "false",
        "needs.path-filter.outputs.frontend": "false",
        "needs.path-filter.outputs.browser": "true",
    }
    assert not Condition(jobs["test-frontend-unit"]["if"], values).parse()
    assert Condition(jobs["test-frontend"]["if"], values).parse()


def test_full_ci_includes_docker_and_is_available_manually() -> None:
    workflow = _workflow("ci.yml")
    assert workflow["on"]["workflow_dispatch"]["inputs"]["run-all-tests"]["type"] == "boolean"
    values = {
        "inputs.run-all-tests": True,
        "needs.set-ci-condition.outputs.should-run-tests": "true",
        "needs.path-filter.outputs.docker": "false",
    }
    assert Condition(workflow["jobs"]["test-docker"]["if"], values).parse()
    browser = workflow["jobs"]["test-frontend"]["with"]
    assert browser["tests_folder"] == "${{ inputs.frontend-tests-folder || 'tests' }}"
    assert "inputs.run-all-tests" in browser["release"]


def test_jest_shards_have_one_blocking_report_and_one_merged_coverage_artifact() -> None:
    jobs = _workflow("jest_test.yml")["jobs"]
    shards = jobs["test-shard"]["strategy"]["matrix"]["shard"]
    assert shards == ["1", "2", "3", "4"]
    report = jobs["jest-unit-tests"]
    assert report["name"] == "Frontend Jest Unit Tests"
    assert "test-shard" in report["needs"]
    assert any(step.get("with", {}).get("name") == "jest-coverage" for step in report["steps"])


@pytest.mark.parametrize(("present_shards", "result"), [(3, "success"), (4, "failure"), (4, "success")])
def test_jest_report_requires_every_shard_and_a_successful_test_result(
    tmp_path: Path, present_shards: int, result: str
) -> None:
    steps = _workflow("jest_test.yml")["jobs"]["jest-unit-tests"]["steps"]
    merge = next(
        step["run"] for step in steps if step.get("name") == "Verify shard results and merge complete coverage"
    )
    # Exercise the real admission checks before nyc (which belongs to the
    # frontend environment, not the lightweight CI-script test environment).
    admission = merge.split("npx --no-install nyc merge", 1)[0]
    for shard in range(1, present_shards + 1):
        folder = tmp_path / "jest-shards" / f"jest-shard-{shard}"
        for artifact in ("coverage/jest/coverage-final.json", "test-results/junit.xml"):
            path = folder / artifact
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
    completed = subprocess.run(  # noqa: S603
        [_bash(), "-c", admission],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_WORKSPACE": tmp_path.as_posix(), "SHARD_RESULT": result},
        check=False,
        capture_output=True,
        text=True,
    )
    assert (completed.returncode == 0) is (present_shards == 4 and result == "success")


def test_frontend_lint_checks_the_pushed_main_commit(tmp_path: Path) -> None:
    git_executable = shutil.which("git")
    assert git_executable, "Git is required to exercise the workflow diff"

    def git(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603
            [git_executable, *args], cwd=tmp_path, check=True, capture_output=True, text=True
        )
        return completed.stdout.strip()

    git("init", "--initial-branch=main")
    git("config", "user.email", "ci-lint-test@example.invalid")
    git("config", "user.name", "CI Lint Test")
    git("config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("base", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "base")
    before = git("rev-parse", "HEAD")
    file = tmp_path / "src/frontend/src/new-file.ts"
    file.parent.mkdir(parents=True)
    file.write_text("export const changed = true;", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "frontend change")
    # origin/main already points at the pushed head. Comparing to it would
    # incorrectly produce an empty diff and skip the new source file.
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    steps = _workflow("lint-js.yml")["jobs"]["run-linters"]["steps"]
    lint = next(step for step in steps if step.get("name") == "Run Biome on PR-changed files")
    assert "github.event.before" in lint["env"]["BASE_SHA"]
    detection = lint["run"].split("# Biome runs from src/frontend", 1)[0]
    completed = subprocess.run(  # noqa: S603
        [_bash(), "-c", detection],
        cwd=tmp_path,
        env={**os.environ, "BASE_REF": "main", "BASE_SHA": before},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "src/frontend/src/new-file.ts" in completed.stdout
