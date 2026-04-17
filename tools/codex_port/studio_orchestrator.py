#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    REPO_ROOT,
    SkillRecord,
    WorkflowStep,
    detect_current_phase,
    load_skill_records,
    parse_workflow_catalog,
    phase_slice,
    slugify,
    workflow_phase_order,
)


GOAL_TO_PHASE = {
    "concept-pack": "concept",
    "systems-ready": "systems-design",
    "vertical-slice": "pre-production",
    "first-playable": "production",
    "quality-lock": "polish",
    "ship": "release",
}

SUPPORT_SKILLS = {
    "concept": [
        "start",
        "help",
        "onboard",
        "project-stage-detect",
        "adopt",
    ],
    "systems-design": [
        "gate-check",
        "quick-design",
        "propagate-design-change",
    ],
    "technical-setup": [
        "gate-check",
        "security-audit",
        "tech-debt",
    ],
    "pre-production": [
        "estimate",
        "playtest-report",
        "qa-plan",
        "test-setup",
        "test-helpers",
        "team-ui",
        "team-combat",
        "team-audio",
        "team-level",
        "team-narrative",
    ],
    "production": [
        "bug-report",
        "bug-triage",
        "scope-check",
        "reverse-document",
        "team-qa",
        "team-live-ops",
        "team-polish",
    ],
    "polish": [
        "smoke-check",
        "soak-test",
        "regression-suite",
        "test-evidence-review",
        "test-flakiness",
        "perf-profile",
        "balance-check",
        "asset-audit",
        "content-audit",
        "milestone-review",
        "team-release",
    ],
    "release": [
        "release-checklist",
        "launch-checklist",
        "changelog",
        "patch-notes",
        "hotfix",
        "day-one-patch",
        "localize",
    ],
    "cross-cutting": [
        "skill-test",
        "skill-improve",
    ],
}

PHASE_DECISIONS = {
    "concept": [
        "concept selection locked by the user after /brainstorm",
        "review mode set in production/review-mode.txt during /start",
    ],
    "systems-design": [
        "MVP system boundaries approved before /design-system loops begin",
        "run /gate-check before moving to architecture",
    ],
    "technical-setup": [
        "engine and core ADRs accepted before /create-control-manifest",
        "security/performance concerns explicitly accepted or fixed before pre-production",
    ],
    "pre-production": [
        "prototype success criteria accepted before epics are split",
        "UX review and accessibility tier locked before implementation picks up",
    ],
    "production": [
        "story pickup and story close remain user-controlled",
        "blocked bugs are triaged before sprint scope is extended",
    ],
    "polish": [
        "quality bar and performance budgets are user-approved before release prep",
    ],
    "release": [
        "ship/no-ship remains a user decision after /release-checklist and /launch-checklist",
    ],
}


@dataclass(slots=True)
class PhasePlan:
    phase: str
    label: str
    core_steps: list[WorkflowStep]
    support_skills: list[SkillRecord]
    decisions: list[str]


def build_skill_index(skills: list[SkillRecord]) -> dict[str, SkillRecord]:
    return {skill.name: skill for skill in skills}


def workflow_steps_by_phase() -> dict[str, list[WorkflowStep]]:
    return parse_workflow_catalog()


def core_commands_for_phase(phase: str, steps_by_phase: dict[str, list[WorkflowStep]]) -> list[WorkflowStep]:
    return steps_by_phase.get(phase, [])


def support_records_for_phase(phase: str, skill_index: dict[str, SkillRecord]) -> list[SkillRecord]:
    names = SUPPORT_SKILLS.get(phase, []) + SUPPORT_SKILLS.get("cross-cutting", [])
    records = [skill_index[name] for name in names if name in skill_index]
    records.sort(key=lambda item: (item.priority, item.name))
    return records


def build_plan(skills: list[SkillRecord], current_phase: str, target_phase: str) -> list[PhasePlan]:
    steps_by_phase = workflow_steps_by_phase()
    skill_index = build_skill_index(skills)
    phases = phase_slice(current_phase, target_phase)
    plans: list[PhasePlan] = []
    for phase in phases:
        core_steps = core_commands_for_phase(phase, steps_by_phase)
        phase_label = core_steps[0].phase_label if core_steps else phase.replace("-", " ").title()
        plans.append(
            PhasePlan(
                phase=phase,
                label=phase_label,
                core_steps=core_steps,
                support_skills=support_records_for_phase(phase, skill_index),
                decisions=PHASE_DECISIONS.get(phase, []),
            )
        )
    return plans


def activated_skill_names(plans: list[PhasePlan]) -> set[str]:
    names: set[str] = set()
    for plan in plans:
        names.update(step.command.lstrip("/") for step in plan.core_steps)
        names.update(skill.name for skill in plan.support_skills)
    return names


def deferred_skills(skills: list[SkillRecord], active: set[str]) -> list[SkillRecord]:
    return sorted((skill for skill in skills if skill.name not in active), key=lambda item: (item.phase, item.name))


def render_markdown(
    idea: str,
    engine: str,
    goal: str,
    current_phase: str,
    target_phase: str,
    plans: list[PhasePlan],
    all_skills: list[SkillRecord],
) -> str:
    active = activated_skill_names(plans)
    deferred = deferred_skills(all_skills, active)
    lines = [
        "# Codex Studio Runbook",
        "",
        f"- Idea: {idea}",
        f"- Engine target: {engine}",
        f"- Current phase: {current_phase}",
        f"- Goal: {goal} -> {target_phase}",
        f"- Active coverage in this runbook: {len(active)}/{len(all_skills)} skills",
        "",
        "## Recommended Start",
        "",
    ]

    first_core = next((step for plan in plans for step in plan.core_steps if step.required), None)
    if first_core:
        lines.append(f"- Primary command: `{first_core.command}`")
    else:
        lines.append("- Primary command: use `/help` to re-evaluate the current phase.")
    lines.append("- Keep the user as approver at every decision point; do not auto-advance across phase gates.")
    lines.append("")

    for plan in plans:
        lines.extend([f"## {plan.label}", ""])
        if plan.core_steps:
            lines.append("### Core Workflow")
            lines.append("")
            for step in plan.core_steps:
                requirement = "required" if step.required else "optional"
                lines.append(f"- `{step.command}` ({requirement}) — {step.description}")
            lines.append("")
        if plan.support_skills:
            lines.append("### Specialist Accelerators")
            lines.append("")
            for skill in plan.support_skills:
                lines.append(f"- `{skill.sample_command}` — {skill.description}")
            lines.append("")
        if plan.decisions:
            lines.append("### Decision Gates")
            lines.append("")
            for decision in plan.decisions:
                lines.append(f"- {decision}")
            lines.append("")

    if deferred:
        grouped: dict[str, list[SkillRecord]] = {}
        for skill in deferred:
            grouped.setdefault(skill.phase, []).append(skill)
        lines.extend(["## Later Lifecycle Coverage", ""])
        for phase in workflow_phase_order():
            records = grouped.get(phase, [])
            if not records:
                continue
            lines.append(f"### {phase}")
            lines.append("")
            for skill in records:
                lines.append(f"- `{skill.sample_command}` — {skill.description}")
            lines.append("")
        extra = grouped.get("auxiliary", []) + grouped.get("team-orchestration", []) + grouped.get("testing-support", [])
        if extra:
            lines.append("### cross-cutting")
            lines.append("")
            seen: set[str] = set()
            for skill in extra:
                if skill.name in seen:
                    continue
                seen.add(skill.name)
                lines.append(f"- `{skill.sample_command}` — {skill.description}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def next_actions(skills: list[SkillRecord], current_phase: str) -> list[str]:
    plans = build_plan(skills, current_phase, current_phase)
    if not plans:
        return ["Use `/help` to re-evaluate the project state."]
    plan = plans[0]
    actions: list[str] = []
    seen: set[str] = set()
    for step in plan.core_steps[:3]:
        if step.command in seen:
            continue
        seen.add(step.command)
        actions.append(f"{step.command} — {step.description}")
    for skill in plan.support_skills[:3]:
        if skill.sample_command in seen:
            continue
        seen.add(skill.sample_command)
        actions.append(f"{skill.sample_command} — {skill.description}")
    return actions


def print_plan_json(
    idea: str,
    engine: str,
    goal: str,
    current_phase: str,
    target_phase: str,
    plans: list[PhasePlan],
    all_skills: list[SkillRecord],
) -> None:
    payload = {
        "idea": idea,
        "engine": engine,
        "goal": goal,
        "current_phase": current_phase,
        "target_phase": target_phase,
        "active_coverage": len(activated_skill_names(plans)),
        "total_skills": len(all_skills),
        "phases": [
            {
                "phase": plan.phase,
                "label": plan.label,
                "core_steps": [asdict(step) for step in plan.core_steps],
                "support_skills": [
                    {
                        "name": skill.name,
                        "sample_command": skill.sample_command,
                        "description": skill.description,
                    }
                    for skill in plan.support_skills
                ],
                "decisions": plan.decisions,
            }
            for plan in plans
        ],
    }
    print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Idea-to-execution runbook generator for the Codex game studio port.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a phase-aware studio runbook.")
    plan_parser.add_argument("--idea", required=True, help="Game idea or feature direction")
    plan_parser.add_argument("--engine", default="unity", help="Engine target, e.g. unity")
    plan_parser.add_argument("--goal", choices=sorted(GOAL_TO_PHASE), default="vertical-slice")
    plan_parser.add_argument("--current-phase", choices=workflow_phase_order(), default="")
    plan_parser.add_argument("--write", default="", help="Optional markdown output path")
    plan_parser.add_argument("--json", action="store_true")

    next_parser = subparsers.add_parser("next", help="Recommend the next commands for the current repo state.")
    next_parser.add_argument("--current-phase", choices=workflow_phase_order(), default="")
    next_parser.add_argument("--json", action="store_true")

    coverage_parser = subparsers.add_parser("coverage", help="Show how the 72 skills distribute across lifecycle phases.")
    coverage_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    skills = load_skill_records()

    if args.command == "coverage":
        by_phase: dict[str, list[str]] = {}
        for skill in skills:
            by_phase.setdefault(skill.phase, []).append(skill.name)
        if args.json:
            print(json.dumps(by_phase, indent=2))
            return
        print("=== Studio Skill Coverage ===")
        for phase, names in sorted(by_phase.items()):
            print(f"- {phase}: {len(names)}")
            for name in sorted(names):
                print(f"  - {name}")
        return

    if args.command == "next":
        current_phase = args.current_phase or detect_current_phase()
        actions = next_actions(skills, current_phase)
        if args.json:
            print(json.dumps({"current_phase": current_phase, "actions": actions}, indent=2))
            return
        print(f"Current phase: {current_phase}")
        print("Recommended next actions:")
        for action in actions:
            print(f"- {action}")
        return

    current_phase = args.current_phase or detect_current_phase()
    target_phase = GOAL_TO_PHASE[args.goal]
    plans = build_plan(skills, current_phase, target_phase)

    if args.json:
        print_plan_json(args.idea, args.engine, args.goal, current_phase, target_phase, plans, skills)
        return

    markdown = render_markdown(args.idea, args.engine, args.goal, current_phase, target_phase, plans, skills)
    print(markdown)

    if args.write:
        output_path = Path(args.write)
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        slug = slugify(args.idea)
        print(f"\nWrote runbook: {output_path} (slug: {slug})")


if __name__ == "__main__":
    main()
