---
description: Polish the current change before shipping — simplify, review, strip noise comments, then verify line endings survived
---

The user wants the current change polished before it ships. Optional scope: $ARGUMENTS

Run the four stages **in this order** — each one assumes the previous has finished, because
simplifying after a review invalidates the review, and stripping comments before a review
hides the reasoning a reviewer needs.

Everything below is scoped to **code changed in this session / working tree**. No stage may
wander into untouched code: that turns a focused change into an unreviewable one.

---

## 0. Establish scope

1. `git branch --show-current` and `git status --short`.
2. Record the changed + added file list. Every later stage is limited to these paths.
3. If the working tree is clean and `$ARGUMENTS` is empty, say so and stop — there is nothing
   to polish.
4. If `$ARGUMENTS` is given, treat it as the scope (a path, branch, or PR number) and pass it
   through to the stages that accept one.
5. If the tree contains changes you did not make yourself, **say so and confirm before
   proceeding** — stages 1 and 3 rewrite code, and silently reworking someone else's
   in-progress edit is not recoverable for them.
6. Note whether the branch is the repo's default branch. If it is, flag it now rather than at
   commit time.

## 1. Simplify

Invoke the `simplify` skill. It covers reuse, simplification, efficiency, and altitude —
quality only, no bug hunting (that's stage 2).

Afterwards, re-run the project's own checks (typecheck / build / tests — whatever the repo
actually uses; check `CLAUDE.md` or `package.json`). A simplification that breaks the build is
not a simplification, and finding that out at stage 4 wastes the later stages.

## 2. Review

Invoke `code-review` (pass `$ARGUMENTS` as the target if one was given).

Then triage the findings — do not blanket-apply them:

- **Confirmed correctness bugs** — fix, then re-run the checks.
- **Anything ambiguous, or that changes agreed behaviour** — report it, don't silently "fix"
  it. A review finding is a claim, not an instruction; some are wrong.
- **Findings about code you didn't touch** — report only. Out of scope.

## 3. Strip unnecessary comments

Go through the comments **in the changed code only** and remove the ones carrying no
information. The risk here is asymmetric: a deleted "why" comment cannot be reconstructed from
the code, while a redundant comment costs almost nothing. **When in doubt, keep it.**

**Remove:**

- Restates the code — `// increment the counter`, `// set the name`, `/// <summary>Gets the name.</summary>`
- Narrates the edit or the session — `// added this`, `// NEW`, `// changed per review`,
  `// fixed`. These read as noise the moment the branch merges.
- Commented-out code. It's in git history; leaving it invites "is this coming back?"
- Empty ceremony — banner blocks with no content, `// ---` separators around a two-line
  function, doc comments that only repeat the signature and parameter names.
- `TODO` / `FIXME` that the change has already done.

**Keep — these are the point of comments:**

- **Why**, not what: rationale, trade-offs, the reason the obvious approach was rejected.
- References to a canonical source or spec — `file.py:123`, issue numbers, a standard. These are
  how the next reader verifies a port is faithful.
- Non-obvious constraints: ordering requirements, boundary conditions, thread-safety,
  "must stay in sync with X".
- Warnings and footguns — anything that starts "note that" or explains what breaks if changed.
- Explanations of a deliberate deviation from the surrounding pattern.
- Anything that would otherwise turn into a reviewer's "why did you do this?" question.

Also match the surrounding file's comment density and style rather than imposing your own.

## 4. Verify line endings survived

New files written by `Write` land with LF regardless of the repo's convention, and editing tools can
write LF into a CRLF file — producing a file that's wrong wholesale, mixed, or a diff that claims
every line changed. All three are review-hostile and easy to miss. (`Edit` preserves an existing
file's endings, so the usual culprit is a **newly created** file.)

**Do not compare the working file against `git show HEAD:<file>`.** With `core.autocrlf=true`
the index stores LF, so every correctly-CRLF working file looks changed — the check produces a
false positive on literally every file. Use the steps below instead.

For each modified or added file from stage 0:

1. **Expected ending** — ask git, don't guess:
   `git check-attr text eol -- <file>`
   - `eol: crlf` → must be CRLF; `eol: lf` → must be LF.
   - `eol: unspecified` → fall back to `git config core.eol`, then `git config core.autocrlf`
     (`true` means CRLF on checkout, `input` or unset means LF), then the file's own
     dominant style.
   - `text: unset`, or a `binary` attribute → skip the file entirely.
2. **Actual ending** — count the bytes; do **not** use `grep -c $'\r$'`. If `$'\r'` fails to expand
   in the shell, that pattern degrades to a bare `$`, which matches every line and reports a
   pure-LF file as 100% CRLF — a silent false pass on every file.
   - `cr=$(tr -cd '\r' < "<file>" | wc -c)`
   - `lf=$(tr -cd '\n' < "<file>" | wc -c)`
   - Cross-check with `file -b "<file>"`, which prints `with CRLF line terminators` when relevant.
3. **Verdict:**
   - `cr == 0` → LF. `cr == lf` → CRLF. `0 < cr < lf` → **mixed**, always a defect.
   - Differs from expected → needs fixing.
4. **Whole-file-rewrite check** — `git diff --numstat -- <file>`. If added + removed is roughly
   twice the file's line count on a file you only edited in a few places, the endings flipped
   even if the file is now internally consistent.
5. **Trailing newline** — `git diff` reporting `\ No newline at end of file` on a file that had
   one is the same class of accident. Restore it.

**Fixing:** normalise the whole file to the expected ending, then re-run steps 2–4 to confirm.
- LF → CRLF: `sed -i 's/$/\r/' <file>` (only on a file with no CR at all, or you'll double them)
- CRLF → LF: `sed -i 's/\r$//' <file>`

Prefer fixing the file over changing `.gitattributes` or git config — the repo's convention is
deliberate and shared, and a config change alters every other file for that developer too.

## 5. Report

Summarise, in a few lines each:

- **Simplified** — what changed and why, or "nothing worth changing".
- **Review** — findings fixed, findings reported-not-fixed (with the reason), findings out of
  scope.
- **Comments** — how many removed and the kinds; note anything you deliberately kept that
  looked redundant but is load-bearing.
- **Line endings** — the per-file verdict table, and anything fixed.
- **Checks** — the exact commands run and their results, so "it's clean" is reproducible
  rather than asserted. Call out any tooling that is broken locally rather than quietly
  skipping it.

Do **not** commit, push, or open a PR unless the user asks — this skill polishes, it doesn't
publish. End by stating what's left for them to decide.
