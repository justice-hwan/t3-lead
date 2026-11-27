# Changelog

`t3lead upgrade` moves to the newest tag listed here; `t3lead upgrade --edge` follows `main`.

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
