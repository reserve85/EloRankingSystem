# Coding Agent Rules

You are implementing this project based on MASTER_CONTEXT.md.

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

## Architecture Rules
- Do not put business logic directly into route handlers.
- Use service layer for business logic.
- Use repository layer for database access.
- Use SQLAlchemy ORM models.
- Use Pydantic schemas for input/output validation.
- Use Alembic for migrations.
- Follow the folder structure defined in MASTER_CONTEXT.md.

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
- Maintain minimum 80% test coverage.
- Tests must cover: Elo logic, ranking logic, inactive players, match validation, permissions, security.

## Development Rules
- Local development uses Python directly, not Docker.
- Docker is only for deployment and final integration testing.
- Do not introduce Docker-specific paths or assumptions into normal development.

## Documentation Rules
- Keep README.md up to date.
- Document new features, setup steps, and configuration changes.
