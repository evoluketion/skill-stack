---
name: create-pr
description: >-
  Write up a PR description for the current branch's committed changes, in the house style:
  a lean, text-only write-up — a short opening paragraph saying what the branch does and why
  (tied back to the GitHub issue the branch is for), then a "What changed" section grouped by
  area of the codebase, with bold area headings and nested bullets naming the files or
  components touched and what changed in each, ending with `Closes #<issue>` so merging
  closes the issue. Then, once you've reviewed and confirmed it,
  offers to push the branch and open it as a draft PR via `gh pr create --draft`. Use this
  whenever the user wants a PR written up or opened: "write a PR description", "create a PR
  for this branch", "draft a PR", "can you describe these changes for review", "open a PR",
  "put this up for review", or a bare "PR this". Use it even when it looks like something
  you could write in a sentence or two by hand — the description has to be built from the
  actual diff grouped by area rather than a restated commit log, has to pull the issue number
  from the branch name the same way create-branch and create-commit do, and the base branch
  is the repo's own default rather than a guessed "main"/"master". This is also the natural
  next step once begin-work finishes working through a plan's stages and everything is
  committed — offer it there rather than just stopping once the stages run out. Do NOT use
  it to make the commits themselves (create-commit does that; this skill only describes
  commits that already exist), to cut the branch (create-branch), or to merge/approve a PR
  once it's open.
---

# Write up the branch as a PR

The commits already say what changed, one concern at a time — `create-commit` made sure of
that. This skill's job is to read that history back as something a reviewer can actually use:
what the branch does, why, and what changed where — enough that a reviewer can review it
with confidence without having to open the code to work out what's going on. Everything up to the point the
user signs off on the wording is read-only. Pushing and opening the PR happen only after a
separate, explicit yes — they're the one step in this skill that isn't reversible with an
undo.

## 1. Get the repo, the issue, and the base

```
python3 ~/.claude/skills/create-pr/scripts/pr.py context --dir "<the working directory>"
```

This resolves the repo, reads the issue number out of the branch name (same convention as
`create-commit` — searched, not anchored, so a prefixed branch still yields its real number),
works out the base branch, and reports how far the branch has diverged from it.

The base detection is deliberately weaker than `create-branch`'s: it only reads local refs
(`origin/HEAD` if set, otherwise `master`/`main` if either exists as a remote-tracking
branch) and never calls `git remote show origin`, which contacts the network. This step runs
before anything has been confirmed, so it stays read-only in the fuller sense — no network at
all, not just no mutation.

| Exit | Meaning | What to do |
|---|---|---|
| 0 | ready | carry on |
| 2 | no commits between base and the branch | say so — there's nothing to open a PR for |
| 3 | not inside a git repo | say so and stop |
| 4 | already on the repo's own default branch | say so and stop — there's no feature branch here |
| 5 | a git command failed | relay it |
| 7 | base branch couldn't be determined locally | **ask the user which branch to target** rather than fetching to find out or guessing `main`/`master` |

If the branch carries no issue number, ask which issue these changes belong to — same rule
as `create-commit`; don't infer one from file paths or the last commit. "None" is a valid
answer here: the PR then simply has no `Closes` line.

If the tree shows uncommitted changes, say so before going further. The description only
covers what's committed — anything else in the tree won't appear in it or in the PR, and the
user may want to commit or stash it first (`create-commit` handles that). It's their call
whether to proceed anyway; this isn't a hard stop.

**If a base branch was requested** ("open this against develop instead", "target release/2.4")
pass it through with `--base` on every subsequent call to this script instead of relying on
auto-detection.

## 2. Read the commits

```
python3 ~/.claude/skills/create-pr/scripts/pr.py commits --dir "<the working directory>" --base <base>
```

This prints `git log --reverse --stat <base>..HEAD` — every commit between the base and the
branch, oldest first, each with its subject and per-file diffstat. Use it to see the shape of
the branch and which areas it touches — not as the outline of the description. The
description describes the branch's end state, not the journey (a "fix review comments" or
"updated prompt" commit is folded into the change it fixed, not given its own mention).

**Diffstats aren't enough to write from.** Read the actual diff for anything whose purpose
isn't obvious from the stat — `git show <hash>` for one commit, or `git diff <base>..HEAD --
<path>` across the whole branch when several commits touch the same area and the grouping
only makes sense read together. Writing "why" from a file list produces a changelog; reading
the diff is what makes it a review aid. If the codebase has an `AGENTS.md`/`CLAUDE.md`,
skim it for architectural context worth carrying into the opening paragraph (which stack a change
touches, what a port needs to stay in parity with, etc.) — the same way you would for any
other task in this repo.

If the issue's full context isn't already in the conversation (title, body, why it
exists), fetch it: `gh issue view <issue> --json title,body,state`. That's what grounds the
opening paragraph in the actual ask rather than a guess reverse-engineered from the diff.
Don't re-fetch if the title or body is already on screen from earlier in the session.

## 3. Group the changes by area

Group by **area of the codebase a reviewer would think in** — a workflow, an infrastructure
root, a service, the UI, docs — not by commit. A branch often has several commits touching
the same area (a feature, a follow-up fix, a review tweak); a reviewer wants the area
explained once, in its final state. Order the groups so the most important change comes
first and supporting/incidental changes (docs, config, small fixes) come last.

A one- or two-area branch may not need groups at all — a flat list of bullets is fine.

## 4. Write the description

Keep it lean, plain text and easy to scan. The bar: **a reviewer should come away knowing
what changed, where, and why, without feeling they need to open the diff to understand it**
— but not so long that they skim it. Concise over complete; every bullet should earn its place.

Use this shape:

```markdown
## What changed

One short paragraph (2–4 sentences): what the branch does, why it's needed (the problem or
ask from #<issue>), and the overall shape of the change — which areas it touches. This
is the only "why" section; there's no separate Summary or Why heading.

- **<Area>**
  - `<path/or/component>`: what changed, and — where it isn't obvious — why it's done that
    way or what behaviour it changes.
  - `<path/or/component>`: ...

- **<Next area>**
  - ...

- **<Small fix / Docs>**
  - ...

Closes #<issue>
```

Optionally, only when there's something worth saying, a short Testing section between the
last group and the `Closes` line:

```markdown
## Testing

- One or two lines: what was run/verified, and plainly what wasn't.
```

`Closes #<issue>` goes on its own line at the very end. It links the PR to the issue and
closes the issue when the PR merges into the default branch. If the branch only does part
of the issue, use `Part of #<issue>` instead, so the issue stays open — and say why you
chose it when showing the draft.

Guidelines:

- **Text only.** Headings, bold area labels, nested bullets and inline code. No tables,
  diagrams, emoji, checklists, collapsible sections or badges.
- **Name the thing.** Each bullet leads with the file, workflow, job, resource or component
  in backticks, then says what changed in it. That's what lets a reviewer map the
  description onto the diff without reading the diff.
- **Say what changed in behaviour, not just what was edited.** "adds a `slot` input and a
  `validate` job that rejects slots outside dev/au" beats "updated deploy-trigger.yml".
- **Carry the context a reviewer needs to judge it**: design decisions, caveats, known
  limitations, anything shared or deliberately left alone ("shares Main dev's secrets and
  tables", "slot builds still write Main's SSM parameter"). These are what reviewers would
  otherwise go digging in the code for.
- **Fold "why" in inline**, a clause at the end of the bullet — not a separate paragraph per
  bullet.
- **Keep it proportionate.** Two levels of bullets at most; one to two lines per bullet; a
  small branch gets a small description. Don't list every file — group trivial ones
  ("tfvars, taskdefs and init script for each slot").
- **No commit hashes or commit-by-commit narration.** The PR's own commits tab covers that.
- **Don't pad.** Skip Testing if there's nothing meaningful to say; never imply coverage
  that didn't happen.

The PR **title** is a short imperative description with no issue number — `Add a dark
mode toggle`. Base it on the issue's title if you fetched it, rather than the branch's own
slug. Leave the number out: GitHub's squash merge appends `(#<PR>)` to the title, and the
body's `Closes` line already links the issue. The body doesn't need its own title heading.

## 5. Show the draft, take changes, then confirm

This is prose, so treat the first draft as a draft. Show it in full and ask whether to
adjust anything before moving on — this is the cheap round-trip, unlike the push and PR
creation that follow it.

## 6. Ask separately whether to push and open the PR

Two different things happen next and neither is implied by "the description looks good":

```
Push feat/42-dark-mode-toggle and open this as a draft PR against main?
```

- **No** → stop. Say the description is ready to use by hand, and that nothing was pushed.
- **Yes** → continue below.

### Push

```
python3 ~/.claude/skills/create-pr/scripts/pr.py push --dir "<the working directory>" --branch <branch> --dry-run
```

Check the dry run's remote status line first — a branch that's already `pushed, up to date`
needs no push at all; say so and skip straight to opening the PR. Otherwise run the same
command without `--dry-run`.

| Exit | Meaning | What to do |
|---|---|---|
| 0 | pushed (or already up to date) | carry on |
| 3 | not inside a git repo | stop |
| 5 | a git command failed | relay it |
| 10 | checked-out branch doesn't match `--branch` | stop — something changed the working tree's branch out from under this run; re-check rather than pushing the wrong one |

### Open the PR

Write the body to a file in your scratchpad first — `gh --body-file` needs a real path, and a
markdown file round-trips the description's formatting exactly rather than fighting shell
quoting:

```
python3 ~/.claude/skills/create-pr/scripts/pr.py open-pr --dir "<the working directory>" --base <base> --head <branch> --title "<short description>" --body-file "<scratchpad>/pr-body.md" --dry-run
```

Then the same command without `--dry-run`.

| Exit | Meaning | What to do |
|---|---|---|
| 0 | PR created — its URL is printed | report it |
| 3 | not inside a git repo | stop |
| 5 | `gh pr create` failed | relay gh's own error |
| 8 | a PR already exists for this branch | its URL is printed — report it, and ask whether to update its body with `gh pr edit --body-file` instead of trying to create a second one |
| 9 | `gh` isn't on PATH or isn't authenticated | say so — `gh auth status` tells the user what's wrong; this isn't something to work around |

## 7. Report

```
#42 — pushed and opened as a draft PR

  branch  feat/42-dark-mode-toggle
  base    main
  PR      https://github.com/<owner>/budget-app/pull/57 (draft, closes #42)
```

If the user said no to pushing, report the description as final instead and note explicitly
that nothing was pushed and no PR was opened.

## Why push and `gh pr create` are allowed here

Reading git and the issue stays read-only through the whole drafting phase, same as every
other skill in this set. Pushing a branch and opening a PR are the exception — visible,
hard-to-reverse actions on GitHub — which is exactly why they sit behind their own
confirmation in step 6, separate from approving the wording in step 5. Never chain the two
confirmations into one question, and never push or open a PR the user hasn't been asked
about in this same conversation.
