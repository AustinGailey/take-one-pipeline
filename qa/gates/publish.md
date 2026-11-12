# Gate S6: Publish

> **Spec only in this repo.** This is the gate as it runs in production. Its checker and the media tools and rulebooks it names are not published here; `qa/run_gate.py` in this repo runs the `plan` and `script` gates.

**Hand-off:** Publish → Measure (and the release itself). **Artifact:** the project's `posts/*` docs (`SCHEMA.md` §3.post: `plan.*`
page-owned, `prep.*` + `publish.*` S6), `projects/<key>/stages/publish` (§3.stage-publish: prep run, checklist, syncedAt) and the
`decisions/schedule-*` consent docs. **Version:** `stages/publish.liveTitleVariant` (the title live at publish).
**Criteria source:** `PIPELINE.md` section 2, S6 row; `PACKAGE-RULES.md` section G (release checklist); `PUBLISHING.md` section 5.
**Runs as:** a qa run (`projects/<key>/qa/<runId>`, stage `publish`, gate `qa/gates/publish.md`) through `content-qa`. Never by
`content-publish`. Gates warn, never block. Run it twice: before the batch is scheduled (Ready posts) and after the release window
(posted URLs, sync).

## Run
```bash
python3 qa/run_gate.py publish --key <key> --bundle <jobs/runs/<job>/bundle.json> --job <sj-id> --producer-stage publish
# by hand: --doc posts/<postId>=<file>.json per post, --doc projects/<key>/stages/publish=<file>.json, --doc decisions/schedule-<key>=<file>.json
# check alone:
python3 qa/checks/publish_check.py --input <out-dir>/raw/publish/publish-input.json [--now 2026-11-01T12:00:00Z] -o <out-dir>/publish.json
```
Outputs: `<out-dir>/publish.json`, `qa/runs/<runId>.json`, `qa/<runId>.write.json`. Exit is always 0.

## Checks
| Check | Threshold | Fails when | Notes |
|---|---|---|---|
| `posts_present` | ≥1 `posts/*` for the project | none | The page creates them at greenlight (long) and sign-off (shorts) |
| `prep_ran` | `stages/publish.prep.at` set and every post has `prep.checkedAt` | prep never ran (some unprepped: warn) | `publish/release_prep.py` |
| `ready_no_blockers.<post>` | a post with `plan.ready` has **0** `prep.issues` of level `bad` (file present, caption present, within limits) | any `bad` issue | `ready_current.<post>`: Ready's `contentHash` = `prep.contentHash` (DM8: Ready attests content) |
| `tt_cut.<post>` | TikTok / Instagram posts that are Ready or scheduled use a `-tt` file (`prep.files[].ref` contains `-tt`) | plain cut (its CTA says "link below") | PACKAGE-RULES G |
| `caption_limit.<post>` | caption ≤ **2200** chars (TikTok, Instagram), ≤ **5000** (YouTube description), title ≤ **100** (YouTube) | over | `plan.captions` (the owner) overrides `prep.captions` |
| `handles.<post>` | copy names the handle of its own platform: the YouTube handle on YouTube, the TikTok / Instagram handle there | the other platform's handle | PACKAGE-RULES G, PUBLISHING §1 |
| `consent.<post>` | a scheduled post (`publish.scheduledFor` or `publish.scheduler.id`) names `publish.scheduleDecisionId`, that decision's `answer.value` is a yes, and its `contentHash` (if recorded) = `prep.contentHash` | no decision, not a yes, or content changed after the yes | `approve.schedule` is a floor: never auto (SCHEMA §5) |
| `date_match.<post>` | `publish.scheduledFor.date` = the post's effective date (`plan.date`, or anchor + offset unless pinned) | differs ("moved": the scheduler still has the old date) | SCHEMA §3.post `state moved` |
| `posted_url.<post>` | effective date passed ⇒ `publish.url` or `plan.manual.url` | no URL after the date (today: warn) | Instagram and YouTube URLs are pasted by the owner; sync fills the scheduler ones |
| `depends.<post>` | `prep.dependsOn`: `needs-url` deps have a URL before this post is Ready/scheduled; `after` deps are dated earlier by `gapDays` | violated | Shorts Related video needs the long form URL |
| `free_resource_first` | `deliverablePlan.<kind>.shipRule.before == "long"` ⇒ that kind's first post ≤ the long form's date − gapDays | later | Skipped when no shipRule; warn when a side is undated |
| `checklist` | every `stages/publish.checklist` item ok | warn only | PACKAGE-RULES G items release_prep computes |
| `synced` | `stages/publish.syncedAt` ≥ the last posted date | warn only | Sync runs after each post day (PUBLISHING §5.4) |

## Not automated (reason recorded)
- **YouTube Studio steps** (title, Test & Compare thumbnails, chapters, end screens, pinned comment, Shorts Related video): The owner's
  manual checklist `marks/publish.studioChecklist`; the gate cannot see Studio. `posted_url` catches the outcome.
- **Community link in every bio:** account state outside the db; checked by hand at the monthly audit.
- **Blob deletion after posting:** `publish/blob.py` housekeeping, not a release defect.

## Escapes that changed this gate
| Date | Escape | Check added |
|---|---|---|
| 2026-10-21 | First version, written from PIPELINE.md S6 + PACKAGE-RULES G when the publish gate was first due (Take One new model) | the whole gate |
