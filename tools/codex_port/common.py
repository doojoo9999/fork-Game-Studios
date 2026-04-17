#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEX_SKILLS_DIR = REPO_ROOT / ".codex" / "skills"
SKILL_PARITY_PATH = REPO_ROOT / "docs" / "codex-port" / "skill-parity.json"
WORKFLOW_CATALOG_PATH = REPO_ROOT / ".codex" / "docs" / "workflow-catalog.yaml"
TEST_CATALOG_PATH = REPO_ROOT / "CCGS Skill Testing Framework" / "catalog.yaml"

VERDICT_KEYWORDS = (
    "PASS",
    "FAIL",
    "CONCERNS",
    "APPROVED",
    "BLOCKED",
    "COMPLETE",
    "READY",
    "COMPLIANT",
    "NON-COMPLIANT",
)

SPECIAL_SAMPLE_COMMANDS = {
    "adopt": "/adopt",
    "architecture-decision": "/architecture-decision input-system",
    "architecture-review": "/architecture-review docs/architecture/architecture.md",
    "art-bible": "/art-bible",
    "asset-audit": "/asset-audit",
    "asset-spec": "/asset-spec inventory-ui",
    "balance-check": "/balance-check combat-system",
    "brainstorm": "/brainstorm cozy extraction roguelite --review lean",
    "bug-report": "/bug-report inventory duplication bug",
    "bug-triage": "/bug-triage sprint-01",
    "changelog": "/changelog sprint-01",
    "code-review": "/code-review production/epics/combat/story-damage-falloff.md",
    "consistency-check": "/consistency-check",
    "content-audit": "/content-audit",
    "create-architecture": "/create-architecture",
    "create-control-manifest": "/create-control-manifest",
    "create-epics": "/create-epics layer: foundation",
    "create-stories": "/create-stories combat-core",
    "day-one-patch": "/day-one-patch inventory duplication fix",
    "design-review": "/design-review design/gdd/inventory-system.md",
    "design-system": "/design-system inventory-system",
    "dev-story": "/dev-story production/epics/combat/story-damage-falloff.md",
    "estimate": "/estimate production/epics/combat/story-damage-falloff.md",
    "gate-check": "/gate-check",
    "help": "/help",
    "hotfix": "/hotfix inventory duplication fix",
    "launch-checklist": "/launch-checklist",
    "localize": "/localize fr",
    "map-systems": "/map-systems",
    "milestone-review": "/milestone-review milestone-01",
    "onboard": "/onboard new-player-flow",
    "patch-notes": "/patch-notes sprint-01",
    "perf-profile": "/perf-profile gameplay",
    "playtest-report": "/playtest-report vertical-slice",
    "project-stage-detect": "/project-stage-detect",
    "propagate-design-change": "/propagate-design-change inventory-system",
    "prototype": "/prototype grapple hook movement",
    "qa-plan": "/qa-plan sprint-01",
    "quick-design": "/quick-design inventory sorting rules",
    "regression-suite": "/regression-suite sprint-01",
    "release-checklist": "/release-checklist",
    "retrospective": "/retrospective sprint-01",
    "reverse-document": "/reverse-document src",
    "review-all-gdds": "/review-all-gdds",
    "scope-check": "/scope-check sprint-01",
    "security-audit": "/security-audit",
    "setup-engine": "/setup-engine unity 6",
    "skill-improve": "/skill-improve team-ui",
    "skill-test": "/skill-test static all",
    "smoke-check": "/smoke-check sprint-01",
    "soak-test": "/soak-test vertical-slice",
    "sprint-plan": "/sprint-plan new",
    "sprint-status": "/sprint-status",
    "start": "/start",
    "story-done": "/story-done production/epics/combat/story-damage-falloff.md",
    "story-readiness": "/story-readiness production/epics/combat/story-damage-falloff.md",
    "team-audio": "/team-audio combat audio pass",
    "team-combat": "/team-combat sword combat loop",
    "team-level": "/team-level forest dungeon",
    "team-live-ops": "/team-live-ops season-01 kickoff",
    "team-narrative": "/team-narrative village intro sequence",
    "team-polish": "/team-polish vertical slice",
    "team-qa": "/team-qa sprint-01",
    "team-release": "/team-release launch candidate",
    "team-ui": "/team-ui inventory screen",
    "tech-debt": "/tech-debt",
    "test-evidence-review": "/test-evidence-review sprint-01",
    "test-flakiness": "/test-flakiness",
    "test-helpers": "/test-helpers",
    "test-setup": "/test-setup",
    "ux-design": "/ux-design inventory-screen",
    "ux-review": "/ux-review design/ux/inventory-screen.md",
}


@dataclass(slots=True)
class WorkflowStep:
    phase: str
    phase_label: str
    name: str
    command: str
    required: bool
    description: str


@dataclass(slots=True)
class SkillRecord:
    name: str
    path: Path
    frontmatter: dict[str, str]
    body: str
    description: str
    argument_hint: str
    allowed_tools: list[str]
    phase: str = "auxiliary"
    category: str = "utility"
    priority: str = "medium"
    spec_path: str = ""
    source: str = ""
    target: str = ""
    workflow_step: WorkflowStep | None = None
    sample_command: str = ""
    aliases: list[str] = field(default_factory=list)

    @property
    def writes_files(self) -> bool:
        return "Write" in self.allowed_tools or "Edit" in self.allowed_tools

    @property
    def uses_agents(self) -> bool:
        return any(tool in self.allowed_tools for tool in ("spawn_agent", "send_input", "wait_agent", "close_agent"))

    @property
    def lower_body(self) -> str:
        return self.body.lower()

    @property
    def has_review_mode_logic(self) -> bool:
        text = self.lower_body
        return "review mode" in text and "full" in text and "lean" in text and "solo" in text


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        return {}, raw

    match = re.search(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if not match:
        return {}, raw

    frontmatter_text = match.group(1)
    body = raw[match.end() :]
    frontmatter: dict[str, str] = {}
    lines = frontmatter_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "|":
            block: list[str] = []
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if candidate.startswith("  "):
                    block.append(candidate[2:])
                    index += 1
                    continue
                break
            frontmatter[key] = "\n".join(block).rstrip()
            continue
        frontmatter[key] = value.strip("\"'")
        index += 1
    return frontmatter, body


def parse_catalog_yaml() -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    lines = TEST_CATALOG_PATH.read_text(encoding="utf-8").splitlines()
    in_skills = False
    current: dict[str, str] | None = None

    for line in lines:
        if line.startswith("skills:"):
            in_skills = True
            continue
        if not in_skills:
            continue
        if line.startswith("agents:"):
            break

        name_match = re.match(r"^  - name: (.+)$", line)
        if name_match:
            if current and "name" in current:
                records[current["name"]] = current
            current = {"name": name_match.group(1).strip()}
            continue

        field_match = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if field_match and current is not None:
            current[field_match.group(1)] = field_match.group(2).strip().strip("\"'")

    if current and "name" in current:
        records[current["name"]] = current

    return records


def parse_skill_parity() -> dict[str, dict[str, str]]:
    entries = json.loads(SKILL_PARITY_PATH.read_text(encoding="utf-8"))
    return {entry["skill"]: entry for entry in entries}


def parse_workflow_catalog() -> dict[str, list[WorkflowStep]]:
    phases: dict[str, list[WorkflowStep]] = {}
    lines = WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8").splitlines()
    current_phase = ""
    current_label = ""
    current_step: dict[str, str] | None = None

    def flush_step() -> None:
        nonlocal current_step
        if not current_step or "command" not in current_step or not current_phase:
            current_step = None
            return
        command = current_step["command"].strip()
        phases.setdefault(current_phase, []).append(
            WorkflowStep(
                phase=current_phase,
                phase_label=current_label or current_phase.replace("-", " ").title(),
                name=current_step.get("name", command.lstrip("/")),
                command=command,
                required=current_step.get("required", "false").lower() == "true",
                description=current_step.get("description", ""),
            )
        )
        current_step = None

    for line in lines:
        phase_match = re.match(r"^  ([a-z-]+):$", line)
        if phase_match:
            flush_step()
            current_phase = phase_match.group(1)
            current_label = ""
            continue

        label_match = re.match(r'^    label: "(.*)"$', line)
        if label_match and current_phase:
            current_label = label_match.group(1)
            continue

        step_match = re.match(r"^      - id: (.+)$", line)
        if step_match:
            flush_step()
            current_step = {"id": step_match.group(1).strip()}
            continue

        field_match = re.match(r'^        ([a-z_]+):\s*"?(.+?)"?$', line)
        if field_match and current_step is not None:
            current_step[field_match.group(1)] = field_match.group(2).strip()

    flush_step()
    return phases


def normalize_hint(hint: str) -> str:
    return hint.strip().strip("[]")


def default_sample_command(name: str, argument_hint: str) -> str:
    if name in SPECIAL_SAMPLE_COMMANDS:
        return SPECIAL_SAMPLE_COMMANDS[name]

    hint = normalize_hint(argument_hint).lower()
    if not hint or "no arguments" in hint:
        return f"/{name}"
    if "feature" in hint or "screen" in hint:
        return f"/{name} inventory screen"
    if "story" in hint or "path" in hint:
        return f"/{name} production/epics/combat/story-damage-falloff.md"
    if "epic" in hint:
        return f"/{name} combat-core"
    if "layer" in hint:
        return f"/{name} layer: foundation"
    if "language" in hint or "locale" in hint:
        return f"/{name} fr"
    if "sprint" in hint:
        return f"/{name} sprint-01"
    if "mode" in hint:
        return f"/{name} static all"
    return f"/{name} sample"


def load_skill_records() -> list[SkillRecord]:
    parity = parse_skill_parity()
    catalog = parse_catalog_yaml()
    workflow = parse_workflow_catalog()
    command_to_step = {
        step.command.lstrip("/"): step
        for steps in workflow.values()
        for step in steps
    }

    skills: list[SkillRecord] = []
    for skill_dir in sorted(CODEX_SKILLS_DIR.iterdir()):
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            continue

        frontmatter, body = parse_frontmatter(skill_path)
        allowed_tools = [
            item.strip()
            for item in frontmatter.get("allowed-tools", "").split(",")
            if item.strip()
        ]
        entry = parity.get(skill_dir.name, {})
        catalog_entry = catalog.get(skill_dir.name, {})
        step = command_to_step.get(skill_dir.name)

        skills.append(
            SkillRecord(
                name=skill_dir.name,
                path=skill_path,
                frontmatter=frontmatter,
                body=body,
                description=frontmatter.get("description", ""),
                argument_hint=frontmatter.get("argument-hint", ""),
                allowed_tools=allowed_tools,
                phase=entry.get("phase", "auxiliary"),
                category=catalog_entry.get("category", "utility") or "utility",
                priority=catalog_entry.get("priority", "medium") or "medium",
                spec_path=catalog_entry.get("spec", ""),
                source=entry.get("source", ""),
                target=entry.get("target", ""),
                workflow_step=step,
                sample_command=default_sample_command(skill_dir.name, frontmatter.get("argument-hint", "")),
            )
        )

    return skills


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "idea"


def detect_current_phase() -> str:
    stage_path = REPO_ROOT / "production" / "stage.txt"
    if stage_path.exists():
        raw = stage_path.read_text(encoding="utf-8").strip().lower()
        mapping = {
            "concept": "concept",
            "systems design": "systems-design",
            "technical setup": "technical-setup",
            "pre-production": "pre-production",
            "production": "production",
            "polish": "polish",
            "release": "release",
        }
        if raw in mapping:
            return mapping[raw]

    source_files = list((REPO_ROOT / "src").glob("**/*"))
    if len([path for path in source_files if path.is_file()]) >= 10:
        return "production"
    if list((REPO_ROOT / "production" / "epics").glob("**/*.md")):
        return "pre-production"
    if list((REPO_ROOT / "docs" / "architecture").glob("adr-*.md")):
        return "technical-setup"
    if (REPO_ROOT / "design" / "gdd" / "systems-index.md").exists():
        return "systems-design"
    if (REPO_ROOT / "design" / "gdd" / "game-concept.md").exists():
        return "concept"
    return "concept"


def workflow_phase_order() -> list[str]:
    return [
        "concept",
        "systems-design",
        "technical-setup",
        "pre-production",
        "production",
        "polish",
        "release",
    ]


def phase_slice(start_phase: str, end_phase: str) -> list[str]:
    order = workflow_phase_order()
    start_index = order.index(start_phase)
    end_index = order.index(end_phase)
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    return order[start_index : end_index + 1]


def group_by(items: Iterable[SkillRecord], key: str) -> dict[str, list[SkillRecord]]:
    grouped: dict[str, list[SkillRecord]] = {}
    for item in items:
        grouped.setdefault(getattr(item, key), []).append(item)
    return grouped

