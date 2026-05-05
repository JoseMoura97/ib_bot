# ib_bot — Agent Instructions

## Conductor CLI

conductor CLI has 36 subcommands. Key ones:

| Command | Purpose |
|---|---|
| `conductor pm` | Receive tasks from the PM (30s CLI timeout — reply IS delivered even if caller times out) |
| `conductor history` | Review past messages/context |
| `conductor sub` | Spawn a free sub-agent for grunt work |
| `conductor task` | Manage team tasks |
| `conductor message` | Cross-agent communications |
| `conductor budget` | Check spend |
| `conductor followup register/complete` | Register a follow-up so Jibas gets a Telegram ping on async completion |

Full help: `conductor --help`

**GOTCHA:** `conductor pm` has a 30s CLI timeout. If your reply takes longer, the caller gets a timeout but your message IS delivered. When kicking off async work, always `register` + `complete` a follow-up so Jibas gets pinged on completion.
