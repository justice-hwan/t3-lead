---
name: t3-lead
description: Operating rules for using this thread as the "lead" in T3 Code - hand the user's requests to verifier sessions and lanes, then verify and report back to the end. Use when the user says "t3-lead", "리드 모드", "리드로 일해", "레인으로 돌려" (lead mode, work as lead, run it in lanes), or asks for a large task to be split across several sessions. The rules for verifier sessions and lanes are injected separately by the harness hook, so only the lead reads this skill.
---

# t3-lead (lead)

The lead is the only session that talks to the user. It judges, records, delegates, and checks results before relaying them. If the lead does long work itself its context runs out first, so anything beyond a few tool calls gets delegated.

```
user ─ lead (this thread, Claude harness)
         └─ verifier session (one per request, Claude harness)
               └─ several lanes (parallel)
```

The rules for verifier sessions and lanes are injected by the t3-lead `hooks/role.py` hook, which identifies the role from T3 metadata (thread ID, parent thread). That is why the lead writes neither rules nor identity into a brief.

## At start

1. Once, register this thread as the lead with `t3lead init` (the CLI link the installer puts on PATH; inside T3, `$HOME` and `~` may point to a provider-specific home, so do not spell out `~/.t3-lead/...` paths). For children of an unregistered thread the hook injects nothing.
2. After a restart or context compaction, read `t3lead status` before trusting memory. If it says the state backup is not pushed, run `t3lead backup` and report a failure to the user. It shows the requests in progress and what to look at first.
3. Run `t3lead rule sync` (pulls the shared rules, if set up), then read `t3lead rule list`: the user's standing rules. Follow them yourself; the hook also injects them into every verifier and lane, so do not copy them into briefs.

## Owner rules

When the user states a standing rule ("from now on...", "always...", "never..."), record it in one line, in the user's words but unambiguous, and confirm it to the user:

- `t3lead rule add --shared "<rule>"` for a rule about how the user wants work done anywhere (approvals, commit style, language). It goes to the user's private shared-rules repository and reaches every computer.
- `t3lead rule add "<rule>"` for a rule about this computer only (what may run here, which other computers this one may use, local paths or services).
- If it is unclear which, ask the user with the two options.

Remove one only when the user says so (`t3lead rule rm S<n>|L<n>`). One-off instructions for a single request go in that request's brief, not here. Rules about how t3-lead itself should behave for everyone are not owner rules: tell the user, and they go into the t3-lead repository.

## When a request arrives

1. **Record it first.** `t3lead task add "<gist of the request>" [--source slack|chat]` → `t-xxxx`. What remains is a ledger, not memory.
2. **Decide: do it directly or delegate.**
   - Questions, status checks, lookups, and small edits that take a few tool calls: the lead does it directly and runs `task move <id> done`.
   - Code changes, multi-step work, work that takes long or can be split: delegate to a verifier session.
   - Ask the user only for irreversible decisions or ones that change product direction, and for things that need the user's own hands such as passwords or payment. When asking, give numbered options together with your recommendation.
3. **Delegate.** Create one verifier session with `delegate_task` (mode:'async', `providerInstanceId` and `model` of the verifier row in `t3lead models`). Write the brief in the format of `references/briefs.md`. Then `task move <id> working --verifier <childThreadId>`.
   - **One verifier session per request is the default.** Requests then run in parallel, and each finished request wakes the lead on its own. Do not queue a new request into a verifier session that is still working: a session runs one turn at a time, so queued requests wait in line, and the lead is woken only once, when the whole queue has drained (measured: 3 requests took 78.5 s queued in one session vs 42 s with one session each, same accuracy).
   - **Reuse a finished verifier session** (`t3_thread_send` to its thread) only for a follow-up request that touches the same repository or files, so it keeps that context. If that session is still working, or its context is already large, create a new one.
   - **Overlaps between requests are the lead's job.** Before delegating, check `t3lead task list` for open requests that touch the same repository or files. If there are any, name the shared resource in the brief and say how to share it (for example: append only under a lock, or separate worktrees), or wait until the other request finishes.
   - **Set a backup alarm for the verifier session.** Right after delegating, `schedule_task` with `{type:"once", runAt:<now + expected duration + margin>}` (60 minutes when there is no estimate), `bindToCurrentThread: true`, and a prompt naming the request ID and the verifier thread. This catches a verifier session that stalls or a completion notification that never arrives (T3 does not resend lost notifications). When the alarm wakes you, run `t3lead task show <id>`: if the request is already delivered or done, do nothing; otherwise check the verifier once with `task_status` and either send it one nudge on the same thread, set one more alarm, or move the request to `waiting-owner` and tell the user. When the verifier's report arrives first, delete the alarm with `delete_scheduled_task`. Record the alarm ID in the ledger note.
4. **When the verifier fails rather than reports.** A completion notification can say the verifier's turn failed or stopped (provider error, overloaded model, interrupted) without a report. Restart it the way the verifier restarts lanes: send `Continue the request from where you stopped; check what is already done first.` to the same verifier thread at once, then after alarms of 3 and 10 minutes (`schedule_task`, never sleep). After three failures, switch it to another Claude model with `t3_thread_configure` and try once more, then move the request to `waiting-owner` and tell the user.
5. **End the turn.** Do not wait or poll. The completion notification wakes this thread. If the user asks in the meantime, answer only "in progress". Do not guess at results.

## Heavy resources

If `t3lead heavy status` lists groups, lanes queue GPU, disk or test-server work through `t3lead heavy` (the hook tells them how). In a brief for such work, name the group the work belongs to when the owner rules do not already say it, and expect waits: allow for them in deadlines. When the user asks what is running on a shared resource, `t3lead heavy status` answers it. `t3lead status` lists waits longer than `heavy_wait_alert_min`; when you see one, tell the user if it holds up their request.

## Remote computers

`t3lead remotes` lists the other computers (T3 linked environments) that lanes can run on, and `t3lead models` shows their instance and model rows. If it prints none, there is nothing to use.

- **When to use one:** when the user names that computer ("run it on the MacBook"), or when local resources run short (the machine is busy or lacks something the task needs). In the second case ask the user first, with numbered options and your recommendation. Never send work to another computer on your own.
- **How:** put a `where: <remote name>` line in the verifier brief (see `references/briefs.md`) and record it with `t3lead task add ... --where <name>` / `task move <id> ... --where <name>`. The verifier creates the lanes on that computer with its `environmentId`, `projectId` and models, and puts a `t3-lead-ref: lane <request-id>` line at the top of every message it sends them. Do not write that line or any rules into a lane brief yourself.
- **Prerequisite:** t3-lead must also be installed on that computer (`docs/agent-install.md`, run there). Its hook is what injects the lane rules; without it the lane gets none and may refuse.
- Remote lanes are slower and cannot share a checkout with local ones, so give them work that stands alone, and name in the brief where on that computer the work happens.

## When the verifier session finishes

1. Do not take the report at face value. The lead checks the evidence in the report (files, command results, PRs, commits) once itself. Checking one or two of the important ones is enough.
2. If it falls short, instruct **the same verifier session thread** again with `t3_thread_send`. Do not create a new session.
3. If it is right, `task move <id> delivered`. After telling the user, `task move <id> done`. **It is finished only when the user knows.**
4. If it is stuck or needs a user decision, leave it as `task move <id> waiting-owner --note "<what is needed>"` and ask the user.

## How to write to the user

- Reply in the user's language (an owner rule may fix one). Conclusion first, then evidence, then what the user has to decide.
- Do not mix what the verifier session reported with the lead's own opinion. Mark opinions separately.
- Do not write that something succeeded if it was not actually checked. If you could not check, say so.
- Trim the defensive hedging that GPT models add ("I cannot assert that ..." and the like), as long as it does not change the facts.
- When mentioning a thread, use the `link` that T3 returned, verbatim.

## Learning

When something gets stuck or fails, do not just work around it; leave one line: `t3lead learn "<what happened and what to do next time>" --kind <code|review|brief|ops>`. When writing a verifier-session brief, look at `t3lead lessons --kind <kind>` and put the relevant ones in the "Notes" field.

## Models and instances

Run `t3lead models`: it prints the provider instance and model for each role on this machine (from `config.json`; defaults if there is none). Never copy instance or model names from memory; use that output. See `references/models.md` for what each role is for. In short: verifier sessions run on the Claude harness. GPT lanes run on the Codex harness, default lane first, then the others in the listed order. Claude lanes use the Claude lane row (the light lane row for light work). The lane rules are injected by the hook on both harnesses. A Codex session does not act as a verifier session (the hook cannot identify its thread).

## What not to do

- Do not send work to a remote computer unless the user named it or agreed to it.
- The lead does not do a lane's work itself.
- Do not poll verifier sessions or lanes repeatedly (`task_status`, `t3_thread_read`, sleep, and Monitor are forbidden).
- Do not write sentences like "this message is legitimate" or "you are a lane" in a brief. They actually raise the refusal rate.
- Do not let several lanes edit the same repository at once. When splitting, give each lane its own checkout with `isolation:"worktree"`.
