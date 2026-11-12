# Gate S5: Package (and the S1 package concept)

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Two phases (2026-10-16, package-first).** `--phase concept` runs at S1 on the package concept (titles, thumbnail concepts, promise)
before S2 starts; its row is `stage:"plan"`, `gate:"qa/gates/package.md#concept"`, so it shows on the S1 strip cell. `--phase final` (default)
is the S5 gate below plus the same promise checks on the shipped variants. Both warn, never block.

**Hand-off:** Package → the owner's screen and Publish. **Artifact:** the newest `projects/<key>/deliverables/package/versions/<v>` payload (titles, thumbnails,
final, description; `SCHEMA.md` §3.version), `stages/package.lineage`, the owner's `marks/package` (pick, item edits) and the short deliverables
`sNN` (newest version media + hooks); falls back to `edit/package/titles.md`, `edit/package/thumbnails/*.png`, `edit/package/description.md`
on disk. **Version:** that package version (`k1` concept, `f1` final; `run_gate.py` passes it for both phases).
**Criteria source:** `PIPELINE.md` section 2, S5 row; standard CTA rule in `SCHEMA.md` §3.stage-script (`ctas`).
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `package`) through `content-qa`. Never by `episode-package`.
Gates warn, never block.

## Run
```bash
python3 qa/run_gate.py package --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
```
This runs, per short, `edit-qc.py --format 9x16` itself (overlay layers and demo ranges are derived from the short's
`meta.json` + `qc/ov-*.mov` build inputs, the same derivation as `shorts-v2/render.sh qc()`; a producer's `qc/edit-qc*.json`
is never read), writing `qa/raw/package/<clip>.edit-qc.json`, then:
```bash
python3 qa/checks/package_check.py --doc <out-dir>/raw/package/episode-shape.json --episode-dir <project folder> --short-qc-dir <out-dir>/raw/package \
  -o <out-dir>/package.json
```
About 2 min per short for edit-qc plus ~2 s per short for whisper. Needs whisper-cli + a local whisper model
and `swift` (Apple Vision OCR, `qa/checks/ocr.swift`, free and on-device).

Concept phase:
```bash
python3 qa/run_gate.py package --phase concept --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
# writes <out-dir>/package-concept.json + qa/<runId>.write.json (row stage plan); the topic comes from the bundle (topics/<topicId>)
```

## Checks
| Check | Threshold | How |
|---|---|---|
| `title_frontload` (both) | the pick's search phrase (topic autocomplete or the title's `keyword`; ≥60 % of its content words) starts within the title's first 3 words | the pick = `marks/package.pick` (the owner), else the version's `recommend`; final = `final.titleIds[0]`; the owner's edited wording wins |
| `title_thumb_distinct` (both) | each title/thumbnail pair shares ≤1 content word, and the thumbnail text is not inside the title. **Final: every `final.thumbnailIds` × every `final.titleIds`** (Test & Compare shows each thumbnail with the live title, and the swap can make any final title live); concept: the pick | content words, stopwords dropped, plurals folded; the owner's edited title wording wins |
| `promise_match` (both) | `package.promise` shares ≥2 content words with blueprint deliverable + after (+ the plan promise) and ≥1 with the picked title | |
| `cold_open_payoff` (both) | the beat that pays off the picked thumbnail (`storyboard.beats[].pays`, else the thumbnail's `payoff.beat`) starts ≤30 s and its lines share a word with the thumbnail text or promise | skipped at S1 when there is no storyboard yet; the storyboard gate's `package_payoff` runs the same check at S2 |
| `final_variants` (final) | 3 `phase:"final"` thumbnails and 2-3 `final.titleIds`, all listed in `lineage.thumbnailVariants` / `titleVariants` | |
| `thumb_face.<id>` (both, warn) | P-D5: largest face ≥ 8 % of the frame and smiling/reacting, not a talking frame or flat stare; a concept with `plateNeeded` and no big face warns "plate needed: <pose>" | Apple Vision landmarks via `package/plates/plates.py` (mouth width ≥ 0.355 = smile; lips parted without it = talking). |
| `thumb_instruction.<id>` (both, warn) | P-D7: the headline starts with an instruction verb | verb list in `plates.py` `IMPERATIVE`; "true to the video" stays the owner's read |
| `thumb_point.<id>` (both, warn) | P-D8: a pointing index finger aims within 50° of `thumbnails[].layout.proof` | Vision hand pose |
| `thumbs_distinct` (both, warn) | P-D2: no pair of the phase's (non-retired) thumbnails shares a template: overall-luma diff ×5 < 0.4 **and** face layout diff < 0.25, or the same `layout.kind` | `plates.py sig_distance`; hue histograms were tried and rejected (skin and shirt dominate) |
| `thumb_160.<file>` (both) | as below, on `package.thumbnails[].path` of the phase (final falls back to `edit/package/thumbnails/`) | |
| `short_edit_qc.<clip>` | 9x16 edit-qc verdict PASS | QA job's own run, as above |
| `short_cta.<clip>` | `ctaId` = the standard community CTA **and** "community" heard in the last 12 s | whisper on the tail (prompted with the channel's product names) |
| `short_hook.<clip>` | first spoken word ≤ 1.0 s **and all 3** of the hook's first words heard, in order, by **2.0 s** (exact match after mishear normalisation; no fuzzy ratio) | hook text = `hooks[clip.hookId]`; whisper word timings on the first 4 s. `MISHEAR` in `package_check.py`, applied to both sides: the spoken-style rulebook's list of product names the transcriber mishears (for example roast→roost/rust) |
| `title_length` | every title option ≤ **60** chars | `package.titles[]`, else the `titles.md` table |
| `thumb_160.<file>` | every headline word (OCR boxes ≥ 8 % of frame height) still read at **160 px** wide | Vision OCR at full size, then on the image shrunk to 160 px and blown back up ×4 |
| `description` | paste block (between `---` lines) has the community link, and its **last link** is example.com/book | booking link only on the last line (2026-10-14 CTA decision) |


## Not automated (reason recorded)
- Title/thumbnail click-worthiness: CTR per variant, scored by Learn (S7), not at the gate.
- Hook strength: shorts % viewed per hook variant, scored by Learn.

## Escapes that changed this gate
| Date | Escape | Check |
|---|---|---|
| 2026-10-17 | The owner: "the thumbnails are lackluster" (KC-002 k1/k2: talking frames, topic labels, no pointing, one dark-violet template) | `thumb_face`, `thumb_instruction`, `thumb_point`, `thumbs_distinct` (warn); tests `qa/tests/test_thumb_rules.py` |
| 2026-10-16 | Not an escape: The owner's call that packaging was invented after the episode (package-first) | `--phase concept`, `title_frontload`, `title_thumb_distinct`, `promise_match`, `cold_open_payoff`, `final_variants` |
| 2026-10-16 | KC-001 f3 "Roast in 1 hour" repeats roast + hour from t1 and t2; the check saw only t1/f1 (esc-010) | `title_thumb_distinct` checks every final thumbnail × every final title |
| 2026-10-16 | KC-001 final row had `version: ""` (esc-011) | `run_gate.py` passes `--version package.version` in the final phase; checker falls back to it |
| 2026-10-16 | KC-001 b4 passed with 2/3 hook words: "roost" fuzzy-matched "roast", one word unheard (esc-012) | `short_hook` needs all 3 words in order after explicit `MISHEAR` normalisation; regression tests `qa/tests/test_package_gate.py` |
