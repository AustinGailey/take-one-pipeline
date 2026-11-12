# Stage gates

One file per hand-off: the checks, the thresholds, the command, what is deliberately not automated, and the escapes that
changed the gate. Criteria summary: `../../PIPELINE.md` section 2. Field shapes: `../../SCHEMA.md`.

A gate is run by the `qa` profile as its own job. It reads the stage docs in the dispatch bundle, runs the checker and
hands back one **new** store doc `projects/<key>/qa/<runId>` (create-only) through `jobs/runs/<job>/results.json`.
The producing agent never runs its own gate: the `qa` lane is the only one in `jobs/profiles.json` that may write
`projects/{key}/qa/*`, and `run_gate.py` refuses a run whose producer is the qa profile.

Entry point: `python3 qa/run_gate.py <stage> --bundle <bundle.json> --job <sj-id> --producer-stage <stage>`.

| Stage | Spec | Checker | In this repo |
|---|---|---|---|
| research (S0) | `research.md` | `research_check.py` + a quote checker for URL facts | spec only |
| plan (S1) | `plan.md` | `../checks/plan_check.py` | spec + runnable checker |
| script (S2) | `script.md` | `../checks/script_check.py` | spec + runnable checker |
| storyboard (S2 Design) | `storyboard.md` | `storyboard_check.py` | spec only |
| capture (S3) | `capture.md` | `capture_check.py` + the capture ledger | spec only |
| edit (S4) | `edit.md` | `edit-qc.py` + `av-qa.sh` + `edit_check.py` | spec only |
| package (S5, and the S1 concept) | `package.md` | `package_check.py` (speech-to-text, OCR) | spec only |
| publish (S6) | `publish.md` | `publish_check.py` | spec only |
| measure (S7) | `measure.md` | `measure_check.py` | spec only |

The seven spec-only gates name files that are not in this repo (stage rulebooks such as `PACKAGE-RULES.md`, media
checkers, the capture ledger). They are left as written so the specs read as they do in production. Section references such as
`SCHEMA.md §3.stage-script` point at the full production schema; the `SCHEMA.md` in this repo is a condensed version
without those numbered sections.

Escapes (defects a passed gate missed): `../escapes.csv`. Every row ends in a new check or a written reason why it
cannot be automated; each gate file lists the escapes that changed it.
