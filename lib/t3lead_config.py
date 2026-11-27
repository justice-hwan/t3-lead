#!/usr/bin/env python3
"""t3-lead configuration loader (shared by bin/t3lead, hooks/role.py and install.sh).

Machine-specific values (paths, T3 provider instance names, model names) live in one JSON file:
  $T3_LEAD_CONFIG if set, otherwise <repository>/config.json (untracked; copy config.example.json).
Every key is optional. Missing keys fall back to defaults based on the *real* home directory taken from
the passwd database (not $HOME, which differs inside wrapped sessions). A leading "~" in a configured path
means that real home.

CLI (used by install.sh):  t3lead_config.py shell | json
"""
import json, os, pwd, shlex, sys

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
    models = {}
    for k, d in DEFAULT_MODELS.items():
        if k == "gpt_lanes":
            v = m.get(k)
            if v is None:
                models[k] = [dict(i) for i in d]
            else:
                if not isinstance(v, list) or not v:
                    raise ConfigError("models.gpt_lanes must be a non-empty list")
                models[k] = [_pair(i, "models.gpt_lanes[%d]" % n) for n, i in enumerate(v)]
        else:
            models[k] = _pair(m[k], "models." + k) if k in m else dict(d)

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
        "models": models,
    }


def _fmt(x):
    return "`%s` / `%s`" % (x["instance"], x["model"])


def template_vars(cfg):
    """Values for {{placeholders}} in rules/*.md."""
    m = cfg["models"]
    lanes = m["gpt_lanes"]
    first = lanes[0]
    rest = [("`%s`" % i["model"]) if i["instance"] == first["instance"] else _fmt(i) for i in lanes[1:]]
    gpt = _fmt(first) + (", then " + ", ".join(rest) if rest else "")
    return {
        "lead": _fmt(m["lead"]),
        "verifier": _fmt(m["verifier"]),
        "gpt_lanes": gpt,
        "gpt_lane_refusal_prone": _fmt(m["gpt_lane_refusal_prone"]),
        "claude_lane": _fmt(m["claude_lane"]),
        "light_lane": _fmt(m["light_lane"]),
    }


def render(text, cfg):
    """Replace {{name}} placeholders; an unknown placeholder is left as written."""
    vars_ = template_vars(cfg)
    for k, v in vars_.items():
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
    else:
        print("usage: t3lead_config.py shell|json", file=sys.stderr); sys.exit(2)
