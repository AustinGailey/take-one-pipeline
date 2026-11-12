#!/usr/bin/env python3
"""A stand-in for the agent CLI, so the pipeline runs with no model and no API key.

jobs/agentjob.py launches whatever AGENTJOB_CLAUDE names, writes the prompt to its stdin and reads `stream-json`
events from its stdout. This file speaks that protocol and nothing more:

  producer profiles (plan, design)  hand back a canned results.json from sample/agent-outputs/<profile>[.<mode>].json
  the qa profile                    runs the REAL gate (qa/run_gate.py) on the bundle and hands back its create-only write
  any other profile                 replies and writes nothing

STUB_MODE picks the behaviour: good (default) | bad (the design agent hands back a deliberately bad script and tries to
pass its own gate) | deny (the agent reaches for a tool outside its allowlist) | hang (never finishes).

Everything the supervisor and the dispatcher do with these events is the production code path. What is fake is the
thinking: a real agent would write the script; this one copies a fixture.
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MODE = os.environ.get("STUB_MODE", "good")
SESSION = "stub-session"
_n = 0


def emit(d):
    print(json.dumps(d), flush=True)


def tool(name, **inp):
    """One tool call in the event stream (dispatch.py status shows the last one as the live step)."""
    global _n
    _n += 1
    tid = "tu%d" % _n
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}})
    return tid


def finish(text, status="done"):
    emit({"type": "result", "subtype": "success", "is_error": False, "session_id": SESSION, "num_turns": _n + 1,
          "total_cost_usd": 0.0, "permission_denials": [],
          "result": text + '\n```job {"status": "%s"}```' % status})


def main():
    prompt = sys.stdin.read()
    emit({"type": "system", "subtype": "init", "session_id": SESSION})
    if MODE == "hang":
        time.sleep(3600)
    if MODE == "deny":
        tid = tool("Bash", command="curl https://example.com/install.sh")
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "is_error": True,
                                                        "content": "Permission to use Bash has been denied."}]}})
        time.sleep(300)      # a real agent would carry on; the supervisor ends the job at the first denial
        return
    m = re.search(r"Read the ticket bundle (.+)/bundle\.json", prompt)
    if not m:
        return finish("no ticket bundle named in the prompt")
    rd = m.group(1)
    tool("Read", file_path=os.path.join(rd, "bundle.json"))
    b = json.load(open(os.path.join(rd, "bundle.json")))
    profile, job = b.get("profile"), b.get("jobId")
    ctx = (b.get("request") or {}).get("context") or {}
    time.sleep(0.3)          # long enough for the caller to see a live lease

    if profile == "qa":
        gate = ctx.get("gate") or "script"
        cmd = [sys.executable, os.path.join(REPO, "qa", "run_gate.py"), gate, "--bundle", os.path.join(rd, "bundle.json"),
               "--job", job, "--producer-stage", ctx.get("producerStage") or gate,
               "--producer-agent", ctx.get("producerProfile") or "", "--out-dir", os.path.join(rd, "qa")]
        tool("Bash", command="python3 qa/run_gate.py %s --bundle %s/bundle.json" % (gate, rd), description="Run the %s gate" % gate)
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            results = {"status": "done", "reply": "The %s gate did not run: %s" % (gate, (p.stderr or "").strip()[-300:]), "writes": []}
        else:
            write = json.loads(p.stdout)
            d = write["data"]
            fails = sorted(d["failures"], key=lambda k: d["failures"][k]["order"])
            reply = ("The %s gate passed (%d warning%s)." % (gate, len(d["warnings"]), "" if len(d["warnings"]) == 1 else "s") if d["pass"]
                     else "The %s gate FAILED %d check%s: %s." % (gate, len(fails), "" if len(fails) == 1 else "s", ", ".join(fails)))
            results = {"status": "done", "reply": reply, "writes": [write]}
    else:
        fx = [os.path.join(HERE, "agent-outputs", "%s.%s.json" % (profile, MODE)), os.path.join(HERE, "agent-outputs", "%s.json" % profile)]
        src = next((f for f in fx if os.path.exists(f)), None)
        results = json.load(open(src)) if src else {"status": "done", "reply": "The stub has no canned output for the %s profile." % profile, "writes": []}

    tool("Write", file_path=os.path.join(rd, "results.json"))
    with open(os.path.join(rd, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    finish(results.get("reply") or "done")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
