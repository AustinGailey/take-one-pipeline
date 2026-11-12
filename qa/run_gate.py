#!/usr/bin/env python3
"""Run one stage gate as an independent QA run and write its outputs. Run by the `qa` profile, never by a producer.

  python3 qa/run_gate.py <gate> --bundle <jobs/runs/<job>/bundle.json> [options]
  python3 qa/run_gate.py <gate> --key <projectKey> --doc projects/<key>/stages/script=<file.json> [--doc <path>=<file> ...]

  gate      plan | script            (the two checkers published in this repo; the other seven gate specs are in qa/gates/)
  --bundle  the dispatch bundle (its `docs` map, keyed by store path, is the gate's input); --doc adds or overrides one doc
  --key     the project key; default: the bundle's projectKey, else the first projects/<key>/ doc path
  --out-dir where reports go (default: .work/qa/<key>/ under the repo)
  --run-id  the qa run id; default <gate>-<yyyymmddThhmmss> UTC
  --job     the dispatch job id (sj-<requestId>); goes in the run's `jobId`
  --producer-agent / --producer-stage   the agent and stage that produced the artifact. Refused when the producer is the
            qa profile itself: producer != checker (PIPELINE.md 1.3; the qa lane is the only one that writes projects/{key}/qa/*).
  --history plan: a JSON list of other projects' plan blocks ({title, promise}), newest last, for the repeat check

Writes  <out-dir>/<gate>.json            the full gate report (every check)
        <out-dir>/runs/<runId>.json      the same report, kept per run
        <out-dir>/<runId>.write.json     the results.json `writes[]` entry: {path: projects/<key>/qa/<runId>, op: create, data}
and prints that write entry on stdout. Every run is a NEW doc projects/<key>/qa/<runId>; never a set on an existing one.
Exit is always 0 once a report exists; pass/fail is in the JSON. A checker that crashes writes no report: never a pass.

The checkers in qa/checks/ read an "episode shape" (chapters[].script, coldOpen, demos[].narration); `episode_shape()`
builds it from the stage docs (maps keyed by id become lists in `order`). Stdlib only.

This file is the published subset of the production runner: the plan and script gates. The production file also drives
the research, storyboard, capture, edit, package, publish and measure checkers, which depend on media tools and
rulebooks that are not in this repo.
"""
import argparse, json, os, re, shlex, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
AGENT, PROFILE = "content-qa", "qa"
GATES = ["plan", "script"]
ALL_GATES = ["research", "plan", "script", "storyboard", "capture", "edit", "package", "publish", "measure"]


def sh(cmd, log):
    print("+", " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
    with open(log, "w") as f:
        return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode


def unwrap(d):
    """A doc saved bare, or wrapped as {data} / {version, data}."""
    if isinstance(d, dict) and isinstance(d.get("data"), dict) and set(d) <= {"data", "version", "path", "id", "updatedAt", "createdAt", "exists"}:
        return d["data"]
    return d if isinstance(d, dict) else {}


def aslist(m, idkey="id"):
    """Maps keyed by id (with `order`) -> the list shape the checkers read; lists pass through."""
    if isinstance(m, list):
        return [x for x in m if isinstance(x, dict)]
    if not isinstance(m, dict):
        return []
    out = []
    for k, v in m.items():
        if isinstance(v, dict):
            v = dict(v); v.setdefault(idkey, k)
            out.append(v)
    return sorted(out, key=lambda x: (x.get("order") is None, x.get("order") if isinstance(x.get("order"), (int, float)) else 0, str(x.get(idkey))))


def vnum(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 0


class Docs:
    """The bundle's docs keyed by store path, with the lookups the gates need."""

    def __init__(self, docs, key):
        self.d = {p: unwrap(v) for p, v in docs.items()}
        self.key = key
        self.P = f"projects/{key}"

    def get(self, path):
        return self.d.get(path) or {}

    def stage(self, name):
        return self.get(f"{self.P}/stages/{name}")

    def marks(self, scope):
        return self.get(f"{self.P}/marks/{scope}")

    def project(self):
        return self.get(self.P)

    def versions(self, deliverable):
        """[(v, doc)] of projects/<key>/deliverables/<id>/versions/<v>, highest number last."""
        pre = f"{self.P}/deliverables/{deliverable}/versions/"
        xs = [(p[len(pre):], v) for p, v in self.d.items() if p.startswith(pre) and "/" not in p[len(pre):]]
        return sorted(xs, key=lambda x: vnum(x[0]))

    def deliverables(self, pattern):
        rx = re.compile(rf"^{re.escape(self.P)}/deliverables/({pattern})$")
        return sorted((m.group(1), v) for p, v in self.d.items() for m in [rx.match(p)] if m)

    def topic(self):
        tid = self.project().get("topicId") or self.stage("research").get("topicId")
        t = self.get(f"topics/{tid}") if tid else {}
        if not t:
            return {}
        out = dict(t.get("candidate") or {})
        out.update({k: v for k, v in t.items() if k != "candidate"})
        return out

    def script_version(self):
        """The script version the gate reads: stages/script.frozen.v (owner) > marks/dl-script.current.v > stages/script.current > newest."""
        sc, mk = self.stage("script"), self.marks("dl-script")
        v = ((sc.get("frozen") or {}).get("v")) or ((mk.get("dl") or mk).get("current") or {}).get("v") or sc.get("current")
        vs = self.versions("script")
        if v and any(x[0] == v for x in vs):
            return v, dict(x for x in vs)[v]
        return (vs[-1][0], vs[-1][1]) if vs else (v or "", {})


def episode_shape(D):
    """The shape the script checker reads, built from the stage docs."""
    proj = D.project()
    doc = {"key": D.key, "code": proj.get("code"), "title": proj.get("title"), "plan": proj.get("plan") or {},
           "promise": (proj.get("plan") or {}).get("promise"), "updated": proj.get("updatedAt", "")}
    bp = (D.stage("design") or {}).get("blueprint") or {}
    if bp.get("targetMinutes"):
        doc["targetMinutes"] = bp["targetMinutes"]

    # outline from stages/script, line text from the script version
    sc = D.stage("script")
    sv, sdoc = D.script_version()
    lines = {k: (v if isinstance(v, dict) else {"text": v}) for k, v in (sdoc.get("lines") or {}).items()}
    if sc or lines:
        text = lambda lid: (lines.get(lid) or {}).get("text", "")
        chapters = []
        for c in aslist(sc.get("chapters")):
            ids = c.get("lineIds") or [k for k, l in lines.items() if l.get("block") == c["id"]]
            ids = sorted(ids, key=lambda k: (lines.get(k) or {}).get("order") or 0)
            chapters.append(dict(c, script=[dict(lines.get(i) or {}, id=i, text=text(i)) for i in ids]))
        # Every lines[].text counts (escape esc-014): lines the outline does not reach are grouped by block into synthetic
        # chapters, except the cold open (below), demo narration and the CTA/hook banks.
        placed = {l["id"] for ch in chapters for l in ch["script"]}
        co_ids = {c.get("lineId") for c in aslist(sc.get("coldOpen")) if c.get("lineId")} | {k for k, l in lines.items() if l.get("block") == "cold-open"}
        loose = {}
        for k, l in sorted(lines.items(), key=lambda kv: kv[1].get("order") or 0):
            if k in placed or k in co_ids or l.get("block") in ("demo", "cta", "hook") or not str(l.get("text", "")).strip():
                continue
            loose.setdefault(l.get("block") or "lines", []).append(dict(l, id=k, text=text(k)))
        for blk, ls in loose.items():
            chapters.append({"id": "unplaced-" + blk, "title": f"{blk} (lines not placed in a chapter)", "block": blk, "script": ls, "unplaced": True})
        doc["chapters"] = chapters
        cands = aslist(sc.get("coldOpen")) or [{"id": k, "lineId": k} for k, l in sorted(lines.items(), key=lambda kv: kv[1].get("order") or 0) if l.get("block") == "cold-open"]
        co_lines = [dict(lines.get(c["lineId"]) or {}, id=c["lineId"], text=text(c["lineId"])) for c in cands if c.get("lineId")]
        doc["coldOpen"] = " ".join(l["text"] for l in co_lines if l.get("text"))
        for sec in ("ctas", "experiments"):
            doc[sec] = aslist(sc.get(sec))
        doc["lineage"] = {"scriptVersion": sv}
    # demo narration: the version's lines with block "demo" and ids dN-NN, one demo per id prefix
    demos = {}
    for k, l in sorted(lines.items(), key=lambda kv: kv[1].get("order") or 0):
        if l.get("block") == "demo" and str(l.get("text", "")).strip():
            demos.setdefault(k.split("-")[0] if re.match(r"^d\d+-", k) else "demo", []).append(dict(l, id=k))
    if demos:
        doc["demos"] = [{"id": did, "narration": ls} for did, ls in demos.items()]
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gate", choices=ALL_GATES)
    ap.add_argument("--bundle")
    ap.add_argument("--doc", action="append", default=[], metavar="PATH=FILE")
    ap.add_argument("--key")
    ap.add_argument("--out-dir")
    ap.add_argument("--run-id")
    ap.add_argument("--job", default="")
    ap.add_argument("--producer-agent", default="")
    ap.add_argument("--producer-stage", default="")
    ap.add_argument("--history")
    a = ap.parse_args()
    if a.producer_agent.strip().lower() == AGENT or a.producer_stage.strip().lower() in ("qa", PROFILE):
        sys.exit(f"refused: producer and checker are both {AGENT} (PIPELINE.md 1.3; projects/{{key}}/qa/* is the qa lane only)")
    if a.gate not in GATES:
        sys.exit(f"the {a.gate} gate's spec is qa/gates/{a.gate}.md; its checker is not part of this repo (it needs media tools and rulebooks that are not published)")

    b = {}
    if a.bundle:
        b = json.load(open(a.bundle))
    docs = dict(b.get("docs") or {})
    for spec in a.doc:
        if "=" not in spec:
            sys.exit(f"--doc wants <store path>=<file>: {spec}")
        p, f = spec.split("=", 1)
        docs[p.strip()] = json.load(open(os.path.expanduser(f)))
    key = a.key or b.get("projectKey") or next((m.group(1) for p in docs for m in [re.match(r"^projects/([^/]+)", p)] if m), None)
    if not key:
        sys.exit("no project key: pass --key or a bundle/doc under projects/<key>/")
    if not docs:
        sys.exit("no docs: pass --bundle <bundle.json> and/or --doc <store path>=<file>")
    D = Docs(docs, key)
    ctx = ((b.get("request") or {}).get("context") or {})
    if not a.producer_stage and ctx.get("gate"):
        a.producer_stage = str(ctx["gate"])
    qa = os.path.abspath(a.out_dir or os.path.join(REPO, ".work", "qa", key))
    raw = os.path.join(qa, "raw", a.gate)
    os.makedirs(raw, exist_ok=True); os.makedirs(os.path.join(qa, "runs"), exist_ok=True)
    run_id = a.run_id or f"{a.gate}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
    run_id = re.sub(r"[^\w.:@+~-]", "-", run_id)
    out = os.path.join(qa, f"{a.gate}.json")
    if os.path.exists(out):
        os.remove(out)          # a stale report from an earlier run must never stand in for this one
    py = sys.executable
    target, version = {"stage": a.gate}, ""

    if a.gate == "plan":
        version = str((D.stage("plan") or {}).get("pitchId") or (D.stage("research") or {}).get("version") or "")
        plan_in = os.path.join(raw, "plan-input.json")
        json.dump({"project": D.project(), "plan": D.stage("plan"), "research": D.stage("research"), "topic": D.topic(),
                   "packageVersions": [v for v, _ in D.versions("package")], "skips": D.marks("skips")}, open(plan_in, "w"), indent=1)
        sh([py, os.path.join(HERE, "checks/plan_check.py"), "--input", plan_in, "--version", version]
           + (["--history", a.history] if a.history else []) + ["-o", out], os.path.join(raw, "plan_check.log"))

    else:   # script
        doc = episode_shape(D)
        docp = os.path.join(raw, "episode-shape.json")       # the adapter's view of the stage docs, kept for the record
        json.dump(doc, open(docp, "w"), indent=1)
        version = str((doc.get("lineage") or {}).get("scriptVersion") or "")
        target = {"deliverableId": "script", "version": version}
        sh([py, os.path.join(HERE, "checks/script_check.py"), "--doc", docp, "--version", version,
            "--artifact", f"projects/{key}/stages/script + deliverables/script/versions/{version}", "-o", out], os.path.join(raw, "script_check.log"))

    if not os.path.exists(out):
        sys.exit(f"the checker wrote no report ({out}); see {raw}/*.log. A gate that crashes is never a pass.")
    rep = json.load(open(out))
    stage = rep.get("stage") or a.gate
    checks = rep.get("checks") or {}
    order = list(checks)
    failures = {k: {"detail": c.get("detail", ""), "order": order.index(k)} for k, c in checks.items() if c.get("status") == "fail"}
    warnings = {k: {"detail": c.get("detail", "")} for k, c in checks.items() if c.get("status") == "warn"}
    skipped = bool(checks) and all(c.get("status") == "skipped" for c in checks.values())   # not a pass
    data = {"runId": run_id, "stage": stage, "gate": rep.get("gate") or f"qa/gates/{a.gate}.md", "target": dict(target, stage=target.get("stage", stage)),
            "artifactVersion": version or None, "pass": bool(rep.get("pass")) and not failures, "failures": failures, "warnings": warnings,
            "skipped": skipped, "notes": list(rep.get("notes") or []), "report": {"ref": os.path.relpath(out, REPO) if out.startswith(REPO + os.sep) else os.path.basename(out)},
            "jobId": a.job or None, "producer": {"agent": a.producer_agent or None, "stage": a.producer_stage or None}, "at": rep.get("at")}
    rep.update({"runId": run_id, "projectKey": key, "jobId": a.job or None})
    json.dump(rep, open(out, "w"), indent=1)
    json.dump(rep, open(os.path.join(qa, "runs", f"{run_id}.json"), "w"), indent=1)
    write = {"path": f"projects/{key}/qa/{run_id}", "op": "create", "data": data}
    json.dump(write, open(os.path.join(qa, f"{run_id}.write.json"), "w"), indent=1)
    print(json.dumps(write, indent=1))
    print(("SKIPPED" if skipped else "PASS" if data["pass"] else f"FAIL {len(failures)} check(s)") + f"  {run_id}  {len(warnings)} warning(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
