# skill-stack

Claude Code skills that take a GitHub issue from open to draft PR:

| Skill | Say | Does |
|---|---|---|
| `initialise-agent` | `Initialise agent for #42` | Reads the issue, cuts the branch (optionally in a new worktree), writes a staged plan |
| `create-branch` | `create a branch for #42` | Cuts a branch named like `feat/42-dark-mode-toggle` from the repo default, here or in a new worktree |
| `begin-work` | `start working` | Builds the plan one stage at a time, asks to commit after each |
| `create-commit` | `commit this` | One commit per concern, as `Fix the thing (#42)` |
| `create-pr` | `create a PR` | Writes the description, then pushes and opens a draft PR that closes the issue |
| `clean-worktrees` | `clean worktrees` | Removes worktrees whose branch is merged and deleted on origin; never-pushed work is kept |
| `skill-creator` | `make a skill for X` | Creates or edits a skill, then offers to sync it to this repo |

`/i #42` is a shortcut for `initialise-agent`, and `/cwt` for `clean-worktrees`. Every
step that changes something asks first. See [USAGE.md](USAGE.md) for the walkthrough.

Other commands:

| Command | Does |
|---|---|
| `/ship [scope]` | Polishes the working-tree change before it ships: runs `simplify`, then `code-review`, strips noise comments, then checks line endings. Doesn't commit or push |
| `/dump <label>` | Writes the session's goal, state, decisions, verification results and next steps to `~/.claude/dumps/<label>/<timestamp>.md`, with secrets redacted |
| `/pickup <label>` | Resumes the live session with that label if there is one, otherwise reads the newest dump and summarises where things stand |

## Install

Requires Python 3, Git, and the GitHub CLI, authenticated (`gh auth login`). On Fedora:

```bash
sudo dnf install python3 git gh
```

Then copy the skills and commands into place:

```bash
mkdir -p ~/.claude/skills ~/.claude/commands
cp -r skills/*   ~/.claude/skills/
cp    commands/* ~/.claude/commands/
```

The skills call their scripts as `python3 ~/.claude/skills/...`, so there are no paths to
edit after copying.

## Keeping this repo in sync

Skills are edited in their installed copy under `~/.claude`, so this repo falls behind
unless changes are copied back. `tools/sync.py` does that:

```bash
python3 tools/sync.py status                          # what differs, ignoring line endings
python3 tools/sync.py copy --skill create-branch      # installed -> repo
python3 tools/sync.py copy --command i
```

`copy` mirrors the whole skill folder, deletions included, but skips `__pycache__` and
`*.bak`. It refuses to overwrite a skill that has uncommitted changes in the repo. Both
commands flag any skill or command the README doesn't mention. Anything listed in
`tools/sync-exclude.txt` is deliberately kept out of the repo and isn't reported.

`skill-creator` runs the check when it finishes creating or editing a skill. For edits made
outside it, add the hook to `~/.claude/settings.json`. After any edit under `~/.claude/skills`
or `~/.claude/commands` that leaves the repo behind, the hook prompts Claude to offer the
copy.

```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Edit|Write",
      "hooks": [
        { "type": "command", "command": "f=\"$HOME/Programming/Github/skill-stack/tools/sync_hook.py\"; [ -f \"$f\" ] && python3 \"$f\" || true", "timeout": 15 }
      ]
    }
  ]
}
```

The hook runs from this repo's working tree, so on a branch without `tools/` it has no
script to run. The `[ -f … ]` guard makes it do nothing there rather than error on every
edit, but no reminders fire while such a branch is checked out.

Sync only runs one way, installed to repo. After pulling changes made on another machine,
reinstall with the `cp` commands above.
