# Find Skills - Reference Card
**Source:** https://clawhub.ai/JimLiuxinghai/find-skills  
**Install:** `npx skills add JimLiuxinghai/find-skills -g -y` (when auth works)
**Browse:** https://skills.sh/

## What It Does
Helps discover and install skills from the open agent skills ecosystem when I need new capabilities.

## Key Commands
```bash
# Search for skills
npx skills find [query]

# Install a skill
npx skills add <owner/repo@skill> -g -y

# Check for updates
npx skills check

# Update all skills
npx skills update
```

## When To Use
- User asks "how do I do X" where X might have a skill
- Need specialized domain knowledge (React, testing, DevOps, etc.)
- Looking for workflows, templates, or best practices
- Extending agent capabilities

## Common Categories
| Category | Example Queries |
|----------|-----------------|
| Web Dev | react, nextjs, typescript, tailwind |
| Testing | testing, jest, playwright, e2e |
| DevOps | deploy, docker, kubernetes, ci-cd |
| Documentation | docs, readme, changelog, api-docs |
| Code Quality | review, lint, refactor, best-practices |
| Design | ui, ux, design-system, accessibility |

## Popular Sources
- `vercel-labs/agent-skills` - React/Next.js best practices
- `ComposioHQ/awesome-claude-skills` - Claude-specific skills
- `JimLiuxinghai/find-skills` - Skill discovery

## Example Usage
```bash
# User asks about React performance
npx skills find react performance
# → Suggests: vercel-labs/agent-skills@vercel-react-best-practices

# User asks about PR reviews  
npx skills find pr review
# → Shows available code review skills

# User asks about deployment
npx skills find deploy kubernetes
# → Finds deployment and K8s skills
```

## Discovered Skills for AgentWork

### Solana/Blockchain
```bash
npx skills add mindrally/skills@solana -g -y        # 65 installs - Solana dev
npx skills add hairyf/blockchain-skills@solana-anchor -g -y  # Anchor framework
npx skills add solana-clawd/openclaw-solana-plugins@solana-trader -g -y
```

### Rust Testing
```bash
npx skills add d-o-hub/rust-self-learning-memory@rust-async-testing -g -y  # 18 installs
npx skills add d-o-hub/rust-self-learning-memory@quality-unit-testing -g -y  # 16 installs
```

### Docker/Deployment
```bash
npx skills add pluginagentmarketplace/custom-plugin-nodejs@docker-deployment -g -y  # 146 installs
npx skills add aaaaqwq/claude-code-skills@docker-deployment -g -y  # 27 installs
```

### Microservices/APIs
```bash
npx skills add manutej/luxor-claude-marketplace@grpc-microservices -g -y  # 52 installs
npx skills add manutej/luxor-claude-marketplace@hasura-graphql-engine -g -y  # 55 installs
```

## Notes
- Skills are modular packages with specialized knowledge/workflows
- Use `-g` for global install, `-y` to skip prompts
- Skills.sh is the browsable registry
- Use `find-skills` skill when user asks "how do I..." to discover capabilities
