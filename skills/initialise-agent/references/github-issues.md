# Reading GitHub issues

Read this when an issue fetch returns something the main workflow doesn't obviously cover.

## Connection

| | |
|---|---|
| Tool | `gh issue view <number> --json …`, run from inside the repo |
| Repo | resolved by `gh` from the checkout's `origin` remote |
| Issue URL | `https://github.com/<owner>/<repo>/issues/<number>` |
| Auth | `gh auth status`; `gh auth login` if it fails |

`gh` picks the repo from the working directory's remotes. If a repo has more than one
GitHub remote (a fork with an `upstream`), `gh` may ask which one is the default the first
time. Relay that rather than answering it; `gh repo set-default` is the user's choice.

## Field sets

Default request:

```
gh issue view 42 --json number,title,body,labels,state,stateReason,assignees,milestone,url
```

`comments` is deliberately **absent**. Comments are opt-in because they are where the long
tail of noise lives — "+1"s, bot messages, CI links — and pulling them by default would
bury the actual requirement. Add it only when the user asks.

When comments *are* requested, they earn their place: the scoping decision ("let's only do
this for the web app for now") is often recorded there and nowhere in the body. Summarise
the thread; don't replay it.

## Body quirks

- **Screenshots.** `![image](https://github.com/user-attachments/assets/…)` and
  `<img width="…" src="…">` tags carry nothing you can read. Strip them before reasoning
  about or forwarding the body, and mention that they exist.
- **Issue templates.** Bodies created from a template keep its headings (`### Describe the
  bug`, `### Steps to reproduce`) and often its untouched placeholder text or
  `_No response_`. Treat unfilled sections as empty, not as requirements.
- **Task lists.** `- [ ] …` items are a ready-made decomposition hint. Ticked ones
  (`- [x]`) are already done. Don't plan them again.
- **Cross-references.** `#17`, `owner/repo#17` and full issue URLs point at related work.
  "Blocked by #17" or "follow-up to #17" is often the real context. Mention it, and offer
  to read the referenced issue rather than fetching it unasked.
- **Link-only bodies.** A body that's just a link to a doc or discussion makes the title
  and body worthless. Say so and offer to read the comments or fetch the linked page
  rather than guessing.
- **HTML comments.** `<!-- … -->` blocks are usually template guidance. Ignore them.

## Vocabulary

Handy for judging whether an issue is already underway before you branch.

- **`state`**: `OPEN` or `CLOSED`.
- **`stateReason`** (closed only): `COMPLETED` or `NOT_PLANNED`; `REOPENED` on a reopened
  open issue.
- **Labels** are freeform per repo, but the defaults (`bug`, `enhancement`,
  `documentation`, `question`) are common. They're the main hint for the branch type in
  create-branch.
- **`milestone`** is a decent scope hint, never a routing hint.

A `CLOSED` issue is a strong sign the user means something other than "start fresh work".
Surface the state and reason and confirm before branching.
