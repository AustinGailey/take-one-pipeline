# Gate S3: Capture

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Design (approved animatic) → record day → Edit. **Artifact:** the project folder (`demos/`, `raw/*.markers.json`,
`capture/coverage.json`) plus `projects/<key>/deliverables/dN` (+ test versions, `SCHEMA.md` §3.version `capture`) and `stages/capture` (§3.stage-capture). **Criteria source:** `PIPELINE.md` section 2, S3 row.
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `capture`) through the `content-qa` skill. Never by the recorder or demo-capture agent.
Gates warn, never block: a failing row goes to the owner with the failures; they fix or proceed (logged `waived`).

## Run
```bash
# before record day (the demo pre-flight)
python3 qa/run_gate.py capture --phase preflight --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
# after recording
python3 qa/run_gate.py capture --phase final --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
```
Outputs: `<out-dir>/capture-preflight.json` / `qa/capture.json` (+ `qa/<runId>.write.json`, the create-only `projects/<key>/qa/<runId>` write; `stage` is `capture` for both).

## Checks
| Check | Phase | Fails when | Notes |
|---|---|---|---|
| `demo_media` | both | a demo dN has no screen recording (`demos/<dN>.*`, `demos/kc-NNN-<dN>[-takeN]-screen.*`, or the `final` version's media ref) and no `deliverables/dN.liveCapture: true` | Without it every narration line of that demo is `blocked` in the ledger. `liveCapture` = the owner drives the demo in Studio Recorder's Screen demo segment and narrates live. |
| `demo_dataset` | both | a demo has no `deliverables/dN.dataset = {path, testedAt}`, the path is missing, or `testedAt` is empty | The data the demo runs on (fixture, seeded doc, sample CSV) and when someone last ran the demo end to end on it. |
| `demo_narration` | both | warn only: a demo has no `narration` lines | Points-mode demos are legal, just looser. |
| `line_coverage` | final | the capture ledger has any pending / retake / verify / blocked line | `capture/coverage.py`; `verify` lines are settled by a transcript check writing `capture/flags.json`. |

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-16 | KC-002: record day ran with no demo captured; d1-d4 narration (28 lines) could not be recorded over anything | `demo_media`, `demo_dataset` (pre-flight), `line_coverage` |
