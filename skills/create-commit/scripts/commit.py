#!/usr/bin/env python3
"""Commit message convention and staged committing for the create-commit skill.

Subcommands:

    issue  --dir <any path inside the repo>
    check  --message "Fix client note replication (#42)"
    check  --test                     # golden tests over the convention
    plan   --dir <any path inside the repo>
    apply  --dir <any path inside the repo> --plan <plan.json> [--dry-run]

`issue` reads the issue number out of the current branch name, which is where
it already lives once create-branch has run. `check` validates one subject
line against the house convention. `plan` prints the working-tree change set with
per-file line counts, which is the raw material for grouping changes into
commits. `apply` takes a grouping and makes the commits.

The plan file is JSON:

    {"commits": [
        {"message": "Add theme setting to the config schema (#42)",
         "files": ["src/config/schema.ts"]},
        {"message": "Add dark mode toggle to the settings page (#42)",
         "files": ["src/settings/ThemeToggle.tsx", "src/settings/ThemeToggle.test.tsx"]}
    ]}

Each commit stages exactly its own files and commits with a pathspec, so
anything you had staged for other files is left alone rather than swept into
the first commit. Files may be left out of the plan entirely - they simply stay
uncommitted, and `apply` reports what it left behind. Nothing is pushed.

Exit codes: 0 ok, 2 nothing to commit, 3 not inside a git repo, 4 a message
fails the convention, 5 a git command failed, 6 the plan does not match the
working tree.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Git's own convention is 50, but the trailing issue reference eats into that.
# Warning rather than failing keeps the check useful without being pedantic.
SUBJECT_SOFT_LIMIT = 72

# Same convention as create-branch: the issue number sits at the start of the
# branch name or straight after a slash (feat/42-dark-mode-toggle).
ISSUE_RE = re.compile(r"(?:^|/)(\d+)(?:-|$)")

# The subject ends with the issue reference: "Fix the thing (#42)".
SUBJECT_RE = re.compile(r"^(.*?)\s*\(#(\d+)\)$")

# Past-tense openers. The convention is the imperative, so these get a nudge -
# not a rejection, because some of them are legitimately the right word
# ("Enable" vs "Enabled" is a real distinction only the author can judge).
PAST_TENSE_HINTS = {
    "added": "Add", "changed": "Change", "corrected": "Correct",
    "created": "Create", "deleted": "Delete", "disabled": "Disable",
    "enabled": "Enable", "fixed": "Fix", "implemented": "Implement",
    "improved": "Improve", "moved": "Move", "refactored": "Refactor",
    "removed": "Remove", "renamed": "Rename", "resolved": "Resolve",
    "updated": "Update",
}


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)
    return proc.stdout.strip("\n")


def git_ok(repo: Path, *args: str) -> bool:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0


def git_try(repo: Path, *args: str) -> tuple[bool, str]:
    """Like git(), but hands the failure back instead of exiting.

    Used inside the commit loop: once some commits exist, dying on git's error
    alone would leave the user unsure which of them were actually made.
    """
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def repo_root(start: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip())


def current_branch(repo: Path) -> str:
    """The checked-out branch, or "HEAD" when detached.

    `symbolic-ref` rather than `rev-parse --abbrev-ref HEAD`, because the latter
    fails in a repo with no commits yet - exactly when the first commit is made.
    """
    proc = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"],
                          cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() or "HEAD"


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
    """The issue number inside a branch name, or None.

    Searched rather than anchored, because a branch can carry a prefix -
    `backup/feat/42-old-approach` is a backup of issue 42's branch, and the
    number that belongs in its commits is 42.
    """
    match = ISSUE_RE.search(branch)
    return match.group(1) if match else None


def check_message(message: str, issue: str | None = None) -> tuple[list[str], list[str]]:
    """Validate one subject line. Returns (errors, warnings).

    Errors mean the message breaks the convention and would look wrong in the
    log next to everything else. Warnings are judgement calls left to the author.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if "\n" in message.strip("\n"):
        errors.append("the subject must be a single line")
    subject = message.strip("\n").split("\n")[0]

    if not subject.strip():
        errors.append("the message is empty")
        return errors, warnings

    if subject != subject.strip():
        warnings.append("leading or trailing whitespace was trimmed")
        subject = subject.strip()

    if subject.startswith("#"):
        # Git treats a leading # as a comment and strips the whole line as soon
        # as the message passes through an editor (amend, rebase -i).
        errors.append('must not start with "#" - put the issue at the end, '
                      'e.g. "Fix client note replication (#42)"')
        return errors, warnings

    match = SUBJECT_RE.match(subject)
    if not match:
        errors.append(
            "must end with the issue reference in brackets, "
            'e.g. "Fix client note replication (#42)"'
        )
        return errors, warnings

    body, found = match.group(1), match.group(2)

    if issue and found != issue.lstrip("#"):
        errors.append(f"references #{found} but this branch is for #{issue.lstrip('#')}")

    if not body.strip():
        errors.append("the issue reference alone is not a commit message")
        return errors, warnings

    if body[0].islower():
        warnings.append(f'start with a capital - "{body[0].upper()}{body[1:]}"')

    if body.rstrip().endswith("."):
        warnings.append("subject lines don't take a trailing full stop")

    first = body.split()[0].lower()
    if first in PAST_TENSE_HINTS:
        warnings.append(
            f'"{body.split()[0]}" is past tense - the convention is the '
            f'imperative, so "{PAST_TENSE_HINTS[first]}"'
        )

    if len(subject) > SUBJECT_SOFT_LIMIT:
        warnings.append(f"subject is {len(subject)} chars (soft limit {SUBJECT_SOFT_LIMIT})")

    return errors, warnings


GOLDEN = [
    # (message, issue, expect_ok, substring expected in the warnings)
    ("Fix client note replication (#42)", "42", True, None),
    ("Add dark mode toggle to the settings page (#7)", None, True, None),
    ("Fixed the search component (#14)", None, True, "past tense"),
    ("Fix the thing. (#14)", None, True, "full stop"),
    ("fix the thing (#14)", None, True, "capital"),
    # Failures: these would look wrong sitting in the log.
    ("Fix client note replication", None, False, None),
    ("#42 Fix the thing", None, False, None),
    ("(#42)", None, False, None),
    ("", None, False, None),
    ("Fix thing (42)", None, False, None),
    ("Fix thing (#42)", "7", False, None),
]


def run_tests() -> int:
    failures = 0
    for message, issue, expect_ok, want_warning in GOLDEN:
        errors, warnings = check_message(message, issue)
        ok = not errors
        label = message or "(empty)"
        problems = []
        if ok != expect_ok:
            problems.append(f"expected {'ok' if expect_ok else 'rejected'}, got the opposite")
            if errors:
                problems.append(f"errors: {errors}")
        if want_warning and not any(want_warning in w for w in warnings):
            problems.append(f"expected a warning mentioning {want_warning!r}, got {warnings}")
        if problems:
            failures += 1
            print(f"FAIL  {label}")
            for p in problems:
                print(f"      {p}")
        else:
            print(f"PASS  {label}")

    for branch, expected in [
        ("feat/42-dark-mode-toggle", "42"),
        ("backup/feat/42-old-approach", "42"),
        ("main", None),
        ("release/2.4", None),
    ]:
        got = issue_number(branch)
        if got != expected:
            failures += 1
            print(f"FAIL  issue from {branch}: expected {expected}, got {got}")
        else:
            print(f"PASS  issue from {branch} -> {got}")

    total = len(GOLDEN) + 4
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


def change_set(repo: Path) -> list[dict]:
    """Every path with something to commit, from `git status -z`.

    NUL-delimited because paths can have spaces in them, and a
    rename arrives as two paths in one record - both of which have to be listed
    in a plan for the rename to commit as a rename.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repo, capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.stderr.write((out.stderr or out.stdout).strip() + "\n")
        raise SystemExit(5)

    parts = out.stdout.split("\0")
    entries: list[dict] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        if not item:
            i += 1
            continue
        xy, path = item[:2], item[3:]
        entry = {"status": xy, "path": path}
        if xy[0] in ("R", "C") and i + 1 < len(parts):
            entry["from"] = parts[i + 1]
            i += 2
        else:
            i += 1
        entries.append(entry)
    return entries


def describe(status: str) -> str:
    x, y = status[0], status[1]
    if status == "??":
        return "new"
    if "D" in (x, y):
        return "deleted"
    if x == "R":
        return "renamed"
    if x == "A":
        return "added"
    return "modified"


def numstat(repo: Path) -> dict[str, tuple[str, str]]:
    """Added/removed line counts per path, for tracked changes.

    Size is the cheapest signal for whether a group of files is really one
    concern or several, so it's worth putting in front of whoever is grouping.
    """
    counts: dict[str, tuple[str, str]] = {}
    for ref in ("HEAD", None):
        args = ["diff", "--numstat", "-z"]
        if ref:
            args.append(ref)
        raw = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
        if raw.returncode != 0:
            continue
        fields = raw.stdout.split("\0")
        i = 0
        while i + 2 < len(fields) or (i < len(fields) and fields[i]):
            chunk = fields[i]
            if not chunk:
                break
            try:
                added, removed, path = chunk.split("\t")
            except ValueError:
                i += 1
                continue
            if path == "":
                # Rename records carry the two paths in the following fields.
                path = fields[i + 2] if i + 2 < len(fields) else ""
                i += 3
            else:
                i += 1
            if path:
                counts[path] = (added, removed)
        if counts:
            break
    return counts


def cmd_plan(dir_arg: str) -> int:
    repo = resolve_repo(dir_arg)
    entries = change_set(repo)
    branch = current_branch(repo)
    issue = issue_number(branch)

    print(f"repo:    {repo}")
    print(f"branch:  {branch}")
    print(f"issue:   {'#' + issue if issue else '(none in branch name - ask which issue)'}")

    if not entries:
        print("\nNothing to commit - the working tree is clean.")
        return 2

    counts = numstat(repo)
    print(f"\n{len(entries)} path(s) with changes:\n")
    for entry in entries:
        added, removed = counts.get(entry["path"], ("-", "-"))
        line = f"  {describe(entry['status']):9} +{added:>5} -{removed:>5}  {entry['path']}"
        if "from" in entry:
            line += f"   (from {entry['from']})"
        print(line)

    staged = [e for e in entries if e["status"][0] not in (" ", "?")]
    if staged:
        print(f"\n{len(staged)} path(s) already staged. `apply` commits by pathspec, so")
        print("anything you staged that a commit doesn't list stays staged and uncommitted.")
    return 0


def load_plan(plan_path: str) -> list[dict]:
    try:
        raw = Path(plan_path).read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"Could not read the plan: {exc}\n")
        raise SystemExit(6)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"The plan is not valid JSON: {exc}\n")
        raise SystemExit(6)

    commits = data.get("commits") if isinstance(data, dict) else data
    if not isinstance(commits, list) or not commits:
        sys.stderr.write('The plan needs a non-empty "commits" list.\n')
        raise SystemExit(6)
    for commit in commits:
        if not isinstance(commit, dict) or "message" not in commit or "files" not in commit:
            sys.stderr.write('Every commit needs "message" and "files".\n')
            raise SystemExit(6)
        if not isinstance(commit["files"], list) or not commit["files"]:
            sys.stderr.write(f'"{commit.get("message")}" lists no files.\n')
            raise SystemExit(6)
    return commits


def cmd_apply(dir_arg: str, plan_path: str, dry_run: bool) -> int:
    repo = resolve_repo(dir_arg)
    commits = load_plan(plan_path)

    branch = current_branch(repo)
    if branch == "HEAD":
        sys.stderr.write("HEAD is detached - check out a branch before committing.\n")
        return 5
    issue = issue_number(branch)

    entries = change_set(repo)
    if not entries:
        sys.stderr.write("Nothing to commit - the working tree is clean.\n")
        return 2

    known = {e["path"] for e in entries}
    known.update(e["from"] for e in entries if "from" in e)

    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}

    for index, commit in enumerate(commits, start=1):
        msg_errors, msg_warnings = check_message(commit["message"], issue)
        errors += [f"commit {index}: {e}" for e in msg_errors]
        warnings += [f"commit {index}: {w}" for w in msg_warnings]

        for path in commit["files"]:
            normalised = path.replace("\\", "/")
            if normalised not in known:
                # Almost always a path that was guessed rather than read from
                # the change set. Committing would silently skip it.
                errors.append(f"commit {index}: {path} has no changes to commit")
            elif normalised in seen:
                errors.append(
                    f"commit {index}: {path} is already in commit {seen[normalised]}"
                )
            else:
                seen[normalised] = index

    if errors:
        sys.stderr.write("The plan doesn't match the working tree:\n\n")
        for error in errors:
            sys.stderr.write(f"  {error}\n")
        return 6 if any("no changes" in e or "already in" in e for e in errors) else 4

    for warning in warnings:
        print(f"warning: {warning}")
    if warnings:
        print()

    leftover = sorted(known - set(seen))

    if dry_run:
        print(f"repo:    {repo}")
        print(f"branch:  {branch}\n")
        for index, commit in enumerate(commits, start=1):
            print(f"{index}. {commit['message']}")
            for path in commit["files"]:
                print(f"     {path}")
            print()
        if leftover:
            print(f"{len(leftover)} path(s) would stay uncommitted:")
            for path in leftover:
                print(f"  {path}")
        print("(dry run - nothing was committed)")
        return 0

    made: list[tuple[str, str]] = []

    def stop(index: int, detail: str) -> int:
        sys.stderr.write(f"commit {index} failed: {detail}\n")
        if made:
            sys.stderr.write(f"\n{len(made)} commit(s) were already made and are not rolled back:\n")
            for sha, message in made:
                sys.stderr.write(f"  {sha}  {message}\n")
            sys.stderr.write(f"\nFix the rest and re-run with a plan covering only what is left.\n")
        return 5

    for index, commit in enumerate(commits, start=1):
        files = [f.replace("\\", "/") for f in commit["files"]]
        # `-A` so a deletion still sitting in the working tree gets staged
        # rather than skipped. The pathspec keeps it scoped to this commit.
        ok, detail = git_try(repo, "add", "-A", "--", *files)
        if not ok:
            # `git rm` drops the entry from the index entirely, so the path is
            # in neither the working tree nor the index and `add` calls it a bad
            # pathspec - even though the deletion is staged and ready. `commit`
            # takes it by pathspec on its own, so only stop if nothing is staged.
            if git_ok(repo, "diff", "--cached", "--quiet", "--", *files):
                return stop(index, detail)
        elif git_ok(repo, "diff", "--cached", "--quiet", "--", *files):
            return stop(index, "nothing staged after add")
        # Committing with the same pathspec is what keeps anything else you had
        # staged out of this commit.
        ok, detail = git_try(repo, "commit", "-m", commit["message"].strip(), "--", *files)
        if not ok:
            return stop(index, detail)
        made.append((git(repo, "rev-parse", "--short", "HEAD"), commit["message"].strip()))

    print(f"{repo.name}: {len(made)} commit(s) on {branch}\n")
    for sha, message in made:
        print(f"  {sha}  {message}")
    if leftover:
        print(f"\n{len(leftover)} path(s) left uncommitted:")
        for path in leftover:
            print(f"  {path}")
    print("\nremote:  not pushed (local only)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_issue = sub.add_parser("issue", help="the issue number implied by the current branch")
    p_issue.add_argument("--dir", required=True)

    p_check = sub.add_parser("check", help="validate a subject line")
    p_check.add_argument("--message")
    p_check.add_argument("--issue", help="the issue number the message must reference")
    p_check.add_argument("--test", action="store_true", help="run the golden tests")

    p_plan = sub.add_parser("plan", help="print the change set to group into commits")
    p_plan.add_argument("--dir", required=True)

    p_apply = sub.add_parser("apply", help="make the commits described by a plan file")
    p_apply.add_argument("--dir", required=True)
    p_apply.add_argument("--plan", required=True, help="path to the plan JSON")
    p_apply.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.cmd == "issue":
        repo = resolve_repo(args.dir)
        branch = current_branch(repo)
        issue = issue_number(branch)
        if not issue:
            sys.stderr.write(f"No issue number in the branch name: {branch}\n")
            return 4
        print(issue)
        return 0

    if args.cmd == "check":
        if args.test:
            return run_tests()
        if not args.message:
            parser.error("check needs --message (or --test)")
        errors, warnings = check_message(args.message, args.issue)
        for warning in warnings:
            print(f"warning: {warning}")
        if errors:
            for error in errors:
                sys.stderr.write(f"error: {error}\n")
            return 4
        print("ok")
        return 0

    if args.cmd == "plan":
        return cmd_plan(args.dir)

    return cmd_apply(args.dir, args.plan, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
