---
name: initialise-agent
description: >-
  Initialise an agent session from a GitHub issue. Reads the issue with `gh` from the repo
  the session is already open on, then: returns it to its default branch, creates and
  checks out a correctly-named issue branch, and spawns an Architect sub-agent to
  decompose complex issues into staged tasks, where each stage is one commit's worth of
  work. Use this whenever the user wants to START WORK on a GitHub issue — "Initialise
  agent for #42", "initialize agent for issue 42", "start work on #42", "set up a session
  for issue 42", "pick up #42", "let's get going on #42", a pasted issue URL, or a bare
  #42 where the intent is clearly to begin implementing, and "initialise work on #42".
  Reads the title and body only by default; add "include comments" to also pull the
  issue's comment thread. The branch step is skippable: "no branch needed", "don't branch,
  I'm already on it" or "just read the issue and plan it" skips it and still does the
  issue read and the plan. The branch can also go **into a new worktree** instead of
  switching the current checkout — "start #42 in a new worktree", "initialise #42 in its
  own worktree", "pick up #42 in a worktree, I'm still mid-way through #41" — which leaves
  the current checkout and its uncommitted work untouched. Use it especially when the
  request names the repo and sounds like plain git work ("start work on #42 in
  budget-app") — doing that by hand reliably gets three things wrong, because the branch
  name follows a convention (`feat/42-dark-mode-toggle`) derived from the issue, the base
  branch differs per repo (some main, some master), and the repo is often still parked on
  a previous issue's branch with uncommitted files. A plain `git checkout -b` is not a
  substitute. Do NOT use for questions *about* an issue that don't involve starting work —
  status checks, "what does #42 say", or commenting on an issue need no branch — and do
  not use it for branch, clone or worktree requests that name no issue. When the user
  wants **only** the branch and nothing else ("create a branch for #42", "cut a branch off
  develop", "just the branch, skip the plan"), use the create-branch skill instead — this
  one calls it for that step and then adds the issue read and the planning pass on top.
---

# Initialise an agent session from a GitHub issue

The point of this skill is speed: one line — `Initialise agent for #42` — should replace
the eight fiddly steps between reading an issue and being ready to write code.

Scope is deliberately tight. **Read the issue, cut the branch in the repo you're already
in, check it out, decompose the work.** No pull requests or PR links, no issue writes (no
comments, labels, assignees or linked branches), no pushing, and no hunting around the
filesystem for the "right" repo. The only things that touch the network are `git fetch`
and the `gh issue view` read.

Speed doesn't mean silence: the one branch-creating step is confirmed with the user first,
showing the repo and the branch name. Everything before it is read-only, so the pause costs
a keystroke and catches a session pointed at the wrong project.

## The sequence

Order matters here. The branch is cut *after* returning to the default branch, because
repos are routinely left parked on a previous issue's branch — cutting first would
silently base new work on last month's unmerged changes.

### 1. Fetch the issue

Run from the session's working directory, so `gh` reads the issue from this repo's own
GitHub remote:

```
gh issue view 42 --json number,title,body,labels,state,stateReason,assignees,milestone,url
```

Add `comments` to the `--json` list **only** when the user asked for comments ("include
comments", "with the comments", "read the thread"). Comments are opt-in because they're
where the noise lives, but when requested they often hold the real scoping decision —
summarise the thread rather than replaying it.

Bodies often carry screenshots as `![image](https://github.com/user-attachments/assets/…)`
or `<img … src="…">` tags. They're unreadable here, so strip them before you reason about
the body or pass it to the Architect, but mention that the issue has screenshots in case
they matter.

If the body is **blank**, don't stop — plan from the title and the codebase. Say in one
line that the body is empty and the plan is built from the title, then carry on. Tell the
Architect the body is blank, so it states its assumptions rather than presenting them as
the issue's requirements, and every gap the title leaves open (scope, behaviour, platforms,
anything a body would normally settle) goes under **Open questions** in the plan. Only
stop when the title is too vague to plan from on its own ("Fix bug", "Update") — then offer
the comments instead.

If the body is nothing but a link, say so plainly and offer the two cheap next steps —
read the comments, or fetch the linked page — instead of proceeding on nothing.
`references/github-issues.md` covers the other quirks (task lists, cross-references,
templates, state vocabulary); read it when an issue returns something surprising.

If the issue is already `CLOSED`, surface that (with its `stateReason`) and confirm before
branching. It usually means the user wants something other than fresh work.

If `gh` fails, relay its error. `gh auth status` explains an auth problem, and "Could not
resolve to an issue" usually means the number belongs to a different repo.

### 2. The repo is the one you're in

There is no inference here, deliberately. The target repo is whichever repo the session's
working directory sits in — `setup` resolves it with `git rev-parse --show-toplevel`, so
running from a nested source folder finds the same root as running from the top. `gh`
reads the issue from that same repo.

Only one case needs a question: **if the session has more than one directory attached**,
ask which of them to work in before going any further. You can see the attached
directories in your own context; there's no command that reports them, so this is the one
step you have to judge rather than check.

Two rules keep it unambiguous:

- **Never switch directory to find a better candidate.** If the working directory isn't
  inside a git repo, say so and stop. Don't go hunting for some other candidate repo.
- **If the user names a repo, or pastes an issue URL, that isn't the one you're in, stop
  and say so.** "Start work on #42 in budget-app" while the session is open on `dotfiles`
  is a contradiction, not an instruction to go and find budget-app. Fetching `#42` here
  would read a different issue entirely, and silently branching `dotfiles` would be the
  worst outcome — it looks like it worked. Name both repos and let the user re-point the
  session or confirm the current one.

An issue spanning several repos is handled as one session per repo, which matches working
one issue per repo at a time.

### 3. Cut the branch — via the `create-branch` skill

**Use the `create-branch` skill for this step; don't hand-roll the git commands.** It owns
the naming convention, the dirty-tree and base-branch checks, and the confirmation prompt,
so the branch you get here is identical to the one a bare "create a branch for #42" would
produce. Follow it end to end, including its confirmation before anything is created —
that pause is the only guard against a branch landing in a session pointed at the wrong
project.

You arrive there already holding what it asks for in its step 1, so hand it straight over
rather than re-fetching: the issue number, its title, body and labels (for the type and
summary), and the working directory. The base is that repo's default branch unless the
user asked for another.

Its exit-code table tells you how to respond to a dirty tree (stop — someone's uncommitted
work is not yours to move), a directory outside a repo, or a base that doesn't resolve. In
every one of those cases the answer is to stop and relay, not to improvise a way through.

The branch stays **local**. Nothing is pushed.

#### In a new worktree

When the user asks for a worktree ("in a new worktree", "in its own worktree", "keep my
current checkout as it is"), tell `create-branch` to use its worktree mode (`--worktree`).
Don't choose a worktree on the user's behalf: a worktree is a new folder with its own
dependencies and build output, and deciding when that's worth it is theirs.

Worktree mode has no dirty-tree stop. A dirty current checkout is fine, and often the
reason for asking. It creates `<repo>-<issue>` beside the repo and leaves this checkout
exactly where it was.

Everything after the branch carries on as normal. The plan lives outside every checkout
(step 5), so a session opened in the worktree finds it. Record the worktree in the plan's
`Repo` line, since a resumed session reads that line to find out where it is:

```
- **Repo**: budget-app — branch `feat/42-dark-mode-toggle` from `main`, in worktree `~/Programming/Github/budget-app-42`
```

This session can't follow the work into the new folder, because its working directory is
fixed. So the report's next step changes: `begin-work` has to run in a new session opened
in the worktree, not here (see step 6). Offering to run it here would build in the wrong
checkout.

#### Skipping the branch

The branch is the one optional step, and there are two ways in:

- **Asked for up front** — "initialise work on #42, no branch needed", "don't branch, I'm
  already on it", "just read the issue and plan it". Skip this step entirely. Don't run
  `create-branch`, and don't ask again — they already answered.
- **Declined at the prompt** — the user says no, or cancels. Take that as *no branch*, not
  as *abandon the session*.

Either way, **carry on with the rest**. The issue is already read, and decomposing and
writing the plan don't need a branch to exist. Stopping dead would throw away the work
already done over a step the user just said they didn't want.

Say which branch the work will land on instead — and **if that's the repo's default
(`main`/`master`), say so plainly before moving on**:

```
No branch cut. You're on main, which is budget-app's default — begin-work will build
there and create-commit will commit there unless you branch first.
```

Skipping usually means "I'm already on the issue branch", which is fine. Occasionally it
means the session is parked on `main`, and every later step will quietly build and commit
there. The dry run in `create-branch` already reports both the current and default branch,
so this costs a comparison, not a new check.

### 4. Decompose — but only when it earns the time

Spawn an Architect (the `Plan` agent type) when the issue genuinely has structure to
uncover: it has a task list or references other issues, touches several parts of the
system, or has a body long enough to be hiding scope.

Skip it when the issue is self-evidently one change — "Fix typo in README" needs no
decomposition — and just record the task directly. Say that you skipped it and why. A
five-minute breakdown of a one-line issue defeats the entire purpose of the skill.

Brief the Architect with the cleaned issue content, the repo you're in, and that repo's
`CLAUDE.md` or `AGENTS.md` if one exists. Those carry load-bearing constraints — the build
tool, a required toolchain version, a test command that isn't the obvious one — and a plan
that ignores them will not build.

Ask it for tasks in dependency order, each one a concrete change to named files, plus any
open questions the issue leaves unanswered.

**Ask for those tasks grouped into stages, where a stage is one commit's worth of work.**
This is the difference between a plan that's a list of things to do and a plan the work
can actually be shipped from. A stage is right-sized when:

- it is one concern a reviewer could judge without reading the other stages;
- it would leave the build green on its own, so it could be committed and pushed as-is;
- its tests live in the same stage as the code they cover — a behaviour and its test are
  one change, not two;
- a rename or signature change sits with its call sites, because splitting them produces a
  stage that doesn't compile.

Most issues land in two to five stages. One stage is the honest answer for a genuinely
single change — don't manufacture more, since a plan that splits one concern into three
commits is as unhelpful as one that lumps three concerns into one.

Have the Architect name each stage with the commit message it should produce, in the
convention: an imperative description, a space, then the issue reference in brackets
(`Load client notes as at call time (#42)`). Writing it up front is what makes the stage
boundary concrete — if the message needs an "and", the stage is doing two things.

### 5. Write the plan and seed the todos

The plan lives **outside** the repo, at a path keyed by owner, repo and issue number,
because issue numbers repeat across repos. Ask the script for it rather than building it
by hand:

```
python3 ~/.claude/skills/create-branch/scripts/issue_branch.py plan-path --dir "<the working directory>" --issue 42
```

That prints `~/.claude/issues/<owner>/<repo>/42/plan.md`, with the owner and repo taken
from `origin`, so a session in a worktree resolves the same file. Keeping it out of the
repo means it never shows up in the diff or gets committed by accident.

```markdown
# #42 — Add a dark mode toggle

- **Issue**: https://github.com/<owner>/budget-app/issues/42
- **Labels / state**: enhancement · OPEN
- **Repo**: budget-app — branch `feat/42-dark-mode-toggle` from `main`
  <!-- when the branch was skipped, say so instead — a resumed session reads this line to
       know where it is: "budget-app — no branch cut; working on `feat/42-existing`" -->

## What the issue asks for
<a few lines, in your own words>

## Stages
Each stage is one commit's worth of work. The heading is the commit message.

### Stage 1 — <imperative description> (#42)
- [ ] 1.1 <a concrete change to named files>
- [ ] 1.2 …

### Stage 2 — <imperative description> (#42)
- [ ] 2.1 …

## Open questions
- …
```

Then seed the session todo list from the tasks, keeping the stage they belong to visible in
each entry, so the work is live in the session and also survives a restart.

The stage headings are not decoration — `create-commit` reads them as the commit messages,
so a finished stage commits without anyone re-deriving how to group the diff. Getting the
boundaries right here is what makes committing cheap later.

### 6. Report

Keep it short — the user wants to start working, not read a summary:

```
#42 — Add a dark mode toggle (enhancement · OPEN)

budget-app
  branch  feat/42-dark-mode-toggle
  base    main @ a1b2c3d (local only, not pushed)

Plan    ~/.claude/issues/<owner>/budget-app/42/plan.md — 3 stages, 7 tasks, 1 open question
Note    The issue has two screenshots I can't read; describe them if they matter.
```

For a worktree, add the path, and make the next step opening a session there:

```
budget-app  (this checkout untouched, still on fix/38-…)
  branch    feat/42-dark-mode-toggle
  worktree  ~/Programming/Github/budget-app-42
  base      origin/main @ a1b2c3d (local only, not pushed)

Plan    ~/.claude/issues/<owner>/budget-app/42/plan.md — 2 stages, 4 tasks
Next    open a new Claude session in the worktree and say "begin work". Install its
        dependencies there first if the stages need them.
```

Otherwise, end by offering the next step rather than starting it: say the word and
`begin-work` builds Stage 1. Planning and building are separate decisions — the user may
want to read the plan, answer an open question, or re-scope a stage before any code exists.

## Stop rather than improvise

Some situations are worth halting on, because the cost of guessing wrong is higher than
the cost of one question:

- **A dirty tree.** Someone's uncommitted work is not yours to move. This doesn't apply in
  worktree mode, which never moves it.
- **A working directory that isn't inside a git repo.** Say so and stop. Don't go
  hunting for a plausible repo elsewhere on disk.
- **More than one directory attached to the session.** Ask which one; don't pick.
- **An issue URL or repo name that doesn't match the repo you're in.**
- **An issue that's already `CLOSED`**, or already has a branch with commits on it.
- **An issue with nothing actionable in it** — a link-only body, or a blank body under a
  title too vague to plan from. Offer the comments or the linked page; don't send the
  Architect in blind or invent requirements. A blank body under a meaningful title is
  *not* this case: plan from the title and list the gaps as open questions (step 1).

And never create the branch without the confirmation in step 3, even when the issue and
the repo both look obvious. It is the only step that changes anything the user would have
to undo.
