# Gate S4: Edit

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Edit → the owner's cut screen and Package. **Artifact:** the newest version of
`projects/<key>/deliverables/long` (`SCHEMA.md` §3.version: `media` ref resolved through the folder, `events`). **Version:** that version's `v`.
**Spec:** `stages/storyboard` (S2 Design) when present; `stages/edit.techniqueEvents` names events.json (§3.stage-edit).
**Criteria source:** `PIPELINE.md` section 2, S4 row; `references/HOUSE-EDIT-GUIDE.md` (edit-qc rules 2, 5, 6, 7, 9, 11).
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `edit`) through `content-qa`. Never by `video-edit`.
The QA job runs `edit-qc.py` and `av-qa.sh` itself. A producer's `qc/edit-qc.json` or `qc.sh` output is **never read**;
the producer's `work/qc-args.json` (overlay layers and offsets, demo ranges) and `work/edl.json` are used as **inputs**
because they describe what is in the render, not whether it passed.
Gates warn, never block.

## Run
```bash
python3 qa/run_gate.py edit --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage> [--render <path>]
```
This runs, in order (about 10–15 min for a 12 min cut, so run it in the background):
```bash
# 1. house-guide checks (eyefix venv: mediapipe + opencv), from the render's folder
python tools/edit-qc.py --render <render> \
  --stage left --inset 24 --kind demo --format 16x9 --edl work/edl.json $(work/qc-args.json) -o <out-dir>/raw/edit/edit-qc.json
# 2. loudness + contact sheet + transcript
bash tools/av-qa.sh <render> <out-dir>/raw/edit/av-qa --target social
# 3. fold into the gate report
python3 qa/checks/edit_check.py --render <render> --edit-qc .../edit-qc.json --av-qa-log .../av-qa.log \
  --events edit/events.json --edl work/edl.json --doc <out-dir>/raw/edit/episode-shape.json -o <out-dir>/edit.json
```
Outputs: `<out-dir>/edit.json`, `qa/<runId>.write.json` (the create-only `projects/<key>/qa/<runId>` write), raw runs in `qa/raw/edit/`.

## Checks
| Check | Threshold | Source |
|---|---|---|
| `edit_qc.overlay_on_face` | 0 overlay pixels (alpha > 8) inside face box + 15 % | edit-qc rule 11 (escape 3) |
| `edit_qc.no_face` | face on screen ≥ 95 % of runtime (demo episodes) | rule 2 |
| `edit_qc.audio_gaps` | no silence > 1.0 s outside whitelisted ranges | rule 7 (escape 1) |
| `edit_qc.tinted_edge` | demo window 6 px edge strip: Lab \|a\|,\|b\| ≤ 2 | rule 9 (escape 2) |
| `edit_qc.punch_in` | no A-B-A framing; ≤ 1 framing change per 20 s | rule 5 (escape 1) |
| `edit_qc.speed_ramp` | no EDL segment with speed > 1.02 | rule 6 |
| `loudness` | integrated **−15..−13 LUFS**, true peak **≤ −1 dBTP** | av-qa.sh, social target |
| `events_present` | `edit/events.json` (or `<render dir>/events.json`) exists | PIPELINE S4 gate |
| `events_complete` | the file names this render (`render`); every event has `techniqueId`, `t_in`, `t_out`, `layer` (the shape `edit-events.py` writes); no > 30 s without an event, including the last 30 s; every EDL boundary has an event of any layer within 0.5 s (a boundary inside one continuous source is a `stage.swap`/morph, not a cut); technique ids resolve in the file's `techniques` registry or a card's `Event ids` row in `library/techniques/T-*.md` (card filenames are not ids); ids used without a card only **warn** | so retention dips can be mapped to techniques |
| `plan_conformance` | with `stages/storyboard`: every planned graphic beat has an event carrying its `beat` id; the event's `component`/`comp`/`template` matches the planned component; planned order kept; graphic events without `beat` (other than chapter tags and captions) are listed as extras. **Missing > 10 %** of planned graphics, or events citing beats not in the storyboard, fails; fewer missing, mismatches, inversions and extras warn. No storyboard (KC-001) → skipped | the edit executes the plan |

## Not automated (reason recorded)
- "Motion graphics look AI / low effort" (escape 5): taste. Covered by arena parity before shipping (reverse-engineering loop).
- Eye contact (escape 4): a capture-stage check (gaze threshold), not edit.

## Escapes that changed this gate
| Date | Escape | Check |
|---|---|---|
| 2026-10-14 | choppy cuts | `audio_gaps` + `punch_in` |
| 2026-10-14 | orange control glow | `tinted_edge` |
| 2026-10-14 | text boxes over the face | `overlay_on_face` |
| 2026-10-15 | KC-001: graphics improvised by the edit, ~5x too few (the owner) | `plan_conformance` (the plan itself is gated by `storyboard.md`) |
