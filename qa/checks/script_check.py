#!/usr/bin/env python3
"""S2 Script gate (qa/gates/script.md). Reads the episode doc only; never edits it.

  python3 qa/checks/script_check.py --doc episode.json [--target-min N] [-o episodes/<id>/qa/script.json]

Checks
  script_present     every chapter has script lines (chapters[].script); points-only chapters = legacy, fail
  runtime            spoken words / 150 wpm within +-15% of the target (episode.targetMinutes, else sum of chapter minutes)
  experiment_share   lines carrying `exp` <= 30% of script lines; every `exp` id defined in episode.experiments
  stage_directions   no production notes in speakable text: coldOpen, script/narration `text`, and
                     chapter `points` (the presenter reads points on camera too)
  community_cta      a standard community CTA exists, the long-form close ends on it, no spoken "book a call"
  claims_sourced     numeric claims (%, x, $, "N out of M") carry `source`, `source: <url>` in `show`, `opinion: true` or opinion
                     phrasing ("I think"); softer claim words warn
"""
import argparse, re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from common import WPM, COMMUNITY, CALL, load_doc, chk, report, words, community_cta

# Production notes that got read on camera in the first episode (the escape that created this check), plus generic edit cues.
DIRECTION = re.compile(
    r"\b(diagram|call ?out|callout|chapter card|lower third|title card|b-roll|broll|on[- ]screen|cut to|zoom (in|to|on)|"
    r"sfx|vo|super|overlay|cutaway|split screen)\s*[:\-—]|"
    r"^\s*(live|saved prompt|example wording|show|demo|graphic|visual|screen|text)\s*:|"
    r"\[[^\]]+\]|\((pause|beat|laughs?|cut|b-roll|on screen)[^)]*\)|"
    r"\bchapter card\b|\bcall ?out\b",
    re.I | re.M)
NUMERIC = re.compile(r"\d+(\.\d+)?\s*(%|percent|x\b|times\b)|\$\s?\d|\b\d+ (out of|in) \d+\b", re.I)
OPINION = re.compile(r"\b(i think|i believe|in my experience|i'd say|my take|i find)\b", re.I)
SOFT = re.compile(r"\b(most|studies|research|data shows|on average|everyone|nobody|always|never)\b", re.I)
SENT = re.compile(r"(?<=[.!?])\s+")


def spoken(doc):
    """[(where, text, line)] for everything that is said on camera in the long-form."""
    out = [(f"coldOpen#{i+1}", s, {}) for i, s in enumerate(SENT.split(doc.get("coldOpen") or "")) if s.strip()]
    for ci, ch in enumerate(doc.get("chapters") or []):
        for ln in ch.get("script") or []:
            out.append((ln.get("id") or f"c{ci+1}", ln.get("text", ""), ln))
    for d in doc.get("demos") or []:
        for j, ln in enumerate(d.get("narration") or []):
            out.append((ln.get("id") or f"{d.get('id')}-n{j+1}", ln.get("text", ""), ln))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--target-min", type=float)
    ap.add_argument("--version", default="")
    ap.add_argument("--artifact", help="what the row names (default: the --doc path)")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    doc = load_doc(a.doc)
    chapters = doc.get("chapters") or []
    lines = spoken(doc)
    script_lines = [l for l in lines if not l[0].startswith("coldOpen")]
    checks = {}

    # script_present
    missing = [c.get("title") for c in chapters if not c.get("script")]
    legacy = bool(missing)
    checks["script_present"] = chk("fail" if missing else "pass",
        f"{len(missing)}/{len(chapters)} chapters have talking points only (no script lines): {missing}" if missing
        else f"{len(chapters)} chapters scripted, {len(script_lines)} lines", chapters_unscripted=missing)

    # runtime (legacy: points stand in for lines, because the presenter reads them; reported as a proxy)
    target = a.target_min or doc.get("targetMinutes") or sum(float(c.get("minutes") or 0) for c in chapters)
    n = sum(len(words(t)) for _, t, _ in lines)
    if legacy:
        n += sum(len(words(p)) for c in chapters if not c.get("script") for p in c.get("points") or [])
    cta = community_cta(doc)
    n += len(words(cta["text"])) if cta else 0
    est = n / WPM
    lo, hi = target * 0.85, target * 1.15
    ok = lo <= est <= hi if target else False
    checks["runtime"] = chk("pass" if ok else "fail",
        f"{n} words -> {est:.1f} min at {WPM} wpm vs target {target:.1f} min (allowed {lo:.1f}-{hi:.1f})"
        + (" [proxy: talking points]" if legacy else ""), words=n, est_min=round(est, 2), target_min=target)

    # experiment_share
    exps = {e.get("id") for e in doc.get("experiments") or []}
    in_exp = [l for l in script_lines if l[2].get("exp")]
    undefined = sorted({l[2]["exp"] for l in in_exp} - exps)
    share = len(in_exp) / len(script_lines) if script_lines else 0.0
    if not script_lines:
        checks["experiment_share"] = chk("skipped", "no script lines to measure")
    else:
        checks["experiment_share"] = chk("fail" if share > 0.30 or undefined else "pass",
            f"{len(in_exp)}/{len(script_lines)} lines in experiments ({share:.0%}, limit 30%)"
            + (f"; undefined experiment ids {undefined}" if undefined else ""), share=round(share, 3))

    # stage_directions
    hits = []
    for where, t, _ in lines:
        m = DIRECTION.search(t)
        if m:
            hits.append({"where": where, "match": m.group(0).strip(), "text": t[:120]})
    for ci, c in enumerate(chapters):
        for pi, p in enumerate(c.get("points") or []):
            m = DIRECTION.search(p)
            if m:
                hits.append({"where": f"ch{ci+1}.points[{pi}]", "match": m.group(0).strip(), "text": p[:120]})
    checks["stage_directions"] = chk("fail" if hits else "pass",
        f"{len(hits)} production notes in speakable text" + (": " + "; ".join(f"{h['where']} '{h['match']}'" for h in hits[:8]) if hits else ""),
        hits=hits)

    # community_cta
    probs = []
    if not cta:
        probs.append("no active community CTA in ctas")
    close = ""
    if chapters and chapters[-1].get("script"):
        close = chapters[-1]["script"][-1].get("text", "")
        if not (COMMUNITY.search(close) or chapters[-1]["script"][-1].get("ctaId") == (cta or {}).get("id")):
            probs.append(f"long-form close does not end on the community CTA: '{close[:80]}'")
    called = [w for w, t, _ in lines if CALL.search(t)]
    if called:
        probs.append(f"spoken booking CTA at {called} (booking link belongs on the description's last line only)")
    live_call = [c["id"] for c in (doc.get("ctas") or []) if c.get("target") == "call" and not c.get("retired")]
    if live_call:
        probs.append(f"active call CTA {live_call} (should be retired)")
    detail = "; ".join(probs) or f"community CTA {cta['id']} standard" + (", close ends on it" if close else " (no scripted close to check; closing CTA appended at edit)")
    checks["community_cta"] = chk("fail" if probs else "pass", detail)

    # claims_sourced
    num, soft = [], []
    for where, t, ln in lines:
        if ln.get("source") or ln.get("opinion") or "source:" in (ln.get("show") or "").lower() or OPINION.search(t):
            continue
        if NUMERIC.search(t):
            num.append(f"{where}: '{t[:70]}'")
        elif SOFT.search(t):
            soft.append(where)
    st = "fail" if num else ("warn" if soft else "pass")
    checks["claims_sourced"] = chk(st, (f"{len(num)} numeric claims without source/opinion: {num[:5]}" if num else "no unsourced numeric claims")
        + (f"; {len(soft)} soft generalisations to eyeball: {soft[:8]}" if soft else ""))

    report("script", "qa/gates/script.md", a.artifact or a.doc, a.version or str(doc.get("updated", "")), checks, a.out)


if __name__ == "__main__":
    main()
