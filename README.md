**English** | [한국어](README.ko.md)

# t3-lead

Hierarchical orchestration for T3 Code: a **lead** session talks to the user, hands each request to a **verifier** session, and the verifier fans the work out to parallel **lanes** and checks their results before reporting back.

```
user ─ lead              (the thread you talk to; Claude harness)
         └─ verifier     (one per request; Claude harness)
               └─ lane × N   (parallel; Codex or Claude harness)
```

The behavior rules for each role are not written into briefs. A `UserPromptSubmit` hook works out a thread's role from T3 metadata and injects the matching rules, so the lead never has to include rules or identity claims in a brief.

## Quick start: let your agent install it

Paste this into any T3 Code thread on the machine (a Claude- or Codex-harness session with shell access):

```text
Install t3-lead on this machine. Follow https://github.com/justice-hwan/t3-lead/blob/main/docs/agent-install.md step by step, show me the verification output, and do not register this thread as the lead.
```

When it is done, open a **new** thread on the lead instance and model the agent reports, and say:

```text
Run t3lead init and work as the lead.
```

From then on, give that thread your requests. For manual setup, see [Configuration](#configuration) and [Install](#install).

## Upgrading

Tell the lead thread (or any T3 thread on that machine):

```text
Run t3lead upgrade, show me the output, then re-read the t3-lead skill.
```

`t3lead upgrade` fast-forwards the checkout to the latest `origin/main` and re-runs `install.sh`. It refuses to run if tracked files have local changes. `t3lead upgrade --check` only lists the new commits, and `t3lead version` shows the installed commit. Verifier and lane rules take effect from the next prompt; hook or wrapper changes apply to sessions started after the upgrade.

## Layout

```
install.sh                 idempotent installer / re-apply script (--dry-run supported)
config.example.json        template for config.json (machine-specific values; config.json is not tracked)
lib/t3lead_config.py       config loader shared by install.sh, bin/t3lead and hooks/role.py
bin/t3lead                 state CLI (requests ledger, lessons, lead registration)
hooks/role.py              role-detection hook (UserPromptSubmit), including remote lanes
rules/verifier.md          rules injected into verifier sessions ({{placeholders}} filled from the config)
rules/lane.md              rules injected into lanes
skill/SKILL.md             lead skill, linked as <skill_dir>/t3-lead
docs/agent-install.md      step-by-step install guide written for an agent
skill/references/          brief formats (briefs.md), models and instances (models.md)
state/                     runtime data (not tracked): tasks/, roles/, lessons.jsonl, hook.log
```

## How the role hook works

On every prompt, `hooks/role.py` receives the hook event on stdin and decides the thread's role.

- **Thread ID** comes from the `T3CODE_THREAD_ID` environment variable (Claude harness).
- **Parent** comes from the header T3 puts at the very start of a message sent by another agent: `[T3 Code: the agent in T3 thread "<parent>" sent this message, not the user.]`
- **Role** is derived from the parent's role: the lead is registered explicitly (`t3lead init`); a child of the lead is a `verifier`, a child of a verifier is a `lane`, and a child of a lane is a `lane`. If the parent is not registered, the thread is `unmanaged` and the hook outputs nothing and exits 0.
- The role is decided once, on the thread's first prompt, saved under `state/roles/`, and the same rules are injected on every later prompt. Each decision is appended to `state/hook.log`.
- For `verifier` and `lane`, the hook prints `rules/verifier.md` / `rules/lane.md` as `additionalContext`.

**Remote lanes.** A lane delegated to another computer (a T3 linked environment) has no parent thread ID in its header: the message starts with `[T3 Code: this message came through T3 Code's tools, not from the user typing in this chat.]`. So the verifier puts a reference line near the top of every message it sends such a lane (first line of the body):

```
t3-lead-ref: lane <request-id>
```

The hook treats a prompt as a lane only when **both** are true: it starts with that remote header, and the reference line is among its first three non-blank lines after it. The header alone decides nothing (no output), and neither does the reference line alone (a user could type it). On the Claude harness the lane role is recorded on the first such message and kept for the thread afterwards; on the Codex harness (no thread ID) every message is checked for the pair. A remote lane's own children follow the usual rule (a child of a lane is a lane). The line is deliberately a plain `key: value` reference, not a sentence about who the lane is: identity claims in a message raise the refusal rate. t3-lead must be installed on the remote computer for this to have any effect.

**Codex harness.** The Codex app-server runs several threads in one process, so `T3CODE_THREAD_ID` is not available. In that case the hook records nothing and decides on every prompt from the message header alone (the sending thread). That is enough for lanes. A Codex session never acts as a verifier (without a thread ID its children could not find it), so for such a session the hook injects nothing when the role would be `verifier`.

## Configuration

Machine-specific values (paths, T3 provider instance names, model names) live in one file, `config.json`, which is not tracked. Copy the template and edit it:

```bash
cp config.example.json config.json
$EDITOR config.json
./install.sh --dry-run     # see what would change, writes nothing
./install.sh
```

Every key is optional. A leading `~` in a path means the **real** home directory, read from the passwd database rather than `$HOME` (which can differ inside wrapped sessions that set their own `HOME`). `config.json` is looked up next to the code; set `T3_LEAD_CONFIG` to use another file.

| Key | Default | Meaning |
|---|---|---|
| `real_home` | passwd home of the current user | the real home, base for `~` and for the defaults below |
| `home` | `~/.t3-lead` | where the repository is cloned and `state/` lives (`T3_LEAD_HOME` overrides it) |
| `claude_settings` | `["~/.claude/settings.json"]` | Claude `settings.json` files that get the hook |
| `claude_wrapper` | none | optional Claude wrapper script to patch (see Install) |
| `codex_homes` | `["~/.codex"]` | Codex homes (`CODEX_HOME`) that get the hook |
| `codex_bin` | `codex` found on `~/.local/bin` or `PATH` | Codex binary used to read the hook trust hash |
| `skill_dirs` | `["~/.claude/skills"]` | skill folders; `t3-lead` is linked into each |
| `cli_link` | `~/.local/bin/t3lead` | where the CLI symlink goes |
| `models` | see below | provider instance and model per role |
| `remotes` | none | other computers (T3 linked environments) that lanes can run on; see below |

`models` holds `{"instance": "...", "model": "..."}` for `lead`, `verifier`, `claude_lane`, `light_lane` and `gpt_lane_refusal_prone`, plus `gpt_lanes`, an ordered list of such pairs (first is the default GPT lane). The defaults, used when a key is missing, are the values in `config.example.json`: `claudeAgent` and `codex` instances with the model names listed in that file. Replace the instance names with whatever your T3 setup calls its Claude and Codex provider instances.

`remotes` maps a short name to a computer: `{"macbook": {"environmentId": "...", "projectId": "...", "label": "...", "models": {...}}}`. `environmentId` and `projectId` are required (T3 refuses a delegated task to another environment without a project: `target_required`); `label` is optional; `models` takes the same keys as the top-level `models`, and any key it omits is inherited from the local value (only correct when the instance names match, so set them when they differ). Get the IDs from `t3_environment_links` and `t3_project_list`. With no `remotes`, the remote paragraph is left out of the verifier rules entirely. `t3lead remotes` lists them and `t3lead models` adds a block per remote.

How the values are used: `rules/verifier.md` contains `{{placeholders}}` (`{{gpt_lanes}}`, `{{claude_lane}}`, `{{light_lane}}`) that `hooks/role.py` fills in from the config each time it injects the rules, so a config change applies on the next prompt with no re-install. The remote paragraph (rule 7) sits between `{{#remotes}}` and `{{/remotes}}` and is injected only when `remotes` is set; `{{remote_list}}` expands to one line per remote with its IDs and models. The lead skill does not hard-code names either: it tells the lead to run `t3lead models`.

## Install

```bash
./install.sh
```

The script is safe to run repeatedly; run it again after re-running any setup that rewrites your Claude or Codex settings. It reads every target from `config.json` (see Configuration). `T3_LEAD_CODEX_BIN` is no longer read; use `codex_bin`.

- `./install.sh --dry-run` prints what each step would do and writes nothing.
- If `T3_LEAD_HOME` is set to something other than the configured `home` (for example a temp folder for a trial run), the script does **not** touch user-global files (Claude/Codex hooks, skill links, CLI link); it only creates `state/` under that folder. Add `--allow-custom-home` to apply the global changes anyway. This keeps a trial run from pointing your real links at a folder that is later deleted.

What it changes (each step reports "already ..." and does nothing if already applied):

1. **Claude hook**: adds a `UserPromptSubmit` command hook (timeout 10 s) to each file in `claude_settings`.
2. **Claude wrapper** (only if `claude_wrapper` is set, e.g. a wrapper script that launches Claude with a restricted environment): passes `T3CODE_THREAD_ID` through the environment allow-list and changes `--setting-sources` from `''` to `user`, so the user-level hook is loaded.
3. **Codex hook**, for each directory in `codex_homes`: adds the hook to `hooks.json`, sets `[features] hooks = true` in `config.toml`, and registers the hook's trust hash (read through `codex app-server` `hooks/list`) in `config.toml`.
4. **Links and directories**: `<skill_dir>/t3-lead` → `skill/` for each `skill_dirs` entry, `cli_link` → `bin/t3lead`, and creates `state/roles/` and `state/tasks/`.

**Backups.** Before the first modification of `settings.json`, `hooks.json` or `config.toml`, the script copies it to `<file>.bak-t3lead-YYYYMMDD` (once per file per day, never overwriting an existing backup). The `claude-wrapper` patch is written in place without a backup.

## `t3lead` CLI

```
t3lead init                                 register this thread (T3CODE_THREAD_ID) as the lead
t3lead task add "<request>" [--source S] [--where R]   record a request, print its ID (t-xxxx)
t3lead task move <id> <state> [--note N] [--verifier THREAD] [--where R]
        states: open working waiting-owner delivered done dropped
        --where: remote computer that runs the lanes (a name from `t3lead remotes`; `-` clears it)
t3lead task list [--all]                    unfinished requests (default) / all
t3lead task show <id>                       full JSON of one request
t3lead learn "<one-line lesson>" [--kind K] append a lesson (default kind: general)
t3lead lessons [--kind K]                   list lessons (a kind also includes general)
t3lead status                               short summary to read after a restart
t3lead models                               provider instance and model per role, from the config (plus one block per remote)
t3lead remotes                              remote computers from the config
```

`open`, `working`, `waiting-owner` and `delivered` count as unfinished. A request is finished only when the user has been told (`delivered` → `done`). Requests are stored as `state/tasks/<id>.json`, lessons as lines in `state/lessons.jsonl`.

A request with `--where` shows `@<name>` in `task list` and `status`; `task show` includes `"where"`. Older request files without it keep working. An unknown name is accepted with a warning.

Typical lead flow: `t3lead init` once → `task add` → delegate to a verifier → `task move <id> working --verifier <thread>` → after the report is verified, `task move <id> delivered` → tell the user → `task move <id> done`.

## Models and instances

Each role's provider instance and model come from `models` in `config.json` (see Configuration); `t3lead models` prints what is in effect. The roles are the lead, the verifier (must be the Claude harness), GPT lanes (default first, then fallbacks in order), a Claude lane, and a light lane. The shipped defaults in `config.example.json` use Claude Opus for the lead and Claude Sonnet for verifiers and Claude lanes. A lead brief may override the instance and model. See `skill/references/models.md` for what each role is for, the measurements behind these choices (hook-injected rules vs rules in the brief) and the effort guidance.

## Remote computers

To run lanes on another computer linked to T3 Code: install t3-lead there too (its hook injects the lane rules), add the computer under `remotes` on the lead's machine, and tell the lead which one to use. The lead uses a remote only when you name it or agree to it (for example when local resources run short, it asks first). It writes `where: <name>` in the verifier brief; the verifier creates the lane with that remote's `environmentId`, `projectId` and models, starts every message to it with the `t3-lead-ref` line, and allows extra time before the deadline alarm. Completion notifications come back as for local lanes. See `docs/agent-install.md` step 7.

## Known limitations

- **One config per checkout.** `home` is also where the hook command registered in your Claude/Codex settings points. If you move the checkout, change `home` and re-run `install.sh`; an existing hook entry with the old path is reported as "command differs from config" and has to be edited by hand (a changed command also needs its Codex trust hash re-registered).
- **The Claude wrapper patch is string-based.** It only recognizes the exact snippets it was written for; if your wrapper looks different, the script says so and you apply the two changes by hand.
- **Instance and model names are not validated.** A wrong name in `config.json` shows up only when a lane is created.
- **Remote lanes need t3-lead on the remote computer.** The lane rules are injected by the hook there. Without it the lane gets no rules, and a remote message whose first lines lack the reference line is not recognized as a lane.
- **Codex sessions do not act as verifiers.** They cannot identify their own thread, so they work only as lanes.
- **No redelivery of lost completion notifications.** The lead is woken by a completion notification; if one is lost, nothing re-sends it. After a restart, `t3lead status` is the way to find requests still marked `working`.
