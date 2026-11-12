"""Shared helpers for the stage gate checkers (qa/checks/*.py).

Every checker prints one JSON report on stdout (and writes it with -o):
  {stage, gate, artifact, version, pass, checks:{<name>:{status: pass|fail|warn|skipped, detail, ...}}, failures:[{check, detail}]}
pass = no check has status "fail". Warnings never fail a gate. A failed gate goes to the owner as a fix-or-waive decision (PIPELINE.md section 5).
"""
import json, os, re, sys
from datetime import datetime, timezone

WPM = 150
COMMUNITY = re.compile(r"\bcommunity\b", re.I)
CALL = re.compile(r"\bbook (a|your) call\b|example\.com/book", re.I)


def load_doc(path):
    """Episode-shape doc (bare fields, or wrapped in {data})."""
    d = json.load(open(path))
    return d.get("data", d) if isinstance(d, dict) else d


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chk(status, detail, **extra):
    return {"status": status, "detail": detail, **extra}


def report(stage, gate, artifact, version, checks, out=None):
    failures = [{"check": k, "detail": c["detail"]} for k, c in checks.items() if c["status"] == "fail"]
    doc = {"stage": stage, "gate": gate, "artifact": artifact, "version": version, "pass": not failures,
           "checks": checks, "failures": failures, "at": now()}
    s = json.dumps(doc, indent=1)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        open(out, "w").write(s)
    print(s)
    for k, c in checks.items():
        print(f"  {c['status'].upper():7} {k:20} {c['detail']}", file=sys.stderr)
    print(("PASS" if doc["pass"] else "FAIL") + f"  {gate}  {artifact}", file=sys.stderr)
    return doc


def words(s):
    return re.findall(r"[A-Za-z0-9'’$%.-]+", s or "")


def active_ctas(doc):
    return [c for c in doc.get("ctas") or [] if not c.get("retired")]


def community_cta(doc):
    return next((c for c in active_ctas(doc) if c.get("target") == "community" and c.get("standard")), None) \
        or next((c for c in active_ctas(doc) if c.get("target") == "community"), None)

