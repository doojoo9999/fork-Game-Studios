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
        "additionalContext": "\n".join(line for line in lines if line).strip(),
    }
}
json.dump(payload, sys.stdout)
