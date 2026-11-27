#!/usr/bin/env bash
# t3-lead install / re-apply (safe to run repeatedly). Run it again after re-running any setup that rewrites
# your Claude / Codex settings.
#
#   ./install.sh [--dry-run] [--allow-custom-home]
#     --dry-run            print what would change, write nothing
#     --allow-custom-home  needed to touch user-global files (Claude/Codex hooks, skill links, CLI link) when
#                          T3_LEAD_HOME differs from the configured home; without it only the state
#                          directories under T3_LEAD_HOME are created (safe for trial runs in a temp folder)
#
# All machine-specific values come from config.json (see config.example.json); every key is optional.
set -euo pipefail
DRY=0; ALLOW_CUSTOM=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --allow-custom-home) ALLOW_CUSTOM=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done
export DRY
SCRIPT_DIR=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
eval "$(python3 "$SCRIPT_DIR/lib/t3lead_config.py" shell)"   # REAL_HOME ROOT CONFIGURED_HOME CLAUDE_* CODEX_* SKILL_DIRS CLI_LINK HOOK_CMD
[ -d "$REAL_HOME" ] || { echo "real home not found: $REAL_HOME" >&2; exit 1; }
if [ -z "$CODEX_BIN" ]; then CODEX_BIN=$(PATH="$REAL_HOME/.local/bin:$PATH" command -v codex || true); fi
export STAMP=$(date +%Y%m%d)
[ "$DRY" = 1 ] && echo "== dry run: nothing will be written =="
if [ "$CONFIG_FOUND" = 1 ]; then echo "config: $CONFIG_PATH"; else echo "config: none ($CONFIG_PATH not found), using defaults"; fi
echo "T3_LEAD_HOME: $ROOT"

echo "instance homes (models rows vs claude_settings / codex_homes):"
python3 "$SCRIPT_DIR/lib/t3lead_config.py" check

GLOBAL=1
# portable path comparison (BSD realpath on macOS has no -m): python's realpath tolerates missing paths
canon() { python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }
if [ "$(canon "$ROOT")" != "$(canon "$CONFIGURED_HOME")" ] && [ "$ALLOW_CUSTOM" != 1 ]; then
  GLOBAL=0
  echo "T3_LEAD_HOME ($ROOT) differs from the configured home ($CONFIGURED_HOME):"
  echo "  user-global files (Claude/Codex hooks, skill links, CLI link) are left untouched."
  echo "  Pass --allow-custom-home to apply them anyway."
fi

if [ "$GLOBAL" = 1 ]; then
[ -f "$ROOT/hooks/role.py" ] || { echo "$ROOT/hooks/role.py not found: clone the repository to $ROOT or set \"home\" in config.json" >&2; exit 1; }

# --- 1. Claude hook ---
python3 - "$HOOK_CMD" ${CLAUDE_SETTINGS[@]+"${CLAUDE_SETTINGS[@]}"} <<'PY'
import json, os, shutil, sys
cmd, *paths = sys.argv[1:]
dry = os.environ.get("DRY") == "1"
def is_ours(c): return "hooks/role.py" in c and "T3_LEAD_HOME" in c
for p in paths:
    if not os.path.isdir(os.path.dirname(p)): print("skipped (directory missing):", p); continue
    d = json.load(open(p)) if os.path.exists(p) else {}
    u = d.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    ours = [h.get("command", "") for m in u for h in m.get("hooks", []) if is_ours(h.get("command", ""))]
    if ours:
        print("hook already present:", p + ("" if cmd in ours else " (command differs from config; update by hand)"))
    elif dry:
        print("hook would be added:", p)
    else:
        u.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
        if os.path.exists(p):
            bak = "%s.bak-t3lead-%s" % (p, os.environ["STAMP"])
            if not os.path.exists(bak): shutil.copy2(p, bak)
        json.dump(d, open(p, "w"), indent=2, ensure_ascii=False); print("hook added:", p)
PY

# --- 2. Claude wrapper (optional, only when claude_wrapper is set in config.json) ---
if [ -z "$CLAUDE_WRAPPER" ]; then
  echo "Claude wrapper: not configured, skipping"
elif [ ! -f "$CLAUDE_WRAPPER" ]; then
  echo "Claude wrapper: skipped (file missing): $CLAUDE_WRAPPER"
else
python3 - "$CLAUDE_WRAPPER" <<'PY'
import os, re, sys
p = sys.argv[1]; s = open(p).read(); o = s
s = s.replace("('PATH','TERM','LANG','LC_ALL','TMPDIR')", "('PATH','TERM','LANG','LC_ALL','TMPDIR','T3CODE_THREAD_ID')")
# tolerate spacing and the variable name (a+=[...] / args += [...])
s = re.sub(r"(\w+\s*\+=\s*\[\s*'--setting-sources'\s*,\s*)''(\s*\])", r"\1'user'\2", s)
if s == o and "'T3CODE_THREAD_ID'" in s and re.search(r"'--setting-sources'\s*,\s*'user'", s): print("Claude wrapper already patched:", p)
elif s == o: print("Claude wrapper: format differs from the expected snippets (check manually):", p)
elif os.environ.get("DRY") == "1": print("wrapper would be patched:", p)
else: open(p, "w").write(s); print("wrapper patched:", p)
PY
fi

# --- 3. Codex hook: register in hooks.json + features.hooks + trust hash via hooks/list ---
python3 - "$HOOK_CMD" "$CODEX_BIN" "$REAL_HOME" ${CODEX_HOMES[@]+"${CODEX_HOMES[@]}"} <<'PY'
import json, os, re, shutil, subprocess, sys
cmd, codex_bin, real_home, *homes = sys.argv[1:]
stamp = os.environ["STAMP"]
DRY = os.environ.get("DRY") == "1"

def is_ours(c): return "hooks/role.py" in c and "T3_LEAD_HOME" in c

def backup(p):
    if os.path.exists(p):
        bak = "%s.bak-t3lead-%s" % (p, stamp)
        if not os.path.exists(bak): shutil.copy2(p, bak)

def write_atomic(p, text):
    backup(p)
    mode = os.stat(p).st_mode & 0o777 if os.path.exists(p) else 0o600
    tmp = p + ".t3lead-tmp"
    with open(tmp, "w") as f: f.write(text)
    os.chmod(tmp, mode); os.replace(tmp, p)

def ensure_hook(home):
    p = os.path.join(home, "hooks.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    u = d.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    ours = [h.get("command", "") for m in u for h in m.get("hooks", []) if is_ours(h.get("command", ""))]
    if ours:
        print("  hooks.json: hook already present" + ("" if cmd in ours else " (command differs from config; update by hand)")); return True
    if DRY: print("  hooks.json: would add the hook"); return False
    u.append({"hooks": [{"type": "command", "command": cmd, "timeout": 10}]})
    write_atomic(p, json.dumps(d, indent=2, ensure_ascii=False) + "\n"); print("  hooks.json: hook added"); return True

def ensure_feature(text):
    """Ensure [features] hooks = true. Returns (new text, changed?)."""
    lines = text.split("\n"); out = []; i = 0; in_feat = False; found = False; done = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            if in_feat and not done:   # end of [features]: there was no hooks line
                out.append("hooks = true"); done = True
            in_feat = (s == "[features]"); found = found or in_feat
        elif in_feat and re.match(r"hooks\s*=", s):
            done = True
            if s.replace(" ", "") != "hooks=true": ln = "hooks = true"
        out.append(ln)
    new = "\n".join(out)
    if in_feat and not done: new = new.rstrip("\n") + "\nhooks = true\n"
    if not found: new = new.rstrip("\n") + "\n\n[features]\nhooks = true\n"
    return new, new != text

def hooks_list(home):
    env = {k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID",)}
    env.update(CODEX_HOME=home, HOME=real_home)
    pr = subprocess.Popen([codex_bin, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, text=True)
    def send(o): pr.stdin.write(json.dumps(o) + "\n"); pr.stdin.flush()
    def recv(i):
        while True:
            l = pr.stdout.readline()
            if not l: raise RuntimeError("app-server exited without responding")
            m = json.loads(l)
            if m.get("id") == i: return m
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "t3lead-install", "version": "0"}}})
        recv(1); send({"method": "initialized"})
        send({"id": 2, "method": "hooks/list", "params": {"cwds": [real_home]}})
        r = recv(2)
        if "error" in r: raise RuntimeError(r["error"])
        return [h for e in r["result"]["data"] for h in e["hooks"]]
    finally:
        pr.terminate()
        try: pr.wait(5)
        except Exception: pr.kill()

def set_trust(text, key, hash_):
    head = '[hooks.state."%s"]' % key
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln.strip() == head:
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("["): j += 1
            body = lines[i + 1:j]
            en = [k for k, b in enumerate(body) if re.match(r"enabled\s*=", b.strip())]
            th = [k for k, b in enumerate(body) if re.match(r"trusted_hash\s*=", b.strip())]
            nb = list(body)
            if en: nb[en[0]] = "enabled = true"
            else: nb.insert(0, "enabled = true"); th = [k + 1 for k in th]
            if th: nb[th[0]] = 'trusted_hash = "%s"' % hash_
            else: nb.insert(1, 'trusted_hash = "%s"' % hash_)
            new = "\n".join(lines[:i + 1] + nb + lines[j:])
            return new, new != text
    new = text.rstrip("\n") + "\n\n%s\nenabled = true\ntrusted_hash = \"%s\"\n" % (head, hash_)
    return new, True

for home in homes:
    print("Codex home:", home)
    if not os.path.isdir(home): print("  skipped (directory missing)"); continue
    present = ensure_hook(home)
    cfg = os.path.join(home, "config.toml")
    text = open(cfg).read() if os.path.exists(cfg) else ""
    text, ch = ensure_feature(text)
    if ch and DRY: print("  config.toml: would set features.hooks = true")
    elif ch: write_atomic(cfg, text); print("  config.toml: set features.hooks = true")
    else: print("  config.toml: features.hooks already enabled")
    if DRY and not present: print("  trust: would be registered after the hook is added"); continue
    if not codex_bin or not os.path.exists(codex_bin):
        print("  codex binary not found, skipping trust registration (set codex_bin in config.json)"); continue
    try:
        mine = [h for h in hooks_list(home) if is_ours(h.get("command", "")) and h["sourcePath"] == os.path.join(home, "hooks.json")]
    except Exception as e:
        print("  hooks/list failed:", e); continue
    if not mine: print("  t3-lead hook not listed by hooks/list (check manually)"); continue
    for h in mine:
        text = open(cfg).read()
        text, ch = set_trust(text, h["key"], h["currentHash"])
        if ch and DRY: print("  trust: would register", h["key"])
        elif ch: write_atomic(cfg, text); print("  trust registered:", h["key"])
        else: print("  trust already registered:", h["key"])
PY

fi  # GLOBAL

# --- 4. state directories, skill links, CLI link ---
link() {  # link <label> <target> <link path>
  local label=$1 target=$2 path=$3
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then echo "$label already: $path -> $target"; return; fi
  if [ -e "$path" ] && [ ! -L "$path" ]; then echo "$label SKIPPED (exists and is not a symlink): $path" >&2; return; fi
  if [ "$DRY" = 1 ]; then echo "$label would link: $path -> $target"; return; fi
  mkdir -p "$(dirname "$path")"; ln -sfn "$target" "$path"; echo "$label linked: $path -> $target"
}
if [ -d "$ROOT/state/roles" ] && [ -d "$ROOT/state/tasks" ]; then echo "state dirs already: $ROOT/state"
elif [ "$DRY" = 1 ]; then echo "state dirs would be created: $ROOT/state"
else mkdir -p "$ROOT/state/roles" "$ROOT/state/tasks"; echo "state dirs created: $ROOT/state"; fi
if [ "$GLOBAL" = 1 ]; then
  for d in ${SKILL_DIRS[@]+"${SKILL_DIRS[@]}"}; do
    if [ ! -d "$d" ] && [ ! -d "$(dirname "$d")" ]; then echo "skill link skipped (parent directory missing): $d"; continue; fi
    link "skill link" "$ROOT/skill" "$d/t3-lead"
  done
  link "CLI link" "$ROOT/bin/t3lead" "$CLI_LINK"
fi
[ "$DRY" = 1 ] && echo "== dry run finished: nothing was written =="
exit 0
