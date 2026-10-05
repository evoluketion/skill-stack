#!/usr/bin/env python3
"""Stage-boundary review table for the begin-work skill.

    review --dir <any path inside the repo> [--stage "Stage 2 - Do the thing (#1)"]
           [--files a.py b.tsx ...] [--summaries summaries.json]
    review --test

Prints the per-file table shown to the user when a stage is finished: what
changed, how big it is, and whether the file's line endings still match what the
repo expects. The mechanical columns come from git; the "What changed" column
comes from `--summaries`, a JSON object mapping path to one line of prose.

The line-ending check is the reason this is a script rather than a handful of
shell commands. Two ways of doing it by hand are actively wrong:

  * comparing the working file against `git show HEAD:<file>` - with
    core.autocrlf=true the index holds LF, so every correctly-CRLF file looks
    changed and the check false-positives on all of them;
  * `grep -c $'\\r$'` - if the shell doesn't expand $'\\r' the pattern degrades
    to a bare `$`, matches every line, and reports a pure-LF file as CRLF.

Counting bytes and asking git for the expected style avoids both.

Exit codes: 0 ok, 2 nothing to review, 3 not inside a git repo, 5 a git command
failed, 6 a named file has no changes, 7 a line-ending defect was found.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# A file only edited in a few places whose diff churns nearly every line has had
# its endings flipped, even if it is now internally consistent.
REWRITE_RATIO = 1.8


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)
    return proc.stdout.strip("\n")


def repo_root(start: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True,
    )
    return Path(proc.stdout.strip()) if proc.returncode == 0 else None


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


def change_set(repo: Path) -> list[dict]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repo, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or proc.stdout).strip() + "\n")
        raise SystemExit(5)

    parts = proc.stdout.split("\0")
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
    if status == "??":
        return "new"
    if "D" in (status[0], status[1]):
        return "deleted"
    if status[0] == "R":
        return "renamed"
    if status[0] == "A":
        return "added"
    return "modified"


def numstat(repo: Path) -> dict[str, tuple[int, int]]:
    counts: dict[str, tuple[int, int]] = {}
    raw = subprocess.run(
        ["git", "diff", "--numstat", "HEAD"], cwd=repo, capture_output=True, text=True,
    )
    if raw.returncode != 0:
        return counts
    for line in raw.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 3:
            continue
        added, removed, path = fields[0], fields[1], fields[-1]
        if added == "-" or removed == "-":
            continue          # binary
        counts[path] = (int(added), int(removed))
    return counts


def expected_eol(repo: Path, path: str) -> str | None:
    """What this file's line endings should be: 'crlf', 'lf', or None to skip.

    Asked of git rather than assumed, because `.gitattributes` is how a repo
    states its convention and it beats any guess made from the file itself.
    """
    out = git(repo, "check-attr", "text", "eol", "binary", "--", path, check=False)
    attrs: dict[str, str] = {}
    for line in out.splitlines():
        # "path: attr: value", and the path may itself contain ": "
        head, _, value = line.rpartition(": ")
        _, _, attr = head.rpartition(": ")
        attrs[attr] = value

    if attrs.get("binary") == "set" or attrs.get("text") == "unset":
        return None
    if attrs.get("eol") in ("crlf", "lf"):
        return attrs["eol"]

    core_eol = git(repo, "config", "core.eol", check=False).strip().lower()
    if core_eol in ("crlf", "lf"):
        return core_eol
    autocrlf = git(repo, "config", "core.autocrlf", check=False).strip().lower()
    if autocrlf == "true":
        return "crlf"
    if autocrlf == "input":
        return "lf"
    return None               # undecidable: fall back to the file's own style


def actual_eol(data: bytes) -> tuple[str, int, int]:
    """('crlf' | 'lf' | 'mixed' | 'none', crlf_count, lone_lf_count)."""
    crlf = data.count(b"\r\n")
    total_lf = data.count(b"\n")
    lone_lf = total_lf - crlf
    if crlf and lone_lf:
        return "mixed", crlf, lone_lf
    if crlf:
        return "crlf", crlf, lone_lf
    if lone_lf:
        return "lf", crlf, lone_lf
    return "none", 0, 0


def looks_binary(data: bytes) -> bool:
    return b"\0" in data[:8000]


def inspect(repo: Path, path: str, kind: str, churn: tuple[int, int] | None) -> dict:
    row: dict = {"path": path, "kind": kind, "churn": churn, "eol": "-", "problems": []}
    if kind == "deleted":
        return row

    full = repo / path
    try:
        data = full.read_bytes()
    except OSError:
        return row

    if looks_binary(data):
        row["eol"] = "binary"
        return row

    found, crlf, lone_lf = actual_eol(data)
    want = expected_eol(repo, path)

    if found == "mixed":
        row["eol"] = f"MIXED ({crlf} CRLF, {lone_lf} LF)"
        row["problems"].append("mixed line endings - always a defect")
    elif want and found != "none" and found != want:
        row["eol"] = f"{found.upper()} (expected {want.upper()})"
        row["problems"].append(f"line endings are {found.upper()}, repo expects {want.upper()}")
    elif found == "none":
        row["eol"] = "n/a"
    else:
        row["eol"] = f"{found.upper()} ok"

    if data and not data.endswith(b"\n"):
        row["problems"].append("no trailing newline")

    # A near-total rewrite of a file that was only edited in places is the
    # signature of a flipped ending, even when the file now reads consistently.
    if churn and kind == "modified":
        lines = data.count(b"\n") or 1
        if churn[0] + churn[1] >= REWRITE_RATIO * lines:
            row["problems"].append(
                f"diff churns {churn[0] + churn[1]} lines of a {lines}-line file "
                "- endings may have flipped"
            )
    return row


def render(rows: list[dict], summaries: dict[str, str], stage: str | None) -> str:
    out: list[str] = []
    if stage:
        out.append(f"**{stage}**\n")

    widths_path = max([len(r["path"]) for r in rows] + [4])
    out.append(f"| {'File'.ljust(widths_path)} | Change   | +/-        | Line endings | What changed |")
    out.append(f"|{'-' * (widths_path + 2)}|----------|------------|--------------|--------------|")
    for row in rows:
        if row["churn"]:
            churn = f"+{row['churn'][0]} -{row['churn'][1]}"
        else:
            churn = "-"
        summary = summaries.get(row["path"], "")
        out.append(
            f"| {row['path'].ljust(widths_path)} | {row['kind']:8} | {churn:10} "
            f"| {row['eol']:12} | {summary} |"
        )

    added = sum(r["churn"][0] for r in rows if r["churn"])
    removed = sum(r["churn"][1] for r in rows if r["churn"])
    out.append("")
    out.append(f"{len(rows)} file(s), +{added} -{removed}.")

    problems = [(r["path"], p) for r in rows for p in r["problems"]]
    if problems:
        out.append("")
        out.append(f"**{len(problems)} problem(s) to fix before committing:**")
        for path, problem in problems:
            out.append(f"- `{path}` — {problem}")
    else:
        out.append("Line endings match the repo for every file.")
    return "\n".join(out)


def cmd_review(dir_arg: str, stage: str | None, files: list[str] | None,
               summaries_path: str | None) -> int:
    repo = resolve_repo(dir_arg)
    entries = change_set(repo)
    if not entries:
        print("Nothing to review - the working tree is clean.")
        return 2

    if files:
        wanted = {f.replace("\\", "/") for f in files}
        known = {e["path"] for e in entries}
        missing = sorted(wanted - known)
        if missing:
            sys.stderr.write("These have no changes to review:\n")
            for path in missing:
                sys.stderr.write(f"  {path}\n")
            return 6
        entries = [e for e in entries if e["path"] in wanted]

    summaries: dict[str, str] = {}
    if summaries_path:
        try:
            summaries = json.loads(Path(summaries_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"Could not read the summaries: {exc}\n")
            return 6

    churn = numstat(repo)
    rows = [
        inspect(repo, e["path"], describe(e["status"]), churn.get(e["path"]))
        for e in sorted(entries, key=lambda e: e["path"])
    ]

    print(render(rows, summaries, stage))
    return 7 if any(r["problems"] for r in rows) else 0


def run_tests() -> int:
    failures = 0
    cases = [
        (b"a\r\nb\r\n", ("crlf", 2, 0)),
        (b"a\nb\n", ("lf", 0, 2)),
        (b"a\r\nb\n", ("mixed", 1, 1)),
        (b"", ("none", 0, 0)),
        (b"no newline", ("none", 0, 0)),
        # The trap: a lone \r inside a CRLF file must not read as mixed.
        (b"a\r\n\r\nb\r\n", ("crlf", 3, 0)),
    ]
    for data, expected in cases:
        got = actual_eol(data)
        if got != expected:
            failures += 1
            print(f"FAIL  {data!r}: expected {expected}, got {got}")
        else:
            print(f"PASS  {data!r} -> {got[0]}")

    if looks_binary(b"\x00\x01\x02") and not looks_binary(b"plain text\n"):
        print("PASS  binary detection")
    else:
        failures += 1
        print("FAIL  binary detection")

    total = len(cases) + 1
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_review = sub.add_parser("review", help="the stage-boundary table")
    p_review.add_argument("--dir")
    p_review.add_argument("--stage", help="stage heading to print above the table")
    p_review.add_argument("--files", nargs="*", help="limit to this stage's files")
    p_review.add_argument("--summaries", help="JSON object mapping path to one line of prose")
    p_review.add_argument("--test", action="store_true", help="run the golden tests")

    args = parser.parse_args()
    if args.test:
        return run_tests()
    if not args.dir:
        parser.error("review needs --dir (or --test)")
    return cmd_review(args.dir, args.stage, args.files, args.summaries)


if __name__ == "__main__":
    raise SystemExit(main())
