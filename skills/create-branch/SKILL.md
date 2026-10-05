---
name: create-branch
description: >-
  Create a correctly-named git branch for a GitHub issue in the repo the session is open
  on. Derives the branch name from the issue using the convention
  `<type>/<issue>-<short-summary>` (feat/42-dark-mode-toggle, fix/7-empty-csv-crash) —
  the type from the issue's labels and content, the summary a few words written from the
  issue rather than its full title — cuts it from that repo's own default branch, or from
  another base if you name one, and confirms the repo, base and branch name with you
  before anything is created. Use this whenever the user asks for a branch: "create a
  branch for #42", "cut a branch off develop for this issue", "new branch for issue 42",
  "make me a branch", "branch this repo for the issue I'm on", or a bare issue number
  where the ask is clearly just the branch. **An explicit branch request wins even when
  it's wrapped in starting-work language** — "im about to start #42, sort out the branch
  for me", "getting going on #42, just get the branch sorted". The user named the branch
  as the thing they want; they can ask for the plan afterwards. Use it even when the
  request sounds like a one-liner someone could type by hand — `git checkout -b` is not a
  substitute, because the branch name follows a convention derived from the issue, the
  base branch differs per repo (some main, some master, some have a develop that is *not*
  the default), and the repo is usually still parked on a previous issue's branch. If the
  session has no issue context, this skill asks for it rather than guessing. Also use it
  when the user wants a branch off a *specific* base ("branch off release/2.4", "cut this
  from develop instead"), or wants the branch **in a new worktree** ("branch #42 in a new
  worktree", "put it in its own worktree", "worktree for #42") so the current checkout
  stays as it is. For starting work on an issue end-to-end — reading the issue,
  branching, and planning the work — use initialise-agent instead; it calls this skill
  for the branch step.
---

# Create an issue branch

One line — `create a branch for #42` — should end with a correctly-named branch checked
out in the right repo, cut from the right base, with nothing of the user's work disturbed.

Everything up to the confirmation is read-only, so the pause before creating costs a
keystroke and catches the two mistakes that are expensive to undo: a branch cut in a
session pointed at the wrong project, and a branch cut from the wrong base.

## 1. Work out which issue

The branch name is derived from the issue number **and what the issue is about**, so you
need the number, the title, and enough of the body and labels to pick a type.

- **Issue already in the conversation** — you fetched it earlier, or the user pasted it.
  Use it. Don't re-fetch just to confirm what's already on screen.
- **Number only** (`create a branch for #42`, or a bare `#42`) — fetch it from this repo:
  `gh issue view 42 --json number,title,body,labels,state,stateReason`. That's the whole
  reason this step is cheap; don't make the user describe an issue you can look up.
- **No issue anywhere in the session** (`create a branch`, `branch this repo`) — **ask.**
  Which issue is this for? Inferring a number from recent files or git history produces a
  branch name that looks plausible and is wrong, which is worse than a question.

If the issue is already `CLOSED`, mention it before branching — it usually means the user
means something other than fresh work. `../initialise-agent/references/github-issues.md`
covers the body quirks (templates, screenshots, task lists) if a fetch returns something
surprising.

**A branch with no issue behind it** — a spike, a backup of another branch — is fine, but
say so: skip the slug step, use the name the user gave verbatim, and note in the
confirmation that it departs from the convention.

## 2. The repo is the one you're in

There is no inference here, deliberately. The target repo is whichever repo the session's
working directory sits in — `setup` resolves it with `git rev-parse --show-toplevel`, so
running from a nested source folder finds the same root as running from the top.

- **Not inside a git repo?** `setup` exits 3. Say so plainly and stop — don't go hunting
  the filesystem for a plausible repo. The fix is for the user to re-point the session,
  which they can do far faster than you can guess it.
- **More than one directory attached to the session?** Ask which one. You can see the
  attached directories in your own context; there's no command that reports them, so this
  is the one step you judge rather than check.
- **The user names a repo, or pastes an issue URL, that isn't the one you're in?** Stop
  and say so. "Branch budget-app for #42" while the session is open on `dotfiles` is a
  contradiction, not an instruction to go and find budget-app. Silently branching
  `dotfiles` is the worst outcome — it looks like it worked.

## 3. Derive the branch name

Two parts are yours to choose; the script does the rest.

- **Type** — one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `ci`,
  `build`. Take it from the labels first (`bug` → `fix`, `enhancement` → `feat`,
  `documentation` → `docs`), otherwise judge it from the body. When it's genuinely
  ambiguous, pick the closest one — the confirmation shows it, and that's where the user
  corrects it.
- **Summary** — two to five words saying what the change is, written from the issue rather
  than copied from its title. "Add a toggle so users can switch the settings page into
  dark mode" becomes `dark mode toggle`. Leave out words the type already says ("fix",
  "add", "bug").

Don't hand-roll the slug — the script lowercases, strips punctuation and accents, and caps
the length the same way every time:

```
python3 ~/.claude/skills/create-branch/scripts/issue_branch.py slug --type feat --issue 42 --summary "dark mode toggle"
```

That prints `feat/42-dark-mode-toggle`. The cap is 50 characters, trimmed at a word
boundary. If it bites, the script says so on stderr:

```
note: shortened to 46 chars at a word boundary (the full summary would give 68, cap is 50)
```

That usually means the summary was too long. Write a shorter one and re-run rather than
shipping a trimmed tail.

## 4. Work out the base

The default is the repo's own default branch, which `setup` detects by asking origin —
repos disagree, and some have a `develop` that is not the default, so it is never assumed.

If the user named a base ("off develop", "from release/2.4", "branch this from the
fix/38 branch"), pass it through with `--base`. `origin/develop` and `develop` both work,
the branch is verified to exist locally or on origin before anything is checked out, and
the confirmation shows the repo default alongside it so a wrong base is obvious.

## 5. Preview, then confirm

`--dry-run` resolves the repo, runs the dirty-tree check, and works out the base without
changing any git state:

```
python3 ~/.claude/skills/create-branch/scripts/issue_branch.py setup --dir "<the working directory>" --branch "feat/42-dark-mode-toggle" --dry-run
```

Running the preview *before* the question means a dirty tree or an unknown base surfaces
instead of landing after the yes. Show the user what it found and wait:

```
About to create a branch:

  repo    budget-app
          ~/Programming/Github/budget-app
  base    main (repo default, currently on main)
  branch  feat/42-dark-mode-toggle

Go ahead?
```

A requested base gets its own note, because it's the detail worth double-checking — and
it's a statement, not a question:

```
  base    develop (requested — repo default is main)
```

Then offer to proceed, to change the base, or to cancel — and take a yes as a yes. The
repo is whichever one the session happens to be open on, and showing it is how the user
catches a misdirected session before a branch lands there; that is what the pause is for.
If the user asks for a different type, summary or whole name, use theirs, but don't prompt
for one: inviting edits turns a one-keystroke confirmation into a negotiation.

## 6. Create it

On a yes, the same command without `--dry-run` (plus `--base` if one was chosen):

```
python3 ~/.claude/skills/create-branch/scripts/issue_branch.py setup --dir "<the working directory>" --branch "feat/42-dark-mode-toggle"
```

`setup` (in its normal mode — see *Worktree mode* below) refuses on a dirty tree, fetches,
returns to the base, pulls, then creates and checks out the branch. If the branch already
exists locally or on origin it checks that out instead of re-cutting it, and says so.

Exit codes tell you how to respond, on the preview and the real run alike:

| Code | Meaning | What to do |
|---|---|---|
| 0 | branch ready | carry on |
| 2 | uncommitted changes | **stop.** Relay the file list. Don't stash, commit or discard — that's the user's call |
| 3 | not inside a git repo | say so and stop; ask the user to point the session at the right directory |
| 4 | invalid branch name or type | show the name and ask |
| 5 | a git command failed | relay git's own error |
| 6 | the requested base doesn't exist | show what was asked for; offer the repo default or a corrected name |
| 8 | worktree mode: the target folder already exists | show the path; don't delete or reuse it — ask |

The branch stays **local**.

### Worktree mode

Only when the user asks for it: "in a new worktree", "in its own worktree", "worktree for
#42", "keep my current checkout as it is". Never choose it yourself — a worktree is a new
folder that needs its own dependencies installed, and the user decides when that's worth
it.

Add `--worktree` to both the preview and the real run. The mechanics change in three ways,
and the confirmation should reflect them:

- **No dirty-tree check.** This checkout is never switched, so uncommitted work here is
  safe. That's usually the reason for asking: the user is mid-way through another issue.
- **The branch goes into a sibling folder** `<repo>-<issue>`, named for the issue number
  only so the path stays short. If the session is itself in a worktree, the folder is
  still named after the main checkout.
- **It's cut from `origin/<base>` after a fetch**, with no upstream set. Local `main`
  isn't pulled, because that would mean checking it out here. `create-pr` sets the
  upstream when it pushes.

The confirmation gains a `path` line and says the current checkout stays put:

```
About to create a branch in a new worktree:

  repo    budget-app
          ~/Programming/Github/budget-app  (stays on fix/38-…, untouched)
  base    main (repo default)
  branch  feat/42-dark-mode-toggle
  path    ~/Programming/Github/budget-app-42

Go ahead?
```

If the branch is already checked out in a worktree, the script reports that path and
creates nothing. Relay the path. The report ends with the one thing this session can't do,
which is move into the new folder:

```
Worktree  ~/Programming/Github/budget-app-42
Next      open a new Claude session there. Install dependencies first if you'll need
          them, and give any dev server a port that doesn't clash with other worktrees.
```

Nothing is pushed — pushing an empty branch just clutters the remote, and the first
`git push -u` after a real commit is the natural moment for it.

## 7. Report

Short. The user wants to start working:

```
budget-app
  branch  feat/42-dark-mode-toggle
  base    main @ a1b2c3d (local only, not pushed)
```

## Stop rather than improvise

The cost of guessing wrong here is higher than the cost of one question:

- **A dirty tree.** Someone's uncommitted work is not yours to move.
- **A working directory outside a git repo**, or more than one directory attached.
- **No issue context**, or a repo named that isn't the one the session is open on.
- **A base that doesn't resolve.** Don't quietly fall back to the default — the user asked
  for that base for a reason.

And never create the branch without the confirmation in step 5, even when the issue and
the repo both look obvious. It is the only step that changes anything the user would have
to undo.
