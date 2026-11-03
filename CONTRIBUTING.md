# Contributing to Multi-AI-Agent

Thank you for your interest in contributing!

## Ways to Contribute

- **Bug reports** — open a GitHub issue with a minimal reproduction.
- **Feature requests** — open an issue describing the use-case first.
- **Pull requests** — fork → branch → code → test → PR.
- **Documentation fixes** — PRs welcome, even for typos.

## Development Setup

### Prerequisites

- Python 3.11 or 3.13
- PostgreSQL 16 (or Docker)
- Redis 7 (or Docker)
- Git

### Quickstart

```bash
git clone https://github.com/backendwithvishal/Multi_AI_Agent.git
cd Multi_AI_Agent
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# Fill in at least GROQ_API_KEY or OPENROUTER_API_KEY in .env
```

### Running Tests

```bash
pytest tests/ -v
```

The test suite does not require live LLM API keys; network-bound paths are mocked.

### Code Style

- Follow **PEP 8**; we use `ruff` for linting and `black` for formatting.
- All public functions and classes must have docstrings.
- Keep type annotations on all function signatures.

## Pull Request Guidelines

1. **Branch naming:** `fix/short-description`, `feat/short-description`, `docs/short-description`.
2. **One logical change per PR.** Split unrelated changes into separate PRs.
3. **Tests required.** New features and bug fixes must include a test that fails before and passes after.
4. **Documentation.** If you add a new env var, add it to `.env.example`, the Settings model, and the README env table. The `tests/test_docs.py` CI check enforces this.
5. **No unverified performance claims.** Do not add statements like "~40% faster" unless you include the benchmark script, environment, date, and commit hash.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add HITL approval TTL extension endpoint
fix: correct thread ownership check for replayed runs
docs: add AI Analysis endpoint to README API table
test: cover prompt injection with multi-line input
```

## Code of Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree your contributions will be licensed under the project's [MIT License](LICENSE).

