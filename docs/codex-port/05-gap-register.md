# Gap Register

| Gap | State | Details |
| --- | --- | --- |
| interaction-tools | open | Source skills mention `AskUserQuestion`; Codex requires direct user prompts instead. |
| task-tool | open | Source team skills mention Claude `Task`; Codex port keeps this as a documented translation to `spawn_agent` / `wait_agent`. |
| supporting-doc-paths | open | Codex skills currently reference `.claude/docs/**` as the preserved source baseline rather than `.codex/docs/**` mirrors. |
| hooks-parity | open | Claude hook behavior is documented but not enforced through Codex runtime hooks in v1. |
