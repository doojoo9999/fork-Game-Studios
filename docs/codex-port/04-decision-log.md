# Decision Log

- Preserve public role names and skill names from the Claude version unless a Codex name collision is discovered.
- Generate `.codex/docs/**` as a transformed mirror of `.claude/docs/**` so Codex prompts and skills avoid Claude-only paths.
- Replace Claude-only interaction primitives (`AskUserQuestion`, `Task`) with direct user prompts and Codex multi-agent primitives.
- Enable repo-local Codex hooks with `.codex/hooks.json` for the hook events current Codex supports, and map unsupported Claude-only hook events to AGENTS rules plus active-context docs.
