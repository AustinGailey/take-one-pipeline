# The pipeline: the operating contract

Take One runs content production (a long video, its demos, shorts, thumbnails and posts) as **one pipeline of eight
stages**. Each stage has an owner and a write lane. Three layers run across all of them: Record, QA and Learn. This
file says who owns what, what each stage hands on, the gate it passes through, and where a person decides. Field
shapes are in `SCHEMA.md`; the job rules are in `JOBS-CONTRACT.md`.

This is a condensed, de-branded copy of the production contract. Stage rulebooks, skills and media tools it mentions
are not in this repo.

```
          ┌──────────── LEARN: the postmortem routes every signal back to the stage that owns it ────────────┐
          ▼                                                                                                  │
 S0 Research → S1 Plan → S2 Design → S3 Capture → S4 Edit → S5 Package → S6 Publish → S7 Measure ─────────────┘
    gate        gate      gates       gate          gate      gate          gate         gate (D+7, D+28)
 ─────────────────────────── QA: an independent gate per hand-off + a monthly audit ──────────────────────────
 ───────────────────── RECORD: the projects/{key} document tree is the single source of truth ───────────────
```

## 1. Ownership rules (the isolation)

1. **One stage, one lane.** A stage writes only its own docs and fields. It reads anything upstream. It never edits
   another stage's output or rulebook. Lanes are data (`jobs/profiles.json`) and are enforced when results are
   collected (`jobs/dispatch.py collect`), not by asking the agent nicely.
2. **Cross-stage changes go through a ticket.** When Edit finds a script problem it does not rewrite the script. It
   lists a follow-up for the Script stage, and that stage owns the fix. Learn works the same way: it proposes rule
   changes, and each stage owner applies them.
3. **Producer ≠ checker.** A stage's gate runs as a separate QA job against the stage's gate spec. The producing agent
   cannot mark its own gate passed: only the `qa` lane may write `projects/{key}/qa/*`, and those docs are
   create-only.
4. **The owner holds four decision gates** and nothing else waits on a person: **topic + package pick (S1)**,
   **approve the animatic (S2)**, **screen the cut and shorts (S4/S5)**, and **publish consent (S6)**. Everything else
   is agent-owned and agent-checked.
5. **Each stage owns one rulebook and one improvement loop.** Rules carry an evidence grade: **P** proven by our own
   results (2+ projects, same direction) · **S** seen in 3+ outlier references · **I** inferred · **U** unknown.
   An I or U never overrides an S or P.

## 2. The stages

| # | Stage | Who | Gate (the QA layer runs it) | Profile |
|---|---|---|---|---|
| S0 | **Research** | agent | `qa/gates/research.md`: ≥3 competitor videos analysed with a stated gap, every fact sourced with a checked quote, one deliverable chosen, outlier bar met | `research` |
| S1 | **Plan** | **owner picks topic + package**; agent proposes | `qa/gates/plan.md`: the promise is a concrete outcome, it is demoable, it is not a repeat. Package concept: `qa/gates/package.md --phase concept` | `plan`, `package` |
| S2 | **Design** | **owner approves the animatic**; agent designs | `qa/gates/script.md` (runtime ±15 % at 150 wpm, ≤30 % experiments, no stage directions, community CTA, claims sourced) **and** `qa/gates/storyboard.md` | `design` |
| S3 | **Capture** | owner records; agent captures approved demos | `qa/gates/capture.md`: pre-flight before record day, line coverage after | `capture` |
| S4 | **Edit** | agent | `qa/gates/edit.md`: house-guide checks, loudness, technique events, conformance to the storyboard | `edit` |
| S5 | **Package** | agent drafts; **owner screens** | `qa/gates/package.md`: titles, thumbnails, shorts, description | `package` |
| S6 | **Publish** | **owner says yes per batch**; agent preps and syncs | `qa/gates/publish.md`: nothing scheduled without the owner's yes; every post ends with its URL | `publish` |
| S7 | **Measure** | agent | `qa/gates/measure.md`: postmortem filed by D+8 with every signal routed to an owner | `rules` |

Two more profiles cross the stages: `qa` (gates, escapes, the monthly audit) and `message` (reply-only: answers
"what's next" questions, writes nothing). That makes the ten profiles in `jobs/profiles.json`.

What each profile may write is its lane in `jobs/profiles.json`. Page-owned fields inside those docs (the owner's
picks, answers, freezes and waivers) are stripped from every agent write.

## 3. Record layer

The `projects/{key}` tree is the spine (`SCHEMA.md`): one project doc, one `stages/<phase>` doc per stage (one writer
lane each), `deliverables/<id>/versions/<v>` (write-once produced work) with `rounds/<n>` (the owner's notes and
verdicts), `marks/<scope>` (the owner's overlays), `qa/<runId>` (one doc per gate run, create-only) and
`results/<deliverableId>__<window>`. Status is computed, never stored.

Every agent run is one job with its profile and project key, so time per stage is recorded as a side effect.

## 4. Learn layer: signal routing

S7 writes; each owner applies. A rule changes grade only through the learning log: signal, projects, before → after,
the owner who applied it.

| Signal | Primary owner | How it is attributed |
|---|---|---|
| Impressions click-through | S5 Package (title, thumbnail) | Compared with our trailing median, per title and thumbnail variant |
| First-30 s retention | S2 Design (cold open) | Script line timings against edit events at each dip |
| Mid-video dips and spikes | S4 Edit or S2 Design | Dip time → technique event → storyboard beat; the postmortem names one owner per dip |
| Shorts % viewed | S5 Package (hook variant) | Hook variant from the package lineage |
| Community joins | S2 Design (CTA wording) | Per project, per CTA experiment |
| The owner's review notes | **The stage whose gate should have caught it** | Each note is classified as an *escape* (section 5) |
| Hours per stage | Record layer | The bottleneck stage gets the next build |

## 5. QA layer: gates, escapes, audit

**Gates.** Each hand-off has a runnable spec in `qa/gates/<stage>.md` (checks, thresholds, the command) and is run by
a QA job, never by the producer. **Gates warn; the owner decides.** A failing run raises one decision card (policy
`fix.gate`) with the failing checks: *fix* (a follow-up to the producing stage, then the gate runs again) or
*proceed* (logged on the run as `waived`, with the reason). The gate holds the hand-off until that card is answered;
it does not get to overrule the person. A waived failure that later shows up as an audience or review problem counts
as an escape.

**Escapes.** Anything the owner or the audience catches that a gate passed is an escape. Each is logged in
`qa/escapes.csv` (`date, episode, stage, defect, caught_by, gate_gap, fix, new_check`) and must end in either a new
gate check or a written reason why it cannot be automated. The first review round produced five: three became
automated edit checks, one (eye line) is logged as a capture check still to build, and the fifth ("the motion
graphics look low effort") is recorded as taste, not automatable.

**Audit** (monthly): gate coverage (did every hand-off have a gate run), gate health (escapes per project; gates with
zero failures in three months may be too loose), rule hygiene, lane discipline (any non-empty
`jobs/runs/*/dropped.json`, any qa run not written by a qa job), drift, flow (hours per stage) and outcome. Output: a
score, the top three findings and **one** next build.

## 6. Cadence

Production is per piece and unscheduled. Each project moves S0 → S5 at its own pace with gates between; only the
posting plan carries dates. Nothing polls: work starts when the owner presses Send, or when a scheduled sweep finds
finished results to apply, a timeout to resume or a stale lease to reap.
