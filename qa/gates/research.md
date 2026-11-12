# Gate S0: Research

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Research → the owner's **topic pick (S1)** and S2 Design. **Artifact:** `projects/<key>/stages/research` (the S0 dossier,
`SCHEMA.md` §3.stage-research) with the owner's `marks/research` (rejected items), plus the linked `topics/<topicId>` (§3.topic). **Version:** `research.version` (e.g. `r1`).
**Criteria source:** `PIPELINE.md` S0 row (outlier bar, sources listed) and the owner's dossier spec (2026-10-15).
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `research`, gate `qa/gates/research.md`) through `content-qa`. Never by `content-research`.
Gates warn, never block. Rejected items (`marks/research.research.<id>.state == "rejected"`) are left out of every check.

## Run
```bash
python3 qa/run_gate.py research --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage <producing stage>
# by hand: --doc projects/<key>/stages/research=<file>.json --doc projects/<key>=<project>.json [--doc topics/<id>=<topic>.json] [--doc projects/<key>/marks/research=<marks>.json]
# check alone, or on a draft not yet on the doc (the episode-shape view run_gate.py builds is qa/raw/research/episode-shape.json):
python3 qa/checks/research_check.py --doc <out-dir>/raw/research/episode-shape.json [--topic <topic>.json] [--research <draft>.json] [--no-fetch] -o <out-dir>/research.json
```
Outputs: `<out-dir>/research.json` and `qa/<runId>.write.json` (the create-only `projects/<key>/qa/<runId>` write). Exit is always 0.
The topic comes from the bundle (`topics/<topicId>`, flat candidate fields merged) so `outlier_bar` sees its outliers; `researchMarks` is built from `marks/research`.

## Checks
| Check | Threshold | Fails when |
|---|---|---|
| `research_present` | `stages/research` exists | missing |
| `competitors_analysed` | **≥3** competitor videos (not rejected), each with `covers`, `misses` and a `gap` | fewer than 3 (analysed from title/metadata only: `competitors_watched` warns) |
| `gap_stated` | `research.gap` (our angle against all of them, one sentence) | empty |
| `outlier_bar` | ≥1 competitor or topic outlier at **≥3x channel median** or **≥1x subs** | none |
| `facts_sourced` | every fact has `sourceUrl` or `sourcePath` + `quote`, and the quote is found at the source (path: text search; URL: `quote-check.py`) | missing source/quote, or quote not found (URL fetch error: `facts_unfetched` warns) |
| `deliverable_chosen` | exactly **1** deliverable chosen (the owner's `marks/research` entry for the item, else the item's `chosen`) | 0 or 2+ (2-3 candidates expected: warn) |
| `pains_sourced` | **≥3** audience pains, each with a source (`source.kind` + url/path/where) | fewer, or any unsourced (search-only sources: `pains_voice` warns) |
| `promise_vs_facts` | every cost word in the promise (`plan.promise`, else topic/research `promise`: free, $N, a month, monthly, subscription, paid, no cost, cheap) appears in a fact whose quote passed `facts_sourced`; "free" warns when a verified fact names a paid plan (a tier name, $N, subscription, plan) and doesn't say free | warn only (esc-013) |
| `questions` | ≥3 questions the episode must answer | warn only |
| `demo_feasible` | `demo.verdict == "yes"` | warn only (partial/no is the owner's call at S1) |
| `craft_refs` | ≥1 reference-bank card | warn only |


## Not automated (reason recorded)
- **Whether the gap is real:** needs someone to watch the competitor videos; `competitors_watched` flags dossiers built from metadata.
  the owner's Dig deeper on a competitor is the fix path.
- **Pain wording quality:** taste. The owner pins or rejects pains in Take One; rejected ones never count.

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-15 | First version, written from the owner's dossier spec when S0 got its Take One view | the whole gate |
| 2026-10-21 | esc-013: KC-001 promise said "roast for free" while verified fact f1 names a paid roaster (the owner's r2 note) | `promise_vs_facts` (warn) |
