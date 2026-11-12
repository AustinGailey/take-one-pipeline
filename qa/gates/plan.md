# Gate S1: Plan

**Hand-off:** Plan (the owner's greenlight) → S2 Design. **Artifact:** the greenlight record: `projects/<key>.plan.*` (the owner's adopted
promise, before, audience, angle, trustJob; page-owned), `projects/<key>/stages/plan` (the plan profile's proposal + `pitchId`,
`greenlit`), read against `stages/research` (pitches, demo verdict, deliverable candidates) and the topic (`SCHEMA.md` §3.project,
§3.stage-plan, §3.stage-research). **Version:** `stages/plan.pitchId` (falls back to `stages/research.version`).
**Criteria source:** `PIPELINE.md` section 2, S1 row (promise is a concrete outcome; demoable with our tools; not a repeat within
8 episodes) and section 8 A (trust job). The **package concept** half of S1 is `package.md` `--phase concept` (row stage `plan`).
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `plan`, gate `qa/gates/plan.md`) through `content-qa`. Never by
`content-research` (plan profile) or `episode-package`. Gates warn, never block.

## Run
```bash
python3 qa/run_gate.py plan --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage plan [--history <last 8 plans>.json]
# by hand, from saved docs:
python3 qa/run_gate.py plan --key <key> --doc projects/<key>=<project>.json --doc projects/<key>/stages/plan=<plan>.json \
  --doc projects/<key>/stages/research=<research>.json [--doc topics/<id>=<topic>.json]
# check alone:
python3 qa/checks/plan_check.py --input <out-dir>/raw/plan/plan-input.json [--history <json list of {key, title, promise}>] -o <out-dir>/plan.json
```
Outputs: `<out-dir>/plan.json` (every check), `qa/runs/<runId>.json`, and `qa/<runId>.write.json` (the create-only
`projects/<key>/qa/<runId>` write for results.json). Exit is always 0; pass/fail is in the JSON.

## Checks
| Check | Threshold | Fails when | Notes |
|---|---|---|---|
| `plan_present` | title, promise, audience, angle (adopted on `projects.plan.*`, else proposed on `stages/plan`) | any missing | The detail says whether the owner adopted it or it is still the S1 proposal |
| `promise_concrete` | the promise is an after-state: **≥5 words**, no topic phrasing (`learn about`, `overview`, `intro to`, `tips`, `the basics`), names a deliverable noun or a number | vague phrase or < 5 words (no deliverable/number: warn) | The blueprint's deliverable (S2) must match it; `package.md` `promise_match` checks that |
| `before_after` | `projects.plan.before` set | warn only | The greenlight room builds before → after |
| `trust_job` | `plan.trustJob` ∈ competence / connection / relevance / proof | warn only | PIPELINE §8 A; the research gate's `trust_mix` warns on 4 in a row |
| `pitch_from_dossier` | `stages/plan.pitchId` is a `stages/research.pitches` id (no pitchId: the promise shares ≥2 content words with a pitch) | pitchId not in the dossier (no pitches at all: warn) | The plan was weighed against alternatives, not invented at greenlight |
| `demoable` | `stages/research.demo.verdict == "yes"` | `no` (partial / missing: warn) | The owner may still greenlight a partial demo; the gate names it |
| `deliverable_planned` | `projects.deliverablePlan` has ≥1 kind not dropped | empty | A dossier deliverable chosen but no lead-magnet planned: warn |
| `signature_idea` | `signatureIdea` set | warn only | What makes this one ours |
| `not_repeat` | with `--history` (the last 8 projects' `{key, title, promise}`): < 60 % of this plan's content words shared with any of them | a repeat | Skipped without `--history`: one bundle holds one project; the skill passes the list when it has it |
| `package_concept` | ≥1 `deliverables/package/versions/k*` exists | warn only | Package-first: S1 ends with the concept; its own checks are `package.md#concept` |
| `greenlit_consistent` | `greenlit` set ⇒ a `pitchId` or an adopted promise exists | warn only | |

## Not automated (reason recorded)
- **Is the promise worth making:** the radar evidence and the owner's judgement in the greenlight room; the topic score vs actual CTR is S7's.
- **Repeat within 8 episodes without a history file:** the qa bundle carries one project; the check runs when the skill supplies `--history`.

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-21 | First version, written from PIPELINE.md S1 when the plan gate was first due (Take One new model, SCHEMA.md r2-target-3) | the whole gate |
