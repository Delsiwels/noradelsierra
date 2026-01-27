# Claude Code Instructions

## Before Completing Any Task

Run these mandatory checks:

### Security Scan
- [ ] Scan for hardcoded secrets, API keys, passwords
- [ ] Check for SQL injection vulnerabilities
- [ ] Check for shell injection vulnerabilities
- [ ] Check for path traversal attacks
- [ ] Verify all user inputs are validated and sanitized
- [ ] Check for XSS vulnerabilities in templates

### Code Quality
- [ ] Run `ruff check webapp/` for linting
- [ ] Run `mypy webapp/ --ignore-missing-imports` for type errors
- [ ] Run `bandit -r webapp/` for Python security issues

### Testing
- [ ] Run `pytest tests/` to verify existing tests pass
- [ ] Write tests for new functionality

### Sensitive Files
Never commit:
- .env files
- API keys or tokens
- credentials.json
- Private keys
