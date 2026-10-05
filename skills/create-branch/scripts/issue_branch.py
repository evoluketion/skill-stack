#!/usr/bin/env python3
"""Branch naming and branch setup for the create-branch and initialise-agent skills.

Subcommands:

    slug      --type feat --issue 42 --summary "dark mode toggle"
    slug      --test                # golden tests over the convention
    setup     --dir <any path inside the repo> --branch <name>
              [--base <branch>] [--dry-run] [--worktree]
    plan-path --dir <any path inside the repo> [--issue 42]

`slug` encodes the branch-naming convention, `<type>/<issue>-<summary>`.
The summary is a short one written from the issue, not its verbatim title.
`setup` resolves which repo a directory belongs to, refuses on a dirty tree,
works out the base branch, returns to it, pulls, then creates and checks out
the issue branch. The base is that repo's own default branch unless `--base`
names another one; either way it is verified to exist before anything is
checked out. Nothing is pushed. `plan-path` prints where the issue's plan
lives: ~/.claude/issues/<owner>/<repo>/<issue>/plan.md.

The repo is always the one you are standing in - `setup` resolves it with
`git rev-parse --show-toplevel`, so a nested subfolder works. There is no
inference from issue contents and no repo-name lookup: either the directory
is inside a git repo or the command fails.

`--worktree` cuts the branch into a new sibling folder (<repo>-<issue>)
instead of switching this checkout: no dirty-tree check, this checkout is
untouched.

Exit codes: 0 ok, 2 dirty tree, 3 not inside a git repo, 4 bad branch name
or type, 5 a git command failed, 6 the requested base branch does not exist,
8 the worktree folder already exists (worktree mode only).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

MAX_BRANCH_LEN = 50

# The branch prefix says what kind of change the branch carries.
TYPES = ("feat", "fix", "docs", "chore", "refactor", "test", "perf", "ci", "build")

# The issue number sits at the start of the name or straight after a slash.
ISSUE_RE = re.compile(r"(?:^|/)(\d+)(?:-|$)")


def slugify(kind: str, issue: str, summary: str, max_len: int = MAX_BRANCH_LEN) -> str:
    """Build `feat/42-dark-mode-toggle` from a type, issue number and summary."""
    kind = kind.strip().lower()
    number = issue.strip().lstrip("#")
    s = unicodedata.normalize("NFKD", summary).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    prefix = f"{kind}/{number}"
    branch = f"{prefix}-{s}" if s else prefix

    if len(branch) > max_len:
        # Truncating changes what the user is about to create, so the caller
        # needs to be able to say so rather than presenting a shortened name as
        # though it came straight from the summary.
        branch = branch[:max_len]
        # Prefer cutting at a word boundary so the tail stays readable.
        if "-" in branch[len(prefix) + 1:]:
            branch = branch[: branch.rindex("-")]
        branch = branch.rstrip("-")
    return branch


def slug_with_note(kind: str, issue: str, summary: str, max_len: int = MAX_BRANCH_LEN):
    """The branch name, plus a note when the cap trimmed it.

    Comparing against an effectively uncapped run is how we know truncation
    happened, rather than threading a flag out of slugify() and complicating
    the one function whose output the golden tests pin.
    """
    branch = slugify(kind, issue, summary, max_len)
    full = slugify(kind, issue, summary, max_len=10**6)
    if branch == full:
        return branch, None
    note = (f"shortened to {len(branch)} chars at a word boundary "
            f"(the full summary would give {len(full)}, cap is {max_len})")
    return branch, note


def issue_number(branch: str) -> str | None:
    """The issue number inside a branch name, or None.

    Searched rather than anchored, so a prefixed backup such as
    `backup/feat/42-old-approach` still yields 42.
    """
    match = ISSUE_RE.search(branch)
    return match.group(1) if match else None


GOLDEN = [
    ("feat", "42", "Dark mode toggle", "feat/42-dark-mode-toggle"),
    ("fix", "#7", "Crash on empty CSV import", "fix/7-crash-on-empty-csv-import"),
    ("docs", "108", "README: install on Fedora", "docs/108-readme-install-on-fedora"),
    ("chore", "3", "Bump deps & tidy CI/config", "chore/3-bump-deps-tidy-ci-config"),
    ("feat", "5", "Café support", "feat/5-cafe-support"),
    ("Feat", "9", "  padded   spaces  ", "feat/9-padded-spaces"),
    ("fix", "12", "", "fix/12"),
    ("fix", "13", "...", "fix/13"),
]


# Worktree folders are <repo>-<issue>. A branch with no issue number keeps its
# own name, with slashes flattened so it stays one folder.
WORKTREE_GOLDEN = [
    ("feat/42-dark-mode-toggle", "budget-app-42"),
    ("fix/7", "budget-app-7"),
    ("spike/backup", "budget-app-spike-backup"),
]

ISSUE_GOLDEN = [
    ("feat/42-dark-mode-toggle", "42"),
    ("backup/feat/42-old-approach", "42"),
    ("fix/7", "7"),
    ("main", None),
    ("release/2.4", None),
    ("v2-cleanup", None),
]

ORIGIN_GOLDEN = [
    ("git@github.com:evoluketion/budget-app.git", ("evoluketion", "budget-app")),
    ("https://github.com/evoluketion/budget-app", ("evoluketion", "budget-app")),
    ("ssh://git@github.com/evoluketion/budget-app.git", ("evoluketion", "budget-app")),
    ("/srv/git/budget-app.git", None),
]


def run_tests() -> int:
    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if not ok and detail:
            print(f"      {detail}")

    for kind, issue, summary, expected in GOLDEN:
        got = slugify(kind, issue, summary)
        report(got == expected, expected, f"got: {got}")

    long_branch, long_note = slug_with_note("feat", "9", "word " * 30)
    report(len(long_branch) <= MAX_BRANCH_LEN and not long_branch.endswith("-") and bool(long_note),
           f"length cap ({len(long_branch)} chars, reported)", f"note={long_note!r}")

    # A name that fits must not claim to have been shortened - a false note
    # would send the skill into a confirmation about a problem that isn't there.
    short_branch, short_note = slug_with_note("fix", "1234", "Notes not replicating")
    report(short_note is None, f"no false note ({len(short_branch)} chars, under cap)",
           f"claimed: {short_note}")

    root = Path("/home/u/Programming/Github/budget-app")
    for branch, expected in WORKTREE_GOLDEN:
        got = worktree_dir(root, branch)
        report(got == root.parent / expected, f"worktree path {expected}", f"got: {got}")

    for branch, expected in ISSUE_GOLDEN:
        got = issue_number(branch)
        report(got == expected, f"issue from {branch} -> {expected}", f"got: {got}")

    for url, expected in ORIGIN_GOLDEN:
        got = parse_origin(url)
        report(got == expected, f"origin {url}", f"got: {got}")

    total = len(GOLDEN) + 2 + len(WORKTREE_GOLDEN) + len(ISSUE_GOLDEN) + len(ORIGIN_GOLDEN)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)
    # Trim newlines only. `status --porcelain` encodes state in leading columns
    # (" M" vs "M "), so stripping leading spaces would corrupt the first line.
    return proc.stdout.strip("\n")


def git_ok(repo: Path, *args: str) -> bool:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode == 0


def repo_root(start: Path) -> Path | None:
    """The repo containing `start`, or None if it isn't inside one.

    Resolving the top level rather than assuming the given path *is* the repo
    means running from a nested source folder behaves the same as running from
    the root.
    """
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip())


def default_branch(repo: Path, required: bool = True) -> str | None:
    """Ask the repo what its default branch is.

    Repos disagree - some are `main`, some `master`, and some carry a
    `develop` that is *not* the default. Guessing would eventually cut a
    branch from the wrong base, so always ask origin.
    """
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref.startswith("origin/"):
        return ref[len("origin/"):]

    shown = git(repo, "remote", "show", "origin", check=False)
    match = re.search(r"HEAD branch:\s*(\S+)", shown)
    if match and match.group(1) != "(unknown)":
        return match.group(1)

    for candidate in ("main", "master"):
        if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{candidate}"):
            return candidate

    if not required:
        return None
    sys.stderr.write("Could not determine the default branch for this repo.\n")
    raise SystemExit(5)


def branch_exists(repo: Path, name: str) -> bool:
    """True if `name` is a branch here or on origin.

    Checked before anything is checked out, because a typo'd `--base` would
    otherwise surface as a confusing `git checkout` failure halfway through -
    after the dirty check has passed and the user has already said yes. The
    `ls-remote` fallback keeps `--dry-run` honest about a base that exists on
    origin but has not been fetched yet, without mutating any refs.
    """
    if git_ok(repo, "rev-parse", "--verify", f"refs/heads/{name}"):
        return True
    if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{name}"):
        return True
    return git_ok(repo, "ls-remote", "--exit-code", "--heads", "origin", name)


def worktree_dir(main_root: Path, branch: str) -> Path:
    """Sibling folder for an issue's worktree: <repo>-<issue>.

    Named by the issue number only, so the folder stays short and easy to
    type. Branches with no issue number fall back to the branch name.
    """
    number = issue_number(branch)
    return main_root.parent / f"{main_root.name}-{number or branch.replace('/', '-')}"


def main_worktree(repo: Path) -> Path:
    # The first `worktree list` entry is always the main checkout, which keeps a
    # session opened inside another worktree from naming its sibling after that
    # worktree (budget-app-1-2).
    first = git(repo, "worktree", "list", "--porcelain").splitlines()[0]
    return Path(first.removeprefix("worktree "))


def parse_origin(url: str) -> tuple[str, str] | None:
    """(owner, repo) from a GitHub remote URL, or None for anything else."""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    return (match.group(1), match.group(2)) if match else None


def plan_path(dir_arg: str, issue: str | None) -> int:
    """Print ~/.claude/issues/<owner>/<repo>/<issue>/plan.md for this repo.

    Keyed by owner and repo because issue numbers repeat across repos. Taken
    from origin rather than the folder name, so a session in a worktree
    finds the same plan as one in the main checkout.
    """
    start = Path(dir_arg)
    repo = repo_root(start) if start.is_dir() else None
    if repo is None:
        sys.stderr.write(f"Not inside a git repository: {start}\n")
        return 3
    number = (issue or "").strip().lstrip("#") or issue_number(
        git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    if not number or not number.isdigit():
        sys.stderr.write("No issue number given and none in the branch name.\n")
        return 4
    origin = parse_origin(git(repo, "remote", "get-url", "origin", check=False))
    owner, name = origin or ("local", main_worktree(repo).name)
    print(Path.home() / ".claude" / "issues" / owner / name / number / "plan.md")
    return 0


def checked_out_in(repo: Path, branch: str) -> str | None:
    """The worktree path that has `branch` checked out, if any."""
    path = None
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def setup_worktree(repo: Path, branch: str, base: str, base_note: str,
                   current: str, dry_run: bool) -> int:
    """Cut the branch into a new sibling worktree, leaving this checkout alone.

    No dirty-tree check: the current checkout is never switched, so its
    uncommitted work is untouched - which is the point of asking for a
    worktree while mid-way through another issue. Local `base` isn't pulled
    either (that would mean checking it out here); the branch is cut from
    origin/<base> after a fetch instead.
    """
    existing = checked_out_in(repo, branch)
    if existing:
        print(f"{repo.name}: {branch} is already checked out in a worktree - nothing created")
        print(f"  path:    {existing}")
        return 0

    path = worktree_dir(main_worktree(repo), branch)
    if path.exists():
        sys.stderr.write(f"{path} already exists and isn't a worktree for {branch}.\n")
        return 8

    if dry_run:
        print(f"repo:    {repo}")
        print(f"current: {current} (left as-is)")
        print(f"base:    {base}")
        print(f"         ({base_note})")
        print(f"branch:  {branch}")
        print(f"path:    {path}")
        print("(dry run - no git state changed)")
        return 0

    git(repo, "fetch", "origin", "--prune")

    if git_ok(repo, "rev-parse", "--verify", f"refs/heads/{branch}"):
        git(repo, "worktree", "add", str(path), branch)
        print(f"{repo.name}: branch already existed locally - checked it out in a new worktree")
        print(f"  branch:  {branch}")
        print(f"  path:    {path}")
        print(f"  base:    pre-dates this run, not re-cut from {base}")
        return 0

    if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{branch}"):
        git(repo, "worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}")
        print(f"{repo.name}: branch existed on origin - tracking copy in a new worktree")
        print(f"  branch:  {branch}")
        print(f"  path:    {path}")
        return 0

    start = (f"origin/{base}" if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{base}")
             else base)
    # --no-track: otherwise the new branch's upstream would be origin/<base>,
    # and a later push/PR would treat main as the branch it belongs to.
    git(repo, "worktree", "add", "--no-track", "-b", branch, str(path), start)
    head = git(path, "rev-parse", "--short", "HEAD")
    print(f"{repo.name}: created a new branch in a new worktree")
    print(f"  branch:  {branch}")
    print(f"  path:    {path}")
    print(f"  base:    {start} @ {head} ({base_note})")
    print(f"  here:    still on {current}, untouched")
    print("  remote:  not pushed (local only)")
    return 0


def setup(dir_arg: str, branch: str, base_arg: str | None, dry_run: bool,
          worktree: bool = False) -> int:
    start = Path(dir_arg)
    if not start.is_dir():
        sys.stderr.write(f"Not a directory: {start}\n")
        return 3

    repo = repo_root(start)
    if repo is None:
        sys.stderr.write(f"Not inside a git repository: {start}\n")
        return 3

    if not git_ok(repo, "check-ref-format", "--branch", branch):
        sys.stderr.write(f"Not a valid git branch name: {branch}\n")
        return 4

    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    if worktree:
        requested = (base_arg or "").strip().removeprefix("origin/")
        repo_default = default_branch(repo, required=not requested)
        if requested and not branch_exists(repo, requested):
            sys.stderr.write(f"No branch named {requested} in {repo.name} or on origin.\n")
            return 6
        note = (f"requested - repo default is {repo_default or 'unknown'}" if requested
                else "repo default")
        return setup_worktree(repo, branch, requested or repo_default, note, current, dry_run)

    # A dirty tree is a hard stop. Switching branches now would either drag the
    # changes onto the new branch or refuse halfway through, and deciding what
    # to do with someone's uncommitted work is not this script's call.
    dirty = git(repo, "status", "--porcelain")
    if dirty:
        print(f"{repo.name} has uncommitted changes on {current}:\n")
        print(dirty)
        print("\nStopping - nothing was stashed, committed or discarded.")
        print("Deal with these (stash, commit, or discard), then re-run.")
        return 2

    # `origin/develop` and `develop` mean the same thing to someone naming a
    # base, so accept either spelling rather than bouncing one as invalid.
    requested = (base_arg or "").strip()
    if requested.startswith("origin/"):
        requested = requested[len("origin/"):]

    # Detect the repo default even when a base was requested: it costs one git
    # call and lets the confirmation say "develop (repo default is main)",
    # which is exactly the moment a wrong base is cheap to catch.
    repo_default = default_branch(repo, required=not requested)
    base = requested or repo_default

    if requested and not branch_exists(repo, requested):
        sys.stderr.write(f"No branch named {requested} in {repo.name} or on origin.\n")
        return 6

    if dry_run:
        print(f"repo:    {repo}")
        print(f"current: {current}")
        print(f"base:    {base}")
        if requested:
            known = f"repo default is {repo_default}" if repo_default else "repo default unknown"
            print(f"         (requested override - {known})")
        else:
            print("         (repo default)")
        print(f"branch:  {branch}")
        print("(dry run - no git state changed)")
        return 0

    git(repo, "fetch", "origin", "--prune")

    if git_ok(repo, "rev-parse", "--verify", f"refs/heads/{branch}"):
        git(repo, "checkout", branch)
        print(f"{repo.name}: branch already existed locally - checked it out")
        print(f"  repo:    {repo}")
        print(f"  branch:  {branch}")
        print(f"  base:    pre-dates this run, not re-cut from {base}")
        return 0

    if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{branch}"):
        git(repo, "checkout", "-b", branch, "--track", f"origin/{branch}")
        print(f"{repo.name}: branch existed on origin - checked out a tracking copy")
        print(f"  repo:    {repo}")
        print(f"  branch:  {branch}")
        print(f"  base:    origin/{branch}")
        return 0

    git(repo, "checkout", base)
    # Pull by naming the remote and branch rather than relying on the base having
    # an upstream set. A locally-created `develop` often has none, and a bare
    # `git pull` there fails with "no tracking information" - which looks like a
    # broken script rather than the missing config it actually is. A base that
    # exists only locally has nothing to pull, so skip it.
    if git_ok(repo, "rev-parse", "--verify", f"refs/remotes/origin/{base}"):
        git(repo, "pull", "--ff-only", "origin", base)
    git(repo, "checkout", "-b", branch)
    head = git(repo, "rev-parse", "--short", "HEAD")
    origin = "requested" if requested else "repo default"
    print(f"{repo.name}: created and checked out a new branch")
    print(f"  repo:    {repo}")
    print(f"  branch:  {branch}")
    print(f"  base:    {base} @ {head} ({origin})")
    print(f"  was on:  {current}")
    print("  remote:  not pushed (local only)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_slug = sub.add_parser("slug", help="derive the branch name from an issue")
    p_slug.add_argument("--type", dest="kind", help=f"one of: {', '.join(TYPES)}")
    p_slug.add_argument("--issue", help="the issue number, with or without #")
    p_slug.add_argument("--summary", help="a short summary of the issue, not its full title")
    p_slug.add_argument("--test", action="store_true", help="run the golden tests")

    p_setup = sub.add_parser("setup", help="dirty-check, return to default, cut the branch")
    p_setup.add_argument("--dir", required=True,
                         help="any path inside the target repo (the repo root is resolved from it)")
    p_setup.add_argument("--branch", required=True)
    p_setup.add_argument("--base",
                         help="branch to cut from; defaults to the repo's own default branch")
    p_setup.add_argument("--dry-run", action="store_true")
    p_setup.add_argument("--worktree", action="store_true",
                         help="cut the branch into a new sibling worktree instead of switching here")

    p_plan = sub.add_parser("plan-path", help="where this issue's plan.md lives")
    p_plan.add_argument("--dir", required=True)
    p_plan.add_argument("--issue", help="defaults to the issue number in the current branch")

    args = parser.parse_args()

    if args.cmd == "slug":
        if args.test:
            return run_tests()
        if not args.kind or not args.issue or args.summary is None:
            parser.error("slug needs --type, --issue and --summary (or --test)")
        if args.kind.strip().lower() not in TYPES:
            sys.stderr.write(f"Unknown type {args.kind!r} - use one of: {', '.join(TYPES)}\n")
            return 4
        if not args.issue.strip().lstrip("#").isdigit():
            sys.stderr.write(f"Not an issue number: {args.issue}\n")
            return 4
        branch, note = slug_with_note(args.kind, args.issue, args.summary)
        print(branch)
        # stdout stays exactly the branch name; the note goes to stderr so it is
        # visible to a reader without contaminating anything that captures stdout.
        if note:
            sys.stderr.write(f"note: {note}\n")
        return 0

    if args.cmd == "plan-path":
        return plan_path(args.dir, args.issue)

    return setup(args.dir, args.branch, args.base, args.dry_run, args.worktree)


if __name__ == "__main__":
    raise SystemExit(main())
