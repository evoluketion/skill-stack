#!/usr/bin/env python3
"""Keep this repo in step with the installed skills and commands.

The installed copies under ~/.claude are where skills get edited and used;
this repo is the version-controlled copy. Sync runs installed -> repo.

    status [--skill NAME ...] [--command NAME ...]
    copy   [--skill NAME ...] [--command NAME ...] [--dry-run]

`status` compares each installed skill (a folder with a SKILL.md) and command
against the repo, ignoring line endings, so a file that only gained CRLFs (from
an editor or core.autocrlf) doesn't show as changed. It also checks that every
skill and command in the repo has a README mention. With no names it reports
everything installed, minus what tools/sync-exclude.txt lists.

`copy` mirrors the named skills/commands into the repo: new and changed files
are written, files deleted from the installed copy are deleted here. It never
copies build junk (__pycache__, *.pyc, *.bak). It refuses when the repo copy
has uncommitted changes, because overwriting those can't be undone - commit
or discard them first.

Exit codes: 0 ok / in sync, 1 status found something out of sync,
2 copy refused (uncommitted changes in the repo copy), 3 name not installed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".claude"
JUNK_DIRS = {"__pycache__"}
JUNK_SUFFIXES = {".pyc", ".bak"}


def is_junk(rel: Path) -> bool:
    return any(p in JUNK_DIRS for p in rel.parts) or rel.suffix in JUNK_SUFFIXES


def files(root: Path) -> dict[Path, Path]:
    if not root.exists():
        return {}
    if root.is_file():
        return {Path(root.name): root}
    return {p.relative_to(root): p for p in root.rglob("*")
            if p.is_file() and not is_junk(p.relative_to(root))}


def same(a: Path, b: Path) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def excluded() -> set[str]:
    path = REPO / "tools" / "sync-exclude.txt"
    if not path.exists():
        return set()
    lines = (l.strip() for l in path.read_text(encoding="utf-8").splitlines())
    return {l for l in lines if l and not l.startswith("#")}


def installed_skills() -> list[str]:
    # A skill is a folder with a SKILL.md. That leaves out `synced/` (plugin
    # skills claude.ai manages) and helper folders such as `trigger-evals/`.
    skip = excluded()
    return sorted(p.parent.name for p in (HOME / "skills").glob("*/SKILL.md")
                  if p.parent.name not in skip)


def installed_commands() -> list[str]:
    skip = excluded()
    return sorted(p.stem for p in (HOME / "commands").glob("*.md") if f"/{p.stem}" not in skip)


def targets(skills: list[str] | None, commands: list[str] | None):
    if not skills and not commands:
        skills, commands = installed_skills(), installed_commands()
    out = []
    for name in skills or []:
        out.append(("skill", name, HOME / "skills" / name, REPO / "skills" / name))
    for name in commands or []:
        out.append(("command", name, HOME / "commands" / f"{name}.md",
                    REPO / "commands" / f"{name}.md"))
    return out


def compare(src: Path, dst: Path):
    a, b = files(src), files(dst)
    changed = sorted(r for r in a.keys() & b.keys() if not same(a[r], b[r]))
    added = sorted(a.keys() - b.keys())
    removed = sorted(b.keys() - a.keys())
    return changed, added, removed


def readme_gaps() -> list[str]:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    gaps = [f"skill {p.name}" for p in sorted((REPO / "skills").glob("*/"))
            if p.is_dir() and f"`{p.name}`" not in readme]
    gaps += [f"command /{p.stem}" for p in sorted((REPO / "commands").glob("*.md"))
             if f"/{p.stem}" not in readme]
    return gaps


def cmd_status(skills, commands) -> int:
    out_of_sync = False
    for kind, name, src, dst in targets(skills, commands):
        if not src.exists():
            print(f"{kind} {name}: not installed")
            out_of_sync = True
            continue
        if not dst.exists():
            print(f"{kind} {name}: NOT IN REPO")
            out_of_sync = True
            continue
        changed, added, removed = compare(src, dst)
        if not (changed or added or removed):
            print(f"{kind} {name}: in sync")
            continue
        out_of_sync = True
        print(f"{kind} {name}: DIFFERS")
        for tag, rels in (("changed", changed), ("new", added), ("deleted", removed)):
            for r in rels:
                print(f"    {tag:<8} {r.as_posix()}")
    gaps = readme_gaps()
    for g in gaps:
        print(f"README: no mention of {g}")
    return 1 if out_of_sync or gaps else 0


def repo_dirty(path: Path) -> list[str]:
    proc = subprocess.run(["git", "status", "--porcelain", "--", str(path)],
                          cwd=REPO, capture_output=True, text=True)
    return [l for l in proc.stdout.splitlines() if l.strip()]


def cmd_copy(skills, commands, dry_run: bool) -> int:
    if not skills and not commands:
        sys.stderr.write("copy needs at least one --skill or --command.\n")
        return 3
    plan = targets(skills, commands)
    for kind, name, src, dst in plan:
        if not src.exists():
            sys.stderr.write(f"{kind} {name} is not installed ({src}).\n")
            return 3
        dirty = repo_dirty(dst)
        if dirty:
            print(f"{kind} {name}: repo copy has uncommitted changes - refusing to overwrite:")
            for l in dirty:
                print(f"    {l}")
            return 2

    for kind, name, src, dst in plan:
        changed, added, removed = compare(src, dst)
        if not (changed or added or removed):
            print(f"{kind} {name}: already in sync")
            continue
        verb = "would copy" if dry_run else "copied"
        print(f"{kind} {name}: {verb} {len(changed)} changed, {len(added)} new, "
              f"{len(removed)} deleted")
        if dry_run:
            continue
        src_files = files(src)
        base = dst if src.is_dir() else dst.parent
        for r in changed + added:
            target = base / r
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_files[r], target)
        for r in removed:
            (base / r).unlink()

    gaps = readme_gaps()
    for g in gaps:
        print(f"README: no mention of {g} - add it")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("status", "copy"):
        p = sub.add_parser(name)
        p.add_argument("--skill", action="append")
        p.add_argument("--command", action="append")
        if name == "copy":
            p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.cmd == "status":
        return cmd_status(args.skill, args.command)
    return cmd_copy(args.skill, args.command, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
