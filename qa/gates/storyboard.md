# Gate S2: Design (storyboard)

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Design → the owner's **approve animatic**, then Capture. **Artifact:** `projects/<key>/stages/design.blueprint` + `stages/storyboard`
(`SCHEMA.md` §3.stage-design, §3.stage-storyboard; beats are a map keyed by id, frames are `{ref}`). **Version:** `blueprint.version/storyboard.version` (e.g. `b1/sb1`).
**Criteria source:** the episode design system (not published); `PIPELINE.md` S2 row.
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `script`, gate `qa/gates/storyboard.md`) through `content-qa`. Never by `episode-design`.
S2 has two gates: `script.md` (the words) and this one (the design). Run both on the same version. Gates warn, never block.

## Run
```bash
python3 qa/run_gate.py storyboard --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
# by hand: --doc projects/<key>/stages/storyboard=<file>.json --doc projects/<key>/stages/design=<file>.json --doc projects/<key>/stages/script=<file>.json --doc projects/<key>/deliverables/script/versions/s1=<file>.json
# check alone, or on a draft not yet on the doc:
python3 qa/checks/storyboard_check.py --doc <out-dir>/raw/storyboard/episode-shape.json [--storyboard <project folder>/design/storyboard.json --blueprint <project folder>/design/blueprint.json] -o <out-dir>/storyboard.json
```
Outputs: `<out-dir>/storyboard.json` and `qa/<runId>.write.json` (the create-only `projects/<key>/qa/<runId>` write) (`stage` is `storyboard` in the report;
`run_gate.py` writes the qa run with `stage: "script"` and `gate: "qa/gates/storyboard.md"` so the S2 strip shows it). Exit is always 0.

Beat start times are cumulative `est` in beat order (150 wpm + holds), so "within 40 s" means planned time.

## Checks
| Check | Threshold | Fails when |
|---|---|---|
| `storyboard_present` | blueprint and ≥1 beat | either missing |
| `blueprint_complete` | deliverable `name` + `showable`; before/after; **3-5 parts** each with an `outcome`; `proof.what`; board slot ids = part ids | any missing |
| `beat_ids` | unique, every beat has one | duplicate or missing id |
| `deliverable_early` | a beat with `shows:"deliverable"` starts **< 40 s** | none |
| `map_beat` | a `block:"map"` beat with `deliverable-board`, one slot per part, every slot `empty` | missing or wrong slot count/state |
| `chapter_grammar` | per part chapter: **open** = first beat, `chapter-open` with `outcome`; ≥1 **why** beat with an informative graphic; a **how**; a **payoff** whose `board` has that part `done` on a `deliverable-board`/`recap-stack`; a **bridge** | open/why/payoff/bridge missing (open not first, no how: warn) |
| `assembly_close` | assembly shows the board all `done` and a `shows:"proof"` beat; close has a `recap-stack`; the last close beat speaks the community CTA | any missing |
| `density` | outside demo action (`role:"how"` beats with a `demo` on `stage`/`split`): **no gap > 25 s** between informative graphics; count in band (non-demo s ÷ 25 .. ÷ 15) | any gap > 25 s (count out of band: warn) |
| `props_complete` | every graphic's component is in the vocabulary with its required props non-empty; no `TBD/lorem/placeholder` text; a graphic whose only text repeats the spoken line fails the **information test** | any of those (not `informative:true`, or component not in kit v3 yet: warn, ticket it) |
| `lines_resolve` | every beat `line`/`lines` id exists in the script version's `lines` (cold open, chapters, demo narration) | unknown id (script lines on no beat: warn) |
| `runtime` | Σ`est` within **±15 %** of `blueprint.targetMinutes` (else doc `targetMinutes`, else Σ chapter minutes); every beat has `est` | outside band or missing est |
| `package_payoff` | the S1 package pick's thumbnail is paid off by a beat (`pays: "<thumbnail id>"`, else the concept's `payoff.beat`) starting **≤30 s** whose lines share a word with the thumbnail text or promise (same code as the package gate's `cold_open_payoff`) | no package on the doc: warn; beat missing, late, or off-promise: fail |
| `frames_animatic` | every graphic beat has a frame; animatic rendered | warn only (placeholder frames warn too) |
| `motion_specified` | every `graphic`/`vo`/`split`/`stage` beat has `motion` (`{in, build, out}` or `{text}`, plain words) | warn only: names beats with none, and beats that only carry the kit default (`source: "kit-default"`, filled by `design.py merge`) (added 2026-10-31, the owner: could not tell motion graphics from still slides) |
| `demo_test` | every agent-captured demo is approved (`approval.state:"approved"`) on a clean-room test take (Demo Playground, `demo-capture/CLEAN-ROOM.md`) | warn only: no test take, or a test not yet approved |
| `demo_needs` | no open human need (`demos[].needs[]`, kinds other than `approval`) | warn only: names the open needs |
| `demo_scan` | each demo's latest test take passed both the pre-capture scan and the OCR frame scan | warn only: scan not run, incomplete, or `blocked: secret-scan` |

Required props per component (`REQ` in the checker): deliverable-board `slots` · chapter-open `n,total,title,outcome` · concept-diagram
`nodes,edges` · process-flow `steps` · compare `left,right,verdict` · stat-reveal `value,context` · checklist-build `items` ·
artifact-card `title,text` · ui-callout `label` · timeline `marks` · quote-source `text,who` · recap-stack `items`.


## Not automated (reason recorded)
- **Face-safe zone:** needs the kit's layout and face tracking; checked on frames by kit v3's stills CLI and after the edit by `edit_qc.overlay_on_face`.
- **"Sophisticated, not AI-looking":** taste. The owner judges it on the animatic; components reach motion-arena parity before they ship.
- **Information test, semantic half:** the checker catches empty, placeholder and repeat-the-sentence graphics; whether a diagram
  actually explains is the owner's call on the animatic (notes there become escapes).

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-17 | Demos were first planned and captured at S3, after the design was approved; no clean room (the owner) | `demo_test`, `demo_needs`, `demo_scan` (Demo Playground in S2) |
| 2026-10-15 | KC-001: sections not introduced; ~7 explaining graphics in 11.6 min; deliverable unclear (the owner) | the whole gate: `chapter_grammar`, `density`, `deliverable_early`, `map_beat` |
