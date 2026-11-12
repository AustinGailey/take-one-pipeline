# Take One: the document model

Every stage reads and writes one tree of JSON documents keyed by path. This file is the condensed public version of
the production schema: the principles, the path table for the parts the engine touches, and the shapes the dispatcher
and the gates depend on. Field tables for media, posts, results and the studio singletons are left out.

Write lanes come from `jobs/profiles.json`. Where this file and that one disagree, one of them is wrong.

## 1. Principles

1. **One writer lane per record.** Every doc under `projects/{key}` has exactly one writer lane: a `stages/<phase>` doc
   belongs to its stage profile; `marks/*`, `rounds/*` and the project doc belong to the owner's page. A few shared
   docs use **field groups** (each group has one writer).
2. **Page-owned, agent-owned, frozen.** Page-owned = the owner's facts (picks, notes, verdicts, overlays).
   Agent-owned = produced work (dossiers, outlines, versions, results). Frozen = write-once after a lock: a version
   after it is delivered, the script after the owner freezes it, a review round after it is submitted.
3. **Status is computed, never stored.** No stored `status`/`phase` on projects, deliverables, versions, decisions.
   The one exception is a job's terminal state, because the lease contract needs exactly one terminal write.
4. **The owner's edits are overlays.** Wording changes, pins, skips and ticks live in `projects/{key}/marks/{scope}`;
   the producer folds them into its next version. The owner never writes a producer's doc and a producer never
   writes the owner's marks.
5. **Agents never write the store.** An agent's `results.json` lists writes; `dispatch.py collect` lane-checks them;
   one caller applies what survived (`JOBS-CONTRACT.md`). In production each of those writes is pinned to the
   document version the agent read, and a stale pin writes nothing; the sample store in this repo does not pin.
6. **Every wait on the owner is a decision doc** with a `policyKey`; ids are deterministic so nothing is raised twice.
7. **Identity is an immutable key** (`kc-001`): doc id = key; titles never appear in ids.

## 2. Path table

| Path | Purpose | Writer |
|---|---|---|
| `projects/{key}` | Identity and the owner's adopted plan (`plan.*`, `deliverablePlan`) | page |
| `projects/{key}/stages/research` | S0 dossier: questions, pains, competitors, facts, demo verdict, pitches | `research` (`plan` may set flags) |
| `projects/{key}/stages/plan` | S1: the plan profile's proposal, plus the owner's greenlight (`pitchId`, `greenlit`: page-owned) | `plan` + page (field groups) |
| `projects/{key}/stages/design` | S2 blueprint and lineage | `design` |
| `projects/{key}/stages/script` | S2 outline: cold open, chapters, CTAs, experiments. `frozen` is page-owned | `design` + page |
| `projects/{key}/stages/storyboard` | S2 beats with frame refs | `design` |
| `projects/{key}/stages/{capture,edit,package,publish,measure}` | Each later stage's working state | that stage's profile |
| `projects/{key}/deliverables/{id}` | One thing the project makes: `script`, `long`, `d1` (demo), `s01` (short), `package` … | the producing profile |
| `projects/{key}/deliverables/{id}/versions/{v}` | One produced version. Write-once after delivery | the producing profile |
| `projects/{key}/deliverables/{id}/versions/{v}/rounds/{n}` | One review round: the owner's notes and verdict | page |
| `projects/{key}/marks/{scope}` | The owner's overlays per scope, including `marks/skips` | page |
| `projects/{key}/qa/{runId}` | One gate run. **Create-only.** `waived` is page-owned | `qa` |
| `projects/{key}/results/{deliverableId}__{window}` | Measured results at D+7 / D+28 | `rules` |
| `decisions/{kind}-{projectKey}-{slug}` | Everything that waits on the owner, one question each | raiser (question) + page (answer) |
| `jobs/sj-{requestId}` | One supervised agent run | supervisor (terminal) |
| `topics/{id}` | Topic candidates and the owner's suggestions | `research` + page (field groups) |
| `rules/{id}` | One learning-log row | `rules` |
| `escapes/{id}` | One QA escape (mirror of `qa/escapes.csv`). Create-only | `qa` |

## 3. Shapes the engine depends on

### Request bundle (input to `dispatch.py start`)

```json
{"requestId": "r-102", "projectKey": "kc-001",
 "request": {"text": "the owner's note", "context": {"kind": "stage", "stage": "design", "action": "script"}},
 "docs": {"projects/kc-001": {}, "projects/kc-001/stages/plan": {}}}
```

`context` routes the request: `action` first, then `stage`, then `kind` (`profiles.json` → `route`). `docs` is the
slice of the store the agent may read, keyed by path.

### Agent results (`jobs/runs/<job>/results.json`)

```json
{"status": "done",
 "reply": "one to four plain sentences for the owner's card",
 "writes": [{"path": "projects/kc-001/stages/script", "op": "merge", "data": {}}],
 "files": [{"path": "/abs/path", "label": "frame 3", "upload": true}],
 "followups": [{"text": "Run the script gate on s1.", "context": {"kind": "stage", "stage": "qa", "action": "gate", "gate": "script"}}],
 "ask": {"kind": "pick", "question": "…", "options": [{"id": "a", "label": "…"}], "select": "one", "sources": []}}
```

`status: "blocked"` plus an `ask` means the agent stopped at a decision that is the owner's. `op` is `set` or `merge`;
a lane marked `create` turns either into `create`, which refuses an existing doc.

### QA run: `projects/{key}/qa/{runId}`

| Field | Type | Note |
|---|---|---|
| `runId, stage, gate` | string | `gate` is the spec file, e.g. `qa/gates/script.md` |
| `target` | `{deliverableId?, version?, stage?}` | what was checked |
| `artifactVersion` | string | the target's own version id (`s1`, `k1`), never a date |
| `pass` | bool | no check failed. `skipped` runs are not passes |
| `failures` | map `check → {detail, order}` | |
| `warnings` | map `check → {detail}` | warnings never fail a gate |
| `producer` | `{agent, stage}` | never the qa profile |
| `jobId, at` | string, ISO | the qa job that ran it |
| `waived` | `{by, at, decisionId, note}` or absent | **page-owned**: the owner's "proceed anyway". No agent lane may write it |

### Decision: `decisions/{…}`

`{kind: screen|pick|answer|approve|fix, policyKey, projectKey, question, options:[{id, label}], select: one|many,
recommend?, plain:{will, why, changes}, target:{…}, sources:[…], raised:{by, at}}` written by the raiser;
`answer:{value, text?, at}` written only by the page.

Policies that appear in this repo (`pick.topic` and `approve.script` are the sample runner's stand-ins for the
production pick and approval cards):

| policyKey | Raised by | Answer |
|---|---|---|
| `pick.topic` | the plan stage, after its gate | the owner picks a pitch (human gate 1) |
| `approve.script` | the design stage, after its gate | the owner approves or sends notes (human gate 2) |
| `fix.gate` | a failing qa run | *fix* (ticket to the producing stage, gate re-runs) or *waive* (logged on the run) |
| `fix.lane` | `dispatch.py collect`, when a write fell outside its lane | acknowledge or re-run |
| `approve.schedule` | the publish stage | a floor: never automatic, expires after 24 h, bound to one batch |

### Job terminal (`<job>.terminal.json`)

`{state: done|failed|needs-owner|handed-back|requeued, reason, attempt, durationS, session, costUsd, report,
denials:[{tool, input}], ask?:{…}, block?:{key, cause, fix, tool?, since}, resume?}`. Written once; first writer wins.

### Escape (`qa/escapes.csv` row)

`date, episode, stage, defect, caught_by, gate_gap, fix, new_check`. `gate_gap` says why the gate missed it;
`new_check` names the check that now catches it, or the reason it cannot be automated.

## 4. Mutability, in one table

| Record | Who may change it | Until |
|---|---|---|
| A stage doc | its stage profile | always (it is working state) |
| A page-owned field inside a stage doc | the owner | always; agents' writes to it are stripped |
| A version | its producer | delivery, then never |
| A qa run | nobody (create-only) | n/a; the owner may add `waived` |
| A decision's question | its raiser | answered |
| A decision's answer | the owner | undo window |
| A job's terminal state | the supervisor or the reaper | written once |
