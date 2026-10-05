#!/usr/bin/env python3
"""PostToolUse hook: after an edit to an installed skill or command, remind
Claude to offer syncing it to this repo.

Reads the hook payload on stdin. Silent unless the edited file sits in
~/.claude/skills/<name>/ (a real skill, with a SKILL.md) or is
~/.claude/commands/<name>.md, and that skill/command now differs from - or is
missing from - the repo. Never fails the tool call: any error just means no
reminder.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync  # noqa: E402


def target(file_path: str):
    p = Path(file_path).resolve()
    skills, commands = (sync.HOME / "skills").resolve(), (sync.HOME / "commands").resolve()
    if p.is_relative_to(skills):
        rel = p.relative_to(skills)
        if len(rel.parts) >= 2 and (skills / rel.parts[0] / "SKILL.md").exists():
            name = rel.parts[0]
            return "skill", name, skills / name, sync.REPO / "skills" / name
    elif p.is_relative_to(commands) and p.suffix == ".md" and p.parent == commands:
        return "command", p.stem, p, sync.REPO / "commands" / p.name
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or (payload.get("tool_response") or {}).get("filePath")
    hit = target(file_path) if file_path else None
    if not hit:
        return 0
    kind, name, src, dst = hit
    if (name if kind == "skill" else f"/{name}") in sync.excluded():
        return 0

    if not dst.exists():
        state = f"is not in the skill-stack repo ({sync.REPO})"
        action = "offer to add it"
    else:
        changed, added, removed = sync.compare(src, dst)
        if not (changed or added or removed):
            return 0
        state = "now differs from its copy in the skill-stack repo"
        action = "offer to copy the changes across"

    flag = "--skill" if kind == "skill" else "--command"
    msg = (f"The installed {kind} '{name}' {state}. When this edit is finished (not after "
           f"every intermediate change), {action}: "
           f'python3 "{sync.REPO / "tools" / "sync.py"}" copy {flag} {name} - '
           "then update the repo README (and USAGE.md if relevant) to match. "
           "Ask first; don't commit.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": msg}}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(0)
