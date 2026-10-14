# Usage guide

This guide walks through one issue, from start to open PR. Every step is a plain-English
prompt in a Claude Code session opened **in the repo you want to work in**. The skills
never switch repos for you, and issues are always read from that repo's GitHub remote.

## 1. Start the issue: `initialise-agent`

```
Initialise agent for #42
```

Other phrasings also work: `start work on #42`, `pick up issue 42`, a pasted issue URL, or
`/i #42`.

What happens:

1. The issue is read with `gh issue view`: title, body, labels, state, assignees and
   milestone. Screenshots are stripped from the body (and mentioned).
   If the body is blank, the plan is built from the title and the codebase, and the
   gaps are listed as open questions.
2. `create-branch` previews the branch and **asks you to confirm** before creating it.
   The preview shows the repo, the base branch and the branch name:
   ```
   feat/42-dark-mode-toggle  from  main
   ```
3. If the issue has real structure, a Plan sub-agent breaks it into **stages**. Each stage
   is one commit's worth of work, and its heading is the commit message. A single-change
   issue skips this step.
4. The plan is written to `~/.claude/issues/<owner>/<repo>/42/plan.md` and the session's
   todo list is filled in from it.

You finish with a short report and an offer to start Stage 1. Nothing is built until you
say so.

### Modifiers

| Add to the prompt | Effect |
|---|---|
| `include comments` | Also reads the issue's comment thread and summarises it. Useful when the scoping decision was made in the comments. |
| `no branch needed` / `don't branch, I'm already on it` | Skips the branch step. The issue is still read and planned. |
| `just read the issue and plan it` | Same as above. |
| `in a new worktree` | Cuts the branch into a sibling folder, `<repo>-<issue>`, instead of switching this checkout. Your current branch and any uncommitted work are left as they are. |

### Working in a new worktree

`/i #42 in a new worktree` creates `~/Programming/Github/<repo>-42` (beside the repo),
cut from `origin/<default>` after a fetch. The plan is still written to
`~/.claude/issues/<owner>/<repo>/42/plan.md`, and it records the worktree path. This
session stays where it is, so to build, open a new Claude session in the worktree and say
`begin work` there. A worktree has its own dependencies and build output, so install them
in it first if the stages need them, and give its dev servers ports that don't clash with
other worktrees. Once the PR is merged, `clean worktrees` removes it.

### When it stops instead

The skill stops and asks rather than guessing when:

- the working tree has uncommitted changes (except in worktree mode, which never touches
  this checkout);
- the session isn't inside a git repo;
- more than one directory is attached to the session;
- you named a different repo from the one you're in (`start #42 in budget-app` while the
  session is open on `dotfiles`), or pasted an issue URL from another repo;
- the issue is already closed;
- the body is only a link, or is empty under a title too vague to plan from. It offers
  to read the comments or the linked page.

## 2. Build it: `begin-work`

```
start working
```

Other phrasings: `start on stage 2`, `work through the plan`, `crack on with #42`, or just
`yes` after the plan is shown.

For each stage:

1. It builds **only that stage**. Anything else it notices along the way is noted, not
   fixed.
2. It runs the repo's own checks, taken from `CLAUDE.md`, `AGENTS.md`, `package.json`,
   `pyproject.toml` or a `Makefile`. It tells you what it ran and what it skipped.
3. It shows a review table:
   ```
   **Stage 2 — Add dark mode toggle to the settings page (#42)**

   | File                         | Change   | +/-    | Line endings | What changed                                 |
   |------------------------------|----------|--------|--------------|----------------------------------------------|
   | src/config/schema.ts         | modified | +15 -2 | LF ok        | Adds the theme setting, defaulting to system |
   | src/settings/ThemeToggle.tsx | added    | +42 -0 | LF ok        | New toggle that switches and saves the theme |
   ```
   Line-ending problems, such as a new file saved as LF where `.gitattributes` asks for
   CRLF, are fixed before the table is shown to you.
4. It asks:
   `Stage 2 is done. Commit it and move on to Stage 3?`

   | Your answer | What happens |
   |---|---|
   | yes | Hands over to `create-commit`, using the stage heading as the message. |
   | keep going | Moves to the next stage without committing. The tree now carries both stages. |
   | ask for changes | Makes the changes, re-runs the table, and asks again. |

`plan.md` is updated as it goes: tasks are ticked, and the commit sha is recorded next to
each committed stage.

If there's no plan, `begin-work` won't make up stages. It offers to run
`initialise-agent`, or to agree a short stage list with you in the chat.

## 3. Commit: `create-commit`

`begin-work` calls this for you, but you can also use it on its own at any time:

```
commit this
commit the tests separately
just commit the migration
```

1. The issue number is taken from the branch name.
2. The changes are grouped into **one commit per concern**.
3. You see the proposed commits and the files in each. Nothing is committed until you
   confirm.

The message convention is an imperative description, then the issue in brackets:

```
Fix client note replication in Test Mode (#42)
```

The issue goes at the end, never the start: git deletes a line that starts with `#` as a
comment whenever the message is edited (`--amend`, `rebase -i`).

Files left out of every group stay uncommitted, and the report says which ones. Anything
you had already staged for other files is left alone. Nothing is pushed.

## 4. Open the PR: `create-pr`

```
create a PR
write a PR description
PR this
```

1. It works out the base branch (the repo's default), the issue number, and the commits
   ahead of the base. Everything here is read locally, with no fetch.
2. It drafts a description: a short paragraph on what the branch does and why (tied to the
   issue), then a **What changed** section grouped by area, optionally **Testing**, and
   finally `Closes #42` so merging the PR closes the issue. The title is a plain
   description with no issue number, because GitHub's squash merge appends the PR number.
3. You review the draft and ask for any changes.
4. **After a separate confirmation**, it pushes the branch and runs
   `gh pr create --draft`. If a PR already exists, it gives you the URL and offers to
   update that PR's body instead.

## Running a single step

Each skill also works on its own:

| You want | Say |
|---|---|
| Only a branch, no plan | `create a branch for #42` or `cut a branch off develop for this issue` |
| A branch from a specific base | `branch off release/2.4 for #42` |
| To commit changes you made by hand | `commit my changes` |
| A PR description without pushing | `write a PR description`, then decline the push |
| To tidy worktrees after their PRs merge | `clean worktrees` or `/cwt` |

`clean-worktrees` removes a worktree only when all of these hold: its branch was pushed,
it has since been deleted on origin, its tip is contained in the default branch, and it
has no uncommitted or untracked files. Anything else is kept, with the reason shown. It
asks before fetching and again before removing anything, and deletes the local branch
with `git branch -d`, never `-D`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "uncommitted changes" when branching | Expected. Commit, stash or discard the changes yourself, then ask again. |
| Branch type looks wrong, e.g. `chore/` for a bug | It's picked from the issue's labels, then its content. Say the type you want at the confirmation (`make it fix/`). |
| "Could not resolve to an issue" | The issue number belongs to a different repo from the one the session is open on. |
| "base branch could not be determined" from `create-pr` | `origin/HEAD` isn't set locally. Tell it the target branch, or run `git remote set-head origin --auto` once. |
| `gh` not authenticated | Run `! gh auth status` in the session, and `gh auth login` if needed. |
| Skill doesn't trigger | Name it directly, e.g. `use the begin-work skill`, and check that it's installed under `~/.claude/skills`. |
| Script not found | The skills aren't installed. See Install in the [README](README.md). |
