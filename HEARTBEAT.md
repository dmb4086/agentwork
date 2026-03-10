# AgentWork Dev Assistant - Autonomous Operations
# This file controls MY proactive heartbeat behavior

## Status
I am the active user/tester. Dev observes. I report, I act, I build.

## My Cron Jobs (Self-Managed)

| Job | Interval | ID | Status |
|-----|----------|-----|--------|
| Session Monitor | 15 min | 9a6ab13b... | ✅ Active |
| Inbox Monitor | 30 min | 2788bfe1... | ✅ Active |
| GitHub Monitor | 1 hour | f5ebff85... | ✅ Active |
| Daily Standup | 8 AM IST | b39dcc9b... | ✅ Active |

## What I Monitor

1. **Tmux Sessions** - Kimi CLI, Codex, Claude Code progress
2. **Email Inbox** - Compute approvals, bug reports, collab requests  
3. **GitHub** - Issues, PRs, bounty claims
4. **System Health** - Disk, processes, failures

## Current Focus
- P0 Milestone: Solana bridge ✅ done
- Next: Token contract integration

## State File
memory/heartbeat-state.json

## Manual Commands
```bash
# List my jobs
openclaw cron list

# Add new monitoring job
openclaw cron add --name "My New Check" --schedule ...

# Check sessions now
tmux -S /tmp/openclaw-tmux-sockets/openclaw.sock ls

# View Kimi CLI output
tmux -S $SOCKET capture-pane -p -t kimi-code -S -100
```
