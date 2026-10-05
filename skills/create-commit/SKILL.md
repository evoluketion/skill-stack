---
name: create-commit
description: >-
  Commit the current work in the house style — `Fix client note replication in Test Mode
  (#42)`: an imperative description, then the issue number from the branch in brackets.
  Reads the diff, groups the changes into one commit per concern, shows you the proposed
  commits and the files in each, and commits them in order once you say yes. Use this
  whenever the user wants work committed: "commit this", "commit my changes", "commit
  what we've done", "make a commit", "commit stage 2", "can you commit the auth fix",
  or a bare "commit". Use it even when it looks like a one-liner someone could type by
  hand — `git commit -am` is not a substitute, because the issue number has to come off
  the branch name, the message has to match a convention the rest of the log follows, and a
  working tree that touches three concerns should become three reviewable commits rather
  than one lump. Also use it when the user wants only part of the tree committed ("just
  commit the migration", "commit the tests separately"). Do NOT use it to push, open a
  pull request, amend or reword existing commits, or write release notes — this skill only
  creates new commits on the branch you are already on.
---

# Commit the current work

The point is a log that reads like the rest of the log: every commit carries its issue,
says what it does in the imperative, and contains one coherent change that a reviewer can
judge on its own.

Everything up to the confirmation is read-only. The commits themselves happen in one
batch, after a yes.

## The convention

```
Fix client note replication in Test Mode (#42)
Only show the export button to owners (#17)
Use useMemo to prevent re-render of the search component (#108)
```

- **Description, a space, then the issue in brackets.** It matches GitHub's own
  squash-merge format and GitHub links it to the issue. Never lead with the `#42`: git
  treats a line starting with `#` as a comment and silently deletes it whenever the message
  passes through an editor (`--amend`, `rebase -i`).
- **Imperative mood** — "Fix", "Add", "Update", "Remove". Not "Fixed", not "has been
  fixed". The test is whether the subject completes "this commit will…".
- **One line, no trailing full stop.** A body is for the rare change whose *reasoning*
  won't fit in a subject — a workaround, a non-obvious tradeoff. Most commits don't need
  one, and a body that just restates the subject is noise.
- **No attribution trailer.** Do not add `Co-Authored-By: Claude` or any generated-with
  footer to these commits, whatever the general default says. A trailer that appears on
  only the AI-assisted commits makes the log inconsistent for no benefit.

Describe the change, not the file. "Update NotesPanel.tsx" tells a reviewer nothing they
can't see in the diff stat; "Load client notes as at call time" tells them what to check.

## 1. Get the issue number from the branch

It's already there — `create-branch` put it in the branch name:

```
python3 ~/.claude/skills/create-commit/scripts/commit.py issue --dir "<the working directory>"
```

If the branch carries no number (`main`, `spike/whatever`), **ask which issue these
changes belong to.** Don't infer one from recent files or the last commit — a commit filed
under the wrong issue is quietly wrong and nobody notices until someone traces the issue.

## 2. Look at what actually changed

```
python3 ~/.claude/skills/create-commit/scripts/commit.py plan --dir "<the working directory>"
```

That prints every path with changes, its status, and its line counts — the raw material
for grouping. **Then read the diff itself** (`git diff`, plus `git diff --cached` if
anything is staged). Grouping from filenames alone produces messages that describe files
rather than changes, which is exactly what the convention is trying to avoid.

## 3. Group into one commit per concern

A good commit is one a reviewer can judge without opening the others, and one that would
leave the build green on its own. In practice:

- **Tests ship with the code they test.** A commit that adds a behaviour and its test is
  one concern, not two.
- **A rename ships with its call sites.** Splitting them leaves a commit that doesn't
  compile.
- **Unrelated fixes are separate commits even when they're small.** "While I was in there"
  is how a one-line fix ends up buried in a 40-file commit.
- **When it's genuinely one change, one commit is the right answer.** Don't manufacture
  three commits out of a change that has one concern; that's as unhelpful as one lump.

Two constraints worth knowing before you plan:

- **Granularity is whole files.** The script stages by path, so it can't split two
  concerns that live in the same file. When that happens, say so and commit them together
  under the broader message, or tell the user they can stage hunks by hand first — don't
  pretend the split happened.
- **Leaving files out is fine.** Anything not listed just stays uncommitted, and the
  script reports what it left. Use that when the user asks for only part of the tree, and
  when work-in-progress shouldn't be committed yet.

**Stop if the change set contains something that shouldn't be committed** — `.env` files,
`*.pem`, credentials pasted into config, a stray database dump, a huge binary. Name it and
ask. Committing a secret is not undone by deleting it in the next commit.

## 4. Write the plan file

JSON, in your scratchpad — **not inside the repo**, where it would show up as an untracked
file and could end up committed:

```json
{"commits": [
  {"message": "Add theme setting to the config schema (#42)",
   "files": ["src/config/schema.ts", "src/config/schema.test.ts"]},
  {"message": "Add dark mode toggle to the settings page (#42)",
   "files": ["src/settings/ThemeToggle.tsx", "src/settings/SettingsPage.tsx"]}
]}
```

Order matters — commits are made top to bottom, so put the change others build on first.

## 5. Preview, then confirm

```
python3 ~/.claude/skills/create-commit/scripts/commit.py apply --dir "<the working directory>" --plan "<scratchpad>/commits.json" --dry-run
```

The dry run validates every message against the convention and every path against the
real change set, so a hallucinated filename or a message missing its issue surfaces before
the user is asked rather than halfway through committing. Show them the result and wait:

```
3 commits proposed on feat/42-dark-mode-toggle:

1. Add theme setting to the config schema (#42)
     src/config/schema.ts
     src/config/schema.test.ts

2. Add dark mode toggle to the settings page (#42)
     src/settings/ThemeToggle.tsx
     src/settings/SettingsPage.tsx

3. Respect the system theme on first load (#42)
     src/app/bootstrap.ts

README.md stays uncommitted.

Commit all three?
```

Say what stays behind — a file silently left out looks like a bug later. Offer to proceed,
to regroup, to reword, or to cancel.

**If the current branch is the repo's default (`main`/`master`), say so above the proposed
commits** and let the user decide:

```
You're on main, which is budget-app's default branch. Commit here?
```

This isn't hypothetical: `initialise-agent` lets the branch step be skipped, so a session
can legitimately be sitting on the default with real work in the tree. Committing there is
sometimes right and usually not, and it's the user's call — but an unmentioned commit on
`main` is discovered at push time, which is the expensive moment to find out.
`git symbolic-ref --short refs/remotes/origin/HEAD` gives the default; the same detection
`create-branch` uses.

## 6. Commit

Same command without `--dry-run`. Each commit stages only its own files and commits with
a pathspec, so anything the user had staged for other files is left alone rather than
swept into the first commit.

| Code | Meaning | What to do |
|---|---|---|
| 0 | commits made | report them |
| 2 | nothing to commit | say the tree is clean; don't invent a change |
| 3 | not inside a git repo | say so and stop |
| 4 | a message breaks the convention | fix the message, don't override the check |
| 5 | a git command failed | relay git's error. If some commits were already made, the script lists them — re-plan for what's left rather than starting over |
| 6 | the plan doesn't match the tree | a listed path has no changes, or is in two commits. Re-read the change set |

A failing pre-commit hook is a real failure — relay what it said rather than retrying with
`--no-verify`. And **nothing is pushed**; pushing is a separate decision.

## 7. Report

```
budget-app — 3 commits on feat/42-dark-mode-toggle

  e7ed874  Add theme setting to the config schema (#42)
  0464b1e  Add dark mode toggle to the settings page (#42)
  3796f02  Respect the system theme on first load (#42)

README.md left uncommitted. Not pushed.
```

## Working stage by stage

When an issue has a staged plan written by `initialise-agent` (at
`~/.claude/issues/<owner>/<repo>/<issue>/plan.md`; `issue_branch.py plan-path` prints it),
each stage is meant to land as its own commit — the stage boundaries were chosen for
exactly that. Committing a finished stage means scoping the plan to that
stage's files and using its message, rather than re-deriving the grouping from scratch.

If the working tree contains more than the finished stage, commit the stage and leave the
rest; say which files you left behind so the user knows the tree is still dirty on purpose.
