# Jobs contract: leases, one terminal write, lanes

One rule set for every unattended agent behind Take One. It exists because the first version showed "hanging" agents
that were not running: a status the agent set itself, then nobody closed.

## The four rules

1. **Lease, not status.** A job is *Working* only while it holds a fresh lease (`leaseUntil` in the future) **and** its
   process is alive. The holder renews the lease on every heartbeat. An expired lease means not working, whatever a
   status field says. UIs derive the state; they never show a bare status as "working".
2. **The supervisor owns the terminal write.** Unattended agents run under a small supervisor that launches
   `claude -p` with a fixed tool allowlist and `--permission-mode dontAsk` (a disallowed tool is denied at once instead
   of waiting on a prompt nobody answers), a hard timeout, and on exit writes **exactly one** terminal state from the
   agent's JSON result and its permission denials. The agent cannot forget to close its job.
3. **The reaper.** Anything with an expired lease and no terminal state gets one: `requeued` (attempt + 1) or, after
   2 attempts, `needs-owner` with the blocking cause.
4. **Parking is terminal, and typed.** A job that stops for the owner ends as `needs-owner` with either a typed `ask`
   `{kind:"approve"|"pick"|"answer"|"sign-in"|"review", question, context?, options?, sources?}` (a decision only the
   owner can make, answered in place) or a `block` `{key, cause, fix, tool?, since}` (a permission, tool or config
   block, grouped by `key` and re-run when the cause is fixed). Never a silent `waiting`, never a tool in an `ask`.

## Derived states (what the UI shows)

| Derived | When |
|---|---|
| Working | lease fresh **and** process alive |
| Not running | status says running, but the lease expired or the process is gone |
| Queued | no lease, not terminal, waiting to be taken |
| Needs you | terminal `needs-owner` with a typed `ask` |
| Blocked on setup | terminal `needs-owner` with a `block` (grouped by `block.key`) |
| Done / Failed | terminal `done` / `failed` + reason |
| Back in the queue | terminal `handed-back` (timeout, stop, budget, agent) or `requeued` (reaper), attempt + 1 |

Terminal states: `done` · `failed` (+`reason`) · `needs-owner` (+typed `ask`, or `block` + `blockingTool`) ·
`handed-back` (+`resume`) · `requeued` (+`nextAttempt`, reaper only).

## The supervisor: `jobs/agentjob.py` (stdlib Python)

- `agentjob.py start <app> <job> --prompt-file F --cwd DIR --tools "Read Edit Bash" [--allow 'Bash(node:*)']…
  [--add-dir D]… [--model sonnet] [--timeout 1500] [--attempt N] [--on-deny stop|continue]` launches a detached
  supervisor and returns `{started, pid, leaseUntil, hardDeadline}` at once (the caller never blocks on a long run).
- State per job in `~/.agent-jobs/<app>/` (`AGENTJOB_HOME` overrides the root): `.spec.json`, `.lease.json` (renewed
  every 15 s, 60 s lease, records the agent's process tree every 3 s), `.terminal.json` (written once with `link()`,
  first writer wins), `.out.json`, `.stream.jsonl`, `.err`.
- The agent runs `claude -p --permission-mode dontAsk --strict-mcp-config --tools … --allowedTools …`. Under dontAsk
  even Write and Edit are denied unless allowed, so the listed `--tools` are the allowlist, except Bash: Bash runs only
  the commands an `--allow 'Bash(node:*)'` pattern names.
  `--on-deny stop` (default): the first permission denial in the event stream ends the job at once as `needs-owner`
  naming the tool. Hard timeout: SIGINT, SIGTERM, SIGKILL to the agent **and every descendant** (tool commands run in
  their own process groups), then `handed-back` with a resume note.
- The agent may end its report with
  ```` ```job {"status":"done|blocked|handed-back","ask":{kind,question,context?,options?},"resume":"…","outputs":[…]}``` ````
  (`blocked` = the owner's decision; a string `ask` is wrapped as `{kind:"answer"}`). A denial writes
  `block:{key:"bash:<cmd>"|"tool:<Tool>", cause, fix}`; a kill or a reap after 2 attempts writes `agent:killed` /
  `agent:died`.
- `status <app> [job]` derives states · `reap <app>` reaps stale leases (and kills leftovers the dead supervisor
  recorded) · `export <app>` lists terminals not yet applied · `ack <app> <job>` marks one applied ·
  `stop <app> <job>` asks the supervisor to stop (it hands back with a resume note).
- `AGENTJOB_CLAUDE` names the agent binary. Anything that reads a prompt on stdin and emits the same `stream-json`
  events works, which is how the tests run with `sample/stub_agent.py` and no API key.

## The dispatcher: `jobs/dispatch.py`

The agent has no access to the document store. Its `results.json` on disk is the source, and the store is written
from it by exactly one writer: the owner's page when it is open, a scheduled sweep when it is closed. In this repo
`sample/run_sample.py` plays that writer.

- **Start.** The caller files the request and calls `dispatch.py start <bundle>` (the request plus the project's docs,
  keyed by store path). `dispatch.py` picks the profile, writes `jobs/runs/<job>/bundle.json` and `prompt.md`, and
  starts `agentjob`. The supervisor holds the lease within a second.
- **Profiles and lanes** (`jobs/profiles.json`, the single source): research, plan, design, package, capture, edit,
  qa, rules, message, publish. Each names its skill, tools, Bash allow rules, timeout and `writes` lane
  `[path regex, fields | "*", {create}?]`. `pageOwned` lists the owner's fields inside agent-writable docs; collect
  strips them. `route` maps a request's context (action, then stage, then kind) to a profile; `route.never` keeps
  non-agent work off the agents. `publish/schedule` runs only when `consent.live` is true and the bundle carries an
  answered `decisions/schedule-{k}` yes under 24 h for the same batch.
- **Agent contract** (`dispatch.py prompt_for`): no store, no MCP, one literal Bash command per call; writes go to
  `jobs/runs/<job>/results.json` `{status, reply, writes:[{path, op:set|merge, data}], files:[{path, upload}],
  followups:[{text, context}], ask:{kind, question, options, select, sources}}`; followups must carry
  `context.projectKey`.
- **Progress.** The caller polls `dispatch.py status`: step (last tool call), tool count, elapsed, lease.
- **Results.** On a terminal state the caller runs `dispatch.py collect`: the lane check. Anything outside the lane,
  and every page-owned field, is dropped into `jobs/runs/<job>/dropped.json` (a JSON array, `[]` when clean) and
  raised as a `decisions/lane-<job>` card; `create` ops refuse an existing doc; the surviving writes are applied; the
  follow-ups are filed and run; then `dispatch.py ack`.
- **Timeouts.** A first-attempt hard timeout is resumed on the same agent session (`dispatch.py resume`), attempt 2,
  with the draft on disk; a second timeout hands back to the owner.
- **Fail fast.** A denied tool ends the job in seconds as a setup block; the card shows the cause and the exact
  profile line to add, and `dispatch.py rerun` runs it again.

## Tests

`tests/test_pipeline.py` (stub agent, no keys) covers: a clean run through two stages and their gates; a bad script
held by its gate; a producer's write to the QA lane dropped at collect; a denied tool ending as a setup block;
the gate runner refusing to check its own profile's work.

The production copy of this contract was also exercised against a real agent CLI in October 2026 (denied tool,
`kill -9` of supervisor and agent, hard timeout). Those runs are not reproduced here and no timings from them are
claimed.
