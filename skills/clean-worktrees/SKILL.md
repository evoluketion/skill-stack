---
name: clean-worktrees
description: >-
  Clean up finished git worktrees in the repo the session is open on. Checks every worktree
  against origin and removes the ones whose branch was pushed, has since been deleted on
  origin, and is fully merged into the repo's default branch — then deletes that local
  branch with a safe `git branch -d`. Never touches a branch that was never pushed, one that
  still exists on origin, one with commits that aren't on the default branch, or a worktree
  with uncommitted or untracked files. Shows what it found and asks before removing
  anything. Use this whenever the user wants old worktrees tidied: "clean worktrees",
  "clean up my worktrees", "prune worktrees", "remove the worktrees for merged issues",
  "get rid of old worktrees", "which worktrees can I delete?", or "tidy up after those PRs
  merged". Use it even when the ask sounds like a one-liner — `git worktree prune` is not a
  substitute (it only drops entries whose folder is already gone), and deleting worktrees
  whose branch "isn't on origin" by hand destroys never-pushed work, which looks identical
  from origin's side. Do NOT use it to create worktrees (that's create-branch /
  initialise-agent), to delete plain local branches that have no worktree, or to delete
  remote branches.
---

# Clean up finished worktrees

One line — `clean worktrees` — should end with every finished worktree gone and every
unfinished one untouched, with a reason shown for each.

The hard part isn't the deleting. It's that a branch merged and deleted on GitHub and a
branch that was **never pushed** look the same from origin: neither is there. The
difference is local. A pushed branch has an upstream recorded, which shows as `[gone]` once
origin deletes it. And even `[gone]` isn't enough, because work can carry on after the
merge. So the script decides with a stack of checks, and the reasons it prints are what
the user reviews.

## The rules

A worktree is **removable** only when all of these hold:

1. It isn't the main checkout, the worktree this session is running in, or locked.
2. It has a branch checked out, not a detached HEAD.
3. That branch has an upstream on origin, and the upstream is gone. It was pushed once and
   has since been deleted there.
4. The branch tip is contained in `origin/<default>`. Every commit reached the default
   branch, and nothing was committed locally after the merge.
5. `git status --porcelain` is empty, so there are no modified or untracked files.

Anything else is kept with its reason. A folder that's already gone is marked `PRUNE`.
The script encodes all of this — **don't re-derive it by hand or override a KEEP**. If the
user wants a kept worktree gone, that's `git worktree remove` done by them, knowing the reason.

## 1. The repo is the one you're in

The same rule as create-branch: the target is whichever repo the session's working
directory sits in, resolved by the script. Not in a repo — stop and say so. More than one
directory attached — ask which. Never go looking for other repos to clean.

## 2. Scan locally first

```
python3 ~/.claude/skills/clean-worktrees/scripts/clean_worktrees.py scan --dir "<the working directory>"
```

This reads local refs only. If there's nothing but the main checkout and nothing to prune,
report that and stop. There's no reason to touch the network to clean nothing.

## 3. Fetch — only after asking

`[gone]` is only accurate right after a fetch. On stale refs a merged branch still looks
like it's on origin, so it's kept. That's the safe direction, but not a useful clean.

The user doesn't let the assistant hit the network on its own. This fetch is a scoped
exception, allowed **only** behind a per-run yes. Ask, showing the `origin:` age the scan
printed:

```
Found 3 worktrees besides the main checkout. Origin refs were last fetched 2 days ago.
Fetch origin (git fetch origin --prune) so I can see which branches are gone?
```

On a yes, re-scan with `--fetch` (give the Bash call a 6-minute timeout — a fetch on a
large repo or slow connection can run for minutes):

```
python3 ~/.claude/skills/clean-worktrees/scripts/clean_worktrees.py scan --dir "<the working directory>" --fetch
```

On a no, carry on with the local scan, and say plainly that the verdicts are based on refs
from `<age>` ago.

## 4. Show the verdicts, then confirm

Condense the scan into a table. Use the folder name, not the full path, and put the
REMOVE rows first:

```
budget-app — origin fetched just now, default main

  remove  budget-app-42   feat/42-dark-mode-toggle   merged, gone on origin, clean
  prune   budget-app-31   —                          folder already deleted
  keep    budget-app-45   fix/45-csv-import-crash    never pushed
  keep    budget-app-40   feat/40-budget-export      2 commits not in origin/main
  keep    budget-app      fix/38-rounding-error      main checkout — branch merged; switch to main?

Remove 1 worktree (and its local branch) and prune 1 stale entry?
```

A few KEEP reasons deserve a line of their own, because the user can act on them:

- **"N commits not in origin/main"** — most often work added after the merge, or a
  squash merge (its commits never land on main). Either way it's the user's call. Say
  which is more likely if the log makes it obvious, but don't decide for them.
- **"branch still exists on origin"** after a merged PR — GitHub didn't auto-delete the
  branch. The worktree stays until the remote branch is deleted.
- **Main checkout on a finished branch** — the main checkout is the repo itself, so it's
  never removed. Suggest switching it to the default branch, and leave it at the suggestion.

If nothing is REMOVE or PRUNE, report the table and stop. There's nothing to confirm.

## 5. Apply

On a yes, pass exactly the REMOVE paths the user saw, plus `--prune` if any PRUNE rows
were shown:

```
python3 ~/.claude/skills/clean-worktrees/scripts/clean_worktrees.py apply --dir "<the working directory>" --paths "<path>" "<path>" --prune
```

`apply` re-checks every path before touching it, so a worktree that gained a file or a
commit since the scan is skipped (`SKIP … no longer removable`) rather than removed on a
stale verdict. It never forces anything.

It removes the worktree, then deletes the branch with `git branch -d`. Before that it
points the branch's upstream at `origin/<default>`, so `-d` checks against the default
branch rather than whatever the main checkout happens to be parked on. Without that, `-d`
refuses genuinely merged branches whenever the main checkout isn't on main.

| Code | Meaning | What to do |
|---|---|---|
| 0 | done | report |
| 3 | not inside a git repo | say so and stop |
| 5 | a git command failed (or fetch timed out) | relay git's error |
| 7 | finished, but a remove or branch delete failed | relay each `FAILED` / `kept` line |

A `FAILED` remove is usually a permissions problem — files created by a container or
`sudo` and owned by root, often under a build or volume folder — or something still
running in that folder. Say that, suggest fixing ownership or stopping the process, and
re-running. Don't retry with force. `apply` has already pruned any half-deleted entry.

## 6. Report

Short:

```
Removed  budget-app-42  (branch feat/42-dark-mode-toggle deleted)
Pruned   1 stale entry
Kept     3 — see reasons above
```

## Stop rather than improvise

- **Never override a KEEP**, and never reach for `--force` or `branch -D`. Every KEEP
  reason is a way work could be lost.
- **Never fetch without the yes in step 3.** It's the only network call, and the
  exception exists only behind that prompt.
- **Scope is worktrees in this repo.** Leave plain local branches that have no worktree
  alone, even ones that are `[gone]` and merged. The user asked for them to be out of scope.
