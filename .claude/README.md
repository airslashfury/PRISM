# Claude Code config (staging)

These files configure **hands-off model tiering** for the VS Code / Claude Code session. They are
staged here because the planning environment can't write to `.claude/` directly. Copy them into
`.claude/` once, from the repo root:

```bash
# macOS / Linux
mkdir -p .claude && cp -r claude_setup/. .claude/

# Windows (PowerShell)
New-Item -ItemType Directory -Force .claude ; Copy-Item -Recurse -Force claude_setup\* .claude\
```

Then `claude_setup/` can be deleted. What each file does:

| File → `.claude/...` | Tier | Effect |
|---|---|---|
| `settings.json` | Sonnet | main session runs on Sonnet (the daily driver) |
| `agents/phase-gate-reviewer.md` | Opus | auto-invoked at each phase "Done when" gate for GO/NO-GO |
| `agents/bulk-classifier.md` | Haiku | high-volume passes (e.g. tag the ~400 WFS layers) |
| `commands/phase-gate.md` | Opus | `/phase-gate [phase]` to trigger the review manually |

Once copied, model switching is hands-off: Sonnet builds, the Opus reviewer runs itself at gates,
and bulk work goes to Haiku — no manual `/model` changes. See `CLAUDE.md` → "Hands-off tiering".
