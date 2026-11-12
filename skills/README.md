# Skills

Each profile in `jobs/profiles.json` names a skill: the instructions a stage agent follows (`content-research`,
`episode-design`, `content-qa` and so on). `jobs/dispatch.py` points the agent at `skills/<skill>/SKILL.md`.

The production skill files are not published. They hold the stage rulebooks and house style, which are specific to
one channel. To run a real agent instead of the stub, add your own `skills/<skill>/SKILL.md` for the profiles you use
and leave `AGENTJOB_CLAUDE` unset so the supervisor launches the `claude` CLI.
