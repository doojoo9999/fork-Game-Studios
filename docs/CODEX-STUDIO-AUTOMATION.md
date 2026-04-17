# Codex Studio Automation

This repo now ships with two Codex-native helper tools under `tools/codex_port/`:

- `skill_harness.py` — structural, rubric, and optional live smoke checks for the 72 in-repo skills
- `studio_orchestrator.py` — idea-to-execution runbook generator that maps a game idea to the right skill sequence

The goal is not to replace the 72 skills. The goal is to make them easier to use as one coordinated system.

## 1. Validate the port

Run a coverage audit:

```bash
python3 tools/codex_port/skill_harness.py audit
```

Run structural checks across all 72 skills:

```bash
python3 tools/codex_port/skill_harness.py static all
```

Run rubric checks across all 72 skills:

```bash
python3 tools/codex_port/skill_harness.py category all
```

Run a live smoke invocation for a specific skill:

```bash
python3 tools/codex_port/skill_harness.py smoke help
python3 tools/codex_port/skill_harness.py smoke team-ui
```

Notes:

- `static` and `category` are local heuristic checks. They do not call the model.
- `smoke` runs `codex exec` with `CODEX_SKIP_STOP_VERIFY=1` and `approval_policy="never"`.
- Smoke output is written to `tmp/skill-harness/live/`.

## 2. Turn an idea into a runbook

Generate a runbook from a game idea:

```bash
python3 tools/codex_port/studio_orchestrator.py plan \
  --idea "stylized co-op extraction roguelite" \
  --engine unity \
  --goal vertical-slice
```

Write the runbook to disk:

```bash
python3 tools/codex_port/studio_orchestrator.py plan \
  --idea "stylized co-op extraction roguelite" \
  --engine unity \
  --goal vertical-slice \
  --write production/session-state/runbooks/co-op-extraction.md
```

Check what to do next for the current repo state:

```bash
python3 tools/codex_port/studio_orchestrator.py next
```

See how all 72 skills distribute across the lifecycle:

```bash
python3 tools/codex_port/studio_orchestrator.py coverage
```

## 3. Recommended operating model

Use the tools in this order:

1. `studio_orchestrator.py plan` to produce the phase-aware runbook.
2. Start the actual studio session with `/start` or `/brainstorm`.
3. Follow the runbook phase by phase, keeping user approvals at the decision gates.
4. Use `/help`, `/project-stage-detect`, and `/gate-check` whenever state becomes unclear.
5. Re-run `skill_harness.py static all` and `category all` after any large port edits.
6. Use `skill_harness.py smoke <skill>` for representative live verification.

## 4. Full-skill utilization strategy

The orchestrator separates skills into three layers:

- Workflow backbone: the linear 7-phase path from `.codex/docs/workflow-catalog.yaml`
- Specialist accelerators: uncataloged team, testing, QA, analysis, and recovery skills
- Later lifecycle backlog: skills not active yet for the current goal, but already mapped to later phases

That means a `vertical-slice` runbook activates only the right subset immediately, but still schedules the remaining skills for later phases instead of hiding them.

## 5. Important limits

- The helper tools keep the user as the final decision maker. They do not auto-run multi-phase implementation without approval.
- `studio_orchestrator.py` is phase-aware, not artifact-perfect. It reads the repo state coarsely to decide where you are.
- `skill_harness.py category` uses heuristic rule checks derived from `CCGS Skill Testing Framework/quality-rubric.md`. It is a compatibility signal, not a formal proof.
- Some repo docs still reflect older Claude counts or path assumptions. Treat the workflow catalog, the in-repo `.codex/skills/*`, and these helper tools as the current Codex runtime surface.
