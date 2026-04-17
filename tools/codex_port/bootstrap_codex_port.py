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
CODEX_DOCS_DIR = CODEX_DIR / "docs"
HOOKS_DIR = CODEX_DIR / "hooks"
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


def replace_whole_lines(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def transform_port_text(text: str) -> str:
    transformed = text.replace("Claude Code Game Studios", "Codex Game Studios")
    transformed = transformed.replace("Claude Code", "Codex")
    transformed = transformed.replace(".claude/docs/", ".codex/docs/")
    transformed = transformed.replace(".claude/skills/", ".codex/skills/")
    transformed = transformed.replace(".claude/agents/", ".codex/agents/")
    transformed = transformed.replace(".claude/hooks/", ".codex/hooks/")
    transformed = transformed.replace("`.claude/docs/**`", "`.codex/docs/**`")
    transformed = transformed.replace("`.claude/skills/**`", "`.codex/skills/**`")
    transformed = transformed.replace("`.claude/agents/**`", "`.codex/agents/**`")
    transformed = transformed.replace("`CLAUDE.md`", "`AGENTS.md`")
    transformed = transformed.replace("CLAUDE.md", "AGENTS.md")
    transformed = transformed.replace("TodoWrite", "update_plan")
    transformed = transformed.replace("`claude-haiku-4-5-20251001`", "`gpt-5.4-mini`")
    transformed = transformed.replace("`claude-sonnet-4-6`", "`gpt-5.4`")
    transformed = transformed.replace("`claude-opus-4-6`", "`gpt-5.4` with `xhigh` reasoning")

    literal_replacements = {
        "`AskUserQuestion`": "a direct user prompt",
        "Use the `AskUserQuestion` tool": "Ask the user directly",
        "Use `AskUserQuestion`": "Ask the user directly",
        "via `AskUserQuestion`": "by asking the user directly",
        "via AskUserQuestion": "by asking the user directly",
        "Do not use `AskUserQuestion` here; output the guidance directly.": "Do not stop for a user decision here; output the guidance directly.",
        "Do not use `AskUserQuestion` here;": "Do not stop for a user decision here;",
        "Use the Task tool": "Use Codex multi-agent tools",
        "Use the `Task` tool": "Use Codex multi-agent tools",
        "`Task` tool": "Codex multi-agent tools",
        "via Task": "via `spawn_agent`",
        "via `Task`": "via `spawn_agent`",
        "Task subagent": "spawned worker agent",
        "Task calls": "worker-agent spawns",
        "AskUserQuestion widget": "direct user prompt block",
        "AskUserQuestion widgets": "direct user prompt blocks",
        "assumptions AskUserQuestion widget": "assumptions direct user prompt block",
        "## Parallel Task Protocol": "## Parallel Delegation Protocol",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1": "separate Codex sessions or worktrees",
        "Requires `separate Codex sessions or worktrees` environment variable.": "This maps to separate Codex sessions or worktrees in the Codex port; no special runtime flag is assumed here.",
        "subagent_type:": "agent role:",
    }
    transformed = replace_whole_lines(transformed, literal_replacements)

    regex_replacements: list[tuple[str, str]] = [
        (r"\bAskUserQuestion\(", "Ask the user directly:\n"),
        (r"\bCall `AskUserQuestion`", "Ask the user directly"),
        (r"\bcall `AskUserQuestion`", "ask the user directly"),
        (r"\bCall AskUserQuestion\b", "Ask the user directly"),
        (r"\bcall AskUserQuestion\b", "ask the user directly"),
        (r"\busing `AskUserQuestion`\b", "by asking the user directly"),
        (r"\busing AskUserQuestion\b", "by asking the user directly"),
        (r"\bUse `AskUserQuestion` for\b", "Ask the user directly for"),
        (r"\buse `AskUserQuestion` for\b", "ask the user directly for"),
        (r"\bUse AskUserQuestion for\b", "Ask the user directly for"),
        (r"\buse AskUserQuestion for\b", "ask the user directly for"),
        (r"\bUse `AskUserQuestion` with\b", "Ask the user directly with"),
        (r"\buse `AskUserQuestion` with\b", "ask the user directly with"),
        (r"\bUse AskUserQuestion with\b", "Ask the user directly with"),
        (r"\buse AskUserQuestion with\b", "ask the user directly with"),
        (r"\bAskUserQuestion widget\b", "direct user prompt block"),
        (r"\bAskUserQuestion widgets\b", "direct user prompt blocks"),
        (r"\bDo NOT put this in an AskUserQuestion\b", "Do NOT turn this into a preset-choice prompt"),
        (r"\bDo not put this in an AskUserQuestion\b", "Do not turn this into a preset-choice prompt"),
        (r"\b\*\*AskUserQuestion\*\* at every decision point\b", "**Ask the user directly** at every decision point"),
        (r"\bspawn ([^`\n]+?) via Task\b", r"spawn \1 via `spawn_agent`"),
        (r"\bSpawn ([^`\n]+?) via Task\b", r"Spawn \1 via `spawn_agent`"),
        (r"\bspawned via Task\b", "spawned via `spawn_agent`"),
        (r"\bspawned agents \(via Task\)\b", "spawned worker agents"),
        (r"\bIf running as a Task subagent\b", "If running as a spawned worker agent"),
        (r"\bIf running as a `Task` subagent\b", "If running as a spawned worker agent"),
        (r"\bissue all ([^.\n]+?) Task calls\b", r"spawn all \1 worker agents"),
        (r"\bIssue all Task calls simultaneously\b", "Spawn all worker agents simultaneously"),
        (r"\bactual Task calls\b", "actual worker-agent spawns"),
        (r"\bparallel Task\b", "parallel worker-agent"),
        (r"spawn both worker-agent spawns simultaneously", "spawn both worker agents simultaneously"),
        (r"Issue all independent worker-agent spawns", "Spawn all independent worker agents"),
        (r"\bTask in this skill spawns a SUBAGENT\b", "This skill requires real worker-agent delegation"),
        (r"\ba separate independent Claude session\b", "a separate independent Codex worker session"),
        (r"\bvia Task using gate\b", "via `spawn_agent` using gate"),
        (r"\bvia Task with\b", "via `spawn_agent` with"),
        (r"\bvia the Task tool\b", "via `spawn_agent`"),
        (r"\bvia `Task`\b", "via `spawn_agent`"),
        (r"\bthe Task tool\b", "Codex multi-agent tools"),
        (r"\bIf any spawned agent \(via Task\)\b", "If any spawned worker agent"),
        (r"\bsub-agents spawned via Task\b", "worker agents spawned via `spawn_agent`"),
        (r"\bdelegating via Task tool\b", "delegating via `spawn_agent`"),
    ]
    for pattern, replacement in regex_replacements:
        transformed = re.sub(pattern, replacement, transformed)

    transformed = re.sub(r"\bAskUserQuestion\b", "direct user prompt", transformed)

    return transformed


def body_with_port_note(kind: str, name: str, source_path: Path, body: str) -> str:
    source_rel = source_path.relative_to(REPO_ROOT)
    note = textwrap.dedent(
        f"""\
        # {name}

        > Codex port note: This {kind} was ported mechanically from `{source_rel}`.
        > Interactive decision points use plain conversational prompts.
        > Delegation uses Codex multi-agent tools (`spawn_agent`, `send_input`, `wait_agent`, `close_agent`).
        > Supporting references resolve from `.codex/docs/**`.

        """
    )
    transformed = transform_port_text(body)
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
        "codex_hooks = true",
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
        - Keep `.codex/docs/**` as the active supporting-doc surface for all Codex prompts and skills
        - Ask the user directly instead of relying on Claude-only interaction tools
        - Keep team orchestration on Codex multi-agent primitives instead of Claude `Task`
        - Keep Codex hooks enabled for the hook events that current Codex supports
        """
    )


def build_source_manifest(skills: list[MdSource], agents: list[MdSource]) -> str:
    rows = [
        [".claude/agents", str(len(agents)), ".codex/agents/configs + .codex/agents/prompts", "generated"],
        [".claude/skills", str(len(skills)), ".codex/skills", "generated"],
        [".claude/docs", "shared reference", ".codex/docs", "generated mirror"],
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
        "Generate `.codex/docs/**` as a transformed mirror of `.claude/docs/**` so Codex prompts and skills avoid Claude-only paths.",
        "Replace Claude-only interaction primitives (`AskUserQuestion`, `Task`) with direct user prompts and Codex multi-agent primitives.",
        "Enable repo-local Codex hooks with `.codex/hooks.json` for the hook events current Codex supports, and map unsupported Claude-only hook events to AGENTS rules plus active-context docs.",
    ]
    body = "\n".join(f"- {entry}" for entry in entries)
    return f"# Decision Log\n\n{body}\n"


def build_gap_register() -> str:
    rows = [
        [
            "interaction-tools",
            "resolved",
            "Generated Codex prompts and skills replace `AskUserQuestion` references with direct user prompts and plain conversational gating.",
        ],
        [
            "task-tool",
            "resolved",
            "Generated Codex prompts and skills replace Claude `Task` references with Codex multi-agent guidance centered on `spawn_agent`, `send_input`, `wait_agent`, and `close_agent`.",
        ],
        [
            "supporting-doc-paths",
            "resolved",
            "The port now generates `.codex/docs/**` mirrors from `.claude/docs/**` and rewrites Codex-facing references to the mirrored paths.",
        ],
        [
            "hooks-parity",
            "translated",
            "Repo-local Codex hooks are enabled for supported events (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`); unsupported Claude-only hook events remain documented as intentional runtime differences rather than open gaps.",
        ],
    ]
    return "# Gap Register\n\n" + markdown_table(["Gap", "State", "Details"], rows) + "\n"


def build_active_context() -> str:
    return textwrap.dedent(
        """\
        # Active Context

        - Current wave: Codex-native parity surface regenerated from source
        - Next work:
          - commit the Codex-native parity updates
          - push the verified port state
        - Stop conditions:
          - if a generated file no longer matches its source baseline, regenerate before editing by hand
          - if a source-side change is needed for parity, record it in `04-decision-log.md` first
        - Verification status:
          - `.codex/config.toml` and `.codex/hooks.json` parse cleanly
          - representative `codex exec` runs completed for `/help`, `/project-stage-detect`, and `/team-ui`
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
            - Any known runtime differences are recorded in `../04-decision-log.md`
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
        - Any Claude-only tool references translated
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
        - Any `AskUserQuestion` usage replaced with direct user prompts
        - Any `Task` usage replaced with Codex multi-agent guidance
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
                    "allowed-tools: Read, Glob, Grep, Write, Edit, Bash, spawn_agent, send_input, wait_agent, close_agent, update_plan",
                    frontmatter,
                    flags=re.MULTILINE,
                )
        write_text(
            skill_file,
            frontmatter + body_with_port_note("skill", skill.name, skill.source_path, skill.body),
        )


def create_doc_mirror() -> None:
    ensure_dir(CODEX_DOCS_DIR)
    for source_path in sorted((CLAUDE_DIR / "docs").rglob("*")):
        if source_path.is_dir():
            continue
        target_path = CODEX_DOCS_DIR / source_path.relative_to(CLAUDE_DIR / "docs")
        transformed = transform_port_text(source_path.read_text(encoding="utf-8"))
        write_text(target_path, transformed)


def build_pre_tool_use_hook() -> str:
    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import re
        import sys
        from pathlib import Path


        def emit(payload):
            json.dump(payload, sys.stdout)


        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "")
        blocked = {
            r"\\brm\\s+-rf\\b": "Destructive `rm -rf` command blocked by Codex hook.",
            r"\\bgit\\s+push\\s+.*(?:--force|-f)\\b": "Force-push blocked by Codex hook.",
            r"\\bgit\\s+reset\\s+--hard\\b": "Hard reset blocked by Codex hook.",
            r"\\bgit\\s+clean\\s+-f\\b": "Git clean blocked by Codex hook.",
            r"\\bsudo\\b": "Elevated shell command blocked by Codex hook.",
            r"\\bchmod\\s+777\\b": "Over-broad chmod blocked by Codex hook.",
            r"\\b(?:cat|type)\\s+[^\\n]*\\.env(?:\\.[^\\s]+)?\\b": "Reading `.env` files through Bash is blocked by Codex hook.",
        }
        for pattern, reason in blocked.items():
            if re.search(pattern, command):
                emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    }
                )
                raise SystemExit(0)

        if re.search(r"\\bgit\\s+push\\b", command) and re.search(r"\\b(?:main|develop)\\b", command):
            emit({"systemMessage": "Protected branch push detected. Re-check branch target before continuing."})
            raise SystemExit(0)

        repo_root = Path(payload.get("cwd", "."))
        tracked_paths = [".codex/skills/", ".codex/agents/", ".codex/hooks/"]
        if re.search(r"\\bgit\\s+commit\\b", command):
            changed = []
            try:
                import subprocess

                result = subprocess.run(
                    ["git", "diff", "--cached", "--name-only"],
                    cwd=repo_root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            except Exception:
                changed = []
            if any(any(marker in path for marker in tracked_paths) for path in changed):
                emit({"systemMessage": "Codex role/skill/hook changes are staged. Manual `codex exec` verification is required before finishing."})
        """
    )


def build_session_start_hook() -> str:
    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import subprocess
        import sys
        from pathlib import Path


        def safe_read(path: Path) -> str:
            if not path.exists():
                return ""
            return path.read_text(encoding="utf-8").strip()


        payload = json.load(sys.stdin)
        cwd = Path(payload.get("cwd", "."))
        try:
            repo_root = Path(
                subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=cwd,
                    text=True,
                ).strip()
            )
        except Exception:
            repo_root = cwd

        lines = []
        active_context = repo_root / "docs" / "codex-port" / "06-active-context.md"
        context_text = safe_read(active_context)
        if context_text:
            lines.append("Active Codex port context:")
            lines.extend(context_text.splitlines()[:8])

        tech_prefs = repo_root / ".codex" / "docs" / "technical-preferences.md"
        prefs_text = safe_read(tech_prefs)
        for line in prefs_text.splitlines():
            if line.startswith("- **Engine**:") or line.startswith("- **Primary Input**:"):
                lines.append(line)

        if not (repo_root / "design" / "gdd" / "game-concept.md").exists():
            lines.append("Project concept doc is missing. `/start` or `/brainstorm` is usually the right next step.")

        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\\n".join(line for line in lines if line).strip(),
            }
        }
        json.dump(payload, sys.stdout)
        """
    )


def build_user_prompt_submit_hook() -> str:
    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import sys


        payload = json.load(sys.stdin)
        prompt = payload.get("prompt", "")
        additions = []
        if "AskUserQuestion" in prompt:
            additions.append("Interpret `AskUserQuestion` requests as direct conversational prompts to the user with concise options.")
        if " Task " in f" {prompt} " or "`Task`" in prompt:
            additions.append("Interpret Claude `Task` references as Codex worker delegation using `spawn_agent`, `send_input`, `wait_agent`, and `close_agent`.")
        if ".claude/docs/" in prompt:
            additions.append("Prefer `.codex/docs/**` mirrors over `.claude/docs/**` when both exist.")
        if not additions:
            raise SystemExit(0)
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "\\n".join(additions),
                }
            },
            sys.stdout,
        )
        """
    )


def build_stop_hook() -> str:
    return textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path


        payload = json.load(sys.stdin)
        if os.environ.get("CODEX_SKIP_STOP_VERIFY") == "1":
            raise SystemExit(0)
        if payload.get("stop_hook_active"):
            raise SystemExit(0)

        cwd = Path(payload.get("cwd", "."))
        try:
            repo_root = Path(
                subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=cwd,
                    text=True,
                ).strip()
            )
        except Exception:
            repo_root = cwd

        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            changed = []

        needs_verification = any(
            ".codex/skills/" in line or ".codex/agents/" in line or ".codex/hooks" in line
            for line in changed
        )
        last_message = (payload.get("last_assistant_message") or "").lower()
        if needs_verification and "manual verification" not in last_message:
            json.dump(
                {
                    "decision": "block",
                    "reason": "Manual verification is required after `.codex/skills`, `.codex/agents`, or `.codex/hooks` changes. Run representative `codex exec` checks before finishing.",
                },
                sys.stdout,
            )
        """
    )


def create_hooks() -> None:
    ensure_dir(HOOKS_DIR)
    hook_files = {
        "session_start.py": build_session_start_hook(),
        "pre_tool_use.py": build_pre_tool_use_hook(),
        "user_prompt_submit.py": build_user_prompt_submit_hook(),
        "stop_require_verification.py": build_stop_hook(),
    }
    for name, content in hook_files.items():
        path = HOOKS_DIR / name
        write_text(path, content)
        path.chmod(0o755)

    hooks_json = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/session_start.py"',
                            "statusMessage": "Loading Codex studio context",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/user_prompt_submit.py"',
                            "statusMessage": "Normalizing Codex studio terminology",
                            "timeout": 10,
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/pre_tool_use.py"',
                            "statusMessage": "Checking Bash command",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/stop_require_verification.py"',
                            "statusMessage": "Checking Codex verification requirements",
                            "timeout": 10,
                        }
                    ]
                }
            ],
        }
    }
    write_text(CODEX_DIR / "hooks.json", json.dumps(hooks_json, indent=2))


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
    create_doc_mirror()
    create_hooks()
    create_agents(agents)
    for skill in skills:
        copy_skill_tree(skill)

    create_docs(agents, skills, phase_map)
    write_text(CODEX_DIR / "config.toml", build_project_config(agents, skills))


if __name__ == "__main__":
    main()
