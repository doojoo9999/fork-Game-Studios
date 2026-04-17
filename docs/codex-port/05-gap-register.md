# Gap Register

| Gap | State | Details |
| --- | --- | --- |
| interaction-tools | resolved | Generated Codex prompts and skills replace `AskUserQuestion` references with direct user prompts and plain conversational gating. |
| task-tool | resolved | Generated Codex prompts and skills replace Claude `Task` references with Codex multi-agent guidance centered on `spawn_agent`, `send_input`, `wait_agent`, and `close_agent`. |
| supporting-doc-paths | resolved | The port now generates `.codex/docs/**` mirrors from `.claude/docs/**` and rewrites Codex-facing references to the mirrored paths. |
| hooks-parity | translated | Repo-local Codex hooks are enabled for supported events (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`); unsupported Claude-only hook events remain documented as intentional runtime differences rather than open gaps. |
