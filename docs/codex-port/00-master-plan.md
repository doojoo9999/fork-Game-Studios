# Codex Studio Full-Port Plan

- Source baseline: `3807bcdfc8b78b02837f6f175cf9b138b39def73`
- Source counts: `49 agents`, `72 skills`
- Port strategy: preserve public names, port mechanically from `.claude`, track all intentional differences in `04-decision-log.md`
- Current implementation mode: generate repeatable Codex artifacts from source files rather than hand-copying prompts

## Waves
1. Foundation runtime: `AGENTS.md`, `.codex/config.toml`, Codex doc registry
2. Role parity: 49 role prompts + role config layers
3. Skill parity: 72 skill directories copied into `.codex/skills`
4. Workflow tracking: phase checklists, parity matrices, active context log
5. Review and iterate: close open gaps from `05-gap-register.md`

## Non-Negotiables
- Never recreate role or skill behavior from memory when the source file exists
- Keep `.claude` source assets untouched as a reference baseline
- Keep `.codex/docs/**` as the active supporting-doc surface for all Codex prompts and skills
- Ask the user directly instead of relying on Claude-only interaction tools
- Keep team orchestration on Codex multi-agent primitives instead of Claude `Task`
- Keep Codex hooks enabled for the hook events that current Codex supports
