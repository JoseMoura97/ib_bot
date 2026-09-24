# ib_bot — Agent Instructions

## Primary checkout belongs to scheduled jobs

`/home/servidor/Desktop/cursor-projects/ib_bot` must remain on `main`: nightly
altdata backup and QA jobs commit and publish from that checkout. Never switch
its branch for lab, feature, review or test work. Create a separate Git worktree
and branch with `git worktree add -b <branch> <separate-path> main`; run edits and
tests there. Integrate verified changes deliberately into main. Never bypass a
timer's main-branch guard. This applies to every PM using this repository.

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
