# Codex Studio Charter

This repository now carries a Codex port alongside the original Claude-oriented assets.

## Operating Model
- Treat `.claude/**` as the source baseline during the parity port.
- Treat `.codex/**` and `docs/codex-port/**` as the Codex target surface.
- Preserve public role names and skill names unless a documented Codex constraint forces a change.
- Never recreate prompts or workflow behavior from memory when the source file exists.

## User Control
- The user keeps decision authority at all times.
- Present options and tradeoffs before making cross-domain or architecture-level changes.
- Use stage-gated approval rather than asking before every single write.
- If a source workflow refers to `AskUserQuestion`, ask the user directly in concise prose.

## Multi-Agent Rules
- Use Codex multi-agent tools for bounded sidecar work or independent review streams.
- Do not let multiple agents edit the same path concurrently.
- Treat Tier 1 roles as gatekeepers and adjudicators, not feature implementers.
- Escalate design conflicts to `creative-director`, technical conflicts to `technical-director`, and schedule/scope conflicts to `producer`.

## Path Ownership
- `.codex/agents/**`: Codex role configs and prompt ports.
- `.codex/skills/**`: Codex skill ports that preserve source names.
- `docs/codex-port/**`: parity tracking, active context, gap register, and port execution docs.
- `.claude/**`: preserved source reference; avoid editing unless the user explicitly asks for source-side changes.

## Anti-Hallucination Rules
- Read the source artifact before editing its Codex counterpart.
- Record intentional differences in `docs/codex-port/04-decision-log.md`.
- Record open uncertainties or unsupported features in `docs/codex-port/05-gap-register.md`.
- Update `docs/codex-port/06-active-context.md` whenever the active wave or next steps change materially.

## Current Parity Strategy
- Hooks are documented but not treated as runtime-critical parity because Codex hooks remain experimental.
- Source references under `.claude/docs/**` remain valid during the first Codex port.
- Generated Codex assets should stay reproducible from `tools/codex_port/bootstrap_codex_port.py`.
