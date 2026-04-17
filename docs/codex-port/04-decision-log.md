# Decision Log

- Preserve public role names and skill names from the Claude version unless a Codex name collision is discovered.
- Treat `.claude/docs/**` as a live reference baseline during the first Codex port instead of bulk-moving every supporting document.
- Replace Claude-only interaction primitives (`AskUserQuestion`, `Task`) with direct user questions and Codex multi-agent primitives.
- Do not rely on `.claude/hooks/**` for parity because Codex hooks are still experimental; track equivalent control points in documentation and AGENTS instructions.
