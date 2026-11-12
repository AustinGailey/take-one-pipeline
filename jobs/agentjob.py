#!/usr/bin/env python3
"""agentjob: run one unattended `claude -p` job under a supervisor that owns its lease and its terminal write.

Contract: JOBS-CONTRACT.md. Stdlib only. State lives in ~/.agent-jobs/<app>/ (AGENTJOB_HOME
overrides the root): <job>.spec.json (what to run), <job>.lease.json (renewed every HEARTBEAT s while the agent
process is alive), <job>.terminal.json (written exactly once, by the supervisor or the reaper), <job>.out.json (the
agent's JSON result), <job>.err (stderr), <job>.stream.jsonl (the agent's event stream).

usage:
  agentjob.py start <app> <job> --prompt-file F --cwd DIR --tools "Read Edit Bash" [--allow RULE]... [--add-dir D]...
                    [--model sonnet] [--timeout SEC] [--attempt N] [--on-deny stop|continue] [--max-budget-usd X]
                    [--resume SESSION_ID]   (continue the agent's earlier claude session; the prompt is its next message)
      Validates, writes the spec, launches the supervisor detached (own session) and returns at once:
      {"started": true, "pid": ..., "leaseUntil": ...} or {"started": false, "why": ...}.
      The agent runs `claude -p --permission-mode dontAsk --tools <tools> --allowedTools <tools minus Bash + --allow rules>
      --strict-mcp-config` (no MCP, nothing outside the allowlist can prompt: it is denied at once). Bash runs only
      what an --allow pattern names, e.g. --allow 'Bash(node:*)'.
      --on-deny stop (default): the first permission denial ends the job as needs-owner naming the tool.
  agentjob.py status <app> [job]      derived state of every job (or one): working | queued | done | failed |
                                      needs-owner | handed-back | requeued | stale   (stale = no live lease, no terminal)
  agentjob.py reap <app> [--max-attempts 2] [--dry-run]
      Every stale job gets a terminal: "requeued" (attempt + 1) or, at max attempts, "needs-owner" with the cause.
  agentjob.py export <app>            terminal states not yet acknowledged (what the db sync must apply)
  agentjob.py ack <app> <job>         mark a terminal as applied to the db (<job>.synced)
  agentjob.py stop <app> <job>        SIGINT the agent's process group; the supervisor then writes handed-back

The agent may end its report with a fenced block  ```job {"status": "done"|"blocked"|"handed-back",
"ask": "..." | {"kind": "approve|pick|answer|sign-in|review", "question": "...", "context": "...", "options": [{"id","label"}],
"go": {"view", "params", "anchor"}, "sources": [{"kind": "app|session|web|file", "label", "route|href|path", "at"?}]}, "resume": "...", "outputs": [...]} ```  ; blocked -> needs-owner with that typed ask
(the owner's decision), handed-back -> resume. A denied tool, a kill or a reap ends needs-owner with a `block`
{key, cause, fix, tool?, since} instead: a setup block, which Take One groups under "Blocked on setup", not "Needs you".
"""
import json, os, re, shutil, signal, subprocess, sys, threading, time

ROOT = os.path.expanduser(os.environ.get("AGENTJOB_HOME") or "~/.agent-jobs")
LEASE, HEARTBEAT = 60, 15            # a lease lasts 60 s and is renewed every 15 s while the agent lives
DEFAULT_TIMEOUT, GRACE = 1500, 20    # hard timeout (s); SIGINT, then SIGTERM after GRACE, then SIGKILL
CLAUDE = os.environ.get("AGENTJOB_CLAUDE") or shutil.which("claude") or "claude"   # AGENTJOB_CLAUDE: any binary that speaks the stream-json protocol (tests use sample/stub_agent.py)
TERMINAL = ("done", "failed", "needs-owner", "handed-back", "requeued")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,120}")
DENY_RE = re.compile(r"(permission to use|has been denied|denied by|not allowed|requires approval)", re.I)


def now():
    return time.time()


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)) if t else None


def appdir(app):
    d = os.path.join(ROOT, app)
    os.makedirs(d, exist_ok=True)
    return d


def path(app, job, ext):
    return os.path.join(appdir(app), job + ext)


def rj(p):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def wj(p, d):
    tmp = "%s.tmp%d" % (p, os.getpid())
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, p)


def write_terminal(app, job, d):
    """Exactly once: the first writer wins (link() fails if the file exists). Returns True if this call wrote it."""
    p = path(app, job, ".terminal.json")
    d = dict(d, job=job, app=app, at=iso(now()), atEpoch=int(now()))
    tmp = "%s.tmp%d" % (p, os.getpid())
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    try:
        os.link(tmp, p)
    except FileExistsError:
        return False
    finally:
        os.remove(tmp)
    return True


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def derive(app, job, t=None):
    """The one place a job's state is decided. Never trusts a bare status."""
    t = now() if t is None else t
    term = rj(path(app, job, ".terminal.json"))
    if term:
        return {"job": job, "state": term["state"], "terminal": term, "synced": os.path.exists(path(app, job, ".synced"))}
    lease = rj(path(app, job, ".lease.json"))
    spec = rj(path(app, job, ".spec.json"))
    if not lease:
        return {"job": job, "state": "queued" if spec else "unknown", "spec": bool(spec)}
    fresh = (lease.get("leaseUntil") or 0) > t
    # the supervisor owns the terminal write: while it lives the job is live, even in the ~50 ms between the agent
    # exiting and .terminal.json landing (found 2026-11-01: that gap read as "stale" and the page stopped polling)
    sup = lease.get("supervisorPid")
    live = alive(sup) if sup is not None else (lease.get("agentPid") is None or alive(lease.get("agentPid")))
    st = "working" if fresh and live else "stale"
    if st == "stale":
        term = rj(path(app, job, ".terminal.json"))   # written between our two reads
        if term:
            return {"job": job, "state": term["state"], "terminal": term, "synced": os.path.exists(path(app, job, ".synced"))}
    out = {"job": job, "state": st, "lease": lease, "fresh": fresh, "alive": live}
    if st == "stale":
        out["cause"] = ("lease expired at %s" % lease.get("leaseUntilIso")) if not fresh else "process gone with the lease still open"
    return out


def jobs_in(app):
    d = appdir(app)
    ids = set()
    for f in os.listdir(d):
        for ext in (".spec.json", ".lease.json", ".terminal.json"):
            if f.endswith(ext):
                ids.add(f[: -len(ext)])
    return sorted(ids)


# ---------- start ----------
def cmd_start(app, job, a):
    if not ID_RE.fullmatch(app) or not ID_RE.fullmatch(job):
        return {"started": False, "why": "app and job ids: letters, digits, _ . : - only"}
    cur = derive(app, job)
    if cur["state"] == "working":
        return {"started": False, "why": "a live supervisor already holds the lease", "lease": cur["lease"]}
    opt = parse_opts(a)
    if not opt.get("prompt-file") or not os.path.isfile(opt["prompt-file"]):
        return {"started": False, "why": "--prompt-file missing or not a file"}
    if not opt.get("cwd") or not os.path.isdir(os.path.expanduser(opt["cwd"])):
        return {"started": False, "why": "--cwd missing or not a folder"}
    if not opt.get("tools"):
        return {"started": False, "why": "--tools is required (the fixed tool allowlist)"}
    for ext in (".terminal.json", ".synced", ".lease.json", ".stop"):  # a new attempt starts clean (a leftover .stop would kill it at once)
        try:
            os.remove(path(app, job, ext))
        except FileNotFoundError:
            pass
    spec = {"app": app, "job": job, "prompt": open(opt["prompt-file"]).read(), "cwd": os.path.expanduser(opt["cwd"]),
            "tools": opt["tools"], "allow": opt.get("allow", []), "addDirs": [os.path.expanduser(x) for x in opt.get("add-dir", [])],
            "model": opt.get("model") or "sonnet", "timeout": int(opt.get("timeout") or DEFAULT_TIMEOUT),
            "attempt": int(opt.get("attempt") or 1), "onDeny": opt.get("on-deny") or "stop",
            "maxBudgetUsd": opt.get("max-budget-usd"), "resume": opt.get("resume") or None, "createdAt": iso(now())}
    wj(path(app, job, ".spec.json"), spec)
    log = open(path(app, job, ".supervisor.log"), "ab")
    p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", app, job], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True, close_fds=True)
    for _ in range(40):  # wait until the supervisor holds its first lease
        l = rj(path(app, job, ".lease.json"))
        if l and l.get("supervisorPid") == p.pid:
            return {"started": True, "pid": p.pid, "leaseUntil": l["leaseUntilIso"], "timeout": spec["timeout"],
                    "hardDeadline": iso(now() + spec["timeout"] + GRACE * 2), "stateDir": appdir(app)}
        if rj(path(app, job, ".terminal.json")):   # a very short job can finish before the first poll sees its lease
            return {"started": True, "pid": p.pid, "leaseUntil": None, "timeout": spec["timeout"], "note": "already finished", "stateDir": appdir(app)}
        time.sleep(0.1)
    return {"started": True, "pid": p.pid, "leaseUntil": None, "note": "supervisor started; lease not seen yet"}


def parse_opts(a):
    o, i = {}, 0
    multi = {"allow", "add-dir"}
    while i < len(a):
        k = a[i]
        if k.startswith("--") and i + 1 < len(a):
            k = k[2:]
            if k in multi:
                o.setdefault(k, []).append(a[i + 1])
            else:
                o[k] = a[i + 1]
            i += 2
        elif k.startswith("--"):
            o[k[2:]] = True
            i += 1
        else:
            i += 1
    return o


# ---------- supervise ----------
def tree(root):
    """root and every descendant (the agent's tool commands run in their own process groups, so a group kill misses them)."""
    if not root:
        return []
    out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True).stdout
    kids, cmd = {}, {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            kids.setdefault(int(parts[1]), []).append(int(parts[0]))
            cmd[int(parts[0])] = parts[2][:120] if len(parts) > 2 else ""
    seen, todo = [], [int(root)]
    while todo:
        x = todo.pop()
        if x in seen:
            continue
        seen.append(x)
        todo += kids.get(x, [])
    return [{"pid": x, "cmd": cmd.get(x, "")} for x in seen if x in cmd]


def kill_tree(procs, sig):
    for x in procs:
        try:
            os.kill(x["pid"], sig)
        except (ProcessLookupError, PermissionError):
            pass


def lease_write(app, job, sup, agent, spec, started):
    t = now()
    wj(path(app, job, ".lease.json"), {"job": job, "app": app, "supervisorPid": sup, "agentPid": agent, "pgid": agent,
                                       "tree": tree(agent),
                                       "host": os.uname().nodename, "startedAt": iso(started), "heartbeatAt": iso(t),
                                       "leaseUntil": t + LEASE, "leaseUntilIso": iso(t + LEASE), "attempt": spec["attempt"],
                                       "timeout": spec["timeout"], "hardDeadline": iso(started + spec["timeout"] + GRACE * 2)})


def outcome_block(text):
    m = None
    for m in re.finditer(r"```job\s*(\{[\s\S]*?\})\s*```", text or ""):
        pass
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def denial_in(ev):
    """A tool_result that says the call was denied -> (tool name, input) or None."""
    msg = ev.get("message") or {}
    for c in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
        if c.get("type") == "tool_result" and c.get("is_error"):
            txt = c.get("content")
            if isinstance(txt, list):
                txt = " ".join(x.get("text", "") for x in txt if isinstance(x, dict))
            # "Exit code N ..." is the command's own output (e.g. a lint saying "not allowed"), never a harness denial.
            if not str(txt or "").lstrip().startswith("Exit code") and DENY_RE.search(str(txt or "")):
                return c.get("tool_use_id"), str(txt)[:300]
    return None


def supervise(app, job):
    spec = rj(path(app, job, ".spec.json"))
    sup, started = os.getpid(), now()
    lease_write(app, job, sup, None, spec, started)
    cmd = [CLAUDE, "-p", "--output-format", "stream-json", "--verbose", "--model", spec["model"],
           "--permission-mode", "dontAsk", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--tools", spec["tools"]]
    # dontAsk denies anything not pre-approved, Write and Edit included: the listed tools are the allowlist, except Bash,
    # which runs only the commands named by --allow patterns ("Bash(node:*)").
    allowed = [t for t in spec["tools"].replace(",", " ").split() if t and t != "Bash"] + list(spec["allow"])
    if allowed:
        cmd += ["--allowedTools"] + allowed
    for d in spec["addDirs"]:
        cmd += ["--add-dir", d]
    if spec.get("maxBudgetUsd"):
        cmd += ["--max-budget-usd", str(spec["maxBudgetUsd"])]
    if spec.get("resume"):   # continue the agent's own earlier session (dispatch.py resume: hard-timeout hand-back, attempt 2)
        cmd += ["--resume", str(spec["resume"])]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None) if env.get("CLAUDE_CODE_OAUTH_TOKEN") else None
    err = open(path(app, job, ".err"), "wb")
    stream = open(path(app, job, ".stream.jsonl"), "w")
    p = subprocess.Popen(cmd, cwd=spec["cwd"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True,
                         start_new_session=True, env=env)
    p.stdin.write(spec["prompt"])
    p.stdin.close()
    lease_write(app, job, sup, p.pid, spec, started)
    state = {"timedOut": False, "denied": None, "stopped": False, "tools": {}, "tree": [], "session": None}

    def kill(why):
        for sig, wait in ((signal.SIGINT, GRACE), (signal.SIGTERM, GRACE), (signal.SIGKILL, 0)):
            procs = tree(p.pid)  # the agent and its tool commands (their own process groups)
            kill_tree(procs, sig)
            try:
                os.killpg(p.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
            end = now() + wait
            while now() < end and p.poll() is None:
                time.sleep(0.5)
            if p.poll() is not None:
                return

    def beat():
        last = 0
        while p.poll() is None:
            state["tree"] = tree(p.pid) or state["tree"]  # every 3 s: what to clean up if the agent dies abruptly
            if now() - last < HEARTBEAT:
                time.sleep(3)
                continue
            last = now()
            if now() - started > spec["timeout"] and not state["timedOut"]:
                state["timedOut"] = True
                threading.Thread(target=kill, args=("timeout",), daemon=True).start()
            if os.path.exists(path(app, job, ".stop")) and not state["stopped"]:
                state["stopped"] = True
                threading.Thread(target=kill, args=("stop",), daemon=True).start()
            lease_write(app, job, sup, p.pid, spec, started)

    threading.Thread(target=beat, daemon=True).start()
    result = None
    for line in p.stdout:
        stream.write(line)
        stream.flush()
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("session_id") and not state["session"]:   # the init event names the session: a killed run (timeout) can still be resumed
            state["session"] = ev["session_id"]
        if ev.get("type") == "assistant":
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    state["tools"][c.get("id")] = {"tool": c.get("name"), "input": json.dumps(c.get("input") or {})[:300]}
        elif ev.get("type") == "user" and not state["denied"]:
            d = denial_in(ev)
            if d:
                state["denied"] = dict(state["tools"].get(d[0]) or {"tool": "?"}, message=d[1])
                if spec["onDeny"] == "stop":
                    threading.Thread(target=kill, args=("denied",), daemon=True).start()
        elif ev.get("type") == "result":
            result = ev
    p.wait()
    stream.close()
    live = {x["pid"]: x["cmd"] for x in tree(1)}  # the agent is gone: anything it started that still runs is an orphan
    left = [x for x in state["tree"] if x["pid"] != p.pid and live.get(x["pid"]) == x["cmd"]]
    kill_tree(left, signal.SIGTERM)
    state["leftovers"] = [x["pid"] for x in left]
    if result:
        wj(path(app, job, ".out.json"), result)
    finish(app, job, spec, p.returncode, result, state, started)
    try:  # the lease ends with the job
        os.remove(path(app, job, ".lease.json"))
    except FileNotFoundError:
        pass


def finish(app, job, spec, rc, result, state, started):
    r = result or {}
    text = r.get("result") or ""
    oc = outcome_block(text) or {}
    denials = [{"tool": d.get("tool_name"), "input": json.dumps(d.get("tool_input") or {})[:300]}
               for d in (r.get("permission_denials") or [])][:12]
    if state["denied"] and not denials:
        denials = [{"tool": state["denied"].get("tool"), "input": state["denied"].get("input", "")}]
    base = {"exit": rc, "attempt": spec["attempt"], "killedLeftovers": state.get("leftovers") or [], "session": r.get("session_id"), "costUsd": r.get("total_cost_usd"),
            "turns": r.get("num_turns"), "durationS": int(now() - started), "report": text[-6000:], "denials": denials,
            "outputs": oc.get("outputs") or []}
    sess = r.get("session_id") or state.get("session")
    base["session"] = sess
    if state["stopped"]:
        d = dict(base, state="handed-back", reason="stopped on request",
                 resume=oc.get("resume") or ("Stopped on request after %d s; resume session %s." % (base["durationS"], sess)))
    elif state["timedOut"]:
        d = dict(base, state="handed-back", reason="hard timeout (%d s)" % spec["timeout"],
                 resume=oc.get("resume") or ("Stopped at the %d s hard timeout; resume session %s." % (spec["timeout"], sess)))
    elif denials and (spec["onDeny"] == "stop" or oc.get("status") != "done"):
        t0 = denials[0]
        # a denied tool is a setup block (Take One "Blocked on setup"), never one of the owner's decisions
        cmd0 = bash_head(t0) if t0["tool"] == "Bash" else None
        d = dict(base, state="needs-owner", reason="permission denied: %s" % t0["tool"], blockingTool=t0["tool"],
                 block=block_of("bash:" + cmd0, "The agent ran `%s …` in Bash, which this job's allowlist doesn't cover (%s)." % (cmd0, t0["input"][:120]),
                                "Its prompt needs the rule: one literal allowed command per Bash call (no cd, ;, &&, pipes, $VAR); "
                                "or add --allow 'Bash(%s:*)' for the job. Then press I fixed it." % cmd0, "Bash")
                 if cmd0 else
                 block_of("tool:" + t0["tool"], "This job's allowlist denies %s (%s)." % (t0["tool"], t0["input"][:120]),
                          "Allow %s for the job (--allow / --tools) or the routine, or run it in a chat." % t0["tool"], t0["tool"]))
    elif oc.get("status") == "blocked":
        # the agent stopped at the owner's decision: a typed ask (SCHEMA.md, decisions)
        d = dict(base, state="needs-owner", reason="agent blocked", ask=typed_ask(oc.get("ask"), "The agent stopped at a decision; see its report."))
    elif oc.get("status") == "handed-back":
        d = dict(base, state="handed-back", reason="agent handed back", resume=oc.get("resume") or text[-300:])
    elif rc == 0 and result and not r.get("is_error"):
        d = dict(base, state="done", reason=oc.get("status") or "finished")
    elif rc is not None and rc < 0:  # killed by a signal nobody here sent: the reaper's rule (re-queue, then needs-owner)
        att = spec["attempt"]
        d = dict(base, state="requeued" if att < 2 else "needs-owner", reason="agent killed by signal %d" % -rc, nextAttempt=att + 1,
                 block=block_of("agent:killed", "The agent was killed %d times (signal %d)." % (att, -rc),
                                "Fix the cause (memory, sleep, a killed app), then press I fixed it; or run it in a chat."))
    elif r.get("subtype") == "error_max_budget_usd":
        d = dict(base, state="handed-back", reason="budget guard", resume="Stopped at its budget guard; resume session %s." % sess)
    else:
        errtail = ""
        try:
            errtail = open(path(app, job, ".err")).read()[-600:]
        except OSError:
            pass
        d = dict(base, state="failed", reason=(r.get("subtype") or ("exit %s" % rc)) + (": " + errtail.strip().splitlines()[-1] if errtail.strip() else ""))
    write_terminal(app, job, d)


# ---------- typed asks and setup blocks (SCHEMA.md decisions; JOBS-CONTRACT.md rule 4) ----------
ASK_KINDS = ("approve", "pick", "answer", "sign-in", "review")


def typed_ask(a, fallback):
    """The agent's ```job ask: a typed object {kind, question, context?, options?, go?} or a plain string."""
    if isinstance(a, dict) and a.get("question"):
        k = a.get("kind") if a.get("kind") in ASK_KINDS else ("pick" if a.get("options") else "answer")
        return dict({x: a[x] for x in ("context", "options", "go", "ref", "sources", "select", "policy", "policyKey", "recommend", "preview", "plain") if a.get(x)}, kind=k, question=str(a["question"])[:300], at=iso(now()))
    return {"kind": "answer", "question": str(a or fallback)[:300], "at": iso(now())}


def bash_head(denial):
    """First word of a denied Bash command ("cd" for `cd x; python3 …`)."""
    try:
        c = json.loads(denial.get("input") or "{}").get("command") or ""
    except ValueError:
        m = re.search(r'"command":\s*"([^"\s;&|]+)', denial.get("input") or "")
        c = m.group(1) if m else ""
    w = re.split(r"[\s;&|]+", c.strip())
    return re.sub(r"[^\w.-]", "", w[0])[:40] if w and w[0] else None


def block_of(key, cause, fix, tool=None):
    b = {"key": key, "cause": cause[:300], "fix": fix[:300], "since": iso(now())}
    if tool:
        b["tool"] = tool
    return b


# ---------- reaper / export ----------
def cmd_reap(app, a):
    mx = int(parse_opts(a).get("max-attempts") or 2)
    dry = "--dry-run" in a
    out = []
    for job in jobs_in(app):
        s = derive(app, job)
        if s["state"] != "stale":
            continue
        att = int((s.get("lease") or {}).get("attempt") or 1)
        if att >= mx:
            d = {"state": "needs-owner", "reason": "reaped: " + s["cause"], "attempt": att, "reaped": True,
                 "block": block_of("agent:died", "The job died %d times (%s)." % (att, s["cause"]),
                                   "Fix the cause, then press I fixed it; or run it in a chat.")}
        else:
            d = {"state": "requeued", "reason": "reaped: " + s["cause"], "attempt": att, "nextAttempt": att + 1, "reaped": True}
        if not dry:
            # what the dead supervisor left running: kill recorded tree members that still run the same command
            live = {x["pid"]: x["cmd"] for x in tree(1)}
            left = [x for x in (s.get("lease") or {}).get("tree") or [] if live.get(x["pid"]) == x["cmd"]]
            kill_tree(left, signal.SIGTERM)
            d["killedLeftovers"] = [x["pid"] for x in left]
            lp = path(app, job, ".lease.json")
            if write_terminal(app, job, d):
                try:
                    os.remove(lp)
                except FileNotFoundError:
                    pass
        out.append(dict(d, job=job))
    return {"reaped": out, "dryRun": dry}


def cmd_export(app):
    rows = []
    for job in jobs_in(app):
        s = derive(app, job)
        if s["state"] in TERMINAL and not s.get("synced"):
            rows.append(s["terminal"])
    return {"app": app, "pending": rows}


def cmd_stop(app, job):
    s = derive(app, job)
    if s["state"] != "working":
        return {"stopped": False, "why": "not working (%s)" % s["state"]}
    open(path(app, job, ".stop"), "w").close()  # the supervisor's heartbeat sees it within HEARTBEAT s
    return {"stopped": True, "via": "stop flag", "withinS": HEARTBEAT}


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    c = a[0]
    if c == "_supervise":
        supervise(a[1], a[2])
        return 0
    if c == "start":
        r = cmd_start(a[1], a[2], a[3:])
    elif c == "status":
        r = {"jobs": [derive(a[1], j) for j in ([a[2]] if len(a) > 2 else jobs_in(a[1]))]}
        for j in r["jobs"]:
            (j.get("terminal") or {}).pop("report", None)
    elif c == "reap":
        r = cmd_reap(a[1], a[2:])
    elif c == "export":
        r = cmd_export(a[1])
    elif c == "ack":
        open(path(a[1], a[2], ".synced"), "w").write(iso(now()))
        r = {"acked": a[2]}
    elif c == "stop":
        r = cmd_stop(a[1], a[2])
    else:
        print(__doc__)
        return 2
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
