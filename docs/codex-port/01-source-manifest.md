        # Source Manifest

        - Source repository commit: `666e0fcb5ad3f5f0f56e1219e8cf03d44e62a49a`
        - Source repository remote: `https://github.com/doojoo9999/fork-Game-Studios.git`
        - Source of truth for parity work: existing `.claude/**` files plus `CLAUDE.md`

        | Source | Count | Codex Target | Status |
| --- | --- | --- | --- |
| .claude/agents | 49 | .codex/agents/configs + .codex/agents/prompts | generated |
| .claude/skills | 72 | .codex/skills | generated |
| .claude/docs | shared reference | .claude/docs (preserved) | reference |
| CLAUDE.md | 1 | AGENTS.md + docs/codex-port | translated |
