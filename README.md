# Ralph Zero

**Agent development orchestrator with context feedback loops**

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/davidkimai/ralph-zero)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/agent%20skills-compatible-purple.svg)](https://agentskills.io)

**Ralph Zero - Your agents can now run Ralph using skills!**

*Works with Claude Code, Cursor, Copilot, Amp, or any Agent Skills agent*

Ralph Zero is an intelligent orchestrator system that agentically implements complex multi-step features through looped agent sessions with quality gates, context synthesis, and iterative learning.

## Overview

Ralph Zero transforms how AI agents build software by providing:

- **Intelligent Orchestration** - Python-based meta-layer manages stateless agent iterations
- **Cognitive Feedback** - System learns patterns via mandatory AGENTS.md documentation
- **Quality-Driven Execution** - Configurable gates (typecheck, tests, browser) enforce standards
- **Universal Compatibility** - Works with Claude Code, Cursor, Copilot, Amp, any Agent Skills agent
- **Context Synthesis** - Injects "memory" from AGENTS.md and progress.txt into each iteration

## Installation

### Universal Installation (Works with Most Agents)

```bash
git clone https://github.com/davidkimai/ralph-zero.git .agent/skills/ralph-zero
cd .agent/skills/ralph-zero
pip install -e .
```

### Agent-Specific Installation

Choose the installation path based on your AI agent platform:

```bash
# Claude Code specific
git clone https://github.com/davidkimai/ralph-zero.git .claude/skills/ralph-zero

# Cursor specific
git clone https://github.com/davidkimai/ralph-zero.git .cursor/skills/ralph-zero

# VS Code Copilot specific
git clone https://github.com/davidkimai/ralph-zero.git .vscode/copilot/skills/ralph-zero

# Gemini CLI specific
git clone https://github.com/davidkimai/ralph-zero.git .gemini/skills/ralph-zero

# Amp specific
git clone https://github.com/davidkimai/ralph-zero.git .config/amp/skills/ralph-zero
```

After cloning to your preferred path:
```bash
cd <skills-directory>/ralph-zero
pip install -e .
```

### Global Installation

For system-wide availability (works across all projects):

```bash
# Universal path
git clone https://github.com/davidkimai/ralph-zero.git ~/.agent/skills/ralph-zero
cd ~/.agent/skills/ralph-zero
pip install -e .
```

## Quick Start

### 1. Create a PRD

```
Load the prd skill and create a PRD for adding task priority levels
```

The skill guides you through questions and generates `tasks/prd-[feature-name].md`.

### 2. Convert to JSON

```
Load ralph-convert skill and convert tasks/prd-task-priority.md to prd.json
```

This validates story structure and generates `prd.json`.

### 3. Run Ralph Zero

**Via CLI:**
```bash
ralph-zero run --max-iterations 50
```

**Via Agent:**
```
Load ralph-zero skill and run autonomous loop
```

Ralph Zero will:
- Create/checkout feature branch from PRD
- Work through stories in priority order
- Run quality gates after each story
- Commit only if gates pass
- Continue until all stories complete or max iterations reached

## Architecture

```
┌─────────────────────────────────────────┐
│  Ralph Zero Orchestrator (Python)      │
│  • ConfigManager  • ContextSynthesizer  │
│  • StateManager   • QualityGates        │
│  • AgentInvoker   • LibrarianCheck      │
└──────────────┬──────────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │  Fresh Agent Instance│
    │  (Stateless)         │
    └──────────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │  Persistent State    │
    │  • prd.json          │
    │  • AGENTS.md         │
    │  • progress.txt      │
    └──────────────────────┘
```

## Configuration

Create `ralph.json` in your project root:

```json
{
  "agent_command": "auto",
  "max_iterations": 50,
  "quality_gates": {
    "typecheck": {
      "cmd": "npm run typecheck",
      "blocking": true,
      "timeout": 60
    },
    "test": {
      "cmd": "npm test",
      "blocking": true,
      "timeout": 120
    }
  },
  "git": {
    "commit_prefix": "[Ralph]",
    "auto_create_branch": true
  },
  "librarian": {
    "check_enabled": true,
    "warning_after_iterations": 3
  }
}
```

See [assets/examples/ralph.json](assets/examples/ralph.json) for complete example.

## CLI Commands

```bash
# Run autonomous development loop
ralph-zero run [--max-iterations N] [--config PATH]

# Validate prd.json and configuration
ralph-zero validate [--config PATH]

# Show current status
ralph-zero status [--verbose]

# Archive current run
ralph-zero archive <branch_name>
```

## Features

- **Stateless Iterations** - Fresh agent per story prevents context overflow
- **Synthesized Context** - Unified "memory" works across all agents
- **Quality Gates** - Configurable checks (typecheck, tests, lint, browser)
- **Cognitive Feedback** - Librarian enforces AGENTS.md pattern documentation
- **Atomic Stories** - Each completable in one iteration (approximately 30min-2hrs)
- **Observable State** - All decisions logged to orchestrator.log
- **Schema Validation** - JSON schemas validate config and PRD structure
- **Type Safety** - Full type hints, mypy compatible
- **Git Integration** - Automatic branching, atomic commits
- **Archiving** - Previous runs archived when starting new features

## Project Structure

```
ralph-zero/
├── SKILL.md                  # Main skill descriptor
├── README.md                 # This file
├── LICENSE                   # MIT license
├── pyproject.toml            # Python build configuration
├── requirements.txt          # Dependencies
│
├── scripts/                  # Python orchestrator
│   ├── ralph_zero.py         # CLI entry point
│   ├── orchestrator/         # Core modules
│   │   ├── config.py         # Configuration management
│   │   ├── state.py          # State management
│   │   ├── context.py        # Context synthesis
│   │   ├── agent.py          # Agent invocation
│   │   ├── quality.py        # Quality gates
│   │   ├── librarian.py      # Cognitive feedback
│   │   ├── core.py           # Main orchestrator
│   │   └── utils.py          # Utilities
│   └── schemas/              # JSON schemas
│       ├── ralph_config.schema.json
│       └── prd.schema.json
│
├── skills/                   # Sub-skills
│   ├── prd/                  # PRD generation
│   ├── ralph-convert/        # PRD to JSON conversion
│   └── ralph-execute/        # Execution (meta)
│
├── assets/                   # Examples and templates
│   ├── examples/
│   └── templates/
│
├── tests/                    # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── docs/                     # Documentation
```

## Development

### Setup Development Environment

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run type checking
mypy scripts/

# Run linting
ruff check scripts/

# Format code
black scripts/

# Run tests
pytest
```

### Type Checking

Ralph Zero uses comprehensive type hints:

```bash
mypy scripts/orchestrator/
```

Target: 100% type checking pass

### Testing

```bash
# Run all tests with coverage
pytest --cov=scripts --cov-report=html

# Run specific test file
pytest tests/unit/test_config.py

# Run with verbose output
pytest -v
```

Target: Greater than 80% code coverage

## Comparison to Original Ralph

| Feature | Original Ralph | Ralph Zero |
|---------|----------------|------------|
| **Orchestrator** | Bash script | Python with types |
| **Agent Support** | Amp-specific | Universal (Agent Skills) |
| **Context** | Auto-handoff only | Synthesized (works everywhere) |
| **State** | Basic | Validated, atomic, logged |
| **Quality Gates** | Fixed | Configurable per project |
| **Cognitive Feedback** | Optional | Enforced (Librarian) |
| **Observability** | Basic logs | Structured JSON logs |
| **Type Safety** | N/A | Full mypy compatibility |

## Documentation

- [SKILL.md](SKILL.md) - Main skill documentation (for agents)
- [Architecture](docs/ARCHITECTURE.md) - System design deep dive
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Examples](docs/EXAMPLES.md) - Real-world usage examples
- [Migration](docs/MIGRATION.md) - Migrating from ralph v1

## Examples

Complete working examples in [assets/examples/](assets/examples/):

- **nextjs-feature.json** - Next.js + TypeScript + Prisma
- **python-api.json** - FastAPI + pytest
- **react-component.json** - React component library

## Contributing

Contributions welcome. Please:

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Ensure type checking passes (`mypy`)
5. Ensure tests pass (`pytest`)
6. Submit a pull request

## Credits

Based on [Geoffrey Huntley's Ralph pattern](https://ghuntley.com/ralph/).

Inspired by:
- **David Kim's ralph-for-agents** - Agent Skills portability
- **Snarktank's ralph** - Cognitive feedback loops

## License

MIT License - See [LICENSE](LICENSE) file

## Links

- **GitHub**: https://github.com/davidkimai/ralph-zero
- **Issues**: https://github.com/davidkimai/ralph-zero/issues
- **Agent Skills**: https://agentskills.io

---

**Status**: Alpha - Active Development  
**Version**: 0.1.0  
**Python**: 3.10+  
**License**: MIT
