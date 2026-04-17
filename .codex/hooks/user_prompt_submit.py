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
            "additionalContext": "\n".join(additions),
        }
    },
    sys.stdout,
)
