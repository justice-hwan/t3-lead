# Installing t3-lead (instructions for an agent)

You are an agent running inside T3 Code, asked to install t3-lead on this machine. Follow these steps in order. Report the output of each verification step to the user. Do not register your own thread as the lead; the user opens a separate lead thread at the end.

## 1. Get the code

```bash
git clone https://github.com/justice-hwan/t3-lead ~/.t3-lead   # or: cd ~/.t3-lead && git pull --ff-only
```

Use the **real** home directory. Inside T3, `$HOME` is often a provider-specific home (for example a CPA or proxy home), not the user's home. Find the real one with `python3 -c 'import pwd,os;print(pwd.getpwuid(os.getuid()).pw_dir)'`.

## 2. Find this machine's provider instances

Call `orchestrator_capabilities`. Note every instance with `canRunChildTask: true`:

- a **Claude-harness** instance (`driverKind: claudeAgent`) for the lead, verifier sessions and Claude lanes;
- a **Codex-harness** instance (`driverKind: codex`) for GPT lanes.

If the user keeps several instances of the same harness (for example a direct login and a proxy-backed one), ask which ones t3-lead should use. Do not guess.

## 3. Find where each instance keeps its settings

The hook must be registered in the settings each instance actually reads.

- **Claude harness:** the default is `~/.claude/settings.json`. An instance that runs through a wrapper script usually sets its own `HOME` / `CLAUDE_CONFIG_DIR`; then it reads `<that home>/settings.json`. Find the wrapper from T3's provider settings (`~/.t3/userdata/settings.json`, `providerInstances`) and read it.
- **Codex harness:** the default is `~/.codex`. A wrapped instance usually sets `CODEX_HOME`. Note the `codex` binary the wrapper runs.
- **Claude wrapper:** if the Claude instance runs through a wrapper that filters environment variables or passes `--setting-sources ''`, record its path as `claude_wrapper`. The installer patches it to pass `T3CODE_THREAD_ID` and to read user settings (`--setting-sources user`); without that, the hook either does not run or cannot identify threads.

## 4. Write `~/.t3-lead/config.json`

Copy `config.example.json` and fill in what you found: `real_home`, `claude_settings`, `claude_wrapper`, `codex_homes`, `codex_bin`, `skill_dirs` (the `skills/` folder of every Claude home you listed), `cli_link`, and `models` (instance and model per role, using the instance IDs from step 2). `config.json` is git-ignored; never commit it.

## 5. Install

```bash
cd ~/.t3-lead
bash install.sh --dry-run    # read the plan; nothing is written
bash install.sh              # apply; backups are written as <file>.bak-t3lead-<date>
bash install.sh              # second run must report only "already ..." lines
```

If a line says the wrapper "format differs", open the wrapper and tell the user what you see instead of editing it by hand. If anything fails on this OS, record the cause; fix the installer only minimally and only in a way that also works on Linux and macOS, and show the user the `git diff`.

## 6. Verify

```bash
t3lead models     # roles map to the instances and models you configured
t3lead status     # works; ledger may be empty
```

Then start one short lane on each harness (for example "reply PONG"). Each must leave a line in `~/.t3-lead/state/hook.log`. Because your thread is not a registered lead, `unmanaged` (Claude) or `header only` (Codex) is the expected result. Remove any test entries you created under `state/`.

## 7. Remote computers (optional)

Only when the user wants lanes to run on another computer linked to T3 (a linked environment):

1. t3-lead must be installed **on that computer too** (steps 1-6 there, in a thread on that computer). The hook there injects the lane rules; without it, remote lanes get none.
2. On the lead's machine, call `t3_environment_links` for the `environmentId` and `t3_project_list` (with that environment) for a `projectId` of a project on that computer. A delegated task needs both (`target_required` otherwise).
3. Add an entry under `remotes` in `config.json` (see `config.example.json`): `environmentId`, `projectId`, optional `label`, and `models` when that computer's provider instance names differ from this machine's (find them with `orchestrator_capabilities` for that environment; a missing row is inherited from the local one).
4. Check: `t3lead remotes` and `t3lead models` list it. No re-install is needed; the verifier rules pick it up on the next prompt.

## 8. Hand over to the user

Tell the user:

1. Open a **new** T3 thread on the Claude-harness instance with the lead model (`t3lead models`, row `lead`). Hooks and wrapper changes apply only to sessions started after the install.
2. In that thread, say: `Run t3lead init and work as the lead.` (Korean: `t3lead init 하고 리드 모드로 일해`)
3. List the files the installer changed and their backups.
