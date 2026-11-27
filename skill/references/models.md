# Models and instances

The instance and model for each role are machine-specific and come from `config.json` (see `config.example.json`).
Run `t3lead models` to print them; use that output, not remembered names. The roles:

| Role | What it is for | Notes |
|---|---|---|
| Lead | user conversation, judgment | |
| Verifier session | creates lanes and verifies their results | must be the Claude harness (parallel lane creation; the hook identifies the thread) |
| GPT lane #1 (default) | general lane work | needs hook injection (install script) |
| GPT lane #2, #3, ... | fallbacks, in the listed order | |
| GPT lane (refusal-prone) | work the default lane tends to refuse | 21/32 refusals without the hook, 0/8 with it |
| Claude lane | lane work on the Claude harness | |
| Light lane | small or cheap tasks | |

- Putting the lane rules in the brief increases refusals (5/16 → 11/16); injecting them with the hook eliminates them (Claude harness 0/8, Codex harness 0/8).
- If a Codex-harness session is used as the verifier session, it creates lanes one at a time at 6–9 second intervals, so they do not run in parallel.
- Effort: start from the lowest. Reading, research, and small edits use low; operational changes use medium; new features use high. Never use max.
- Remote computers (`remotes` in `config.json`) carry their own copies of the lane rows. A row a remote does not set is inherited from the local one, which is only right when the instance names match; `t3lead models` marks inherited rows "(same as local)".
