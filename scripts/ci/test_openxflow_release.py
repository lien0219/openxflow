"""Release admission and real Git history tests; no external writes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from openxflow_release import (
    Git,
    ReleaseContractError,
    find_boundary,
    parse_version,
    read_version,
    validate_event,
    validate_rules,
    validate_transition,
)

SHA = "a" * 40


def event():
    return {
        "action": "closed",
        "repository": {"full_name": "lien0219/openxflow"},
        "pull_request": {
            "number": 7,
            "merged": True,
            "merge_commit_sha": SHA,
            "base": {"ref": "main", "repo": {"full_name": "lien0219/openxflow"}},
        },
    }


@pytest.mark.parametrize("value", ["0.0.0", "0.1.0", "1.13.42", "10.0.0"])
def test_semver(value):
    assert parse_version(value) == tuple(map(int, value.split(".")))
    assert read_version(value + "\n") == value
    assert read_version(value + "\r\n") == value


@pytest.mark.parametrize(
    "value",
    ["", " 0.1.0", "0.1.0 ", "01.2.3", "1.2", "1.2.3rc1", "v1.2.3", "1.2.3\n\n", "1.2.3\nx", "1.\n2.3", "\ufeff1.2.3"],
)
def test_version_file_is_strict(value):
    with pytest.raises(ReleaseContractError):
        read_version(value)


@pytest.mark.parametrize(
    "name",
    [
        "push",
        "workflow_dispatch",
        "workflow_call",
        "workflow_run",
        "schedule",
        "release",
        "pull_request_target",
        "create",
    ],
)
def test_non_pr_events_never_admitted(name):
    with pytest.raises(ReleaseContractError):
        validate_event(event(), name, "lien0219/openxflow")


@pytest.mark.parametrize(
    ("location", "value"),
    [
        ("action", "opened"),
        ("action", "synchronize"),
        ("merged", False),
        ("merged", "true"),
        ("base", "develop"),
        ("base", "feature/a"),
        ("base", "sync/official"),
        ("base", "official"),
        ("base", "release/1.0"),
        ("sha", "b" * 39),
        ("repository", "another/openxflow"),
    ],
)
def test_event_denials(location, value):
    payload = event()
    if location == "action":
        payload[location] = value
    elif location == "merged":
        payload["pull_request"][location] = value
    elif location == "base":
        payload["pull_request"]["base"]["ref"] = value
    elif location == "sha":
        payload["pull_request"]["merge_commit_sha"] = value
    else:
        payload["repository"]["full_name"] = value
    with pytest.raises(ReleaseContractError):
        validate_event(payload, "pull_request", "lien0219/openxflow")


def test_closed_merged_main_event():
    assert validate_event(event(), "pull_request", "lien0219/openxflow") == (7, SHA)


def test_version_transition_and_retry():
    assert validate_transition(None, "0.1.0")
    assert validate_transition("0.1.0", "0.1.1")
    assert not validate_transition("0.1.1", "0.1.1")
    with pytest.raises(ReleaseContractError):
        validate_transition("0.1.1", "0.1.0")


@pytest.fixture
def repo(tmp_path):
    def cmd(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    cmd("init", "-b", "main")
    cmd("config", "user.name", "Release Test")
    cmd("config", "user.email", "release-test@example.invalid")
    (tmp_path / "deploy").mkdir()

    def commit(version=None):
        if version:
            (tmp_path / "deploy/IMAGE_VERSION").write_text(version + "\n", encoding="utf-8")
        cmd("add", ".")
        cmd("commit", "--allow-empty", "-m", "test")
        return cmd("rev-parse", "HEAD")

    baseline = commit("0.1.0")
    return cmd, commit, Git(tmp_path), baseline


@pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
def test_exact_merge_boundary_for_three_github_strategies(repo, method):
    cmd, commit, git, baseline = repo
    cmd("checkout", "-b", "feature")
    commit("0.2.0")
    commit()
    cmd("checkout", "main")
    before = commit()
    if method == "merge":
        cmd("merge", "--no-ff", "feature", "-m", "Merge PR")
    elif method == "squash":
        cmd("merge", "--squash", "feature")
        commit()
    else:
        cmd("checkout", "feature")
        cmd("rebase", "main")
        cmd("checkout", "main")
        cmd("merge", "--ff-only", "feature")
    source = cmd("rev-parse", "HEAD")
    introduced = set(cmd("rev-list", "--first-parent", f"{before}..{source}").splitlines())
    boundary = find_boundary(git, source, lambda sha: sha in introduced, 3)
    assert boundary == before
    assert boundary != baseline
    assert git.version(boundary) == "0.1.0"
    assert git.version(source) == "0.2.0"
    assert validate_transition(git.version(boundary), git.version(source))


def test_ordinary_pr_cannot_steal_unfinished_version_release(repo):
    _, commit, git, baseline = repo
    release_source = commit("0.2.0")
    ordinary_source = commit()
    boundary = find_boundary(git, ordinary_source, lambda sha: sha == ordinary_source, 1)
    assert boundary == release_source
    assert not validate_transition(git.version(boundary), git.version(ordinary_source))
    assert git.ancestor(baseline, ordinary_source)
    assert not git.ancestor(ordinary_source, release_source)


def test_ambiguous_rebase_evidence_fails_closed(repo):
    _, commit, git, _ = repo
    source = commit("0.2.0")
    with pytest.raises(ReleaseContractError, match="association"):
        find_boundary(git, source, lambda _: False, 1)
    with pytest.raises(ReleaseContractError, match="bound"):
        find_boundary(git, source, lambda _: True, 1)


def good_rules():
    return [
        {
            "type": "pull_request",
            "parameters": {"require_code_owner_review": True, "required_approving_review_count": 1},
        },
        {"type": "non_fast_forward"},
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "OpenXFlow release policy"},
                    {"context": "OpenXFlow image rehearsal"},
                ],
            },
        },
    ]


def test_bootstrap_requires_effective_main_rules():
    validate_rules(good_rules())
    for index in range(4):
        rules = good_rules()
        rules.pop(index)
        with pytest.raises(ReleaseContractError):
            validate_rules(rules)
    rules = good_rules()
    rules[0]["parameters"]["require_code_owner_review"] = False
    with pytest.raises(ReleaseContractError):
        validate_rules(rules)
    rules = good_rules()
    rules[3]["parameters"]["required_status_checks"] = []
    with pytest.raises(ReleaseContractError):
        validate_rules(rules)


def test_seed_is_valid_without_freezing_future_bumps():
    root = Path(__file__).resolve().parents[2]
    parse_version(read_version((root / "deploy/IMAGE_VERSION").read_text(encoding="utf-8")))
