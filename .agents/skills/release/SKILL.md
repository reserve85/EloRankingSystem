---
name: release
description: Test, Commit, Push and Release a new Version on Github
---

# release

- NEVER skip tests
- NEVER commit if tests fail
- NEVER push if lint fails
- Always run tests AFTER lint (lint may auto-fix things)
- If tests fail, fix the code, re-run tests, repeat

## Usage

When the user says "release" or "/release", execute this workflow

## Steps

### Pre-flight
1. Run `ruff check app/ tests/ --select E,F,W --ignore E501` — fix any errors
2. Run whole test suite: `python -m pytest tests/ -v --tb=long` — fix any failures
3. Repeat until both pass

### Commit
4. Stage all changed files (use `git add -f` for test files due to .gitignore)
5. Commit with a meaningful message

### Version & Release
6. Get latest tag: `git describe --tags --abbrev=0`
7. Increment patch: `v1.0.8` → `v1.0.9`
8. Push: `git push origin main`
9. Tag: `git tag v1.0.9 && git push origin v1.0.9`
10. GitHub Actions builds exe and creates the release