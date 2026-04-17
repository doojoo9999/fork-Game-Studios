#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import REPO_ROOT, SkillRecord, VERDICT_KEYWORDS, load_skill_records


PHASE_RE = re.compile(r"^##\s+", re.MULTILINE)
ASK_WRITE_RE = re.compile(
    r"may i write|file write protocol|before (?:writing|any write)|approval",
    re.IGNORECASE,
)
READ_ONLY_RE = re.compile(
    r"read-only|writes no files|does not write files|reports findings but writes no files|orchestrator does not write files",
    re.IGNORECASE,
)
NEXT_STEP_RE = re.compile(
    r"^##\s+(?:Next Steps|Follow-Up|Recommended Next|After This|Output)\b|/[\w-]+",
    re.IGNORECASE | re.MULTILINE,
)
TABLE_RE = re.compile(r"^\|.+\|$", re.MULTILINE)


@dataclass(slots=True)
class CheckResult:
    code: str
    verdict: str
    detail: str


@dataclass(slots=True)
class SkillReport:
    name: str
    command: str
    report_type: str
    status: str
    checks: list[CheckResult]


def verdict_rank(verdict: str) -> int:
    return {"PASS": 0, "WARN": 1, "FAIL": 2}.get(verdict, 2)


def summarize_status(checks: list[CheckResult]) -> str:
    if any(check.verdict == "FAIL" for check in checks):
        return "FAIL"
    if any(check.verdict == "WARN" for check in checks):
        return "WARN"
    return "PASS"


def static_checks(skill: SkillRecord) -> SkillReport:
    checks: list[CheckResult] = []
    frontmatter = skill.frontmatter
    required_fields = ["name", "description", "argument-hint", "user-invocable", "allowed-tools"]
    missing = [field for field in required_fields if not frontmatter.get(field)]
    checks.append(
        CheckResult(
            code="S1",
            verdict="PASS" if not missing else "FAIL",
            detail="all required frontmatter fields present" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    phase_count = len(PHASE_RE.findall(skill.body))
    checks.append(
        CheckResult(
            code="S2",
            verdict="PASS" if phase_count >= 2 else "FAIL",
            detail=f"{phase_count} section headings found",
        )
    )

    present_keywords = [keyword for keyword in VERDICT_KEYWORDS if keyword in skill.body]
    checks.append(
        CheckResult(
            code="S3",
            verdict="PASS" if present_keywords else "FAIL",
            detail=", ".join(present_keywords) if present_keywords else "no verdict keyword found",
        )
    )

    has_write_protocol = bool(ASK_WRITE_RE.search(skill.body))
    read_only_declared = bool(READ_ONLY_RE.search(skill.body))
    protocol_verdict = "PASS"
    protocol_detail = "approval language found"
    if skill.writes_files and not has_write_protocol:
        if read_only_declared:
            protocol_verdict = "PASS"
            protocol_detail = "read-only or delegated-write language overrides broad tool allowance"
        else:
            protocol_verdict = "FAIL"
            protocol_detail = "writes/edit allowed but no approval language found"
    elif not skill.writes_files and not has_write_protocol:
        protocol_verdict = "PASS" if read_only_declared else "WARN"
        protocol_detail = "read-only language found" if read_only_declared else "read-only or delegated write pattern; no explicit approval language found"
    checks.append(CheckResult(code="S4", verdict=protocol_verdict, detail=protocol_detail))

    has_handoff = bool(NEXT_STEP_RE.search(skill.body[-1200:]))
    checks.append(
        CheckResult(
            code="S5",
            verdict="PASS" if has_handoff else "WARN",
            detail="handoff or follow-up detected" if has_handoff else "no clear handoff section found near end",
        )
    )

    context_value = frontmatter.get("context", "")
    context_is_fork = "fork" in context_value.lower()
    checks.append(
        CheckResult(
            code="S6",
            verdict="PASS" if not context_is_fork or phase_count >= 5 else "WARN",
            detail="context complexity looks plausible" if not context_is_fork or phase_count >= 5 else "fork-like context with fewer than 5 phases",
        )
    )

    mode_words = len(re.findall(r"\b(?:static|spec|category|audit|all|full|lean|solo)\b", skill.body.lower()))
    checks.append(
        CheckResult(
            code="S7",
            verdict="PASS" if skill.argument_hint.strip() else "WARN",
            detail=f"argument hint present; mode words detected={mode_words}" if skill.argument_hint.strip() else "empty argument hint",
        )
    )

    return SkillReport(
        name=skill.name,
        command=skill.sample_command,
        report_type="static",
        status=summarize_status(checks),
        checks=checks,
    )


def _review_mode_check(skill: SkillRecord) -> CheckResult:
    return CheckResult(
        code="MODE",
        verdict="PASS" if skill.has_review_mode_logic else "FAIL",
        detail="full/lean/solo review mode handling found" if skill.has_review_mode_logic else "review mode handling not detected",
    )


def _parallel_check(skill: SkillRecord) -> CheckResult:
    text = skill.lower_body
    if "parallel" in text and ("spawn_agent" in text or "wait_agent" in text):
        return CheckResult("PAR", "PASS", "parallel orchestration language detected")
    if "parallel" in text:
        return CheckResult("PAR", "WARN", "parallel language found without explicit agent tool references")
    return CheckResult("PAR", "FAIL", "parallel orchestration not detected")


def category_checks(skill: SkillRecord, static_report: SkillReport | None = None) -> SkillReport:
    checks: list[CheckResult] = []
    text = skill.lower_body
    category = skill.category
    static_report = static_report or static_checks(skill)

    if category == "gate":
        directors = ["creative-director", "technical-director", "producer", "art-director"]
        mentioned = [name for name in directors if name in text]
        checks.append(_review_mode_check(skill))
        checks.append(CheckResult("G2", "PASS" if len(mentioned) == 4 and "parallel" in text else ("WARN" if len(mentioned) >= 2 else "FAIL"), f"directors mentioned={', '.join(mentioned) or 'none'}"))
        checks.append(CheckResult("G3", "PASS" if "lean" in text and "phase-gate" in text else "FAIL", "lean-mode phase gate handling" if "lean" in text and "phase-gate" in text else "lean gate handling not detected"))
        checks.append(CheckResult("G4", "PASS" if "solo" in text and "skip" in text else "FAIL", "solo-mode skip handling" if "solo" in text and "skip" in text else "solo skip handling not detected"))
        checks.append(CheckResult("G5", "PASS" if "production/stage.txt" not in skill.body or bool(ASK_WRITE_RE.search(skill.body)) else "FAIL", "stage writes appear gated"))
    elif category == "review":
        checks.append(CheckResult("R1", "PASS" if not skill.writes_files or bool(ASK_WRITE_RE.search(skill.body)) else "FAIL", "review writes are gated"))
        checks.append(CheckResult("R2", "PASS" if "8 required sections" in text or "8 sections" in text or "per-section status" in text else "WARN", "section coverage language detected" if "8 required sections" in text or "8 sections" in text or "per-section status" in text else "no explicit section-count language"))
        vocab = ("approved" in text and "needs revision" in text) or ("pass" in skill.body and "concerns" in skill.body and "fail" in skill.body)
        checks.append(CheckResult("R3", "PASS" if vocab else "FAIL", "verdict vocabulary detected" if vocab else "required verdict vocabulary missing"))
        post_analysis = "after its analysis" in text or "post-analysis" in text or "after analysis" in text or "does not spawn director gates during analysis" in text
        checks.append(CheckResult("R4", "PASS" if "spawn_agent" not in text or post_analysis else "WARN", "analysis/gate sequencing looks valid" if "spawn_agent" not in text or post_analysis else "director or lead delegation appears without clear post-analysis sequencing"))
        checks.append(CheckResult("R5", "PASS" if TABLE_RE.search(skill.body) or "checklist" in text else "WARN", "structured findings format detected" if TABLE_RE.search(skill.body) or "checklist" in text else "no clear table/checklist output detected"))
    elif category == "authoring":
        section_cycle = "section-by-section" in text or "one section at a time" in text or "phase 1" in text and "phase 2" in text
        checks.append(CheckResult("A1", "PASS" if section_cycle or skill.name in {"quick-design", "architecture-decision", "create-architecture"} else "WARN", "authoring cycle detected" if section_cycle or skill.name in {"quick-design", "architecture-decision", "create-architecture"} else "no explicit section cycle language"))
        checks.append(CheckResult("A2", "PASS" if ASK_WRITE_RE.search(skill.body) else "FAIL", "approval language found before writes"))
        retrofit = "already exists" in text or "retrofit" in text or "update specific sections" in text or skill.name == "quick-design"
        checks.append(CheckResult("A3", "PASS" if retrofit else "WARN", "retrofit/update path detected" if retrofit else "no retrofit/update path detected"))
        if "creative-director" in text or "technical-director" in text or "art-director" in text:
            checks.append(_review_mode_check(skill))
        else:
            checks.append(CheckResult("A4", "PASS", "no explicit director gate required"))
        skeleton = "skeleton" in text or "all section headers" in text or skill.name in {"quick-design", "architecture-decision", "create-architecture", "ux-review"}
        checks.append(CheckResult("A5", "PASS" if skeleton else "WARN", "skeleton-first or lightweight exemption detected" if skeleton else "no skeleton-first language detected"))
    elif category == "readiness":
        dimension_hits = sum(1 for term in ("design", "architecture", "scope", "definition of done", "dod") if term in text)
        checks.append(CheckResult("RD1", "PASS" if dimension_hits >= 3 else "FAIL", f"dimensions detected={dimension_hits}"))
        hierarchy = ("ready" in text and "needs work" in text and "blocked" in text) or ("complete" in text and "complete with notes" in text and "blocked" in text)
        checks.append(CheckResult("RD2", "PASS" if hierarchy else "FAIL", "verdict hierarchy detected" if hierarchy else "missing multi-level verdict hierarchy"))
        checks.append(CheckResult("RD3", "PASS" if "external action" in text or "cannot be fixed by the story author alone" in text or "proposed adr" in text else "WARN", "blocked semantics described" if "external action" in text or "cannot be fixed by the story author alone" in text or "proposed adr" in text else "blocked semantics not explicit"))
        if "qa-lead" in text or "lead-programmer" in text:
            checks.append(_review_mode_check(skill))
        else:
            checks.append(CheckResult("RD4", "WARN", "no explicit readiness gate agent detected"))
        checks.append(CheckResult("RD5", "PASS" if "next ready story" in text or "surface the next" in text else "WARN", "next-story handoff detected" if "next ready story" in text or "surface the next" in text else "next story handoff missing"))
    elif category == "pipeline":
        template_hint = "template" in text or "schema" in text or "epic.md" in text or "story" in text
        checks.append(CheckResult("P1", "PASS" if template_hint else "WARN", "template/schema references detected" if template_hint else "no clear template/schema reference"))
        ordering_hint = "layer" in text or "priority" in text or "foundation" in text or "core" in text
        checks.append(CheckResult("P2", "PASS" if ordering_hint else "WARN", "ordering language detected" if ordering_hint else "no ordering language detected"))
        checks.append(CheckResult("P3", "PASS" if ASK_WRITE_RE.search(skill.body) else "FAIL", "approval language found before artifact writes"))
        checks.append(CheckResult("P4", "PASS" if "gate" not in text or skill.has_review_mode_logic else "WARN", "gate mode logic present or not needed"))
        read_before_write = "read" in text and ("before" in text or "then" in text)
        checks.append(CheckResult("P5", "PASS" if read_before_write else "WARN", "reads-before-writes language detected" if read_before_write else "no explicit reads-before-writes language"))
    elif category == "analysis":
        read_only = "read-only" in text or ("writes no files" in text) or ("read" in skill.allowed_tools and not skill.writes_files)
        checks.append(CheckResult("AN1", "PASS" if read_only else "WARN", "read-only scan language detected" if read_only else "read-only behavior not explicit"))
        checks.append(CheckResult("AN2", "PASS" if TABLE_RE.search(skill.body) or "severity" in text or "priority" in text else "WARN", "structured findings language detected" if TABLE_RE.search(skill.body) or "severity" in text or "priority" in text else "findings structure not explicit"))
        checks.append(CheckResult("AN3", "PASS" if not skill.writes_files or ASK_WRITE_RE.search(skill.body) else "FAIL", "writes gated or not used"))
        checks.append(CheckResult("AN4", "PASS" if "director gate" not in text and "creative-director" not in text and "technical-director" not in text else "WARN", "no director gates detected during analysis" if "director gate" not in text and "creative-director" not in text and "technical-director" not in text else "director-related text detected"))
    elif category == "team":
        named_agents = skill.body.count("agent role:") + skill.body.count("**")
        checks.append(CheckResult("T1", "PASS" if "Team Composition" in skill.body or named_agents >= 4 else "FAIL", f"named agent signals={named_agents}"))
        checks.append(_parallel_check(skill))
        blocked = "blocked" in text and ("surface immediately" in text or "halt" in text or "do not proceed" in text)
        checks.append(CheckResult("T3", "PASS" if blocked else "FAIL", "blocked handling detected" if blocked else "blocked handling missing"))
        collect = "all three review streams" in text or "all must report" in text or "collect all verdicts" in text or "wait_agent" in text
        checks.append(CheckResult("T4", "PASS" if collect else "WARN", "wait-for-all semantics detected" if collect else "no explicit wait-for-all semantics"))
        usage = "usage" in text or "if required argument" in text or "if missing" in text
        checks.append(CheckResult("T5", "PASS" if usage else "WARN", "usage/missing-argument handling detected" if usage else "missing-argument handling not explicit"))
    elif category == "sprint":
        reads_state = "production/sprints/" in skill.body or "production/milestones/" in skill.body or "sprint-status" in text
        checks.append(CheckResult("SP1", "PASS" if reads_state else "FAIL", "sprint/milestone state read detected" if reads_state else "no sprint/milestone state read detected"))
        if "producer" in text or "pr-sprint" in text or "pr-milestone" in text:
            checks.append(_review_mode_check(skill))
        else:
            checks.append(CheckResult("SP2", "WARN", "no explicit sprint gate detected"))
        checks.append(CheckResult("SP3", "PASS" if TABLE_RE.search(skill.body) or "action items" in text or "risk" in text else "WARN", "structured sprint output detected" if TABLE_RE.search(skill.body) or "action items" in text or "risk" in text else "structured sprint output not explicit"))
        checks.append(CheckResult("SP4", "PASS" if not skill.writes_files or ASK_WRITE_RE.search(skill.body) else "FAIL", "writes gated or not used"))
    else:
        clean_static = static_report.status == "PASS"
        checks.append(CheckResult("U1", "PASS" if clean_static else "FAIL", f"static status={static_report.status}"))
        gate_text = any(term in text for term in ("creative-director", "technical-director", "producer", "art-director", "phase-gate"))
        checks.append(CheckResult("U2", "PASS" if not gate_text or skill.has_review_mode_logic else "WARN", "gate logic valid or not needed"))

    return SkillReport(
        name=skill.name,
        command=skill.sample_command,
        report_type="category",
        status=summarize_status(checks),
        checks=checks,
    )


def format_report(report: SkillReport) -> str:
    lines = [f"=== {report.report_type.upper()} {report.name} ===", f"Command: {report.command}", f"Status: {report.status}", ""]
    for check in report.checks:
        lines.append(f"- [{check.verdict}] {check.code}: {check.detail}")
    return "\n".join(lines)


def print_summary(reports: list[SkillReport]) -> None:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for report in reports:
        counts[report.status] += 1
    print(f"Summary: PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}")


def audit(skills: list[SkillRecord], as_json: bool) -> None:
    workflow_skills = sum(1 for skill in skills if skill.workflow_step is not None)
    specs = sum(1 for skill in skills if skill.spec_path)
    by_phase: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for skill in skills:
        by_phase[skill.phase] = by_phase.get(skill.phase, 0) + 1
        by_category[skill.category] = by_category.get(skill.category, 0) + 1

    payload = {
        "total_skills": len(skills),
        "workflow_skills": workflow_skills,
        "uncataloged_skills": len(skills) - workflow_skills,
        "spec_paths_present": specs,
        "phases": by_phase,
        "categories": by_category,
        "skills": [
            {
                "name": skill.name,
                "phase": skill.phase,
                "category": skill.category,
                "priority": skill.priority,
                "workflow_step": skill.workflow_step.command if skill.workflow_step else "",
                "sample_command": skill.sample_command,
            }
            for skill in skills
        ],
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print("=== Codex Skill Harness Audit ===")
    print(f"Skills: {payload['total_skills']}")
    print(f"Workflow backbone: {workflow_skills}")
    print(f"Uncataloged/support skills: {payload['uncataloged_skills']}")
    print(f"Spec paths present: {specs}/{len(skills)}")
    print("")
    print("By phase:")
    for phase, count in sorted(by_phase.items()):
        print(f"- {phase}: {count}")
    print("")
    print("By category:")
    for category, count in sorted(by_category.items()):
        print(f"- {category}: {count}")


def pick_skills(skills: list[SkillRecord], names: list[str]) -> list[SkillRecord]:
    if names == ["all"]:
        return skills
    wanted = set(names)
    selected = [skill for skill in skills if skill.name in wanted]
    missing = sorted(wanted - {skill.name for skill in selected})
    if missing:
        raise SystemExit(f"Unknown skills: {', '.join(missing)}")
    return selected


def run_smoke(skills: list[SkillRecord], output_dir: Path, timeout: int, as_json: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: list[dict[str, object]] = []

    for skill in skills:
        output_path = output_dir / f"{skill.name}.txt"
        command = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "-m",
            "gpt-5.4-mini",
            "-c",
            'reasoning_effort="low"',
            "-c",
            'approval_policy="never"',
            "-C",
            str(REPO_ROOT),
            "-o",
            str(output_path),
            skill.sample_command,
        ]
        env = os.environ.copy()
        env["CODEX_SKIP_STOP_VERIFY"] = "1"
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        last_message = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
        payload.append(
            {
                "skill": skill.name,
                "command": skill.sample_command,
                "returncode": completed.returncode,
                "output_file": str(output_path),
                "status": "PASS" if completed.returncode == 0 else "FAIL",
                "last_message_excerpt": last_message[:500],
                "stderr_excerpt": completed.stderr[:500],
            }
        )

    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print("=== Codex Skill Smoke ===")
    for entry in payload:
        print(f"- {entry['skill']}: {entry['status']} ({entry['command']}) -> {entry['output_file']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Codex-native compatibility harness for the 72 in-repo skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Show catalog coverage and grouping info.")
    audit_parser.add_argument("--json", action="store_true")

    static_parser = subparsers.add_parser("static", help="Run structural checks.")
    static_parser.add_argument("skills", nargs="+", help="'all' or one or more skill names")
    static_parser.add_argument("--json", action="store_true")

    category_parser = subparsers.add_parser("category", help="Run rubric checks.")
    category_parser.add_argument("skills", nargs="+", help="'all' or one or more skill names")
    category_parser.add_argument("--json", action="store_true")

    smoke_parser = subparsers.add_parser("smoke", help="Run live Codex smoke invocations.")
    smoke_parser.add_argument("skills", nargs="+", help="'all' or one or more skill names")
    smoke_parser.add_argument("--output-dir", default="tmp/skill-harness/live")
    smoke_parser.add_argument("--timeout", type=int, default=180)
    smoke_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    skills = load_skill_records()

    if args.command == "audit":
        audit(skills, args.json)
        return

    selected = pick_skills(skills, args.skills)

    if args.command == "static":
        reports = [static_checks(skill) for skill in selected]
        if args.json:
            print(json.dumps([asdict(report) for report in reports], indent=2))
        else:
            for report in reports:
                print(format_report(report))
                print("")
            print_summary(reports)
        raise SystemExit(1 if any(report.status == "FAIL" for report in reports) else 0)

    if args.command == "category":
        reports = [category_checks(skill) for skill in selected]
        if args.json:
            print(json.dumps([asdict(report) for report in reports], indent=2))
        else:
            for report in reports:
                print(format_report(report))
                print("")
            print_summary(reports)
        raise SystemExit(1 if any(report.status == "FAIL" for report in reports) else 0)

    if args.command == "smoke":
        run_smoke(selected, REPO_ROOT / args.output_dir, args.timeout, args.json)
        return


if __name__ == "__main__":
    main()
