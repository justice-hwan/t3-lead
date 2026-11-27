#!/usr/bin/env python3
"""t3-lead configuration loader (shared by bin/t3lead, hooks/role.py and install.sh).

Machine-specific values (paths, T3 provider instance names, model names) live in one JSON file:
  $T3_LEAD_CONFIG if set, otherwise <repository>/config.json (untracked; copy config.example.json).
Every key is optional. Missing keys fall back to defaults based on the *real* home directory taken from
the passwd database (not $HOME, which differs inside wrapped sessions). A leading "~" in a configured path
means that real home.

Remote computers (T3 linked environments) go under "remotes", keyed by a short name:
  {"macbook": {"environmentId": "...", "projectId": "...", "label": "...", "models": {<same keys as models>}}}
environmentId and projectId are required per entry; label and every models key are optional (a missing model
row is inherited from the local models). No "remotes" key means no remote computers.

CLI (used by install.sh):  t3lead_config.py shell | json | check
"""
import json, os, pwd, re, shlex, sys

CODE_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

DEFAULT_MODELS = {
    "lead": {"instance": "claudeAgent", "model": "claude-opus-5-5"},
    "verifier": {"instance": "claudeAgent", "model": "claude-sonnet-5-5"},
    "gpt_lanes": [
        {"instance": "codex", "model": "gpt-6.1-terra"},
        {"instance": "codex", "model": "gpt-6.1-sol"},
        {"instance": "codex", "model": "gpt-6.2-astra"},
    ],
    "gpt_lane_refusal_prone": {"instance": "codex", "model": "gpt-6.2-sol"},
    "claude_lane": {"instance": "claudeAgent", "model": "claude-sonnet-5-5"},
    "light_lane": {"instance": "claudeAgent", "model": "claude-haiku-5-5"},
}


class ConfigError(Exception):
    pass


def passwd_home():
    return pwd.getpwuid(os.getuid()).pw_dir


def config_path():
    return os.environ.get("T3_LEAD_CONFIG") or os.path.join(CODE_DIR, "config.json")


def _pair(v, where):
    if not (isinstance(v, dict) and isinstance(v.get("instance"), str) and isinstance(v.get("model"), str)
            and v["instance"] and v["model"]):
        raise ConfigError('%s must be {"instance": "...", "model": "..."}' % where)
    return {"instance": v["instance"], "model": v["model"]}


MODEL_KEYS = list(DEFAULT_MODELS)


def _models(m, where, base):
    """Parse a models object; a missing key is taken from `base` (a parsed models dict)."""
    if not isinstance(m, dict):
        raise ConfigError("%s must be an object" % where)
    models = {}
    for k in MODEL_KEYS:
        if k == "gpt_lanes":
            v = m.get(k)
            if v is None:
                models[k] = [dict(i) for i in base[k]]
            else:
                if not isinstance(v, list) or not v:
                    raise ConfigError("%s.gpt_lanes must be a non-empty list" % where)
                models[k] = [_pair(i, "%s.gpt_lanes[%d]" % (where, n)) for n, i in enumerate(v)]
        else:
            models[k] = _pair(m[k], "%s.%s" % (where, k)) if k in m else dict(base[k])
    return models


def _remotes(raw, local_models):
    r = raw.get("remotes")
    if r is None:
        return {}
    if not isinstance(r, dict):
        raise ConfigError("remotes must be an object keyed by remote name")
    out = {}
    for name, v in r.items():
        w = "remotes.%s" % name
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", name):
            raise ConfigError("remote name %r must use only letters, digits, '.', '_' and '-'" % name)
        if not isinstance(v, dict):
            raise ConfigError("%s must be an object" % w)
        for k in ("environmentId", "projectId"):
            if not (isinstance(v.get(k), str) and v[k]):
                raise ConfigError("%s.%s must be a non-empty string" % (w, k))
        label = v.get("label")
        if label is not None and not isinstance(label, str):
            raise ConfigError("%s.label must be a string" % w)
        given = v.get("models") or {}
        out[name] = {
            "environmentId": v["environmentId"],
            "projectId": v["projectId"],
            "label": label or "",
            "models": _models(given, w + ".models", local_models),
            "own_models": sorted(k for k in given if k in MODEL_KEYS) if isinstance(given, dict) else [],
        }
    return out


def load(use_file=True):
    path = config_path()
    raw = {}
    found = use_file and os.path.isfile(path)
    if found:
        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception as e:
            raise ConfigError("cannot read %s: %s" % (path, e))
        if not isinstance(raw, dict):
            raise ConfigError("%s must contain a JSON object" % path)
    elif use_file and os.environ.get("T3_LEAD_CONFIG"):
        raise ConfigError("T3_LEAD_CONFIG points to a missing file: %s" % path)

    pw = passwd_home()
    real_home = pw
    if raw.get("real_home"):
        rh = raw["real_home"]
        real_home = os.path.normpath(pw + rh[1:] if rh == "~" or rh.startswith("~/") else rh)

    def p(x):
        if not isinstance(x, str) or not x:
            raise ConfigError("expected a non-empty path string, got %r" % (x,))
        if x == "~" or x.startswith("~/"):
            x = real_home + x[1:]
        return os.path.normpath(x)

    def plist(key, default):
        v = raw.get(key)
        if v is None:
            return [default]
        if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
            raise ConfigError("%s must be a list of path strings" % key)
        return [p(i) for i in v]

    configured_home = p(raw["home"]) if raw.get("home") else os.path.join(real_home, ".t3-lead")
    env_home = os.environ.get("T3_LEAD_HOME")
    home = p(env_home) if env_home else configured_home

    m = raw.get("models") or {}
    if not isinstance(m, dict):
        raise ConfigError("models must be an object")
    models = _models(m, "models", DEFAULT_MODELS)
    remotes = _remotes(raw, models)

    hg = raw.get("heavy_groups") or {}
    if not isinstance(hg, dict) or not all(re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", k) and isinstance(v, int)
                                           and not isinstance(v, bool) and v >= 1 for k, v in hg.items()):
        raise ConfigError("heavy_groups must map group names (letters, digits, . _ -) to slot counts >= 1")
    for k in ("heavy_max_load", "heavy_wait_alert_min"):
        v = raw.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
            raise ConfigError("%s must be a positive number" % k)
    sr = raw.get("state_remote")
    if sr is not None and not isinstance(sr, str):
        raise ConfigError("state_remote must be a git URL string")
    wrapper = raw.get("claude_wrapper")
    codex_bin = raw.get("codex_bin")
    return {
        "config_path": path,
        "config_found": found,
        "real_home": real_home,
        "home": home,
        "configured_home": configured_home,
        "claude_settings": plist("claude_settings", os.path.join(real_home, ".claude", "settings.json")),
        "claude_wrapper": p(wrapper) if wrapper else None,
        "codex_homes": plist("codex_homes", os.path.join(real_home, ".codex")),
        "codex_bin": p(codex_bin) if codex_bin else None,
        "skill_dirs": plist("skill_dirs", os.path.join(real_home, ".claude", "skills")),
        "cli_link": p(raw["cli_link"]) if raw.get("cli_link") else os.path.join(real_home, ".local", "bin", "t3lead"),
        "state_remote": raw.get("state_remote") or None,
        "heavy_max_load": raw.get("heavy_max_load"),
        "heavy_wait_alert_min": raw.get("heavy_wait_alert_min", 10),
        "owner_rules_dir": p(raw["owner_rules_dir"]) if raw.get("owner_rules_dir") else None,
        "t3_settings": p(raw["t3_settings"]) if raw.get("t3_settings") else os.path.join(real_home, ".t3", "userdata", "settings.json"),
        "models": models,
        "remotes": remotes,
        "heavy_groups": dict(hg),
    }


def check_instance_homes(cfg):
    """Compare the homes of the T3 provider instances named in the local models rows with claude_settings /
    codex_homes. Returns (notes, warnings). A wrapped instance (a CPA or proxy instance) usually has its own
    home; if that home is missing from config.json the hook is never installed there and its sessions get no
    role rules."""
    notes, warns = [], []
    path = cfg["t3_settings"]
    try:
        with open(path) as f:
            insts = json.load(f).get("providerInstances") or {}
    except FileNotFoundError:
        return ["T3 settings not found (%s); instance homes not checked (set t3_settings in config.json)" % path], []
    except Exception as e:
        return ["cannot read T3 settings %s: %s; instance homes not checked" % (path, e)], []
    m = cfg["models"]
    used = [m["lead"], m["verifier"], *m["gpt_lanes"], m["gpt_lane_refusal_prone"], m["claude_lane"], m["light_lane"]]
    claude = {os.path.realpath(x) for x in cfg["claude_settings"]}
    codex = {os.path.realpath(x) for x in cfg["codex_homes"]}
    seen = set()
    for row in used:
        name = row["instance"]
        if name in seen:
            continue
        seen.add(name)
        inst = insts.get(name)
        if inst is None:
            # built-in instances (claudeAgent / codex) may have no entry; they use the default homes
            driver, home = name, None
            if name not in ("claudeAgent", "codex"):
                warns.append("instance %r (in models) is not in T3 settings %s; check the instance ID" % (name, path))
                continue
        else:
            driver = inst.get("driver")
            home = (inst.get("config") or {}).get("homePath") or None
            if inst.get("enabled") is False:
                warns.append("instance %r (in models) is disabled in T3 settings" % name)
        if driver == "claudeAgent":
            want = os.path.join(home or os.path.join(cfg["real_home"], ".claude"), "settings.json")
            if os.path.realpath(want) not in claude:
                warns.append('instance %r reads %s, which is not in claude_settings; add it to config.json and re-run '
                             'install.sh, or its sessions get no role rules' % (name, want))
            else:
                notes.append("instance %r: claude settings %s covered" % (name, want))
        elif driver == "codex":
            want = home or os.path.join(cfg["real_home"], ".codex")
            if os.path.realpath(want) not in codex:
                warns.append('instance %r uses CODEX_HOME %s, which is not in codex_homes; add it to config.json and '
                             're-run install.sh, or its sessions get no role rules' % (name, want))
            else:
                notes.append("instance %r: codex home %s covered" % (name, want))
        else:
            notes.append("instance %r: driver %r not checked" % (name, driver))
    return notes, warns


def read_rule_file(path):
    """Rules stored one per line as `- <rule>`; blank lines ignored. Missing file: no rules."""
    try:
        with open(path) as f:
            return [l[2:].strip() if l.startswith("- ") else l.strip() for l in f if l.strip()]
    except OSError:
        return []


def owner_rule_sets(cfg):
    """[(label, prefix, path, rules)]: shared rules (owner_rules_dir/rules.md) first, then this computer's."""
    out = []
    if cfg.get("owner_rules_dir"):
        p = os.path.join(cfg["owner_rules_dir"], "rules.md")
        out.append(("shared (all computers)", "S", p, read_rule_file(p)))
    p = os.path.join(cfg["home"], "state", "owner-rules.md")
    out.append(("this computer only", "L", p, read_rule_file(p)))
    return out


def _fmt(x):
    return "`%s` / `%s`" % (x["instance"], x["model"])


def _gpt_text(lanes):
    first = lanes[0]
    rest = [("`%s`" % i["model"]) if i["instance"] == first["instance"] else _fmt(i) for i in lanes[1:]]
    return _fmt(first) + (", then " + ", ".join(rest) if rest else "")


def remote_list(cfg):
    """One bullet per configured remote computer, for the {{remote_list}} placeholder in rules/verifier.md."""
    lines = []
    for name, r in cfg.get("remotes", {}).items():
        m = r["models"]
        lines.append("- `%s`%s: `target.environmentId` `%s`, `target.projectId` `%s`; GPT lanes %s; "
                     "GPT lane (refusal-prone) %s; Claude lane %s; light lane %s" % (
                         name, " (%s)" % r["label"] if r["label"] else "", r["environmentId"], r["projectId"],
                         _gpt_text(m["gpt_lanes"]), _fmt(m["gpt_lane_refusal_prone"]),
                         _fmt(m["claude_lane"]), _fmt(m["light_lane"])))
    return "\n".join(lines)


def template_vars(cfg):
    """Values for {{placeholders}} in rules/*.md."""
    m = cfg["models"]
    return {
        "lead": _fmt(m["lead"]),
        "verifier": _fmt(m["verifier"]),
        "gpt_lanes": _gpt_text(m["gpt_lanes"]),
        "gpt_lane_refusal_prone": _fmt(m["gpt_lane_refusal_prone"]),
        "claude_lane": _fmt(m["claude_lane"]),
        "light_lane": _fmt(m["light_lane"]),
        "remote_list": remote_list(cfg),
        "t3lead": cfg["cli_link"],
        "heavy_list": ", ".join("`%s` (%d slot%s)" % (g, n, "" if n == 1 else "s")
                                for g, n in sorted(cfg.get("heavy_groups", {}).items())),
    }


def render(text, cfg):
    """Replace {{name}} placeholders; an unknown placeholder is left as written.
    A {{#remotes}}...{{/remotes}} block is kept (markers removed) only when remotes are configured, and a
    {{#heavy}}...{{/heavy}} block only when heavy_groups is."""
    for block, on in (("remotes", bool(cfg.get("remotes"))), ("heavy", bool(cfg.get("heavy_groups")))):
        if on:
            text = text.replace("{{#%s}}" % block, "").replace("{{/%s}}\n" % block, "").replace("{{/%s}}" % block, "")
        else:
            text = re.sub(r"\{\{#%s\}\}.*?\{\{/%s\}\}\n?" % (block, block), "", text, flags=re.S)
    for k, v in template_vars(cfg).items():
        text = text.replace("{{%s}}" % k, v)
    return text


def hook_command(cfg):
    root = cfg["home"]
    return "T3_LEAD_HOME=%s python3 %s" % (shlex.quote(root), shlex.quote(os.path.join(root, "hooks", "role.py")))


def _shell(cfg):
    out = []
    sc = lambda k, v: out.append("%s=%s" % (k, shlex.quote(v or "")))
    ar = lambda k, v: out.append("%s=(%s)" % (k, " ".join(shlex.quote(i) for i in v)))
    sc("REAL_HOME", cfg["real_home"]); sc("ROOT", cfg["home"]); sc("CONFIGURED_HOME", cfg["configured_home"])
    sc("CONFIG_PATH", cfg["config_path"]); sc("CONFIG_FOUND", "1" if cfg["config_found"] else "0")
    sc("CLAUDE_WRAPPER", cfg["claude_wrapper"]); sc("CODEX_BIN", cfg["codex_bin"]); sc("CLI_LINK", cfg["cli_link"])
    sc("HOOK_CMD", hook_command(cfg))
    ar("CLAUDE_SETTINGS", cfg["claude_settings"]); ar("CODEX_HOMES", cfg["codex_homes"]); ar("SKILL_DIRS", cfg["skill_dirs"])
    return "\n".join(out)


if __name__ == "__main__":
    try:
        cfg = load()
    except ConfigError as e:
        print("t3lead config error: %s" % e, file=sys.stderr); sys.exit(2)
    mode = sys.argv[1] if len(sys.argv) > 1 else "json"
    if mode == "shell":
        print(_shell(cfg))
    elif mode == "json":
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    elif mode == "check":
        notes, warns = check_instance_homes(cfg)
        for n in notes: print("  " + n)
        for w in warns: print("  WARNING: " + w)
    else:
        print("usage: t3lead_config.py shell|json|check", file=sys.stderr); sys.exit(2)
