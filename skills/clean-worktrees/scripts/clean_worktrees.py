#!/usr/bin/env python3
"""Find and remove git worktrees whose branches are finished with.

Subcommands:

    scan  --dir <any path inside the repo> [--fetch]
    apply --dir <any path inside the repo> --paths <worktree> [<worktree> ...]
          [--prune] [--dry-run]

`scan` lists every worktree of the repo and classifies each one as REMOVE,
KEEP or PRUNE, with the reason. It only reads local refs unless `--fetch` is
given, in which case it runs `git fetch origin --prune` first - the one network
call in this script, and the skill only passes it after the user has said yes.

`apply` removes the worktrees named by `--paths`, then deletes each one's local
branch with `git branch -d`. It re-checks every path against the same rules
before touching it, so a worktree that changed between the scan and the yes
(new commits, new files) is skipped rather than removed on a stale verdict.
`--prune` also runs `git worktree prune` for entries whose folder is gone.
Nothing is ever forced: no `worktree remove --force`, no `branch -D`.

A worktree is removable only when ALL of these hold:
  - it is not the main checkout, not the one `--dir` sits in, and not locked
  - it has a branch checked out (not a detached HEAD)
  - that branch has an upstream on origin, and the upstream ref is gone
    (it was pushed once, and has since been deleted on origin)
  - the branch tip is contained in origin/<default branch>, so every commit
    reached the default branch and nothing was added locally since
  - `git status --porcelain` is empty: no modified or untracked files

"Not on origin" alone is not enough - a branch that was never pushed isn't on
origin either, and that is exactly the work this must never touch.

Exit codes: 0 ok, 3 not inside a git repo, 5 a git command failed,
7 apply finished but at least one removal or branch delete failed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

FETCH_TIMEOUT_S = 300


def run(cwd: Path, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def git(cwd: Path, *args: str, timeout: int | None = None) -> str:
    proc = run(cwd, *args, timeout=timeout)
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)
    # Newlines only - porcelain status encodes state in its leading columns.
    return proc.stdout.strip("\n")


def git_ok(cwd: Path, *args: str) -> bool:
    return run(cwd, *args).returncode == 0


def norm(p: str | Path) -> str:
    # `worktree list` and the shell can spell the same folder differently
    # (symlinks, trailing slashes) - compare them as the same path.
    return os.path.normcase(os.path.normpath(str(Path(p).resolve())))


def default_branch(repo: Path) -> str:
    """The repo's own default branch, asked of origin rather than assumed.

    Same resolution as create-branch: repos disagree between main and
    master, and some have a develop that is not the default.
    """
    ref = run(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    for candidate in ("main", "master"):
        if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{candidate}"):
            return candidate
    sys.stderr.write("Could not determine the default branch (no origin/HEAD, main or master).\n")
    raise SystemExit(5)


@dataclass
class Worktree:
    path: str
    branch: str | None = None      # short name; None when detached
    locked: bool = False
    prunable: bool = False
    bare: bool = False


def list_worktrees(repo: Path) -> list[Worktree]:
    out = git(repo, "worktree", "list", "--porcelain")
    trees: list[Worktree] = []
    for block in out.split("\n\n"):
        wt = None
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree":
                wt = Worktree(path=value)
            elif wt is None:
                continue
            elif key == "branch":
                wt.branch = value.removeprefix("refs/heads/")
            elif key == "locked":
                wt.locked = True
            elif key == "prunable":
                wt.prunable = True
            elif key == "bare":
                wt.bare = True
        if wt:
            trees.append(wt)
    return trees


def branch_finished(repo: Path, branch: str, default: str) -> bool:
    ref = f"refs/heads/{branch}"
    upstream = git(repo, "for-each-ref", "--format=%(upstream)", ref).strip()
    return (upstream.startswith("refs/remotes/origin/")
            and not git_ok(repo, "rev-parse", "--verify", "--quiet", upstream)
            and git_ok(repo, "merge-base", "--is-ancestor", ref, f"refs/remotes/origin/{default}"))


def classify(repo: Path, wt: Worktree, main_path: str, here: str, default: str):
    """(verdict, reason) - verdict is REMOVE, KEEP or PRUNE."""
    if wt.prunable:
        return "PRUNE", "folder is gone - stale entry"
    if norm(wt.path) == main_path:
        # The main checkout is the repo itself, so it is never removed - but if
        # it's parked on a finished branch, that's worth a nudge.
        if wt.branch and wt.branch != default and branch_finished(repo, wt.branch, default):
            return "KEEP", (f"main checkout - its branch is merged and gone on origin; "
                            f"switch it to {default}?")
        return "KEEP", "main checkout"
    if norm(wt.path) == here:
        return "KEEP", "this session is running in it"
    if wt.locked:
        return "KEEP", "locked (git worktree lock)"
    if wt.bare:
        return "KEEP", "bare"
    if not wt.branch:
        return "KEEP", "detached HEAD - no branch to judge"

    ref = f"refs/heads/{wt.branch}"
    upstream = git(repo, "for-each-ref", "--format=%(upstream)", ref).strip()
    if not upstream:
        return "KEEP", "never pushed (no upstream)"
    if not upstream.startswith("refs/remotes/origin/"):
        return "KEEP", f"upstream is not on origin ({upstream})"
    if git_ok(repo, "rev-parse", "--verify", "--quiet", upstream):
        return "KEEP", "branch still exists on origin"

    if not git_ok(repo, "merge-base", "--is-ancestor", ref, f"refs/remotes/origin/{default}"):
        ahead = git(repo, "rev-list", "--count", f"refs/remotes/origin/{default}..{ref}").strip()
        return "KEEP", (f"gone on origin but {ahead} commit(s) not in origin/{default} - "
                        "unmerged, squash-merged, or committed to after merge")

    dirty = git(Path(wt.path), "status", "--porcelain")
    if dirty:
        n = len(dirty.splitlines())
        return "KEEP", f"merged, but has {n} uncommitted/untracked file(s)"

    return "REMOVE", f"gone on origin, fully merged into origin/{default}, clean"


def resolve(dir_arg: str):
    start = Path(dir_arg)
    if not start.is_dir():
        sys.stderr.write(f"Not a directory: {start}\n")
        raise SystemExit(3)
    proc = run(start, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        sys.stderr.write(f"Not inside a git repository: {start}\n")
        raise SystemExit(3)
    return Path(proc.stdout.strip())


def fetch_age(repo: Path) -> str:
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    fh = common / "FETCH_HEAD"
    if not fh.exists():
        return "never fetched"
    mins = int((time.time() - fh.stat().st_mtime) // 60)
    if mins < 60:
        return f"last fetched {mins} min ago"
    if mins < 60 * 48:
        return f"last fetched {mins // 60} h ago"
    return f"last fetched {mins // (60 * 24)} days ago"


def evaluate(repo: Path):
    trees = list_worktrees(repo)
    main_path = norm(trees[0].path)
    here = norm(repo)
    default = default_branch(repo)
    return default, [(wt, *classify(repo, wt, main_path, here, default)) for wt in trees]


def cmd_scan(dir_arg: str, fetch: bool) -> int:
    repo = resolve(dir_arg)
    if fetch:
        try:
            git(repo, "fetch", "origin", "--prune", timeout=FETCH_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            sys.stderr.write(f"git fetch timed out after {FETCH_TIMEOUT_S}s.\n")
            return 5
    default, rows = evaluate(repo)

    print(f"repo:     {repo.name}  ({repo})")
    print(f"default:  origin/{default}")
    print(f"origin:   {'fetched just now' if fetch else fetch_age(repo)}")
    print()
    for wt, verdict, reason in rows:
        print(f"{verdict:<7} {wt.path}")
        print(f"        branch: {wt.branch or '(detached)'}")
        print(f"        {reason}")
    counts = {v: sum(1 for _, x, _ in rows if x == v) for v in ("REMOVE", "PRUNE", "KEEP")}
    print(f"\n{counts['REMOVE']} to remove, {counts['PRUNE']} to prune, {counts['KEEP']} kept")
    return 0


def delete_branch(repo: Path, branch: str, default: str) -> bool:
    """`git branch -d`, judged against origin/<default>.

    With its upstream gone, `-d` checks the branch against the HEAD of the
    checkout it runs in - and the main checkout is routinely parked on some
    other issue branch, so a genuinely merged branch gets refused. Pointing
    the upstream at origin/<default> first makes git's own check test exactly
    what classify() already verified, without resorting to -D.
    """
    key = f"branch.{branch}.merge"
    original = run(repo, "config", "--get", key).stdout.strip()
    git(repo, "config", key, f"refs/heads/{default}")
    proc = run(repo, "branch", "-d", branch)
    if proc.returncode == 0:
        return True
    if original:
        git(repo, "config", key, original)
    msg = (proc.stderr or proc.stdout).strip().splitlines()
    print(f"        branch {branch} kept - git branch -d refused: {msg[0] if msg else ''}")
    return False


def cmd_apply(dir_arg: str, paths: list[str], prune: bool, dry_run: bool) -> int:
    repo = resolve(dir_arg)
    default, rows = evaluate(repo)
    by_path = {norm(wt.path): (wt, verdict, reason) for wt, verdict, reason in rows}
    failed = False

    for p in paths:
        hit = by_path.get(norm(p))
        if hit is None:
            print(f"SKIP    {p}\n        not a worktree of {repo.name}")
            continue
        wt, verdict, reason = hit
        if verdict != "REMOVE":
            # The verdict changed since the scan - trust the fresh one.
            print(f"SKIP    {wt.path}\n        no longer removable: {reason}")
            continue
        if dry_run:
            print(f"WOULD   remove {wt.path} and delete branch {wt.branch}")
            continue

        proc = run(repo, "worktree", "remove", wt.path)
        if proc.returncode != 0:
            failed = True
            print(f"FAILED  {wt.path}\n        {(proc.stderr or proc.stdout).strip()}")
            continue
        print(f"REMOVED {wt.path}")

        if delete_branch(repo, wt.branch, default):
            print(f"        deleted branch {wt.branch}")
        else:
            failed = True

    if prune or failed:
        # After a failed remove (usually a permissions problem) the folder can be
        # half-deleted; prune tidies the entry if the folder is now gone.
        if dry_run:
            print("WOULD   run git worktree prune")
        else:
            git(repo, "worktree", "prune")
            print("PRUNED  stale worktree entries")

    return 7 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="classify every worktree (read-only unless --fetch)")
    p_scan.add_argument("--dir", required=True)
    p_scan.add_argument("--fetch", action="store_true",
                        help="git fetch origin --prune first (network)")

    p_apply = sub.add_parser("apply", help="remove the named worktrees and their branches")
    p_apply.add_argument("--dir", required=True)
    p_apply.add_argument("--paths", nargs="*", default=[])
    p_apply.add_argument("--prune", action="store_true",
                         help="also git worktree prune entries whose folder is gone")
    p_apply.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "scan":
        return cmd_scan(args.dir, args.fetch)
    return cmd_apply(args.dir, args.paths, args.prune, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
