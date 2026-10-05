#!/usr/bin/env python3
"""Repo analysis and gh/git mechanics for the create-pr skill.

Subcommands:

    context  --dir <any path inside the repo> [--base <branch>]
    commits  --dir <any path inside the repo> --base <branch>
    push     --dir <any path inside the repo> --branch <name> [--dry-run]
    open-pr  --dir <any path inside the repo> --base <branch> --head <branch>
             --title <title> --body-file <path> [--dry-run]

`context` resolves the repo, the issue number from the branch name, the base
(default) branch, how far the branch has diverged from it, and whether it's
already pushed. `commits` prints the commit log between base and HEAD with
per-commit diffstats - the raw material for grouping into the "What changed"
section. `push` and `open-pr` are the only two subcommands that touch the
network, and only run for real without --dry-run.

All git reads here stay local - no `fetch`, `ls-remote`, or `git remote show`
(which contacts the remote by default). If the default branch can't be
worked out from local refs, `context` says so rather than guessing over the
network; the caller asks the user instead.

Exit codes (context): 0 ok, 2 no commits ahead of base, 3 not inside a git
repo, 4 already on the repo default branch, 5 a git command failed,
7 base branch could not be determined locally.

Exit codes (commits): 0 ok, 2 no commits, 3 not inside a git repo,
5 a git command failed, 6 the base ref does not exist locally.

Exit codes (push): 0 ok (or nothing to push), 3 not inside a git repo,
5 a git command failed, 10 the checked-out branch isn't the one named.

Exit codes (open-pr): 0 created, 3 not inside a git repo, 5 gh failed,
8 a PR already exists for this branch (its URL is printed), 9 gh is not on
PATH or not authenticated.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Same convention as create-branch: feat/42-dark-mode-toggle.
ISSUE_RE = re.compile(r"(?:^|/)(\d+)(?:-|$)")

# Candidates tried only against local remote-tracking refs - never against
# the network. Only needed when origin/HEAD isn't set locally.
DEFAULT_BRANCH_CANDIDATES = ("master", "main")


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)
    return proc.stdout.strip("\n")


def git_ok(repo: Path, *args: str) -> bool:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0


def repo_root(start: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip())


def resolve_repo(dir_arg: str) -> Path:
    start = Path(dir_arg)
    if not start.is_dir():
        sys.stderr.write(f"Not a directory: {start}\n")
        raise SystemExit(3)
    repo = repo_root(start)
    if repo is None:
        sys.stderr.write(f"Not inside a git repository: {start}\n")
        raise SystemExit(3)
    return repo


def issue_number(branch: str) -> str | None:
    """Same convention as create-commit/create-branch: searched, not anchored,
    so a prefixed branch (`backup/feat/42-...`) still yields its real number."""
    match = ISSUE_RE.search(branch)
    return match.group(1) if match else None


def default_branch_local_only(repo: Path) -> str | None:
    """The repo's default branch, from local refs only.

    Deliberately weaker than create-branch's detection (no `git remote show
    origin`, which contacts the network): this runs during the read-only
    analysis phase, before anything has been confirmed. If this can't work it
    out, the caller asks the user rather than falling back to a network call.
    """
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    for candidate in DEFAULT_BRANCH_CANDIDATES:
        if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{candidate}"):
            return candidate
    return None


def remote_status(repo: Path, branch: str) -> str:
    """Human-readable divergence between the local branch and origin/<branch>."""
    if not git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{branch}"):
        return "not pushed yet"
    ahead = git(repo, "rev-list", "--count", f"origin/{branch}..{branch}", check=False)
    behind = git(repo, "rev-list", "--count", f"{branch}..origin/{branch}", check=False)
    if ahead == "0" and behind == "0":
        return "pushed, up to date with origin"
    parts = []
    if ahead and ahead != "0":
        parts.append(f"{ahead} commit(s) ahead of origin/{branch}")
    if behind and behind != "0":
        parts.append(f"{behind} commit(s) behind origin/{branch}")
    return "pushed, " + ", ".join(parts)


def cmd_context(dir_arg: str, base_arg: str | None) -> int:
    repo = resolve_repo(dir_arg)
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    issue = issue_number(branch)

    base = base_arg or default_branch_local_only(repo)

    print(f"repo:    {repo.name}")
    print(f"dir:     {repo}")
    print(f"branch:  {branch}")
    print(f"issue:   {'#' + issue if issue else '(none in branch name - ask which issue)'}")

    if base is None:
        print("base:    could not be determined from local refs")
        print("\nNo origin/HEAD set locally and neither master nor main exists as a")
        print("remote-tracking branch. Ask the user which branch to open the PR against")
        print("rather than guessing or fetching to find out.")
        return 7

    print(f"base:    {base}" + (" (requested)" if base_arg else " (repo default)"))

    if branch == base:
        print("\nCurrently on the base branch itself - there's no feature branch to")
        print("open a PR from.")
        return 4

    if not git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{base}") \
            and not git_ok(repo, "rev-parse", "--verify", base):
        sys.stderr.write(f"'{base}' is not a known local or remote-tracking branch.\n")
        return 7

    base_ref = f"origin/{base}" if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{base}") else base
    ahead = git(repo, "rev-list", "--count", f"{base_ref}..{branch}")
    behind = git(repo, "rev-list", "--count", f"{branch}..{base_ref}")
    print(f"ahead:   {ahead} commit(s) ahead of {base_ref}, {behind} behind")

    dirty = git(repo, "status", "--porcelain")
    print(f"tree:    {'clean' if not dirty else 'has uncommitted changes'}")
    if dirty:
        print(dirty)

    print(f"remote:  {remote_status(repo, branch)}")

    if ahead == "0":
        print(f"\nNo commits between {base_ref} and {branch} - nothing to open a PR for.")
        return 2

    return 0


def cmd_commits(dir_arg: str, base: str) -> int:
    repo = resolve_repo(dir_arg)
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    base_ref = f"origin/{base}" if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{base}") else base
    if not git_ok(repo, "rev-parse", "--verify", base_ref):
        sys.stderr.write(f"'{base}' is not a known local or remote-tracking branch.\n")
        return 6

    count = git(repo, "rev-list", "--count", f"{base_ref}..{branch}")
    if count == "0":
        print(f"No commits between {base_ref} and {branch}.")
        return 2

    log = git(repo, "log", "--reverse", "--stat", f"{base_ref}..{branch}")
    print(log)
    return 0


def cmd_push(dir_arg: str, branch_arg: str, dry_run: bool) -> int:
    repo = resolve_repo(dir_arg)
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if current != branch_arg:
        sys.stderr.write(
            f"Checked-out branch is {current}, not {branch_arg} - refusing to push the wrong branch.\n"
        )
        return 10

    status = remote_status(repo, current)
    if dry_run:
        print(f"would run: git push -u origin {current}")
        print(f"current remote status: {status}")
        return 0

    if status == "pushed, up to date with origin":
        print(f"{current} is already pushed and up to date - nothing to push.")
        return 0

    git(repo, "push", "-u", "origin", current)
    print(f"pushed {current} to origin.")
    return 0


def cmd_open_pr(dir_arg: str, base: str, head: str, title: str, body_file: str, dry_run: bool) -> int:
    repo = resolve_repo(dir_arg)

    if shutil.which("gh") is None:
        sys.stderr.write("gh is not on PATH.\n")
        return 9

    if dry_run:
        print(f"would check for an existing PR: gh pr view {head}")
        print(f"would run: gh pr create --draft --base {base} --head {head} "
              f"--title \"{title}\" --body-file {body_file}")
        return 0

    existing = subprocess.run(
        ["gh", "pr", "view", head, "--json", "url,number,isDraft,state"],
        cwd=repo, capture_output=True, text=True,
    )
    if existing.returncode == 0:
        print("A PR already exists for this branch:")
        print(existing.stdout.strip())
        return 8

    created = subprocess.run(
        ["gh", "pr", "create", "--draft", "--base", base, "--head", head,
         "--title", title, "--body-file", body_file],
        cwd=repo, capture_output=True, text=True,
    )
    if created.returncode != 0:
        sys.stderr.write((created.stderr or created.stdout).strip() + "\n")
        return 5

    print(created.stdout.strip())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_context = sub.add_parser("context", help="repo, issue number, base branch, divergence")
    p_context.add_argument("--dir", required=True)
    p_context.add_argument("--base", help="override the auto-detected base branch")

    p_commits = sub.add_parser("commits", help="commit log with diffstats, base..HEAD")
    p_commits.add_argument("--dir", required=True)
    p_commits.add_argument("--base", required=True)

    p_push = sub.add_parser("push", help="push the current branch (network)")
    p_push.add_argument("--dir", required=True)
    p_push.add_argument("--branch", required=True)
    p_push.add_argument("--dry-run", action="store_true")

    p_pr = sub.add_parser("open-pr", help="create a draft PR via gh (network)")
    p_pr.add_argument("--dir", required=True)
    p_pr.add_argument("--base", required=True)
    p_pr.add_argument("--head", required=True)
    p_pr.add_argument("--title", required=True)
    p_pr.add_argument("--body-file", required=True)
    p_pr.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.cmd == "context":
        return cmd_context(args.dir, args.base)
    if args.cmd == "commits":
        return cmd_commits(args.dir, args.base)
    if args.cmd == "push":
        return cmd_push(args.dir, args.branch, args.dry_run)
    return cmd_open_pr(args.dir, args.base, args.head, args.title, args.body_file, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
