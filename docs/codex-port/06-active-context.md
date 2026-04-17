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
