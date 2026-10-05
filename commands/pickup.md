---
description: Resume a named session from its most recent dump, with live session fallback
---

The user wants to resume the session labelled: $ARGUMENTS

0. If `$ARGUMENTS` is empty, ask the user which label to resume (optionally list the directories under `~/.claude/dumps/`) and stop.

1. Attempt `/resume $ARGUMENTS` — if a live session resumes successfully, stop here

2. Otherwise, look for dump files at `~/.claude/dumps/$ARGUMENTS/*.md`
   - If the directory doesn't exist or is empty, tell the user "No session or dump found for $ARGUMENTS" and stop

3. Sort the files by filename descending and read the newest one

4. Present back to the user:
   - **Dump timestamp and how many total dumps exist for this label** — also state how old the newest dump is (e.g. "~3 days ago"); the older it is, the more the "External State to Re-check" items should be distrusted
   - **Branch & directory** — cd there if not already
   - **Goal**
   - **Current State**
   - **Decisions & Deferrals** — surface these so settled calls aren't accidentally re-litigated (skip if the dump omitted the section or marked it "none")
   - **External State to Re-check** — the stale-by-definition items (PR/CI/reviews/deploys); call these out as needing re-verification (skip if "none")
   - **Next Steps**
   - **Open Questions / Blockers**

5. Say: "Ready to continue — should I pick up from the top next step, or do you want to review first?"

6. Treat the dump as ground truth. Do **not** verify git/branch state (HEAD, status, pushed/unpushed) by default — trust what the dump records and present it. Only check branch state if the user asks, or if a next step you're about to execute genuinely depends on it. If next steps reference specific files, read them as needed before acting.