        # Source Manifest

        - Source repository commit: `3807bcdfc8b78b02837f6f175cf9b138b39def73`
        - Source repository remote: `https://github.com/doojoo9999/fork-Game-Studios.git`
        - Source of truth for parity work: existing `.claude/**` files plus `CLAUDE.md`

        | Source | Count | Codex Target | Status |
| --- | --- | --- | --- |
| .claude/agents | 49 | .codex/agents/configs + .codex/agents/prompts | generated |
| .claude/skills | 72 | .codex/skills | generated |
| .claude/docs | shared reference | .codex/docs | generated mirror |
| CLAUDE.md | 1 | AGENTS.md + docs/codex-port | translated |
