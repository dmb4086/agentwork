# AgentWork Dev Assistant - Autonomous Heartbeat System
# I (the assistant) control this schedule to self-monitor and be proactive

# CORE PRINCIPLE: I am the active user. When something needs attention, I act.
# The human observes. I report what I find and what I did about it.

## My Cron Jobs (Self-Managed)

### 1. Interactive Session Monitor (Every 15 min)
Checks: tmux sessions (Kimi CLI, Codex, etc.)
Actions: Capture output, report progress, alert on errors

### 2. Inbox Monitor (Every 30 min)  
Checks: steveneizenstat@gmail.com via Himalaya
Actions: Flag urgent emails, draft responses, summarize for human

### 3. GitHub Monitor (Every hour)
Checks: agentwork repos for issues, PRs, bounty claims
Actions: Label issues, triage, respond to contributors

### 4. Bounty System Monitor (Every 2 hours)
Checks: Bounty submissions, verification status, payouts
Actions: Trigger verification, update bounty status

### 5. Daily Standup (8 AM IST)
Checks: All systems, overnight activity, plan for day
Actions: Generate summary, queue tasks, request resources

## Manual Override
I can edit this file and run:
  openclaw cron add <job>
  openclaw cron list
  openclaw cron remove <id>

## State Tracking
Check state in: memory/heartbeat-state.json
