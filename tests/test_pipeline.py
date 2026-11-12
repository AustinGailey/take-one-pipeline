"""End-to-end tests: the sample project through the real dispatcher, supervisor, lanes and gates, with the stub agent.

No model, no network, no keys. Each test gets its own work folder (store, runs, job state).
"""
import json, os, subprocess, sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "sample"))
import run_sample  # noqa: E402


def run(tmp_path, mode):
    p = run_sample.Pipeline(str(tmp_path / "work"), mode, quiet=True)
    return p, p.go()


def test_clean_run_passes_both_gates_and_stops_at_the_owner(tmp_path):
    p, res = run(tmp_path, "good")
    assert not res["held"]
    assert [(j["profile"], j["state"]) for j in res["jobs"]] == [("plan", "done"), ("qa", "done"), ("design", "done"), ("qa", "done")]
    assert [(g["stage"], g["pass"]) for g in res["gates"]] == [("plan", True), ("script", True)]
    assert res["dropped"] == []
    # the run ends on a person, not on the next stage: the approval card exists and has no answer
    assert res["waitingOn"] == "decisions/approve-kc-001-script"
    assert "answer" not in p.store.get(res["waitingOn"])
    assert p.store.get("projects/kc-001/stages/capture") is None


def test_gate_blocks_a_deliberately_bad_script(tmp_path):
    p, res = run(tmp_path, "bad")
    assert res["held"]
    gate = res["gates"][-1]
    assert gate["stage"] == "script" and gate["pass"] is False
    assert {"stage_directions", "claims_sourced"} <= set(gate["failures"])
    # the failing run is on the record, written by the qa job and naming the producer
    stored = p.store.get(gate["path"])
    assert stored["pass"] is False and stored["producer"]["stage"] == "design"
    assert stored["jobId"] == res["jobs"][-1]["job"] and res["jobs"][-1]["profile"] == "qa"
    # the hand-off is held on one fix-or-waive card; no approval card was raised and nothing downstream exists
    assert res["heldAt"].startswith("decisions/fix-kc-001-script-")
    assert p.store.get(res["heldAt"])["policyKey"] == "fix.gate"
    assert p.store.get("decisions/approve-kc-001-script") is None


def test_producer_cannot_pass_its_own_gate_or_write_owner_fields(tmp_path):
    p, res = run(tmp_path, "bad")
    dropped = {d["path"]: d for d in res["dropped"]}
    # the design agent wrote projects/kc-001/qa/script-self-check {pass: true}: outside its lane, never applied
    assert dropped["projects/kc-001/qa/script-self-check"]["why"] == "outside this stage's lane"
    assert p.store.get("projects/kc-001/qa/script-self-check") is None
    # it also set the owner's freeze on the script: stripped, the rest of the doc applied
    assert "frozen (page-owned)" in dropped["projects/kc-001/stages/script"]["fields"]
    assert "frozen" not in p.store.get("projects/kc-001/stages/script")
    # dropped writes are never silent: a file on disk and a decision card
    design_job = next(j["job"] for j in res["jobs"] if j["profile"] == "design")
    on_disk = json.load(open(os.path.join(res["work"], "runs", design_job, "dropped.json")))
    assert len(on_disk) == 2
    assert p.store.get("decisions/lane-" + design_job)["policyKey"] == "fix.lane"
    # every qa doc in the store came from a qa job
    qa_docs = [k for k in p.store.docs() if "/qa/" in k]
    assert len(qa_docs) == 2 and all(p.store.get(k)["jobId"] in {j["job"] for j in res["jobs"] if j["profile"] == "qa"} for k in qa_docs)


def test_denied_tool_ends_the_job_as_a_setup_block(tmp_path):
    p, res = run(tmp_path, "deny")
    assert res["held"] and res["heldAt"] == "job:needs-owner"
    job = res["jobs"][0]
    assert job["state"] == "needs-owner"
    assert job["block"]["key"] == "bash:curl" and job["block"]["tool"] == "Bash"
    assert 'profiles.plan.allow += "Bash(curl:*)"' in job["block"]["line"]
    assert res["gates"] == [] and p.store.get("projects/kc-001/stages/plan") is None


def test_gate_runner_refuses_to_check_its_own_profile(tmp_path):
    p, _ = run(tmp_path, "good")
    bundle = os.path.join(p.work, "bundles", "r-004.json")
    r = subprocess.run([sys.executable, os.path.join(REPO, "qa", "run_gate.py"), "script", "--bundle", bundle,
                        "--producer-stage", "qa", "--out-dir", str(tmp_path / "qa")], capture_output=True, text=True)
    assert r.returncode != 0 and "producer and checker are both" in r.stderr
    assert not (tmp_path / "qa").exists()


def test_profiles_and_gates_are_what_the_readme_counts():
    profiles = json.load(open(os.path.join(REPO, "jobs", "profiles.json")))["profiles"]
    gates = [f for f in os.listdir(os.path.join(REPO, "qa", "gates")) if f.endswith(".md") and f != "README.md"]
    assert len(profiles) == 10 and len(gates) == 9
    # exactly one profile may write gate runs, and only as create
    qa_writers = [n for n, pr in profiles.items() for row in pr["writes"] if "/qa/" in row[0]]
    assert qa_writers == ["qa"]
    assert profiles["qa"]["writes"][0][2] == {"create": True}
