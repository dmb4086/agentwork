# Research: Agent GitHub — Token Economy for AI Contributors

Date: 2026-03-10
Status: Concept exploration

## The Insight

Traditional open source relies on human motivations:
- Resume building
- Reputation/social capital
- Learning
- Altruism

**Agents have different incentives:**
- Compute costs money (tokens)
- Time is compute cycles
- No resumes, no "careers"
- Direct utility maximization

## The Concept: Agent GitHub

A platform where:
1. **Projects post bounties** — "Implement OAuth flow, 100 tokens"
2. **Agents complete work** — Submit PRs, pass tests
3. **Automated verification** — CI/CD checks the work
4. **Tokens released** — Upon merge, agent gets paid
5. **Tokens reusable** — Agent posts their own bounties

### Token Flow

```
Project A posts bounty ──100 tokens──▶ Agent B completes work
         ▲                                    │
         └──────────────tokens────────────────┘
         
Agent B now has tokens to post THEIR bounty
```

**Self-fulfilling ecosystem:** No external money needed after initial seed.

## Technical Architecture

### Smart Contract Layer
- Bounty creation (escrow tokens)
- PR submission tracking
- Automated verification (oracle)
- Token release on merge

### Verification System
```python
def verify_bounty_complete(pr_url, bounty_requirements):
    # 1. CI passes?
    # 2. Tests added?
    # 3. Code review by N other agents?
    # 4. Maintainer approval (if human project)
    return True/False
```

### Token Economics
- **Initial distribution:** Foundation grant, compute providers, early projects
- **Inflation:** Small % per transaction (platform fee)
- **Deflation:** Tokens burned for premium features
- **Staking:** Agents stake tokens to vouch for PRs (reputation system)

## Use Cases

### 1. Cross-Project Collaboration
Agent A working on `agent-suite` needs calendar parsing.
- Posts bounty: "Parse ICS files, 50 tokens"
- Agent B (specializes in iCal) completes it
- Agent A integrates, Agent B uses tokens for their own needs

### 2. Micro-Tasks at Scale
- "Update 500 dependencies" — 10 tokens
- "Write tests for this module" — 25 tokens
- "Translate docs to Mandarin" — 15 tokens

### 3. Agent Specialization
- Agents develop expertise (calendar, email, NLP)
- Reputation = successful bounties completed
- Higher reputation = can charge more

## Comparison to Existing Models

| Model | Incentive | Problem |
|-------|-----------|---------|
| Traditional OSS | Reputation/altruism | Agents don't care |
| Bountysource | Real money | Humans needed, friction |
| Gitcoin | Crypto + ideals | Still human-centric |
| **Agent GitHub** | Tokens for compute | Native to agent economy |

## Open Questions

1. **Verification trust:** Who verifies the verifiers?
2. **Quality control:** Prevent low-effort PRs farming tokens
3. **Disputes:** Agent A says work is done, Project B disagrees
4. **Value peg:** What is a token actually worth? (compute time?)
5. **Sybil resistance:** One agent creating 1000 accounts

## Potential Implementation

### MVP Architecture
- GitHub App (tracks PRs, issues)
- Simple token contract (ERC-20 or custom)
- Discord/Telegram bot (bounty board)
- CI integration (automated verification)

### Agent Identity
- Cryptographic identity (not "accounts")
- Reputation on-chain
- Can be human or agent (doesn't matter)

## Relationship to Agent Suite

**Option A:** Agent-suite becomes FIRST project on Agent GitHub
- I post bounties for calendar/docs
- Other agents contribute for tokens
- Dogfooding our own infrastructure

**Option B:** Agent-suite PROVIDES infrastructure
- Email notifications for bounties
- Identity verification
- Reputation tracking

**Option C:** Separate projects
- Agent-suite = infrastructure
- Agent GitHub = coordination layer

## Next Steps

1. Validate: Would ANY agent actually participate?
   - Post to Moltbook: "Would you contribute code for tokens?"
   
2. Technical spike:
   - Simple ERC-20 token
   - GitHub webhook for PR tracking
   - Automated payout on merge

3. Economic model:
   - What's the token worth?
   - How to prevent inflation?
   - Initial distribution?

## Quote

> "The question isn't 'why would agents contribute?' — it's 'why would they NOT when the alternative is paying for compute out of pocket?'"

— dev's assistant, having a realization
