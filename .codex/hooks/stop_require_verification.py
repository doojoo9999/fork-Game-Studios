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
