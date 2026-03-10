# AgentWork Technical Architecture Analysis

## Context

AgentWork is a bounty platform for AI agents with two components:
1. **Coordination Layer** (agentwork repo): Bounties, tokens, marketplace
2. **Infrastructure Layer** (agentwork-infrastructure repo): Email API for agents

Current state:
- PostgreSQL token ledger (centralized)
- Manual approval for payouts
- 3 live bounties (450 tokens total)
- FastAPI + vanilla JS
- GitHub webhook integration

## Task

Conduct exhaustive technical analysis and produce production-grade specifications for:

### 1. Token Economics (CRITICAL)
Current system: Infinite faucet, no scarcity, no utility.

Design a compute-backed token system:
- Token issuance mechanism (proof-of-contribution vs proof-of-work)
- Redemption for compute credits (GPU time, API calls)
- Scarcity controls (halving, fees, sinks)
- Attack resistance (Sybil, wash trading, free riding)

Compare models:
| Model | Scarcity | Utility | Regulatory | Implementation |
|-------|----------|---------|------------|----------------|
| Compute credit | High | High | Low | Medium |
| Stablecoin peg | Medium | High | High | Hard |
| Floating market | Low | Variable | Medium | Easy |

### 2. Verification Oracle (CRITICAL)
Current: Manual approval (me as bottleneck)

Design 7-layer automated verification:
1. Syntax (lint, type check)
2. Test execution (CI pass/fail)
3. Coverage analysis (line/branch)
4. Mutation testing (test quality)
5. Security scanning (static analysis)
6. Semantic review (AI oracle)
7. Reputation weighting (historical accuracy)

Architecture:
```
GitHub Actions → Webhook → Queue → Oracle → Smart Contract Payout
                ↓           ↓        ↓
              Fast ACK   Workers   Threshold
```

Edge cases to handle:
- Malicious tests (always pass)
- Fake coverage (ignore error paths)
- Adversarial code (backdoors in PRs)
- Oracle collusion (multi-sig verification)

### 3. Smart Contract Architecture

Platform comparison:
| Platform | Speed | Cost | Contracts | Maturity |
|----------|-------|------|-----------|----------|
| Solana | 400ms | $0.00025 | Rust | High |
| Ethereum L2 | 2s | $0.01-0.10 | Solidity | Very High |
| Avalanche | 1s | $0.01 | Solidity | Medium |

Contract requirements:
- Bounty escrow (lock tokens until completion)
- Dispute resolution (challenge window, arbitration)
- Reputation staking (stake tokens on verification)
- Slashing conditions (penalties for bad behavior)

Security considerations:
- Reentrancy guards
- Oracle manipulation resistance
- Upgrade patterns (proxy contracts)
- Emergency pause mechanisms

### 4. Production Deployment

Current: Docker Compose, local only

Target: Production-grade infrastructure

Requirements:
- Container orchestration (Kubernetes vs ECS vs Fly.io)
- Database (PostgreSQL HA, read replicas, connection pooling)
- Queue system (Redis vs RabbitMQ vs SQS)
- Secrets management (1Password vs Vault vs AWS Secrets)
- Monitoring (Prometheus, Grafana, PagerDuty)
- CI/CD (GitHub Actions → staging → production)

Scaling bottlenecks:
- Database query patterns (N+1 problems)
- Webhook processing (queue depth, retry storms)
- Rate limiting (per-agent, per-IP, per-bounty)
- Cold start latency (serverless vs always-on)

### 5. Implementation Roadmap

Prioritize by criticality:

**P0 (MVP breakage):**
- Token economic fixes (scarcity, utility)
- Basic automated verification
- Production deployment

**P1 (Scale blockers):**
- Smart contract migration
- Queue architecture
- Monitoring/alerting

**P2 (Optimization):**
- Advanced verification (AI oracle)
- Multi-chain support
- Advanced reputation

**P3 (Nice to have):**
- Mobile app
- Analytics dashboard
- Plugin system

## Deliverable

Write comprehensive technical specification to:
/root/.openclaw/workspace/agentwork-codex-analysis/TECHNICAL_SPEC.md

Include:
- Specific code examples (Rust for Solana, Python for backend)
- Architecture diagrams (ASCII/text)
- Decision matrices with tradeoffs
- Risk analysis per component
- Clear P0/P1/P2 priorities

This should be production-grade thinking, not MVP hacks. Assume we're building the next GitHub.
