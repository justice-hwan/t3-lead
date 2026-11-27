#!/usr/bin/env python3
"""t3-lead role-detection hook (UserPromptSubmit) v0.

- Thread ID: environment variable T3CODE_THREAD_ID.
- Parent: the T3 header at the very start of the prompt,
  [T3 Code: the agent in T3 thread "<parent>" sent this message, not the user.]
- Role: the lead is registered with `role.py --register-lead <thread>`. A child of the lead is a verifier,
  a child of a verifier is a lane, and a child of a lane is a lane. If the parent is not registered,
  the thread is "unmanaged" (nothing is injected).
- The role is decided once, on the first prompt, and recorded in state/roles/; the same guidance
  is injected on every later prompt.
"""
import hashlib, json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib"))
import t3lead_config

try:
    CFG, CFG_ERROR = t3lead_config.load(), None
except Exception as e:  # a broken config must not break the prompt: use built-in defaults and log it
    CFG, CFG_ERROR = t3lead_config.load(use_file=False), str(e)
ROOT = CFG["home"]
ROLES = os.path.join(ROOT, "state", "roles")
LOG = os.path.join(ROOT, "state", "hook.log")
HEADER = re.compile(r'\A\s*\[T3 Code: the agent in T3 thread "([^"]+)" sent this message, not the user\.\]')
CHILD_ROLE = {"lead": "verifier", "verifier": "lane", "lane": "lane"}


def path_for(tid):
    return os.path.join(ROLES, hashlib.sha256(tid.encode()).hexdigest()[:32] + ".json")


def read_role(tid):
    try:
        with open(path_for(tid)) as f:
            return json.load(f)
    except Exception:
        return None


def write_role(tid, role, parent):
    os.makedirs(ROLES, exist_ok=True)
    rec = {"thread": tid, "role": role, "parent": parent, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = path_for(tid) + ".tmp%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, path_for(tid))
    return rec


def log(rec):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--register-lead":
        print(json.dumps(write_role(sys.argv[2], "lead", None), ensure_ascii=False))
        return
    try:
        event = json.load(sys.stdin)
    except Exception:
        return
    tid = os.environ.get("T3CODE_THREAD_ID", "")
    prompt = event.get("prompt") or ""
    entry = {"t": time.strftime("%H:%M:%S"), "thread": tid[-24:], "decided": None}
    if CFG_ERROR:
        entry["config_error"] = CFG_ERROR
    if not tid:
        # The Codex app-server runs several threads in one process, so the thread ID is unknown.
        # In that case nothing is recorded; the role is decided on every prompt from the header alone
        # (the sending thread). That is enough for lanes (the leaves).
        m = HEADER.match(prompt)
        prec = read_role(m.group(1)) if m else None
        rec = {"role": CHILD_ROLE.get(prec["role"]) if prec else None} if prec else {"role": None}
        entry["why"] = "no T3CODE_THREAD_ID (header only)"
        entry["parent"] = (m.group(1) if m else "")[-24:]
    else:
        rec = read_role(tid)
    if tid and rec is None:
        m = HEADER.match(prompt)
        parent = m.group(1) if m else None
        prec = read_role(parent) if parent else None
        role = CHILD_ROLE.get(prec["role"]) if prec else None
        rec = write_role(tid, role or "unmanaged", parent)
        entry["decided"] = rec["role"]
        entry["parent"] = (parent or "")[-24:]
    role = rec["role"]
    if not tid and role == "verifier":
        role = None  # without a thread ID its children cannot find it, so never act as a verifier
    entry["role"] = role
    log(entry)
    rules = {"lane": "lane.md", "verifier": "verifier.md"}.get(role)
    if not rules:
        return
    with open(os.path.join(ROOT, "rules", rules)) as f:
        ctx = t3lead_config.render(f.read(), CFG)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
