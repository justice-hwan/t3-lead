# Changelog

`t3lead upgrade` moves to the newest tag listed here; `t3lead upgrade --edge` follows `main`.

## v0.3.0 — 2026-11-27

- State backup: `state_remote` (a private git repository) and `t3lead backup [--init|--status]`; every ledger, lesson and local-rule change is committed and pushed in the background. `t3lead status` warns when the backup is behind.
- Heavy queues: `heavy_max_load` holds the head of the queue while the computer is busy; waits longer than `heavy_wait_alert_min` are recorded in `state/heavy/events.jsonl` and listed by `t3lead status`.
- Heavy-resource queues: `t3lead heavy --group G -- <command>` runs a command when a slot in group G (`heavy_groups` in config.json) is free, first come first served across all sessions on the computer; dead callers free their slot. Lane rule 7 (injected only when groups are configured) tells lanes to use it; `t3lead heavy status` shows holders and waiters.

## v0.2.0 — 2026-11-27

- Owner rules: `t3lead rule add [--shared]|list|rm|sync`. Shared rules live in a private repository cloned at `owner_rules_dir` (committed and pushed on change); rules for one computer live in `state/owner-rules.md`. The hook appends both to every verifier and lane prompt; the lead syncs and reads them at start.
- The lead skill no longer carries a user-specific reply language; that is an owner rule now.
- Failed-run restarts: verifier rule 7 restarts a lane whose turn failed or stopped (same thread, then 3- and 10-minute alarms, then the next model); the lead does the same for a failed verifier. Tested: a lane killed mid-run reported `failed` within 2 s and finished after one restart. Remote-lane rule is now rule 8.

## v0.1.0 — 2026-11-27

First release.

- Lead → verifier → lanes on T3 Code: lead skill (`skill/SKILL.md`), role hook (`hooks/role.py`) that injects verifier and lane rules on the Claude and Codex harnesses.
- `t3lead` CLI: lead registration, request ledger, lessons, status, models, remotes, version, upgrade.
- Machine-specific values in `config.json` (paths, provider instances, models); idempotent `install.sh` with `--dry-run`, backups, and a guard against trial runs touching global files.
- Deadline alarms for verifiers and backup alarms for the lead (`schedule_task`), so lost completion notifications and stalled sessions are caught.
- Remote computers (T3 linked environments) as lane hosts, identified by a `t3-lead-ref` line; lane-only install for computers that only host lanes.
- `install.sh` warns when a provider instance used in `models` keeps its settings in a home missing from `claude_settings` / `codex_homes`.
- Release tags: `t3lead upgrade` follows the latest `vX.Y.Z` tag, `--edge` follows `main`.
- Verified on Linux and macOS (Mac Studio → MacBook remote lanes on both harnesses).
