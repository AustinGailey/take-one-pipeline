# Gate S2: Script

**Hand-off:** Script → the owner's approve, then Capture. **Artifact:** `projects/<key>/stages/script` (outline: coldOpen, chapters, ctas, experiments; `SCHEMA.md` §3.stage-script)
+ the line text of `deliverables/script/versions/<v>` (§3.version `lines`) + demo narration (`deliverables/dN` lines). **Version:** the script
version read (`stages/script.frozen.v` > `marks/dl-script.current.v` > `stages/script.current` > newest). **Criteria source:** `PIPELINE.md` section 2, S2 row; the spoken-style rulebook.
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `script`) through the `content-qa` skill. Never by the `design` profile that wrote the script.
Gates warn, never block: a failing row goes to the owner with the failures; they fix or proceed (logged `waived`).

## Run
```bash
python3 qa/run_gate.py script --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
# by hand: --doc projects/<key>/stages/script=<file>.json --doc projects/<key>/deliverables/script/versions/s1=<file>.json [--doc projects/<key>/deliverables/d1=<file>.json]
# check alone: python3 qa/checks/script_check.py --doc <out-dir>/raw/script/episode-shape.json -o <out-dir>/script.json
```
Outputs: `<out-dir>/script.json` (every check) and `qa/<runId>.write.json` (the create-only `projects/<key>/qa/<runId>` write). Exit is always 0;
pass/fail is in the JSON (`pass`, `failures[]`).

## Checks
| Check | Threshold | Fails when | Notes |
|---|---|---|---|
| `script_present` | every chapter resolves its `lineIds` to version lines | any chapter has only `points` (no lines) | Points-only = pre-W44 legacy. Points are what the presenter reads aloud, so they are not a script. |
| `runtime` | words ÷ **150 wpm** within **±15 %** of target | outside the band | Words = coldOpen + chapter lines + demo narration + the standard CTA. Target = `targetMinutes`, else the sum of `chapters[].minutes`. Legacy docs use the points as a proxy and say so. |
| `experiment_share` | lines with `exp` **≤ 30 %** of script lines; every `exp` id defined in `experiments[]` | over 30 %, or an undefined id | Skipped when there are no script lines. |
| `stage_directions` | **0** production notes in speakable text | any hit | Scans coldOpen, `script[].text`, `narration[].text` **and** `points` (the presenter reads points too). Patterns: `Diagram:`, `Callout`, `Chapter card`, `Live:`, `Saved prompt:`, `Example wording:`, `Show:`, `On screen`, `B-roll`, `Cut to`, `Zoom in`, `[brackets]`, `(pause)`, `Lower third`, `Title card`, `SFX`, `VO:`. Production notes belong in `show`. |
| `community_cta` | a standard, unretired `community` CTA; the last scripted line of the last chapter is that CTA (text names community or `ctaId` matches); no spoken "book a call" / example.com/book; no unretired `call` CTA | any of those | Standard CTA decided 2026-10-14 (`stages/script.ctas`, `SCHEMA.md` §3.stage-script). |
| `claims_sourced` | numeric claims (`%`, `Nx`, `$N`, "N out of M") carry `source`, `source: <url>` in `show`, `opinion: true`, or opinion phrasing ("I think") | any unsourced numeric claim | Soft generalisations ("most", "always", "studies") only **warn** for a human eyeball. |

## Not automated (reason recorded)
- Voice match ("sounds like the presenter"): judged by the owner at the approve gate; drift is measured after recording.
- Hook quality: scored by Learn from shorts % viewed per hook variant, not at the gate.

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-14 | KC-001: 7 of 15 stage directions spoken on camera | `stage_directions` (also scans `points`) |
