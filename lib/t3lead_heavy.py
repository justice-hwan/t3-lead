"""Heavy-resource queue: run a command only when a slot in its group is free, first come first served.

A group (for example "gpu") has a number of slots from config.json `heavy_groups`. Every caller registers in
the group's queue file; the first <slots> live entries hold the slots, the rest wait in arrival order. An entry
is live while its wrapper process exists and keeps its heartbeat fresh, so a crashed or killed caller frees its
slot within HEARTBEAT_TTL seconds. All queue changes happen under an flock on a lock file next to the queue.

The wrapped command runs as a child of this process and the slot is held until it exits, so the real work must
run in the foreground inside the wrapper. To run it in the background, background the whole
`t3lead heavy ...` line instead.
"""
import fcntl, json, os, signal, subprocess, sys, threading, time, uuid

POLL = 2.0
HEARTBEAT = 10.0
HEARTBEAT_TTL = 60.0
REPORT_EVERY = 300.0
EXIT_TIMEOUT = 75  # EX_TEMPFAIL: gave up waiting (--max-wait)


def group_dir(state_dir, group):
    return os.path.join(state_dir, "heavy", group)


class Queue:
    def __init__(self, state_dir, group, slots):
        self.dir = group_dir(state_dir, group)
        self.group, self.slots = group, slots
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "queue.json")
        self.lock_path = os.path.join(self.dir, "queue.lock")

    def _locked(self, fn):
        with open(self.lock_path, "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                q = self._read()
                out = fn(q)
                self._write(q)
                return out
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def _read(self):
        try:
            with open(self.path) as f:
                d = json.load(f)
            return d.get("entries", []) if isinstance(d, dict) else []
        except (OSError, ValueError):
            return []

    def _write(self, q):
        tmp = "%s.%d.tmp" % (self.path, os.getpid())
        with open(tmp, "w") as f:
            json.dump({"version": 1, "entries": q}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @staticmethod
    def _alive(e, now):
        if now - e.get("heartbeat", 0) > HEARTBEAT_TTL:
            return False
        try:
            os.kill(e["pid"], 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        return True

    def _prune(self, q):
        now = time.time()
        q[:] = [e for e in q if self._alive(e, now)]

    def snapshot(self):
        def fn(q):
            self._prune(q)
            return [dict(e) for e in q]
        return self._locked(fn)

    def join(self, label, owner):
        e = {"id": uuid.uuid4().hex[:12], "pid": os.getpid(), "label": label, "owner": owner,
             "arrived": time.time(), "heartbeat": time.time()}
        self._locked(lambda q: (self._prune(q), q.append(e)))
        return e["id"]

    def beat(self, eid):
        """Refresh the heartbeat. Returns (position, holders) where position < slots means it holds a slot."""
        def fn(q):
            self._prune(q)
            ids = [e["id"] for e in q]
            if eid not in ids:  # pruned (e.g. suspended past the TTL): rejoin at the back
                q.append({"id": eid, "pid": os.getpid(), "label": "?", "owner": "", "arrived": time.time(),
                          "heartbeat": time.time()})
                ids.append(eid)
            for e in q:
                if e["id"] == eid:
                    e["heartbeat"] = time.time()
            return ids.index(eid), [dict(e) for e in q[:self.slots]]
        return self._locked(fn)

    def leave(self, eid):
        self._locked(lambda q: q.__setitem__(slice(None), [e for e in q if e["id"] != eid]))


def describe(e):
    who = e.get("owner") or "pid %d" % e["pid"]
    return "%s (%s, since %s)" % (e.get("label") or "?", who, time.strftime("%H:%M:%S", time.localtime(e["arrived"])))


def load_pct():
    """1-minute load average as a percentage of the CPU count."""
    try:
        return os.getloadavg()[0] / (os.cpu_count() or 1) * 100
    except OSError:
        return 0.0


def record_event(state_dir, rec):
    try:
        with open(os.path.join(state_dir, "heavy", "events.jsonl"), "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def run(state_dir, groups, group, cmd, label=None, max_wait=None, out=sys.stderr, max_load=None, alert_min=None):
    if group not in groups:
        print("unknown heavy group %r; configured: %s (heavy_groups in config.json)" %
              (group, ", ".join(sorted(groups)) or "none"), file=out)
        return 2
    if not cmd:
        print("give the command after --", file=out)
        return 2
    q = Queue(state_dir, group, groups[group])
    owner = os.environ.get("T3CODE_THREAD_ID", "")[-24:]
    label = label or " ".join(cmd)[:80]
    eid = q.join(label, owner)
    start = time.time()
    last_report = 0.0
    child = None
    stop = threading.Event()

    def cleanup(*_):
        stop.set()
        if child and child.poll() is None:
            child.terminate()
        q.leave(eid)

    def on_signal(signum, _frame):
        cleanup()
        sys.exit(128 + signum)

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        if signal.getsignal(s) != signal.SIG_IGN:  # keep nohup's ignored SIGHUP
            signal.signal(s, on_signal)
    try:
        alerted = False
        while True:
            pos, holders = q.beat(eid)
            load = load_pct() if (max_load and pos < q.slots) else 0.0
            if pos < q.slots and not (max_load and load > max_load):
                break
            now = time.time()
            if now - last_report >= REPORT_EVERY:
                if pos < q.slots:
                    print("heavy[%s]: next in line, waiting for load %.0f%% <= %.0f%%" % (group, load, max_load),
                          file=out, flush=True)
                else:
                    print("heavy[%s]: waiting, %d ahead; holding: %s" % (group, pos - q.slots + 1,
                          "; ".join(describe(h) for h in holders)), file=out, flush=True)
                last_report = now
            if alert_min and not alerted and now - start >= alert_min * 60:
                alerted = True
                record_event(state_dir, {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": "long-wait", "group": group,
                                         "label": label, "owner": owner, "waited_min": round((now - start) / 60, 1),
                                         "reason": "load" if pos < q.slots else "slots",
                                         "holders": [describe(h) for h in holders]})
            if max_wait is not None and now - start > max_wait:
                print("heavy[%s]: gave up after %ds (--max-wait)" % (group, now - start), file=out, flush=True)
                q.leave(eid)
                return EXIT_TIMEOUT
            time.sleep(POLL)
        waited = time.time() - start
        if waited >= POLL:
            print("heavy[%s]: slot acquired after %ds" % (group, waited), file=out, flush=True)

        def heartbeat():
            while not stop.wait(HEARTBEAT):
                try:
                    q.beat(eid)
                except Exception:
                    pass
        threading.Thread(target=heartbeat, daemon=True).start()
        child = subprocess.Popen(cmd)
        return child.wait()
    finally:
        cleanup()


def long_waits(state_dir, groups, alert_min):
    """Entries currently waiting longer than alert_min minutes: [(group, entry, minutes)]."""
    out, now = [], time.time()
    for g in sorted(groups):
        q = Queue(state_dir, g, groups[g])
        for e in q.snapshot()[q.slots:]:
            m = (now - e["arrived"]) / 60
            if m >= alert_min:
                out.append((g, e, m))
    return out


def status(state_dir, groups, out=sys.stdout):
    if not groups:
        print("no heavy groups configured (heavy_groups in config.json)", file=out)
        return
    for g in sorted(groups):
        q = Queue(state_dir, g, groups[g])
        entries = q.snapshot()
        hold, wait = entries[:q.slots], entries[q.slots:]
        print("%s  slots %d, running %d, waiting %d" % (g, q.slots, len(hold), len(wait)), file=out)
        for e in hold:
            print("  run   " + describe(e), file=out)
        for e in wait:
            print("  wait  " + describe(e), file=out)
