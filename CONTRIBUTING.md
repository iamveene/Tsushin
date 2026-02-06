# Contributing to Tsushin

Thank you for your interest in contributing to Tsushin! This document provides guidelines and information for contributors.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How to Contribute

### Reporting Issues

- Search existing issues before creating a new one
- Use the issue templates when available
- Provide clear reproduction steps for bugs
- Include relevant system information (OS, Docker version, etc.)

### Submitting Pull Requests

1. **Fork the repository** and create your branch from `master`
2. **Set up your development environment**:
   ```bash
   git clone https://github.com/your-username/tsushin.git
   cd tsushin
   python3 install.py
   ```
3. **Make your changes** following the code style guidelines below
4. **Test your changes** thoroughly
5. **Commit your changes** with clear, descriptive messages
6. **Push to your fork** and submit a pull request

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring

### Commit Messages

Use clear and descriptive commit messages:

```
type(scope): brief description

Detailed explanation if needed.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
- `feat(memory): add cross-agent fact sharing`
- `fix(flows): resolve step execution timeout`
- `docs(readme): update installation instructions`

## Code Style Guidelines

### Python (Backend)

- Follow PEP 8 conventions
- Use type hints where appropriate
- Write docstrings for public functions and classes
- Keep functions focused and reasonably sized

### TypeScript/React (Frontend)

- Use TypeScript for all new code
- Follow the existing component patterns
- Use functional components with hooks
- Keep components focused on single responsibilities

### General

- Write self-documenting code with clear variable/function names
- Add comments for complex logic
- Keep files reasonably sized
- Remove unused code and imports

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.8+
- Node.js 18+ (for frontend development)

### Running Tests

```bash
# Backend tests
cd backend
pytest tests/

# Frontend (if applicable)
cd frontend
npm test
```

### Pre-commit Hooks

Install pre-commit hooks to prevent secrets from being committed:

```bash
./scripts/setup-hooks.sh
```

## Architecture Overview

Tsushin follows a multi-tenant architecture with these main components:

- **Backend (FastAPI)**: API server, agent runtime, memory system
- **Frontend (Next.js)**: Web UI for management and playground
- **Database (SQLite)**: Per-tenant data storage
- **Docker**: Container orchestration for all services

See the main README for detailed architecture diagrams.

## Areas for Contribution

- **New Skills**: Extend agent capabilities with new skills
- **Integrations**: Add support for more external services
- **Documentation**: Improve guides and API documentation
- **Testing**: Expand test coverage
- **Bug Fixes**: Help resolve reported issues
- **Performance**: Optimize memory usage and response times

## Questions?

If you have questions about contributing, feel free to:

- Open a discussion on GitHub
- Check existing issues and PRs for context
- Review the codebase documentation

## License

By contributing to Tsushin, you agree that your contributions will be licensed under the MIT License.
