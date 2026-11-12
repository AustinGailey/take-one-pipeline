# Gate S7: Measure

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Measure → the Learn layer (rule tickets to owners) and S0 of the next project. **Artifact:** one window of
`projects/<key>/stages/measure` (`SCHEMA.md` §3.stage-measure: `windows.d7|d28 {at, resultDocs, postmortem{ref}, tickets}`),
the window's result docs `projects/<key>/results/<deliverableId>__<window>` (§3.result), `<project folder>/postmortem.md` and
`LEARNING-LOG.md` on disk, `stages/package.lineage` (variant attribution), `rules/*`. **Version:** the window (`d7`, `d28`).
**Criteria source:** `PIPELINE.md` section 2, S7 row (postmortem filed by D+8 with every signal routed) and section 4 (signal routing).
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `measure`, gate `qa/gates/measure.md`) through `content-qa`. Never by
`content-postmortem`. Gates warn, never block. Before the window is due the gate is `skipped` (`window_due`), not a pass.

## Run
```bash
python3 qa/run_gate.py measure --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage measure [--window d7|d28]
# by hand: --doc projects/<key>/stages/measure=<file>.json --doc projects/<key>/results/long__d7=<file>.json --doc posts/<key>-long-youtube=<file>.json ...
# check alone:
python3 qa/checks/measure_check.py --input <out-dir>/raw/measure/measure-input.json --window d7 [--now ISO] -o <out-dir>/measure.json
```
Outputs: `<out-dir>/measure.json`, `qa/runs/<runId>.json`, `qa/<runId>.write.json`. Exit is always 0. Default window =
the latest in `stages/measure.windows`, else `d7`.

## Checks
| Check | Threshold | Fails when | Notes |
|---|---|---|---|
| `window_due` | long post date + 7 / + 28 ≤ today | skipped (not failed) before the due date | No long post date: gates what exists and says so |
| `postmortem_filed` | `windows.<w>.postmortem.ref` exists on disk and has a `<w>` / `D+N` section | missing window, file, or section | `postmortem/postmortem.py` writes one section per window |
| `postmortem_on_time` | `windows.<w>.at` ≤ due + 1 day (**D+8** / D+29) | warn only | |
| `results_doc` | `results/long__<w>` has `views, impressions, ctr, avdSec, pctViewed` | missing doc or metric | `synthetic` results warn: they never feed rules or the trailing median |
| `signals_routed` | every `summary.signals[]` entry names an owner stage (S0-S7 / record / gate-owner) | any without an owner | PIPELINE section 4 |
| `baseline_basis` | every verdict names its basis (trailing median of ≥3 episodes, or the absolute floor) | warn only | `postmortem.py ABS` until 3 episodes exist |
| `moments_attributed` | each dip / spike has an owner (S4 or S2) and a technique id, beat or script line | no owner (no technique/beat/line: warn) | Dip time → `events.json` → beat → line |
| `tickets_filed` | a signal below baseline ⇒ `windows.<w>.tickets` non-empty | warn only | Tickets are asks the page files from `followups`; the bundle cannot verify them |
| `rules_logged` | every `ruleId` named in the summary or `rules/*` in the bundle has a row in `LEARNING-LOG.md` | a rule id with no log row | Grades change only through the log |
| `lineage_complete` | `stages/package.lineage.titleVariants` and `thumbnailVariants` non-empty | warn only | Without them CTR cannot be attributed to a variant |
| `thumbnail_winner` | d28 with ≥2 thumbnail variants ⇒ `stages/measure.thumbnailWinner` set | warn only | Test & Compare result |
| `shorts_results` | every posted short has `results/<sid>__<w>` | warn only | Shorts numbers come from the Studio shorts CSV |

## Not automated (reason recorded)
- **Whether a rule change was the right call:** judged next episode by `content-postmortem` (did the metric move); the gate only checks it was logged.
- **Reading the retention CSV correctly:** `postmortem.py` is the only reader; its synthetic run (`postmortem/make-synthetic.py`) is the regression test.
- **Community joins:** no API; the owner types the number into `marks/measure.inputs`.

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-21 | First version, written from PIPELINE.md S7 + section 4 when the measure gate was first due (Take One new model) | the whole gate |
