---
name: skill-test
description: "Validate skill files for structural compliance and behavioral correctness. Three modes: static (linter), spec (behavioral), audit (coverage report)."
argument-hint: "static [skill-name | all] | spec [skill-name] | audit"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write
context: fork
---

# Skill Test

Validates `.claude/skills/*/SKILL.md` files for structural compliance and
behavioral correctness. No external dependencies — runs entirely within the
existing skill/hook/template architecture.

**Three modes:**

| Mode | Command | Purpose | Token Cost |
|------|---------|---------|------------|
| `static` | `/skill-test static [name\|all]` | Structural linter — 7 compliance checks per skill | Low (~1k/skill) |
| `spec` | `/skill-test spec [name]` | Behavioral verifier — evaluates assertions in test spec | Medium (~5k/skill) |
| `audit` | `/skill-test audit` | Coverage report — which skills have specs, last test dates | Low (~2k total) |

---

## Phase 1: Parse Arguments

Determine mode from the first argument:

- `static [name]` → run 7 structural checks on one skill
- `static all` → run 7 structural checks on all skills (Glob `.claude/skills/*/SKILL.md`)
- `spec [name]` → read skill + test spec, evaluate assertions
- `audit` (or no argument) → read catalog, list all skills, show coverage

If argument is missing or unrecognized, output usage and stop.

---

## Phase 2A: Static Mode — Structural Linter

For each skill being tested, read its `SKILL.md` fully and run all 7 checks:

### Check 1 — Required Frontmatter Fields
The file must contain all of these in the YAML frontmatter block:
- `name:`
- `description:`
- `argument-hint:`
- `user-invocable:`
- `allowed-tools:`

**FAIL** if any are absent.

### Check 2 — Multiple Phases
The skill must have ≥2 numbered phase headings. Look for patterns like:
- `## Phase N` or `## Phase N:`
- `## N.` (numbered top-level sections)
- At least 2 distinct `##` headings if phases aren't explicitly numbered

**FAIL** if fewer than 2 phase-like headings are found.

### Check 3 — Verdict Keywords
The skill must contain at least one of: `PASS`, `FAIL`, `CONCERNS`, `APPROVED`,
`BLOCKED`, `COMPLETE`, `READY`, `COMPLIANT`, `NON-COMPLIANT`

**FAIL** if none are present.

### Check 4 — Collaborative Protocol Language
The skill must contain ask-before-write language. Look for:
- `"May I write"` (canonical form)
- `"before writing"` or `"approval"` near file-write instructions
- `"ask"` + `"write"` in close proximity (within same section)

**WARN** if absent (some read-only skills legitimately skip this).
**FAIL** if `allowed-tools` includes `Write` or `Edit` but no ask-before-write language is found.

### Check 5 — Next-Step Handoff
The skill must end with a recommended next action or follow-up path. Look for:
- A final section mentioning another skill (e.g., `/story-done`, `/gate-check`)
- "Recommended next" or "next step" phrasing
- A "Follow-Up" or "After this" section

**WARN** if absent.

### Check 6 — Fork Context Complexity
If frontmatter contains `context: fork`, the skill should have ≥5 phase headings
(`##` level or numbered Phase N headers). Fork context is for complex multi-phase
skills; simple skills should not use it.

**WARN** if `context: fork` is set but fewer than 5 phases found.

### Check 7 — Argument Hint Plausibility
`argument-hint` must be non-empty. If the skill body mentions multiple modes
(e.g., "Mode A | Mode B"), the hint should reflect them. Cross-reference the
hint against the first phase's "Parse Arguments" section.

**WARN** if hint is `""` or if documented modes don't match hint.

---

### Static Mode Output Format

For a single skill:
```
=== Skill Static Check: /[name] ===

Check 1 — Frontmatter Fields:    PASS
Check 2 — Multiple Phases:       PASS (7 phases found)
Check 3 — Verdict Keywords:      PASS (PASS, FAIL, CONCERNS)
Check 4 — Collaborative Protocol: PASS ("May I write" found)
Check 5 — Next-Step Handoff:     WARN (no follow-up section found)
Check 6 — Fork Context Complexity: PASS (8 phases, context: fork set)
Check 7 — Argument Hint:         PASS

Verdict: WARNINGS (1 warning, 0 failures)
Recommended: Add a "Follow-Up Actions" section at the end of the skill.
```

For `static all`, produce a summary table then list any non-compliant skills:
```
=== Skill Static Check: All 52 Skills ===

Skill                  | Result       | Issues
-----------------------|--------------|-------
gate-check             | COMPLIANT    |
design-review          | COMPLIANT    |
story-readiness        | WARNINGS     | Check 5: no handoff
...

Summary: 48 COMPLIANT, 3 WARNINGS, 1 NON-COMPLIANT
Aggregate Verdict: N WARNINGS / N FAILURES
```

---

## Phase 2B: Spec Mode — Behavioral Verifier

### Step 1 — Locate Files

Find skill at `.claude/skills/[name]/SKILL.md`.
Find spec at `tests/skills/[name].md`.

If either is missing:
- Missing skill: "Skill '[name]' not found in `.claude/skills/`."
- Missing spec: "No test spec found for '[name]'. Run `/skill-test audit` to see
  coverage gaps, or create a spec using the template at
  `.claude/docs/templates/skill-test-spec.md`."

### Step 2 — Read Both Files

Read the skill file and test spec file completely.

### Step 3 — Evaluate Assertions

For each **Test Case** in the spec:

1. Read the **Fixture** description (assumed state of project files)
2. Read the **Expected behavior** steps
3. Read each **Assertion** checkbox

For each assertion, evaluate whether the skill's written instructions, if
followed correctly given the fixture state, would satisfy it. This is a
Claude-evaluated reasoning check, not code execution.

Mark each assertion:
- **PASS** — skill instructions clearly satisfy this assertion
- **PARTIAL** — skill instructions partially address it, but with ambiguity
- **FAIL** — skill instructions would NOT satisfy this assertion given the fixture

For **Protocol Compliance** assertions (always present):
- Check whether the skill requires "May I write" before file writes
- Check whether the skill presents findings before requesting approval
- Check whether the skill ends with a recommended next step
- Check whether the skill avoids auto-creating files without approval

### Step 4 — Build Report

```
=== Skill Spec Test: /[name] ===
Date: [date]
Spec: tests/skills/[name].md

Case 1: [Happy Path — name]
  Fixture: [summary]
  Assertions:
    [PASS] [assertion text]
    [FAIL] [assertion text]
       Reason: The skill's Phase 3 says "..." but the fixture state means "..."
  Case Verdict: FAIL

Case 2: [Edge Case — name]
  ...
  Case Verdict: PASS

Protocol Compliance:
  [PASS] Uses "May I write" before file writes
  [PASS] Presents findings before asking approval
  [WARN] No explicit next-step handoff at end

Overall Verdict: FAIL (1 case failed, 1 warning)
```

### Step 5 — Offer to Write Results

"May I write these results to `tests/results/skill-test-spec-[name]-[date].md`
and update `tests/skills/catalog.yaml`?"

If yes:
- Write results file to `tests/results/`
- Update the skill's entry in `tests/skills/catalog.yaml`:
  - `last_spec: [date]`
  - `last_spec_result: PASS|PARTIAL|FAIL`

---

## Phase 2C: Audit Mode — Coverage Report

### Step 1 — Read Catalog

Read `tests/skills/catalog.yaml`. If missing, note that catalog doesn't exist
yet (first-run state).

### Step 2 — Enumerate All Skills

Glob `.claude/skills/*/SKILL.md` to get the complete list of skills.
Extract skill name from each path (directory name).

### Step 3 — Build Coverage Table

For each skill:
- Check if a spec file exists at `tests/skills/[name].md`
- Look up `last_static`, `last_static_result`, `last_spec`, `last_spec_result`
  from catalog (or mark as "never" if not in catalog)
- Assign priority:
  - `critical` — gate-check, design-review, story-readiness, story-done, review-all-gdds, architecture-review
  - `high` — create-epics-stories, create-control-manifest, propagate-design-change, story-done
  - `medium` — team-* skills, sprint-plan, sprint-status
  - `low` — all others

### Step 4 — Output Report

```
=== Skill Test Coverage Audit ===
Date: [date]
Total skills: 52
Specs written: 4 (7.7%)
Never tested (static): 48

Coverage Table:
Skill                  | Has Spec | Last Static      | Static Result | Last Spec        | Spec Result | Priority
-----------------------|----------|------------------|---------------|------------------|-------------|----------
gate-check             | YES      | never            | —             | never            | —           | critical
design-review          | YES      | never            | —             | never            | —           | critical
story-readiness        | YES      | never            | —             | never            | —           | critical
story-done             | YES      | never            | —             | never            | —           | critical
architecture-review    | NO       | never            | —             | never            | —           | critical
review-all-gdds        | NO       | never            | —             | never            | —           | critical
...

Top 5 Priority Gaps (no spec, critical/high priority):
1. /architecture-review — critical, no spec
2. /review-all-gdds — critical, no spec
3. /create-epics-stories — high, no spec
4. /propagate-design-change — high, no spec
5. /sprint-plan — medium, no spec

Coverage: 4/52 specs (7.7%)
```

No file writes in audit mode.

Offer: "Would you like to run `/skill-test static all` to check structural
compliance across all skills? Or `/skill-test spec [name]` to run a specific
behavioral test?"

---

## Phase 3: Recommended Next Steps

After any mode completes, offer contextual follow-up:

- After `static [name]`: "Run `/skill-test spec [name]` to validate behavioral
  correctness if a test spec exists."
- After `static all` with failures: "Address NON-COMPLIANT skills first. Run
  `/skill-test static [name]` individually for detailed remediation guidance."
- After `spec [name]` PASS: "Update `tests/skills/catalog.yaml` to record this
  pass date. Consider running `/skill-test audit` to find the next spec gap."
- After `spec [name]` FAIL: "Review the failing assertions and update the skill
  or the test spec to resolve the mismatch."
- After `audit`: "Start with the critical-priority gaps. Use the spec template
  at `.claude/docs/templates/skill-test-spec.md` to create new specs."
