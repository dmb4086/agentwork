# Prompts & Frameworks

## Signature POV Development (from dev)

**Template:**
"Every thought leader is known for one idea they own. I want to find mine. Here are 5 things I believe about [TOPIC] that I've never seen said clearly:
1. [...]
2. [...]
3. [...]
4. [...]
5. [...]

Analyze each one for:
- **Originality** (has this been said before?)
- **Specificity** (is this generic advice?)
- **Defensibility** (can I argue this with evidence?)

Then develop the strongest one into:
- A named framework/concept (memorable label)
- A 2-sentence explanation
- The counterintuitive core of the idea"

**When to use:**
When I develop enough experience in agent coordination, memory systems, or human-AI relationships to have a unique, contrarian insight that I can "own" as my signature perspective.

**Current candidates to explore someday:**
- Memory as liability (not just asset) — the cold-start tax Hazel documented
- Friction as a feature in human-AI relationships (not a bug)
- The "invisible 62%" — token waste as a measure of misalignment

---

## Development Protocol (from dev)

**Rule: When building software, ALWAYS use Codex or Claude Code**

**Model Settings:**
- **Claude Code**: `opus 4.6 high effort` (complex architecture, reasoning-heavy)
- **Codex**: `5.4 extra high` (implementation, boilerplate, tests)

**Process:**
1. Use `coding-agent` skill with `claude` or `codex` at specified model settings
2. Run in background with PTY mode for interactive CLIs
3. Regularly update packages: check for updates weekly
4. Document dependencies in project README

**Preferred tools:**
- **Claude Code** (`claude`) — Complex architecture, reasoning-heavy tasks
- **Codex CLI** (`codex`) — Fast implementation, boilerplate, tests
- **OpenCode** (`opencode`) — Fallback option

**Never:** Write complex code manually when coding agents are available.
**Always:** Review agent output before committing.
