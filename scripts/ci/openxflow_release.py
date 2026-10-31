"""Fail-closed admission for the only OpenXFlow production release entry point.

Network adapters are deliberately small so history and failure behavior can be
tested without credentials. CLI writers independently revalidate the event.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY = "lien0219/openxflow"
IMAGE = "ghcr.io/" + REPOSITORY
SOURCE = "https://github.com/" + REPOSITORY
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
CHECKS = {"OpenXFlow release policy", "OpenXFlow image rehearsal"}


class ReleaseContractError(ValueError):
    """A publication invariant is unproven or violated."""


def require(condition, message):
    if not condition:
        raise ReleaseContractError(message)


def parse_version(text):
    require(isinstance(text, str) and SEMVER.fullmatch(text), "Invalid strict MAJOR.MINOR.PATCH version")
    return tuple(map(int, text.split(".")))


def read_version(text):
    # Permit one conventional line ending; never trim spaces, BOMs or extra lines.
    if text.endswith("\r\n"):
        version = text[:-2]
    elif text.endswith("\n"):
        version = text[:-1]
    else:
        version = text
    require("\r" not in version, "IMAGE_VERSION contains an invalid carriage return")
    parse_version(version)
    return version


def validate_transition(before, after):
    current = parse_version(after)
    if before is None:
        return True
    previous = parse_version(before)
    require(current >= previous, "Product version must not decrease")
    return current != previous


def validate_event(event, event_name, repository):
    pr = event.get("pull_request", {})
    base = pr.get("base", {})
    require(repository == REPOSITORY == event.get("repository", {}).get("full_name"), "Wrong repository")
    require(event_name == "pull_request" and event.get("action") == "closed", "Only closed PR events are admitted")
    require(pr.get("merged") is True, "PR must be merged")
    require(base.get("ref") == "main" and base.get("repo", {}).get("full_name") == REPOSITORY, "Wrong PR base")
    require(SHA.fullmatch(pr.get("merge_commit_sha") or ""), "Invalid merge_commit_sha")
    require(isinstance(pr.get("number"), int) and pr["number"] > 0, "Missing PR number")
    return pr["number"], pr["merge_commit_sha"]


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        require(urllib.parse.urlparse(newurl).scheme == "https", "Insecure HTTP redirect")
        if redirected and urllib.parse.urlparse(req.full_url).netloc != urllib.parse.urlparse(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def request(url, headers, method="GET", data=None):
    require(url.startswith("https://"), "HTTPS required")
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.build_opener(SafeRedirect()).open(req, timeout=120) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


class GitHub:
    def __init__(self):
        self.headers = {
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def api(self, path, method="GET", body=None, missing=False):
        url = "https://api.github.com/repos/" + REPOSITORY + "/" + path
        data = None if body is None else json.dumps(body).encode()
        status, raw, _ = request(url, self.headers, method, data)
        if status == 404 and missing:
            return None
        require(200 <= status < 300, f"GitHub {method} {path.split('?')[0]} returned HTTP {status}")
        return json.loads(raw) if raw else None

    def pages(self, path, key=None):
        output = []
        for page in range(1, 101):
            response = self.api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
            items = response[key] if key else response
            require(isinstance(items, list), "Expected paginated API list")
            output.extend(items)
            if len(items) < 100:
                return output
        raise ReleaseContractError("API pagination bound exceeded")


class Git:
    def __init__(self, directory="."):
        self.directory = str(directory)

    def run(self, *args):
        return subprocess.check_output(["git", "-C", self.directory, *args], text=True, encoding="utf-8").strip()

    def ancestor(self, older, newer):
        result = subprocess.run(["git", "-C", self.directory, "merge-base", "--is-ancestor", older, newer], check=False)
        require(result.returncode in (0, 1), "Unable to verify Git ancestry")
        return result.returncode == 0

    def parents(self, sha):
        return self.run("show", "-s", "--format=%P", sha).split()

    def version(self, sha):
        entries = self.run("ls-tree", sha, "--", "deploy/IMAGE_VERSION")
        if not entries:
            return None
        raw = subprocess.check_output(["git", "-C", self.directory, "show", f"{sha}:deploy/IMAGE_VERSION"])
        return read_version(raw.decode("utf-8"))


def find_boundary(git, source, associated, commit_count):
    """First parent of merge, or bounded PR-associated first-parent rebase span.

    GitHub associates squash/rebased commits with their merged PR. If that
    evidence is absent or ambiguous, stop instead of guessing from base/head SHA.
    """
    parents = git.parents(source)
    require(1 <= len(parents) <= 2, "Unsupported merge topology")
    if len(parents) == 2:
        return parents[0]
    require(associated(source), "Missing source PR association")
    current = source
    for _ in range(min(commit_count, 250) + 1):
        parents = git.parents(current)
        require(len(parents) == 1, "PR association walk exceeded bound")
        parent = parents[0]
        if not associated(parent):
            return parent
        current = parent
    raise ReleaseContractError("PR association walk exceeded bound")


def validate_rules(rules):
    types = {rule["type"] for rule in rules}
    require(
        {"pull_request", "non_fast_forward", "deletion", "required_status_checks"} <= types,
        "main requires PR, no force push/deletion, and required checks",
    )
    # GitHub enforces its own PR approval policy before merging. Do not
    # additionally require a Code Owner review here: a single-maintainer
    # repository can deliberately require zero approvals while keeping the
    # PR, status-check, no-force-push and no-deletion rules in effect.
    checks = [rule.get("parameters", {}) for rule in rules if rule["type"] == "required_status_checks"]
    contexts = {check["context"] for rule in checks for check in rule.get("required_status_checks", [])}
    require(
        CHECKS <= contexts and any(r.get("strict_required_status_checks_policy") for r in checks),
        "main requires current release policy and image rehearsal checks",
    )


def readiness(api):
    require(os.environ.get("OPENXFLOW_RELEASE_ENABLED") == "true", "Administrator bootstrap readiness is not confirmed")
    require(api.api("branches/main")["protected"], "main is not protected")
    validate_rules(api.pages("rules/branches/main"))


def live_event(api):
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    number, sha = validate_event(event, os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REPOSITORY"])
    pr = api.api(f"pulls/{number}")
    require(
        pr["merged"] is True and pr["merge_commit_sha"] == sha and pr["base"]["ref"] == "main",
        "Live PR does not match the closed event",
    )
    return number, sha, pr


def plan_release(api, git):
    readiness(api)
    number, source, _pr = live_event(api)
    require(git.run("rev-parse", "HEAD") == source, "Checkout is not the verified merge source")
    git.run("fetch", "origin", "main", "--no-tags")
    require(git.ancestor(source, "FETCH_HEAD"), "Source is not in protected main history")

    def associated(sha):
        prs = api.pages(f"commits/{sha}/pulls")
        return any(
            item["number"] == number and item["merged_at"] is not None and item["base"]["ref"] == "main" for item in prs
        )

    # The pull request payload exposes ``commits_url`` rather than a numeric
    # count. Fetch the bounded list so rebase walks cannot run indefinitely.
    commit_count = len(api.pages(f"pulls/{number}/commits"))
    boundary = find_boundary(git, source, associated, commit_count)
    before, version = git.version(boundary), git.version(source)
    require(version is not None, "Missing IMAGE_VERSION")
    changed = validate_transition(before, version)
    recovered = False if changed else release_recovery_requested(git, boundary, source, version)
    return {
        "source": source,
        "version": version,
        "before": before,
        "boundary": boundary,
        "changed": changed or recovered,
        "recovered": recovered,
        "pr": number,
        "created": git.run("show", "-s", "--format=%cI", source),
    }


def release_recovery_requested(git, boundary, source, version):
    """Recover an unpublished version through an explicit single-PR marker.

    The first attempt introduces vX.Y.Z. For a subsequent failed attempt,
    introduce vX.Y.Z-retry-<previous-main-SHA-prefix>. Every attempt must
    add a *new* marker naming its exact previous protected-main commit.
    Normal unchanged-version merges remain ineligible for publication.
    """
    original = f"deploy/release-recovery/v{version}"
    if git.run("ls-tree", boundary, "--", original):
        path = f"{original}-retry-{boundary[:12]}"
        if git.run("ls-tree", boundary, "--", path):
            return False
        if not git.run("ls-tree", source, "--", path):
            return False
        original_sha = git.run("show", f"{boundary}:{original}")
        require(SHA.fullmatch(original_sha), "Original recovery marker must contain a commit SHA")
        require(
            git.run("show", f"{source}:{original}") == original_sha,
            "Original recovery marker must remain unchanged",
        )
    else:
        path = original
        if git.run("ls-tree", boundary, "--", path):
            return False
        if not git.run("ls-tree", source, "--", path):
            return False

    expected = git.run("show", f"{source}:{path}")
    require(SHA.fullmatch(expected), "Recovery marker needs an exact main commit SHA")
    require(expected == boundary, "Recovery marker does not match the prior main commit")
    require(git.version(boundary) == version, "Recovery requires an unchanged product version")
    return True


def validate_coordinate_version(git, plan, version, target):
    """Allow delayed older events only when a newer release is their descendant."""
    candidate = parse_version(plan["version"])
    existing = parse_version(version)
    require(SHA.fullmatch(target), "Existing version has invalid source")
    if existing == candidate:
        require(target == plan["source"], "Version already belongs to another source")
    elif git.ancestor(target, plan["source"]):
        require(existing < candidate, "Version is below an earlier published version")
    else:
        require(
            git.ancestor(plan["source"], target) and existing > candidate,
            "Existing release is outside the ordered main lineage",
        )


def guard_plan(plan, api):
    _, source, _ = live_event(api)
    require(plan["source"] == source, "Plan belongs to another event")
    parse_version(plan["version"])


def ensure_release(api, source, version, digest):
    """Create or verify the exact tag and Release; never mutate a conflict."""
    parse_version(version)
    require(SHA.fullmatch(source), "Release source is not a full commit SHA")
    require(DIGEST.fullmatch(digest), "Release digest is not immutable")
    tag = "v" + version
    encoded = urllib.parse.quote(tag, safe="")
    ref = api.api("git/ref/tags/" + encoded, missing=True)
    if ref is None:
        api.api("git/refs", method="POST", body={"ref": "refs/tags/" + tag, "sha": source})
    else:
        target = ref.get("object", {}).get("sha", "")
        if ref.get("object", {}).get("type") == "tag":
            target = api.api("git/tags/" + target)["object"]["sha"]
        require(target == source, f"immutable Git tag {tag} points to another commit")

    marker = f"Source SHA: {source}\nDigest: {digest}\n"
    existing = api.api("releases/tags/" + encoded, missing=True)
    if existing is not None:
        body = existing.get("body") or ""
        require(
            existing.get("tag_name") == tag and marker in body,
            f"existing GitHub Release {tag} has conflicting source or digest",
        )
        return existing
    body = (
        f"## OpenXFlow {version}\n\n"
        f"- Product version: `{version}`\n"
        f"- Source SHA: {source}\n"
        f"- Digest: {digest}\n"
        f"- Architectures: `linux/amd64`, `linux/arm64`\n\n"
        f"### Production image\n\n"
        f"```bash\n docker pull {IMAGE}:main-v{version}\n```\n\n"
        f"Application image rollback does not roll back PostgreSQL migrations. "
        f"Back up production data and review migration compatibility before deployment.\n\n" + marker
    )
    return api.api(
        "releases",
        method="POST",
        body={
            "tag_name": tag,
            "target_commitish": source,
            "name": "OpenXFlow " + version,
            "body": body,
            "draft": False,
            "prerelease": False,
        },
    )


def output(**values):
    if "GITHUB_OUTPUT" in os.environ:
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "readiness", "release"])
    parser.add_argument("--output", default="plan.json")
    parser.add_argument("--source")
    parser.add_argument("--version")
    parser.add_argument("--digest")
    args = parser.parse_args()
    api = GitHub()
    if args.command == "readiness":
        readiness(api)
    elif args.command == "release":
        ensure_release(api, args.source or "", args.version or "", args.digest or "")
    else:
        plan = plan_release(api, Git())
        Path(args.output).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        output(source=plan["source"], version=plan["version"], changed=plan["changed"], created=plan["created"])


if __name__ == "__main__":
    main()
