# Brief format

The hook injects the rules and the identity. A brief contains only what concerns the work itself.

## Lead → verifier session

```
Request <t-xxxx>: <one line: what the user wants>

Goal: <what must be different once this is done>
Completion conditions (things you can check directly):
- <e.g. `pytest tests/auth` passes>
- <e.g. a PR is open and CI is green>
- <e.g. file X contains Y>
Scope: <repositories/folders you may touch>, must not touch: <...>
Splitting into lanes: <independent tasks that can be split / tasks that need an order>, lanes that edit the same repository get isolation:"worktree"
where: <remote name from `t3lead remotes`; omit for this computer>   (only when the user named that computer or agreed to it; say where on that computer the work happens)
Notes: <related files, earlier lessons (t3lead lessons), user preferences>
Report: once, after verifying every lane. Conclusion, evidence (files, commands, PRs, commits), what remains or needs a user decision.
```

## Verifier session → lane

```
<lane ID>: <one line: the task you own>

To do: <concretely>
Deliverable: <file / commit / PR / report>
Completion conditions: <what the verifier session will check directly>
Completion claim format: end your final answer's last line with
  DONE_CLAIM <evidence: file paths, commands and results, commit SHA, PR number>
If you are not done, do not write DONE_CLAIM; state what remains.
```

For a remote lane (`where:` in the lead's brief), the first line of the brief, and of every later message to that lane including `NOT_DONE`, is the reference line `t3-lead-ref: lane <request-id>` (the request ID from the lead's brief). Nothing else about who the lane is; the hook on that computer reads this line to apply the lane rules.

The verifier session checks the evidence in `DONE_CLAIM` against the real state, and if it is wrong, sends `NOT_DONE: <reason>` to the same thread (at most 2 times per lane).
