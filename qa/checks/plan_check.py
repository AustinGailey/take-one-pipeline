#!/usr/bin/env python3
"""S1 Plan gate (qa/gates/plan.md). Reads the greenlight record and what it was built from: projects/<key> (plan.*, topicId,
deliverablePlan), projects/<key>/stages/plan (the plan profile's proposal + the owner's greenlight), stages/research (pitches,
demo verdict, deliverable candidates) and the topic. SCHEMA.md §3.project, §3.stage-plan, §3.stage-research.

  python3 qa/checks/plan_check.py --input <plan-input.json> [--history <json list of {title, promise}>] [--version X] [-o qa/plan.json]

The input is what run_gate.py assembles: {project, plan, research, topic, packageVersions[], skips}. Criteria: PIPELINE.md S1 row
("promise is a concrete outcome; demoable with our tools; not a repeat within 8 episodes") and PIPELINE.md §8 A (trust job).
The package concept itself is the package gate's `--phase concept`.
"""
import argparse, json, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import chk, report, words

TRUST = {"competence", "connection", "relevance", "proof"}
VAGUE = re.compile(r"\b(learn about|understand(ing)?|overview|introduction to|intro to|tips( and tricks)?|everything you need|get started with|the basics)\b", re.I)
OUTCOME = re.compile(r"\b(\d+|one|two|three|four|five|a|an|your|the)\s+(\w+\s+){0,3}(page|doc|document|system|workflow|template|checklist|prompt|agent|report|plan|script|site|page|dashboard|sheet|list|kit|board|calendar|pipeline|bot|tool|file|email|post|video|course|lesson|funnel|form|audit|map)s?\b", re.I)
STOP = set("a an the and or but of to in on for with your you my i me we our it its is are be this that these those how what why from at by as into one 1 vs just get got make made can do does did not no all every each per own using use".split())
REPEAT_WINDOW = 8


def cwords(s):
    return {w.lower().rstrip("s") for w in words(s) if w.lower() not in STOP and len(w) > 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--history")
    ap.add_argument("--version", default="")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    I = json.load(open(a.input))
    proj, plan, R, topic = I.get("project") or {}, I.get("plan") or {}, I.get("research") or {}, I.get("topic") or {}
    pp = proj.get("plan") or {}
    skips = (I.get("skips") or {}).get("gates") or {}
    C = {}

    # the plan exists: the owner's adopted values on the project doc (page) or the plan profile's proposal (S1 lane)
    promise = str(pp.get("promise") or plan.get("promise") or "").strip()
    title = str(proj.get("title") or plan.get("title") or "").strip()
    have = {k: bool(pp.get(k) or plan.get(k)) for k in ("promise", "audience", "angle")}
    have["title"] = bool(title)
    missing = [k for k, v in have.items() if not v]
    C["plan_present"] = chk("fail" if missing else "pass", f"missing {missing} (projects/<key>.plan.* or stages/plan)" if missing
                            else f"title, promise, audience, angle present ({'adopted on the project doc' if pp.get('promise') else 'S1 proposal only, not adopted yet'})")
    if not promise:
        return report("plan", "qa/gates/plan.md", "projects.plan + stages/plan", a.version, C, a.out)

    # promise is a concrete outcome (after-state the viewer leaves with), not a topic
    n = len(words(promise))
    vague = VAGUE.search(promise)
    C["promise_concrete"] = chk("fail" if vague or n < 5 else ("warn" if not OUTCOME.search(promise) and not re.search(r"\d", promise) else "pass"),
                                (f"'{promise}': " + ("vague phrasing '%s'" % vague.group(0) if vague else f"only {n} words" if n < 5 else "names no deliverable or number (is it an after-state?)"))
                                if (vague or n < 5 or not (OUTCOME.search(promise) or re.search(r"\d", promise))) else f"'{promise}' names an outcome")
    C["before_after"] = chk("pass" if pp.get("before") else "warn", "before-state set in the greenlight room" if pp.get("before") else "projects.plan.before is empty (the greenlight room builds before -> after)")

    tj = pp.get("trustJob") or plan.get("trustJob") or (R.get("pitches") or {}).get(plan.get("pitchId") or "", {}).get("trustJob") if isinstance(R.get("pitches"), dict) else pp.get("trustJob")
    C["trust_job"] = chk("pass" if tj in TRUST else "warn", f"trustJob {tj}" if tj in TRUST else f"plan.trustJob missing or not one of {sorted(TRUST)} (PIPELINE §8 A)")

    # the greenlit pitch comes from the dossier
    pitches = R.get("pitches") or {}
    pl = pitches if isinstance(pitches, dict) else {p.get("id"): p for p in pitches if isinstance(p, dict)}
    pid = plan.get("pitchId")
    if not pl:
        C["pitch_from_dossier"] = chk("warn", "stages/research has no pitches (S1 proposals): the plan was not weighed against alternatives")
    elif pid and pid in pl:
        C["pitch_from_dossier"] = chk("pass", f"greenlit pitch {pid} is in the dossier")
    elif pid:
        C["pitch_from_dossier"] = chk("fail", f"stages/plan.pitchId {pid} is not a dossier pitch {sorted(pl)[:6]}")
    else:
        near = [k for k, p in pl.items() if len(cwords(promise) & cwords(str(p.get("promise", "")))) >= 2]
        C["pitch_from_dossier"] = chk("pass" if near else "warn", f"no pitchId yet; promise matches pitch {near[0]}" if near else "no pitchId and the promise matches no dossier pitch")

    demo = R.get("demo") or {}
    verdict = str(demo.get("verdict") or "").lower()
    C["demoable"] = chk("pass" if verdict == "yes" else "fail" if verdict == "no" else "warn",
                        f"dossier demo verdict '{verdict or 'missing'}'" + (f": {demo.get('why') or demo.get('note') or ''}" if verdict != "yes" else ""))

    dp = proj.get("deliverablePlan") or {}
    kinds = [k for k, v in dp.items() if not (isinstance(v, dict) and v.get("drop"))]
    C["deliverable_planned"] = chk("fail" if not kinds else "pass", f"deliverablePlan: {kinds}" if kinds else "projects.deliverablePlan is empty: nothing planned to make")
    chosen = [d.get("id") for d in (R.get("deliverables") if isinstance(R.get("deliverables"), list) else list((R.get("deliverables") or {}).values())) if isinstance(d, dict) and d.get("chosen")]
    if dp and "lead-magnet" not in kinds and chosen:
        C["deliverable_planned"]["detail"] += f"; dossier chose {chosen} but no lead-magnet in deliverablePlan"
        C["deliverable_planned"]["status"] = "warn" if C["deliverable_planned"]["status"] == "pass" else C["deliverable_planned"]["status"]

    si = pp.get("signatureIdea") or plan.get("signatureIdea")
    C["signature_idea"] = chk("pass" if si else "warn", f"signature idea: {str(si)[:80]}" if si else "no signatureIdea (what makes this one ours)")

    # not a repeat within 8 episodes (needs the history run_gate.py cannot build from one bundle)
    if a.history and os.path.exists(a.history):
        hist = json.load(open(a.history))[-REPEAT_WINDOW:]
        mine = cwords(promise) | cwords(title)
        hits = [(h.get("key") or h.get("code") or h.get("title", "")[:30], len(mine & (cwords(h.get("promise", "")) | cwords(h.get("title", "")))))
                for h in hist if isinstance(h, dict)]
        rep = [f"{k} ({n} shared words)" for k, n in hits if mine and n / max(1, len(mine)) >= 0.6]
        C["not_repeat"] = chk("fail" if rep else "pass", f"repeats {rep}" if rep else f"distinct from the last {len(hist)} projects")
    else:
        C["not_repeat"] = chk("skipped", "no --history (last 8 projects' plan blocks) given")

    kv = I.get("packageVersions") or []
    C["package_concept"] = chk("pass" if kv else "warn", f"package concept version(s) {kv} (checked by qa/gates/package.md#concept)" if kv
                               else "no package concept yet (package-first: S1 ends with titles + thumbnail concepts)")
    g = plan.get("greenlit")
    if g and not (pid or pp.get("promise")):
        C["greenlit_consistent"] = chk("warn", "stages/plan.greenlit set but no pitchId and no adopted promise on the project doc")
    elif g:
        C["greenlit_consistent"] = chk("pass", f"greenlit by {g.get('by')} at {g.get('at')}")
    if skips:
        C["skips"] = chk("warn", f"the owner skipped gate checks: {sorted(skips)}")
    report("plan", "qa/gates/plan.md", "projects.plan + stages/plan", a.version or str(pid or ""), C, a.out)


if __name__ == "__main__":
    main()
