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
    r"\brm\s+-rf\b": "Destructive `rm -rf` command blocked by Codex hook.",
    r"\bgit\s+push\s+.*(?:--force|-f)\b": "Force-push blocked by Codex hook.",
    r"\bgit\s+reset\s+--hard\b": "Hard reset blocked by Codex hook.",
    r"\bgit\s+clean\s+-f\b": "Git clean blocked by Codex hook.",
    r"\bsudo\b": "Elevated shell command blocked by Codex hook.",
    r"\bchmod\s+777\b": "Over-broad chmod blocked by Codex hook.",
    r"\b(?:cat|type)\s+[^\n]*\.env(?:\.[^\s]+)?\b": "Reading `.env` files through Bash is blocked by Codex hook.",
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

if re.search(r"\bgit\s+push\b", command) and re.search(r"\b(?:main|develop)\b", command):
    emit({"systemMessage": "Protected branch push detected. Re-check branch target before continuing."})
    raise SystemExit(0)

repo_root = Path(payload.get("cwd", "."))
tracked_paths = [".codex/skills/", ".codex/agents/", ".codex/hooks/"]
if re.search(r"\bgit\s+commit\b", command):
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
