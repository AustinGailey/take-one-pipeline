#!/usr/bin/env python3
"""Run the fictional sample project through two stages of the pipeline, with a stub agent and no API key.

  python3 sample/run_sample.py          a clean run: both gates pass and the run stops at the owner's approval
  python3 sample/run_sample.py --bad    the design agent hands back a bad script and tries to pass its own gate:
                                        the lane check drops that write, the real gate fails, the hand-off is held (exit 1)

What this file is: the caller. In production the owner's web page files requests, applies the lane-checked writes to
the document store and raises decision cards. Here a folder of JSON files is the store and this script does those
three jobs. It talks to the engine only through the same CLI the page uses:

  jobs/dispatch.py start @bundle  ->  status (poll)  ->  collect (lane check)  ->  ack

What is real: the dispatcher, the supervisor (lease, allowlist, one terminal write), the profiles and lanes, and the
plan and script gate checkers. What is fake: the agent (sample/stub_agent.py copies fixtures instead of thinking) and
the owner (answers are pre-recorded in sample/project/owner-answers.json).
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
KEY = "kc-001"
NOW = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Store:
    """The document store: one JSON file per document path."""

    def __init__(self, root):
        self.root = root

    def _f(self, path):
        return os.path.join(self.root, path + ".json")

    def get(self, path):
        try:
            return json.load(open(self._f(path)))
        except OSError:
            return None

    def put(self, path, data):
        os.makedirs(os.path.dirname(self._f(path)), exist_ok=True)
        with open(self._f(path), "w") as f:
            json.dump(data, f, indent=1)

    def merge(self, path, data):
        def deep(a, b):
            for k, v in b.items():
                a[k] = deep(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
            return a
        self.put(path, deep(self.get(path) or {}, data))

    def create(self, path, data):
        if self.get(path) is not None:
            raise RuntimeError("create refused: %s already exists" % path)
        self.put(path, data)

    def docs(self):
        out = {}
        for d, _, files in os.walk(self.root):
            for f in files:
                if f.endswith(".json"):
                    p = os.path.relpath(os.path.join(d, f), self.root)[:-5].replace(os.sep, "/")
                    out[p] = json.load(open(os.path.join(d, f)))
        return out


class Pipeline:
    def __init__(self, work, mode="good", quiet=False):
        self.work = os.path.abspath(work)
        marker = os.path.join(self.work, ".takeone-sample")
        if os.path.isdir(self.work) and os.listdir(self.work):
            if not os.path.exists(marker):      # never wipe a folder this script did not create
                raise SystemExit("--work %s exists and is not a sample work folder; pick an empty or new path" % self.work)
            shutil.rmtree(self.work)
        os.makedirs(self.work, exist_ok=True)
        open(marker, "w").close()
        shutil.copytree(os.path.join(HERE, "project", "store"), os.path.join(self.work, "store"))
        os.makedirs(os.path.join(self.work, "bundles"))
        self.store = Store(os.path.join(self.work, "store"))
        self.answers = json.load(open(os.path.join(HERE, "project", "owner-answers.json")))
        self.env = dict(os.environ, AGENTJOB_HOME=os.path.join(self.work, "agent-jobs"), TAKEONE_RUNS=os.path.join(self.work, "runs"),
                        AGENTJOB_CLAUDE=os.path.join(HERE, "stub_agent.py"), STUB_MODE=mode)
        self.n, self.quiet = 0, quiet
        self.jobs, self.gates, self.dropped = [], [], []

    def say(self, *a):
        if not self.quiet:
            print(*a, flush=True)

    def dispatch(self, *args):
        p = subprocess.run([sys.executable, os.path.join(REPO, "jobs", "dispatch.py")] + list(args), capture_output=True, text=True, env=self.env)
        try:
            return json.loads(p.stdout)
        except ValueError:
            raise RuntimeError("dispatch %s: %s %s" % (args[0], p.stdout, p.stderr))

    def run(self, text, context, timeout=60):
        """File one request, run its agent, apply what survives the lane check. Returns dispatch.collect's answer."""
        self.n += 1
        rid = "r-%03d" % self.n
        bundle = {"requestId": rid, "projectKey": KEY, "request": {"text": text, "context": context}, "docs": self.store.docs()}
        bf = os.path.join(self.work, "bundles", rid + ".json")
        json.dump(bundle, open(bf, "w"), indent=1)
        s = self.dispatch("start", "@" + bf)
        if not s.get("started"):
            raise RuntimeError("not started: %s" % s.get("why"))
        job = s["jobId"]
        self.say("  %-7s job %s started (skill %s, timeout %s s)" % (s["profile"], job, s["skill"], s["timeout"]))
        end, seen = time.time() + timeout, None
        while True:
            st = self.dispatch("status", job)["jobs"][0]
            if st["state"] == "working" and st.get("step") != seen:
                seen = st.get("step")
                self.say("          working: %s" % seen)
            if st["state"] not in ("working", "queued"):
                break
            if time.time() > end:
                self.dispatch("stop", job)
                raise RuntimeError("job %s still %s after %d s" % (job, st["state"], timeout))
            time.sleep(0.2)
        c = self.dispatch("collect", job)
        self.say("          %s: %s" % (c["state"], c.get("reply") or c.get("reason")))
        for w in c.get("writes") or []:
            {"create": self.store.create, "set": self.store.put, "merge": self.store.merge}[w["op"]](w["path"], w["data"])
            self.say("          applied  %-6s %s" % (w["op"], w["path"]))
        for d in c.get("dropped") or []:
            self.dropped.append(dict(d, job=job, profile=c.get("profile")))
            self.say("          DROPPED  %s  (%s%s)" % (d.get("path"), d.get("why"), ": " + ", ".join(d["fields"]) if d.get("fields") else ""))
        for d in c.get("decisions") or []:
            self.store.put(d["path"], d["data"])
            self.say("          raised   %s  [%s]" % (d["path"], d["data"]["policyKey"]))
        self.dispatch("ack", job)
        self.jobs.append({"job": job, "profile": c.get("profile"), "state": c["state"], "block": c.get("block")})
        c["jobId"], c["requestId"] = job, rid
        return c

    def stage(self, text, stage):
        """A producing stage, then every gate it queued as a follow-up. Returns (collected, [qa run docs])."""
        c = self.run(text, {"kind": "stage", "stage": stage})
        runs = []
        if c["state"] != "done":
            return c, runs
        for fu in c.get("followups") or []:
            if (fu.get("context") or {}).get("stage") != "qa":
                continue
            q = self.run(fu["text"], dict(fu["context"], followupOf=c["requestId"], producerStage=stage, producerProfile=c["profile"]))
            for w in q.get("writes") or []:
                if "/qa/" in w["path"]:
                    runs.append(dict(w["data"], path=w["path"]))
        self.gates += runs
        return c, runs

    def hold(self, run):
        """A failing gate holds the hand-off: one fix-or-waive card for the owner (policy fix.gate)."""
        fails = sorted(run["failures"], key=lambda k: run["failures"][k]["order"])
        path = "decisions/fix-%s-%s" % (KEY, run["runId"])
        self.store.put(path, {"kind": "fix", "policyKey": "fix.gate", "projectKey": KEY,
                              "question": "The %s gate failed %d check%s. Fix or proceed?" % (run["stage"], len(fails), "" if len(fails) == 1 else "s"),
                              "plain": {"will": "Nothing moves to the next stage until you answer.", "why": "; ".join("%s: %s" % (k, run["failures"][k]["detail"]) for k in fails)},
                              "options": [{"id": "fix", "label": "Send it back to the %s stage" % run["producer"]["stage"]}, {"id": "waive", "label": "Proceed anyway (logged on the run)"}],
                              "select": "one", "target": {"qaRunId": run["runId"], "stage": run["stage"]}, "raised": {"by": "page", "at": NOW()}})
        self.say("\n  HELD at the %s gate (%s). %d failing check%s:" % (run["stage"], run["gate"], len(fails), "" if len(fails) == 1 else "s"))
        for k in fails:
            self.say("    FAIL  %-18s %s" % (k, run["failures"][k]["detail"][:150]))
        self.say("  raised %s [fix.gate]: fix (back to the producer, gate re-runs) or waive (logged). Nothing downstream was filed." % path)
        return path

    def go(self):
        res = {"held": False, "heldAt": None, "waitingOn": None, "work": self.work}
        self.say("Project %s, store %s\n" % (KEY, os.path.relpath(self.store.root)))

        self.say("S1 Plan")
        c, runs = self.stage("Propose the plan for the shortlisted topic.", "plan")
        bad = self.blocked(c, runs)
        if bad:
            return self.finish(res, bad)
        self.say("\n  OWNER GATE 1: topic pick  [decisions/pick-%s-topic]" % KEY)
        a = self.answers["pick-%s-topic" % KEY]
        self.store.put("decisions/pick-%s-topic" % KEY, {
            "kind": "pick", "policyKey": "pick.topic", "projectKey": KEY, "question": "Which pitch do we make?",
            "options": [{"id": k, "label": v["title"]} for k, v in self.store.get("projects/%s/stages/research" % KEY)["pitches"].items()],
            "select": "one", "raised": {"by": "page", "at": NOW()}, "answer": {"value": a["value"], "text": a["text"], "at": NOW()}})
        self.store.merge("projects/%s" % KEY, {"plan": a["plan"]})                                            # page-owned
        self.store.merge("projects/%s/stages/plan" % KEY, {"pitchId": a["value"], "greenlit": {"by": "owner", "at": NOW()}})   # page-owned
        self.say('  the owner picked %s: "%s"  (pre-recorded answer)\n' % (a["value"], a["text"]))

        self.say("S2 Design (script)")
        c, runs = self.stage("Write the script for the greenlit plan. " + a["text"], "design")
        bad = self.blocked(c, runs)
        if bad:
            return self.finish(res, bad)
        path = "decisions/approve-%s-script" % KEY
        self.store.put(path, {"kind": "approve", "policyKey": "approve.script", "projectKey": KEY, "question": "Approve script s1 for recording?",
                              "options": [{"id": "approve", "label": "Approve"}, {"id": "notes", "label": "Send notes"}], "select": "one",
                              "target": {"deliverableId": "script", "version": "s1"}, "raised": {"by": "page", "at": NOW()}})
        self.say("\n  OWNER GATE 2: approve the script  [%s]" % path)
        self.say("  not answered: the run stops here. S3 Capture starts only after a person says yes.")
        res["waitingOn"] = path
        return self.finish(res, None)

    def blocked(self, c, runs):
        """-> a reason the hand-off does not happen, or None."""
        if c["state"] != "done":
            b = c.get("block") or {}
            self.say("\n  STOPPED: job ended %s%s" % (c["state"], (": " + b.get("cause", "")) if b else ""))
            if b:
                self.say("  fix: %s" % b.get("fix"))
            return "job:" + c["state"]
        if not runs:
            self.say("\n  HELD: the stage finished but no gate run exists for it. No gate, no hand-off.")
            return "no-gate"
        for r in runs:
            if not r["pass"]:
                return self.hold(r)
        r = runs[-1]
        self.say("  gate %s PASS (%d warning%s, run %s)" % (r["gate"], len(r["warnings"]), "" if len(r["warnings"]) == 1 else "s", r["runId"]))
        return None

    def finish(self, res, held):
        res.update(held=bool(held), heldAt=held, jobs=self.jobs, gates=self.gates, dropped=self.dropped,
                   decisions=sorted(p for p in self.store.docs() if p.startswith("decisions/")))
        self.say("\nSummary")
        self.say("  jobs       %s" % ", ".join("%s=%s" % (j["profile"], j["state"]) for j in self.jobs))
        self.say("  gate runs  %s" % (", ".join("%s=%s" % (g["stage"], "pass" if g["pass"] else "FAIL") for g in self.gates) or "none"))
        self.say("  dropped    %d write(s) outside a lane" % len(self.dropped))
        self.say("  decisions  %s" % ", ".join(res["decisions"]))
        self.say("  result     %s" % ("HELD: " + str(held) if held else "waiting on the owner: " + str(res["waitingOn"])))
        return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bad", action="store_true", help="the design agent hands back a deliberately bad script")
    ap.add_argument("--mode", choices=["good", "bad", "deny"], help="stub behaviour (default good; --bad = bad)")
    ap.add_argument("--work", default=os.path.join(REPO, ".work"), help="scratch folder: store, bundles, runs, job state (wiped first)")
    a = ap.parse_args()
    res = Pipeline(a.work, a.mode or ("bad" if a.bad else "good")).go()
    return 1 if res["held"] else 0


if __name__ == "__main__":
    sys.exit(main())
