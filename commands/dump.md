---
description: Dump current session context to a timestamped file under a named label
---

The user wants to snapshot this session. The label is: $ARGUMENTS

0. If `$ARGUMENTS` is empty, ask the user for a label and stop — don't write to a label-less path like `~/.claude/dumps//<timestamp>.md`.

1. Run these shell commands and capture output:
   - `date +"%Y-%m-%dT%H-%M-%S"` — timestamp for filename and header (colon-free, so the dump folder can be copied to any filesystem)
   - `pwd` — working directory
   - `git branch --show-current` — current branch (if in a git repo)
   - `git status --short` — uncommitted changes (if in a git repo)
   - `git log --oneline -10` — recent commits (if in a git repo)
   - `git log --oneline @{u}..HEAD` — unpushed commits (empty output = everything is pushed; if it errors there's no upstream tracking branch — note that)
   - For each untracked path, `git check-ignore -v <path>` — distinguishes a real "commit this?" decision from a gitignored non-decision

2. Create the directory `~/.claude/dumps/$ARGUMENTS/` if it doesn't exist

3. Write a new file `~/.claude/dumps/$ARGUMENTS/<timestamp>.md` (e.g. `2026-06-15T14-32-00.md` — use the colon-free timestamp from step 1; never put `:` in the filename) with:

   **Never write secrets into the dump.** No API keys, tokens, passwords, bearer/ID tokens, connection strings, private keys, or `.env`/config-file secret *values*. If a fact requires one, redact it (e.g. "Stripe key in `.env:4` — redacted") — name the location, never the value. This applies to every section below.

---

# Session Dump: $ARGUMENTS
**Dumped:** <timestamp>
**Directory:** <pwd>
**Branch:** <branch or "not a git repo">
**Git Status:** <git status output or "clean">
**Push State:** <"all pushed" / list unpushed commits / "no upstream tracking branch">

## Recent Commits
<git log output>

## Goal
<What this session was trying to achieve>

## Current State
<Where things are right now — what's done, what's half-done, what's broken>

## Key Files Touched
<Bare list of file paths central to this work, so a cold reader can navigate fast>

## Decisions & Deferrals
<What was deliberately chosen NOT to do, and why — plus who signed off. Captures settled calls so a resume doesn't re-litigate them. Write "none" if nothing applies.>

## Verification Snapshot
<Exact commands run and their result (e.g. "npm run test:unit → 57 pass"), so "it works" is reproducible rather than a claim. Note any locally-broken tooling so resume doesn't chase it.>

## External State to Re-check
<State a dump CAN'T freeze — PR status, CI checks, review comments, deploys, external dashboards. Include links/IDs. Phrased as "re-verify, don't trust": these are stale by definition. Write "none" if nothing applies.>

## Next Steps
<Ordered list of immediate next actions>

## Open Questions / Blockers
<Anything unresolved or blocking>

---

4. Print: "✓ Dumped to ~/.claude/dumps/$ARGUMENTS/<timestamp>.md"
