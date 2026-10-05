---
name: begin-work
description: >-
  Start implementing a GitHub issue, working through the planned stages one at a time. Reads the
  staged plan written by initialise-agent, builds one stage, then stops and shows you a
  per-file table — what changed, how big it is, whether the line endings still match the
  repo — and asks whether to commit before moving on. Use this whenever the user says to
  start building: "start working", "begin work", "let's go", "go ahead and implement it",
  "start on stage 2", "work through the plan", "crack on with #42", or a simple "yes"
  after you've laid out a plan. **Especially use it when the user points at a plan file
  directly** — "implement the plan in ~/.claude/issues/<owner>/budget-app/42/plan.md", "work through
  plan.md", "do what the plan says". Opening that file and coding from it looks like the
  obvious move and is the wrong one: the plan is a list of *stages*, and working it by hand
  skips the stage boundaries, the minimal-comment and line-ending discipline, and the
  per-stage commit prompt that are the whole reason it was written in stages. Reading the
  plan is the skill's own first step, not a substitute for it.
  Use it even when the change looks small enough to just do —
  working stage by stage is what keeps commits reviewable, and the stage boundary is where
  the line-ending and comment-noise checks happen, both of which are far cheaper to catch
  before a commit than after. Do NOT use it to write the plan (initialise-agent does that),
  to make the commits themselves (create-commit does that, and this skill hands over to it),
  or to polish a finished branch before a PR (/ship). If there is no plan yet, this skill
  says so rather than improvising stage boundaries mid-flight.
---

# Work the plan, one stage at a time

The plan already decided what a commit's worth of work looks like. This skill's job is to
build one stage at a time, keep the code clean enough that nothing has to be undone later,
and stop at each boundary so the user decides what gets committed.

Two things go wrong when work isn't staged: the diff grows until nobody can review it, and
unrelated changes get welded together in one commit. Both are cheap to avoid up front and
expensive to unpick afterwards.

## 1. Find the plan

The issue number is in the branch name (`feat/42-dark-mode-toggle`), and the plan lives at
`~/.claude/issues/<owner>/<repo>/<issue>/plan.md`. Ask the script for the exact path; with
no `--issue` it takes the number from the current branch:

```
python3 ~/.claude/skills/create-branch/scripts/issue_branch.py plan-path --dir "<the working directory>"
```

Exit 4 means the branch carries no issue number — ask which issue this is. Read the plan
and find the first stage with unticked tasks.

**If there's no plan, don't invent the stages as you go.** Say so and offer the two real
options: run `initialise-agent` to plan properly, or — for a change genuinely small enough
not to need it — agree a short stage list with the user in the chat before touching code.
Stage boundaries are commit boundaries; discovering them halfway through an edit produces
exactly the unreviewable commit this skill exists to prevent.

Say which stage you're starting in one line. It doesn't need ceremony, but the user should
never be guessing which part of the plan is live.

## 2. Build exactly that stage

Everything in the stage, nothing from the next one. When you spot something outside the
stage that wants fixing — a bug in adjacent code, a tidy-up, a better name — **note it and
leave it.** Carrying it into this stage silently widens the commit, and the note costs
nothing. The exception is something that genuinely blocks the stage; say so and deal with
it as part of the work.

### Comments: bare minimum

Only non-obvious detail. JSDoc on top-level declarations. Intent first — **why, not what** —
in one or two sentences of simple technical English. Self-explanatory code gets no comment at
all.

**Never write:**

- **Negations, or what the code isn't.** No `// this does not handle X`, no
  `// without this, Y would happen`, no hypothetical failure narration. State what is true.
- **Narration of logic that lives elsewhere.** Describe this declaration, not what its callers
  or consumers do with it. That prose goes stale the moment the other file moves.
- **Prose mirrors of code.** If the sentence can be read off the lines below it, delete it —
  `// increment the counter`, `// set the name`, `/// <summary>Gets the name.</summary>`.
- **References to specs, plans, issues or scenario ids.** No issue numbers, no "see the plan",
  no "case 3b". The commit and the history carry that; a comment carrying it rots.
- Narration of your own edit — `// added this`, `// NEW`, `// updated logic`.
- Section banners and separators around short functions.
- Commented-out code. Git has it.

**Do write, when the code genuinely cannot say it:**

- The rationale or trade-off behind a choice that looks arbitrary.
- A non-obvious constraint the reader must respect: ordering, a boundary condition,
  thread-safety, a value that has to stay in step with something else.
- A deliberate deviation from the surrounding pattern.

Obeying this is usually a matter of turning the sentence around. Instead of the reason it
isn't the other way, state the rule:

```
// Without this guard, another provider's update would read the flags as absent and disarm capture.
->
/** These flags are PostHog's, so only its updates change them. */
```

Keep them general rather than line-by-line: one comment explaining why a block exists beats
five narrating its steps. And match the density of the file you're in — a codebase that
comments sparsely shouldn't suddenly sprout annotations because a new file was added.

### Line endings: match what the file already is

Most repos are LF, but some pin CRLF for certain files in `.gitattributes`, and the failure
is silent. A file whose endings flip produces a diff claiming every line changed, which
buries the actual change and wastes a reviewer's time. Two habits prevent nearly all of
it:

- **Editing an existing file** — leave its endings alone. `Edit` preserves them; a
  wholesale rewrite of the file does not.
- **Creating a new file** — this is where it goes wrong. New files land LF regardless of
  what the repo uses. Check the convention (`.gitattributes`, or a sibling file) and match
  it, and end the file with a newline.

You don't have to eyeball this — the stage-boundary check below verifies it for every file
and tells you exactly which ones are wrong.

### Verify as you go

Run whatever the repo actually uses — check `CLAUDE.md`, `AGENTS.md`, `package.json`,
`pyproject.toml`, `Makefile` or `justfile` rather than assuming. A guessed command fails
for reasons that have nothing to do with the code.

Where the project's checks are quick, run them before calling a stage done. Where a full
build is genuinely slow, run the narrowest useful thing instead and **say what you ran and
what you skipped** — "tests pass, full build not run" is useful; silence reads as verified
when it isn't.

## 3. At the stage boundary, stop and show the work

Write a one-line summary per file to the scratchpad:

```json
{"src/settings/ThemeToggle.tsx": "New toggle that switches and saves the theme",
 "src/config/schema.ts": "Adds the theme setting, defaulting to system"}
```

Then render the table:

```
python3 ~/.claude/skills/begin-work/scripts/stage_review.py review --dir "<the working directory>" --stage "Stage 2 — Add dark mode toggle to the settings page (#42)" --files <this stage's files> --summaries "<scratchpad>/summaries.json"
```

It prints what the user needs to judge the stage, with the line-ending verdict per file:

```
**Stage 2 — Add dark mode toggle to the settings page (#42)**

| File                          | Change   | +/-     | Line endings | What changed                                 |
|-------------------------------|----------|---------|--------------|----------------------------------------------|
| src/config/schema.ts          | modified | +15 -2  | LF ok        | Adds the theme setting, defaulting to system |
| src/settings/ThemeToggle.tsx  | added    | +42 -0  | LF ok        | New toggle that switches and saves the theme |

2 file(s), +57 -10.
Line endings match the repo for every file.
```

**Exit code 7 means a line-ending defect — fix it before asking anything.** The script
names the file and the problem (wrong style, mixed within one file, missing trailing
newline, or a diff that churns the whole file). Don't show the user a table full of
problems and ask them what to do about it; they're your defects, so fix them and re-run.

`--files` scopes the table to the stage. Leave it off to show everything in the tree, which
is worth doing if the tree holds more than this stage's work — the user should know what
else is sitting there uncommitted.

## 4. Ask — never commit on your own initiative

The commit is the user's call, every time. One question covers both decisions:

```
Stage 2 is done. Commit it and move on to Stage 3 (Respect the system theme on first load)?
```

- **Yes** → hand over to the `create-commit` skill, using the stage heading as the commit
  message. It runs its own confirmation, which is the right amount of ceremony for the one
  step that writes history.
- **Keep going without committing** → fine. Say the tree is carrying two stages of work now,
  because that changes what the next boundary looks like.
- **Changes wanted first** → make them, re-run the table, ask again.

Then tick the stage's tasks in `plan.md` and note the commit sha next to the stage heading
if it was committed. A stage that was built but not committed is not done — record it as
built, not shipped, so a resumed session doesn't assume the work is safely in history.

## 5. When the stages run out

Report what landed, what didn't, and what's left over:

```
#42 — 3 of 3 stages built, 2 committed.

  e7ed874  Add theme setting to the config schema (#42)
  0464b1e  Add dark mode toggle to the settings page (#42)
  Stage 3  built, not committed (you asked to review it first)

Noted along the way, not fixed — outside the stages:
  - SettingsPage.tsx swallows the config load error (pre-existing)

Not pushed. `/ship` first if the branch wants polishing, then `create-pr` writes up the PR.
```

Don't push and don't open a PR — neither was asked for, and both are decisions the user
makes once they've seen the branch. Once every stage is built and committed (even if the
user declines `/ship`), offer `create-pr` as the next step rather than just stopping — it
reads the branch's own commit history back as a PR description, and only pushes or opens the
PR after its own separate confirmation.
