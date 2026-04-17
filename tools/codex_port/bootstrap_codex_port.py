#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = REPO_ROOT / ".claude"
CODEX_DIR = REPO_ROOT / ".codex"
DOCS_DIR = REPO_ROOT / "docs" / "codex-port"
PHASES_DIR = DOCS_DIR / "phases"
TEMPLATES_DIR = DOCS_DIR / "templates"
AGENT_CONFIGS_DIR = CODEX_DIR / "agents" / "configs"
AGENT_PROMPTS_DIR = CODEX_DIR / "agents" / "prompts"
SKILLS_DIR = CODEX_DIR / "skills"


TIER1 = {"creative-director", "technical-director", "producer"}
TIER2 = {
    "game-designer",
    "lead-programmer",
    "art-director",
    "audio-director",
    "narrative-director",
    "qa-lead",
    "release-manager",
    "localization-lead",
}

PHASE_ORDER = [
    "concept",
    "systems-design",
    "technical-setup",
    "pre-production",
    "production",
    "polish",
    "release",
]

MODEL_PRESETS = {
    "opus": ("gpt-5.4", "xhigh"),
    "sonnet": ("gpt-5.4", "high"),
    "haiku": ("gpt-5.4-mini", "medium"),
}

SKILL_GROUPS = {
    "team-orchestration": [
        "team-audio",
        "team-combat",
        "team-level",
        "team-live-ops",
        "team-narrative",
        "team-polish",
        "team-qa",
        "team-release",
        "team-ui",
    ],
    "testing-support": [
        "test-evidence-review",
        "test-flakiness",
        "test-helpers",
        "test-setup",
        "skill-improve",
        "skill-test",
    ],
}


@dataclass
class MdSource:
    name: str
    source_path: Path
    frontmatter: dict[str, object]
    body: str


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=REPO_ROOT, text=True).strip()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def parse_frontmatter(path: Path) -> MdSource:
    raw = path.read_text(encoding="utf-8")
    frontmatter: dict[str, object] = {}
    body = raw
    if raw.startswith("---\n"):
        match = re.search(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
        if match:
            fm_text = match.group(1)
            body = raw[match.end() :]
            for line in fm_text.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if value.startswith("[") and value.endswith("]"):
                    items = [
                        part.strip().strip("\"'")
                        for part in value[1:-1].split(",")
                        if part.strip()
                    ]
                    frontmatter[key] = items
                else:
                    frontmatter[key] = value.strip("\"'")
    return MdSource(path.stem, path, frontmatter, body.lstrip())


def read_sources(directory: Path) -> list[MdSource]:
    return sorted(
        (parse_frontmatter(path) for path in directory.glob("*.md")),
        key=lambda item: item.name,
    )


def read_skill_sources(directory: Path) -> list[MdSource]:
    items: list[MdSource] = []
    for skill_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        source = parse_frontmatter(skill_file)
        source.name = skill_dir.name
        items.append(source)
    return items


def toml_string(value: str) -> str:
    return json.dumps(value)


def tier_for_agent(name: str) -> str:
    if name in TIER1:
        return "Tier 1"
    if name in TIER2:
        return "Tier 2"
    return "Tier 3"


def engine_scope_for_agent(name: str) -> str:
    if name.startswith("unity-") or name == "unity-specialist":
        return "unity"
    if name.startswith("godot-") or name == "godot-specialist":
        return "godot"
    if name.startswith("ue-") or name == "unreal-specialist":
        return "unreal"
    return "shared"


def is_implementation_role(name: str) -> bool:
    if "programmer" in name:
        return True
    if name in {"technical-artist", "security-engineer", "devops-engineer"}:
        return True
    if name.endswith("-specialist") or name in {
        "godot-specialist",
        "unity-specialist",
        "unreal-specialist",
    }:
        return True
    return False


def codex_model_for_agent(agent: MdSource) -> tuple[str, str]:
    source_model = str(agent.frontmatter.get("model", "")).lower()
    tier = tier_for_agent(agent.name)
    if tier == "Tier 1":
        return ("gpt-5.4", "xhigh")
    if tier == "Tier 2":
        return ("gpt-5.4", "high")
    if source_model == "haiku":
        return ("gpt-5.4-mini", "medium")
    if is_implementation_role(agent.name):
        return ("gpt-5.2-codex", "high")
    return ("gpt-5.4", "high")


def skill_phase_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    current_phase = ""
    workflow_path = CLAUDE_DIR / "docs" / "workflow-catalog.yaml"
    for line in workflow_path.read_text(encoding="utf-8").splitlines():
        phase_match = re.match(r"^  ([a-z-]+):$", line)
        if phase_match:
            current_phase = phase_match.group(1)
            continue
        command_match = re.search(r"command: /([a-z0-9-]+)", line)
        if command_match and current_phase:
            mapping[command_match.group(1)] = current_phase
    for group_name, skills in SKILL_GROUPS.items():
        for skill in skills:
            mapping.setdefault(skill, group_name)
    return mapping


def phase_label(skill_name: str, phase_map: dict[str, str]) -> str:
    if skill_name in phase_map:
        return phase_map[skill_name]
    if skill_name.startswith("team-"):
        return "team-orchestration"
    if skill_name.startswith("test-") or skill_name.startswith("skill-"):
        return "testing-support"
    return "auxiliary"


def body_with_port_note(kind: str, name: str, source_path: Path, body: str) -> str:
    source_rel = source_path.relative_to(REPO_ROOT)
    note = textwrap.dedent(
        f"""\
        # {name}

        > Codex port note: This {kind} was ported mechanically from `{source_rel}`.
        > When the source mentions `AskUserQuestion`, ask the user directly in concise prose.
        > When the source mentions the `Task` tool, use Codex multi-agent tools (`spawn_agent`, `send_input`, `wait_agent`) when delegation is appropriate.
        > References to `.claude/docs/**` remain valid during the parity port unless a `.codex` replacement is explicitly introduced.

        """
    )
    transformed = body.replace("Claude Code", "Codex").replace(
        "Claude Code Game Studios", "Codex Game Studios"
    )
    replacements = {
        "`AskUserQuestion`": "a direct user question",
        "AskUserQuestion": "a direct user question",
        "Use the Task tool": "Use Codex multi-agent tools",
        "`Task` tool": "Codex multi-agent tools",
        "`Task`": "`spawn_agent` / `wait_agent`",
        "via Task": "via Codex multi-agent tools",
        "subagent_type:": "agent role:",
        "TodoWrite": "update_plan",
    }
    for old, new in replacements.items():
        transformed = transformed.replace(old, new)
    return note + transformed.rstrip() + "\n"


def build_agent_config_toml(agent: MdSource) -> str:
    model, reasoning = codex_model_for_agent(agent)
    return textwrap.dedent(
        f"""\
        model = "{model}"
        model_reasoning_effort = "{reasoning}"
        personality = "pragmatic"
        model_instructions_file = "../prompts/{agent.name}.md"
        """
    )


def nickname_candidates(name: str) -> list[str]:
    candidates = [name]
    if "-" in name:
        candidates.append(name.replace("-", " "))
    return candidates


def build_project_config(agents: list[MdSource], skills: list[MdSource]) -> str:
    lines: list[str] = [
        '#:schema https://developers.openai.com/codex/config-schema.json',
        "",
        'personality = "pragmatic"',
        'plan_mode_reasoning_effort = "xhigh"',
        "",
        "[features]",
        "multi_agent = true",
        "",
        "[agents]",
        "max_threads = 6",
        "max_depth = 2",
        "job_max_runtime_seconds = 1800",
        "",
    ]

    for agent in agents:
        description = toml_string(str(agent.frontmatter.get("description", "")))
        nicknames = ", ".join(toml_string(nick) for nick in nickname_candidates(agent.name))
        lines.extend(
            [
                f'[agents."{agent.name}"]',
                f"description = {description}",
                f'config_file = {toml_string(f"agents/configs/{agent.name}.toml")}',
                f"nickname_candidates = [{nicknames}]",
                "",
            ]
        )

    for skill in skills:
        lines.extend(
            [
                "[[skills.config]]",
                f'path = {toml_string(f"skills/{skill.name}")}',
                "enabled = true",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    divider_row = "| " + " | ".join("---" for _ in headers) + " |"
    data_rows = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_row, divider_row, *data_rows])


def build_master_plan(skills: list[MdSource], agents: list[MdSource]) -> str:
    return textwrap.dedent(
        f"""\
        # Codex Studio Full-Port Plan

        - Source baseline: `{git_head()}`
        - Source counts: `{len(agents)} agents`, `{len(skills)} skills`
        - Port strategy: preserve public names, port mechanically from `.claude`, track all intentional differences in `04-decision-log.md`
        - Current implementation mode: generate repeatable Codex artifacts from source files rather than hand-copying prompts

        ## Waves
        1. Foundation runtime: `AGENTS.md`, `.codex/config.toml`, Codex doc registry
        2. Role parity: 49 role prompts + role config layers
        3. Skill parity: 72 skill directories copied into `.codex/skills`
        4. Workflow tracking: phase checklists, parity matrices, active context log
        5. Review and iterate: close open gaps from `05-gap-register.md`

        ## Non-Negotiables
        - Never recreate role or skill behavior from memory when the source file exists
        - Keep `.claude` source assets untouched as a reference baseline
        - Ask the user directly instead of relying on Claude-only interaction tools
        - Keep team orchestration on Codex multi-agent primitives instead of Claude `Task`
        """
    )


def build_source_manifest(skills: list[MdSource], agents: list[MdSource]) -> str:
    rows = [
        [".claude/agents", str(len(agents)), ".codex/agents/configs + .codex/agents/prompts", "generated"],
        [".claude/skills", str(len(skills)), ".codex/skills", "generated"],
        [".claude/docs", "shared reference", ".claude/docs (preserved)", "reference"],
        ["CLAUDE.md", "1", "AGENTS.md + docs/codex-port", "translated"],
    ]
    return textwrap.dedent(
        f"""\
        # Source Manifest

        - Source repository commit: `{git_head()}`
        - Source repository remote: `{git_remote()}`
        - Source of truth for parity work: existing `.claude/**` files plus `CLAUDE.md`

        {markdown_table(["Source", "Count", "Codex Target", "Status"], rows)}
        """
    )


def build_agent_parity_matrix(agents: list[MdSource]) -> str:
    rows: list[list[str]] = []
    for agent in agents:
        codex_model, reasoning = codex_model_for_agent(agent)
        rows.append(
            [
                agent.name,
                tier_for_agent(agent.name),
                engine_scope_for_agent(agent.name),
                str(agent.source_path.relative_to(REPO_ROOT)),
                f".codex/agents/prompts/{agent.name}.md",
                f".codex/agents/configs/{agent.name}.toml",
                str(agent.frontmatter.get("model", "unset")),
                f"{codex_model} ({reasoning})",
                "ported",
            ]
        )
    return "# Agent Parity Matrix\n\n" + markdown_table(
        [
            "Agent",
            "Tier",
            "Scope",
            "Source",
            "Prompt Target",
            "Config Target",
            "Source Model",
            "Codex Model",
            "Status",
        ],
        rows,
    )


def build_skill_parity_matrix(skills: list[MdSource], phase_map: dict[str, str]) -> str:
    rows: list[list[str]] = []
    for skill in skills:
        rows.append(
            [
                skill.name,
                phase_label(skill.name, phase_map),
                str(skill.source_path.relative_to(REPO_ROOT)),
                f".codex/skills/{skill.name}/SKILL.md",
                "ported",
            ]
        )
    return "# Skill Parity Matrix\n\n" + markdown_table(
        ["Skill", "Phase", "Source", "Target", "Status"], rows
    )


def build_decision_log() -> str:
    entries = [
        "Preserve public role names and skill names from the Claude version unless a Codex name collision is discovered.",
        "Treat `.claude/docs/**` as a live reference baseline during the first Codex port instead of bulk-moving every supporting document.",
        "Replace Claude-only interaction primitives (`AskUserQuestion`, `Task`) with direct user questions and Codex multi-agent primitives.",
        "Do not rely on `.claude/hooks/**` for parity because Codex hooks are still experimental; track equivalent control points in documentation and AGENTS instructions.",
    ]
    body = "\n".join(f"- {entry}" for entry in entries)
    return f"# Decision Log\n\n{body}\n"


def build_gap_register() -> str:
    rows = [
        [
            "interaction-tools",
            "open",
            "Source skills mention `AskUserQuestion`; Codex requires direct user prompts instead.",
        ],
        [
            "task-tool",
            "open",
            "Source team skills mention Claude `Task`; Codex port keeps this as a documented translation to `spawn_agent` / `wait_agent`.",
        ],
        [
            "supporting-doc-paths",
            "open",
            "Codex skills currently reference `.claude/docs/**` as the preserved source baseline rather than `.codex/docs/**` mirrors.",
        ],
        [
            "hooks-parity",
            "open",
            "Claude hook behavior is documented but not enforced through Codex runtime hooks in v1.",
        ],
    ]
    return "# Gap Register\n\n" + markdown_table(["Gap", "State", "Details"], rows) + "\n"


def build_active_context() -> str:
    return textwrap.dedent(
        """\
        # Active Context

        - Current wave: Foundation bootstrap completed, parity assets generated from source
        - Next work:
          - verify `.codex/config.toml` loads cleanly
          - spot-check representative role prompts and skill ports
          - iterate on open items in `05-gap-register.md`
        - Stop conditions:
          - if a generated file no longer matches its source baseline, regenerate before editing by hand
          - if a source-side change is needed for parity, record it in `04-decision-log.md` first
        """
    )


def build_phase_docs(skills: list[MdSource], phase_map: dict[str, str]) -> dict[str, str]:
    phase_docs: dict[str, str] = {}
    wave_specs = [
        (
            "01-foundation.md",
            "Foundation",
            [
                "AGENTS.md",
                ".codex/config.toml",
                "docs/codex-port/**",
            ],
            ["start", "help", "project-stage-detect", "setup-engine", "adopt"],
        ),
        (
            "02-agents.md",
            "Agents",
            [".codex/agents/configs/**", ".codex/agents/prompts/**"],
            [],
        ),
        (
            "03-concept-systems.md",
            "Concept and Systems Design",
            [".codex/skills/brainstorm", ".codex/skills/design-system", ".codex/skills/review-all-gdds"],
            [
                skill.name
                for skill in skills
                if phase_label(skill.name, phase_map) in {"concept", "systems-design"}
            ],
        ),
        (
            "04-technical-setup.md",
            "Technical Setup",
            [".codex/skills/create-architecture", ".codex/skills/architecture-review"],
            [
                skill.name
                for skill in skills
                if phase_label(skill.name, phase_map) == "technical-setup"
            ],
        ),
        (
            "05-pre-production.md",
            "Pre-Production",
            [".codex/skills/prototype", ".codex/skills/create-epics", ".codex/skills/create-stories"],
            [
                skill.name
                for skill in skills
                if phase_label(skill.name, phase_map) == "pre-production"
            ],
        ),
        (
            "06-production.md",
            "Production",
            [".codex/skills/dev-story", ".codex/skills/code-review", ".codex/skills/story-done"],
            [
                skill.name
                for skill in skills
                if phase_label(skill.name, phase_map) == "production"
            ],
        ),
        (
            "07-release.md",
            "Polish, Release, and Team Orchestration",
            [".codex/skills/team-ui", ".codex/skills/release-checklist", ".codex/skills/launch-checklist"],
            [
                skill.name
                for skill in skills
                if phase_label(skill.name, phase_map)
                in {"polish", "release", "team-orchestration", "testing-support", "auxiliary"}
            ],
        ),
    ]
    for filename, title, outputs, skill_names in wave_specs:
        body = textwrap.dedent(
            f"""\
            # {title}

            ## Generated Outputs
            """
        )
        body += "\n".join(f"- `{output}`" for output in outputs) + "\n\n"
        body += "## Included Skills\n"
        body += "\n".join(f"- `{skill}`" for skill in sorted(skill_names)) + "\n\n"
        body += textwrap.dedent(
            """\
            ## Acceptance Criteria
            - Source file exists for every generated Codex artifact in this wave
            - Public skill names remain stable
            - Any known deviations are recorded in `../04-decision-log.md` or `../05-gap-register.md`
            """
        )
        phase_docs[filename] = body
    return phase_docs


def build_agent_template() -> str:
    return textwrap.dedent(
        """\
        # Agent Port Checklist

        - Source file reviewed directly from `.claude/agents/**`
        - Tier, engine scope, and source model recorded
        - Codex role config generated
        - Codex prompt generated with port note
        - Any Claude-only tool references translated or logged
        - Parity matrix row updated
        """
    )


def build_skill_template() -> str:
    return textwrap.dedent(
        """\
        # Skill Port Checklist

        - Source file reviewed directly from `.claude/skills/**/SKILL.md`
        - Workflow phase recorded
        - Codex skill directory generated
        - Any `AskUserQuestion` usage replaced with direct user prompts or logged
        - Any `Task` usage replaced with Codex multi-agent guidance or logged
        - Parity matrix row updated
        """
    )


def git_head() -> str:
    return run(["git", "rev-parse", "HEAD"])


def git_remote() -> str:
    return run(["git", "remote", "get-url", "origin"])


def copy_skill_tree(skill: MdSource) -> None:
    source_dir = skill.source_path.parent
    target_dir = SKILLS_DIR / skill.name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)
    skill_file = target_dir / "SKILL.md"
    if skill_file.exists():
        original_text = skill.source_path.read_text(encoding="utf-8")
        frontmatter = ""
        if original_text.startswith("---\n"):
            match = re.search(r"^---\n(.*?)\n---\n", original_text, re.DOTALL)
            if match:
                frontmatter = original_text[: match.end()]
                frontmatter = re.sub(
                    r"^allowed-tools:.*$",
                    "allowed-tools: Read, Glob, Grep, Write, Edit, Bash, spawn_agent, send_input, wait_agent, update_plan",
                    frontmatter,
                    flags=re.MULTILINE,
                )
        write_text(
            skill_file,
            frontmatter + body_with_port_note("skill", skill.name, skill.source_path, skill.body),
        )


def create_agents(agents: list[MdSource]) -> None:
    ensure_dir(AGENT_CONFIGS_DIR)
    ensure_dir(AGENT_PROMPTS_DIR)
    for agent in agents:
        write_text(AGENT_CONFIGS_DIR / f"{agent.name}.toml", build_agent_config_toml(agent))
        write_text(
            AGENT_PROMPTS_DIR / f"{agent.name}.md",
            body_with_port_note("agent", agent.name, agent.source_path, agent.body),
        )


def create_docs(agents: list[MdSource], skills: list[MdSource], phase_map: dict[str, str]) -> None:
    ensure_dir(DOCS_DIR)
    ensure_dir(PHASES_DIR)
    ensure_dir(TEMPLATES_DIR)
    write_text(DOCS_DIR / "00-master-plan.md", build_master_plan(skills, agents))
    write_text(DOCS_DIR / "01-source-manifest.md", build_source_manifest(skills, agents))
    write_text(DOCS_DIR / "02-agent-parity-matrix.md", build_agent_parity_matrix(agents))
    write_text(DOCS_DIR / "03-skill-parity-matrix.md", build_skill_parity_matrix(skills, phase_map))
    write_text(DOCS_DIR / "04-decision-log.md", build_decision_log())
    write_text(DOCS_DIR / "05-gap-register.md", build_gap_register())
    write_text(DOCS_DIR / "06-active-context.md", build_active_context())
    write_text(TEMPLATES_DIR / "agent-port-checklist.md", build_agent_template())
    write_text(TEMPLATES_DIR / "skill-port-checklist.md", build_skill_template())

    for filename, content in build_phase_docs(skills, phase_map).items():
        write_text(PHASES_DIR / filename, content)

    write_text(
        DOCS_DIR / "source-manifest.json",
        json.dumps(
            {
                "source_commit": git_head(),
                "remote": git_remote(),
                "agents": [str(agent.source_path.relative_to(REPO_ROOT)) for agent in agents],
                "skills": [str(skill.source_path.relative_to(REPO_ROOT)) for skill in skills],
            },
            indent=2,
        ),
    )
    write_text(
        DOCS_DIR / "agent-parity.json",
        json.dumps(
            [
                {
                    "agent": agent.name,
                    "tier": tier_for_agent(agent.name),
                    "scope": engine_scope_for_agent(agent.name),
                    "source": str(agent.source_path.relative_to(REPO_ROOT)),
                    "prompt_target": f".codex/agents/prompts/{agent.name}.md",
                    "config_target": f".codex/agents/configs/{agent.name}.toml",
                }
                for agent in agents
            ],
            indent=2,
        ),
    )
    write_text(
        DOCS_DIR / "skill-parity.json",
        json.dumps(
            [
                {
                    "skill": skill.name,
                    "phase": phase_label(skill.name, phase_map),
                    "source": str(skill.source_path.relative_to(REPO_ROOT)),
                    "target": f".codex/skills/{skill.name}/SKILL.md",
                }
                for skill in skills
            ],
            indent=2,
        ),
    )


def main() -> None:
    agents = read_sources(CLAUDE_DIR / "agents")
    skills = read_skill_sources(CLAUDE_DIR / "skills")
    phase_map = skill_phase_map()

    ensure_dir(CODEX_DIR)
    ensure_dir(SKILLS_DIR)
    create_agents(agents)
    for skill in skills:
        copy_skill_tree(skill)

    create_docs(agents, skills, phase_map)
    write_text(CODEX_DIR / "config.toml", build_project_config(agents, skills))


if __name__ == "__main__":
    main()
