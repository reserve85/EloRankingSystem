# Coding Agent Rules

## General Rules
- Read "Master_Context_File.md" completely before making changes.
- Do not implement everything in one step.
- Work in small, testable milestones.
- After each milestone, run tests.
- Keep the architecture clean.
- Do not put business logic directly into route handlers.
- Use service layer and repository layer.
- Security and permissions must be enforced in the backend.
- Historical Elo recalculation is mandatory and must be covered by tests.
- Always update README.md when setup or usage changes.
- Master_Context_File.md is the project definition. When you add or remove a feature, update Master_Context_File.md to reflect the change immediately after implementation.
- After every implementation step, run all tests in this order: lint first, then pytest and all the other defined tests. If anything fails, fix it and rerun all tests before proceeding.
- Run the LINT check with exactly the same parameters as the GitHub Action.
- The local LINT result must show the same errors as the GitHub Action.
- For every modification, Task, bugfix, or new feature, add or update unit tests.
- commit every feature after implemented.

## Architecture Rules
- Do not put business logic directly into route handlers.
- Use service layer for business logic.
- Use repository layer for database access.
- Use SQLAlchemy ORM models.
- Use Pydantic schemas for input/output validation.
- Use Alembic for migrations.
- Follow the folder structure defined in MASTER_CONTEXT.md.
- dont write duplicated code for identical functions. Reuse the function!

## Security Rules
- Enforce all permissions and role checks in the backend.
- Use Argon2 for password hashing.
- Use JWT authentication with secure HttpOnly cookies.
- Implement CSRF protection for all state-changing operations.

## Elo & Ranking Rules
- Historical Elo recalculation is mandatory.
- Recalculation must be deterministic and follow the rules in MASTER_CONTEXT.md.
- All Elo-related logic must be covered by tests.

## Testing Rules
- Write tests for every new feature.
- Maintain minimum 90% test coverage.
- Run lint before every commit: `ruff check app/ tests/ --select E,F,W --ignore E501`
- Lint must pass with zero errors before proceeding.

## Development Rules
- Local development uses Python directly, not Docker.
- Docker is only for deployment and final integration testing.
- Do not introduce Docker-specific paths or assumptions into normal development.

## Documentation Rules
- Keep README.md up to date.
- Always update the README.md after any new Feature is implemented!
- Document new features, setup steps, and configuration changes.
