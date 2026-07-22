# Elo Ranking System - Master Context File / Product Requirements Document (PRD)

## Project Overview

Develop a production-ready web application for a dart club that manages player rankings using the Elo Rating System.

The application must calculate player rankings based on match results and provide modern administration, reporting, user management, security, and Docker-based deployment capabilities.

The system is intended to be deployed via Docker and maintained entirely through GitHub.

Docker is only required for deployment and final integration testing.

The application must run both:
- directly via uvicorn
- inside Docker

Do not make implementation decisions that require Docker during normal development.

Development:
Local Python

Deployment:
Docker

Repository:

```text
https://github.com/reserve85/EloRankingSystem
````

The application must be maintainable, secure, containerized, testable, and suitable for long-term operation in a club environment.

***

# Goals

The final application shall provide:

* Elo-based ranking system
* Responsive web interface
* Player management
* User management
* Match management
* Automatic inactive player handling
* Historical Elo recalculation
* Ranking reports
* PDF export
* Secure authentication and authorization
* Docker deployment
* SQLite database
* Automated tests
* GitHub-based CI/CD workflow
* Clear project documentation
* Clean and maintainable architecture

***

# Important rules:
- Read "Master_Context.md" completely before making changes.
- Do not implement everything in one step.
- Work in small, testable milestones.
- After each milestone, run tests.
- Keep the architecture clean.
- Do not put business logic directly into route handlers.
- Use service layer and repository layer.
- Security and permissions must be enforced in the backend.
- Historical Elo recalculation is mandatory and must be covered by tests.
- Always update README.md when setup or usage changes.
- Master_Context.md is the project definition. When you add or remove a feature, update Master_Context.md to reflect the change immediately after implementation.
- After every implementation step, run all tests in this order: lint first, then pytest and all the other defined tests. If anything fails, fix it and rerun all tests before proceeding.

***

# Core Requirements

## Rating System

The application must use the standard Elo Rating System.

Reference:

```text
https://en.wikipedia.org/wiki/Elo_rating_system
```

## Match Types

Only two match outcomes exist:

* Winner
* Loser

Draws are not supported.

## Elo Formula

Use the standard Elo calculation:

```text
Expected(A) = 1 / (1 + 10^((RatingB - RatingA) / 400))

Expected(B) = 1 / (1 + 10^((RatingA - RatingB) / 400))

NewRating = OldRating + K * (Actual - Expected)
```

Actual result:

```text
Winner = 1
Loser  = 0
```

Default configuration:

```yaml
elo:
  default_rating: 1200
  k_factor: 32
```

The K factor must be configurable.

The default Elo rating must be configurable.

***

# Technology Stack

## Backend

Preferred technology:

* Python 3.12+
* FastAPI

## ORM

* SQLAlchemy

## Database Migrations

* Alembic

## Database

* SQLite

The database access layer must be designed in a way that allows future migration to PostgreSQL without changing business logic.

## Frontend

Requirements:

* Responsive
* Mobile-friendly
* Tablet-friendly
* Desktop-friendly
* Consistent visual design

Preferred technologies:

* Bootstrap 5
* Tabler UI
* DataTables
* Jinja2 Templates
* HTMX optional

## PDF Generation

* reportlab

## Authentication

Preferred:

* JWT Authentication
* Secure HttpOnly cookies

***

# Architecture Requirements

The application must follow a clean and maintainable architecture.

## Backend Architecture

Required principles:

* Clear separation of concerns
* Service layer for business logic
* Repository layer for database access
* SQLAlchemy ORM models
* Pydantic schemas for validation
* Role-based access control
* Centralized configuration handling
* Centralized error handling
* Transactional handling for critical operations

## Suggested Folder Structure

```text
app/
├── api/
│   ├── routes/
│   └── dependencies/
├── auth/
├── core/
├── models/
├── schemas/
├── services/
├── repositories/
├── templates/
├── static/
├── reports/
├── migrations/
└── main.py

tests/
├── test_elo.py
├── test_rankings.py
├── test_inactive_players.py
├── test_permissions.py
└── test_matches.py
```

The implementation should avoid placing business logic directly inside route handlers.

***

# Configuration

The application must use configuration files and environment variables.

Required files:

```text
.env.example
config.yaml.example
```

## Example Configuration

```yaml
app:
  name: Elo Ranking System
  environment: production
  debug: false

elo:
  default_rating: 1200
  k_factor: 32

ranking:
  inactivity_months: 3

system_user:
  username: system
  password: change_me

security:
  jwt_secret: change_me
  jwt_algorithm: HS256
  access_token_lifetime_minutes: 480
  cookie_secure: true
  cookie_httponly: true
  cookie_samesite: strict

storage:
  data_dir: /data
  upload_dir: /uploads
  log_dir: /logs
```

Secrets must never be committed to GitHub.

***

# User Roles

The system must support three roles.

## SYSTEM

Host administrator.

Highest privileges.

Characteristics:

* Defined via YAML configuration
* Not created through the UI
* Automatically provisioned on first startup
* Can manage everything
* Cannot be deleted through the UI
* Cannot be downgraded through the UI

Example:

```yaml
system_user:
  username: system
  password: change_me
```

## ADMIN

Full application administrator.

Can:

* Manage users
* Manage players
* Manage matches
* Manage club settings
* Export PDF reports
* Manage rankings
* View audit logs
* Manage backups

## USER

Restricted user.

Can:

* Create new match results
* View rankings

Cannot:

* Create users
* Edit users
* Edit players
* Delete matches
* Access administration functionality
* Change club settings
* Export administrative reports unless explicitly allowed later

Backend authorization must enforce all role restrictions.

Restrictions must never rely solely on frontend controls.

***

# User Management

Administrators can:

* Create users
* Create admins
* Disable users
* Enable users
* Reset passwords
* Change user roles
* View user list

The SYSTEM user can manage all users.

Passwords must never be stored in plaintext.

Password hashing must use:

```text
Argon2
```

## User Table

Required fields:

```text
ID
Username
Password Hash
Role
Active Status
Created At
Updated At
Last Login At
```

***

# Club Configuration

Administrators must be able to configure:

* Club name
* Club logo
* Default Elo rating
* K factor
* Inactive player threshold

Supported logo formats:

* PNG
* SVG
* JPG
* JPEG

Uploaded files must be validated.

Validation must include:

* File extension
* MIME type
* Maximum file size
* Storage path safety
* Protection against path traversal

Club settings must be stored in the database and may be initialized from the YAML configuration.

***

# Player Management

Administrators can:

* Create players
* Edit players
* Disable players
* Reactivate players manually if needed
* Set initial Elo rating

Default Elo:

```text
1200
```

Players must never be hard-deleted if they have match history.

Disabled players:

* Must remain in the database
* Must retain Elo history
* Must remain available in historical reports
* Must not appear in active player selection unless explicitly enabled by an administrator

## Player Table

Required fields:

```text
ID
Name
Start Elo
Current Elo
Created At
Updated At
Active Status
Disabled Status
Last Match Date
```

***

# Match Management

Matches must contain:

```text
ID
Date
Player A
Player B
Winner
Loser
Elo Before A
Elo Before B
Elo After A
Elo After B
Elo Change A
Elo Change B
Created By
Created At
Updated At
```

Administrators can:

* Create matches
* Edit matches
* Delete matches
* View match history

Users can:

* Create matches
* View rankings

Users cannot:

* Edit matches
* Delete matches

## Validation

Match validation must include:

* Player A cannot equal Player B
* Winner must be either Player A or Player B
* Loser must be the other player
* Date must be valid
* Date range must be valid
* Both players must exist
* Disabled players must not be selectable for new matches unless explicitly allowed by an administrator

***

# Historical Elo Recalculation

This is a mandatory requirement.

If a historical match is modified or deleted, all subsequent Elo ratings must be recalculated automatically.

## Required Behavior

When a match is added, edited, or deleted:

1. Identify the earliest affected match date.
2. Reset affected players to their correct rating before that match.
3. Recalculate all subsequent matches chronologically.
4. Update all stored Elo snapshots.
5. Update player current Elo ratings.
6. Update ranking calculations.
7. Write an audit log entry.
8. Execute the full operation inside a database transaction.

The recalculation must be deterministic.

Matches must be sorted by:

```text
Date ASC
Created At ASC
ID ASC
```

This ensures stable Elo calculations when multiple matches exist on the same date.

## Important

The system must not only update the edited match.

It must recalculate the complete affected Elo timeline after the changed match.

***

# Elo History

The system must maintain a complete Elo history.

Every match must store:

* Elo before match
* Elo after match
* Elo change

Historical rankings must be reproducible for any selected date range.

The current Elo rating of a player is derived from the result of the latest recalculation.

***

# Inactive Player Handling

## Automatic Inactive Players

The system must automatically exclude inactive players from rankings.

## Definition

A player is considered inactive if they have not played any match during a configurable inactivity period.

Default:

```yaml
ranking:
  inactivity_months: 3
```

Example:

* Player has played no match during the last 3 months
* Player is automatically considered inactive
* Player no longer appears in leaderboard rankings

## Important

Inactive players:

* Must remain in the database
* Must retain their Elo history
* Must retain their current Elo rating
* Must remain available in reports
* Must remain selectable for future matches
* Must not be deleted automatically

## Reactivation

When an inactive player plays a new match:

* Player becomes active automatically
* Player immediately reappears in ranking tables
* Player keeps the previous Elo rating

No manual reactivation should be required.

## Difference Between Disabled and Inactive

Inactive:

* Calculated automatically based on match activity
* Player can still play future matches
* Player is hidden from rankings only

Disabled:

* Set manually by an administrator
* Player should not be selectable for new matches by default
* Player remains in historical reports

***

# Ranking System

## Date Range Selection

All rankings are generated for a selected period.

Filters:

```text
From Date
To Date
```

Default:

```text
Current Month
```

Example:

```text
From = First day of current month
To   = Today
```

Admin PDF export default period:

```text
Previous Month
```

## Ranking Table

Required columns:

```text
Position
Player Name
Current Elo Rating
Elo Change (+/-)
Position Change (+/-)
```

## Details

### Position

Current ranking position at the end of the selected period.

### Elo Rating

Current Elo at the end of the selected period.

### Elo Change

Difference between:

```text
Rating at period start
vs
Rating at period end
```

### Position Change

Difference between:

```text
Position at period start
vs
Position at period end
```

Players considered inactive must not appear in the active leaderboard.

Inactive players must remain available in reports if explicitly included.

***

# User Interface

The user interface must be login protected.

The UI must be:

* Responsive
* Mobile-friendly
* Tablet-friendly
* Desktop-friendly
* Consistent in visual design
* Easy to use for non-technical users

Preferred UI stack:

* Bootstrap 5
* Tabler UI
* DataTables

***

# User Dashboard

Login protected.

## Add Match

Fields:

```text
Date
Player A
Player B
Result
```

Default values:

```text
Date = Today
```

Result options:

```text
Player A wins
Player B wins
```

Validation:

* Player A cannot equal Player B
* Result is required
* Date is required
* Both players are required

After a match is saved:

* Elo ratings are calculated
* Player ratings are updated
* Ranking is updated
* Audit log entry is created

## Ranking View

Show current ranking table.

Display:

```text
Position
Name
Elo Rating
Elo Change
Position Change
```

***

# Admin Dashboard

Login protected.

The admin dashboard must provide access to all administrative features.

## Club Management

Functions:

* Edit club name
* Upload club logo
* Change default Elo rating
* Change K factor
* Change inactivity threshold

## User Management

Functions:

* Create Admin
* Create User
* Disable User
* Enable User
* Reset Password
* Change Role

## Player Management

Functions:

* Add Player
* Edit Player
* Disable Player
* Reactivate Player
* View player Elo history
* View player match history

## Match Management

Functions:

* Add Match
* Edit Match
* Delete Match
* View Match History

When a match is edited or deleted, Elo recalculation must run automatically.

## Ranking View

Filter:

```text
From
To
```

Display:

```text
Position
Player
Elo
Elo Change
Position Change
```

Color rules:

use different colors for 
* Elo Change
* Position Change

```text
No change  = black
Negative   = red
Positive   = green
```

***

# PDF Export

Administrators must be able to generate a ranking report as PDF.

## Export Options

```text
From Date
To Date
```

Default:

```text
Previous Month
```

## Export Content

The PDF export must contain:

* Club Name
* Club Logo
* Ranking Table
* Elo Changes
* Position Changes
* Export Date
* Selected date range

Color rules:

use different colors for 
* Elo Change
* Position Change

```text
No change  = black
Negative   = red
Positive   = green
```

The PDF must be visually consistent with the application design.

***

# Audit Logging

The system must log important actions.

## Events to Log

```text
Login attempts
Failed logins
Logout events
Match created
Match edited
Match deleted
Ranking recalculated
User created
User edited
User disabled
User enabled
Password reset
Player created
Player edited
Player disabled
Player reactivated
Club settings changed
PDF exported
Backup created
Backup restored
Administrative actions
```

Passwords and secrets must never be logged.

## Audit Log Table

Required fields:

```text
ID
Timestamp
User ID
Username
Action
Entity Type
Entity ID
Old Value
New Value
IP Address
User Agent
```

Audit logs should be viewable by ADMIN and SYSTEM users.

***

# Security Requirements

Security requirements are mandatory.

## Password Security

Passwords must never be stored in plaintext.

Use:

```text
Argon2
```

## Authentication

Use:

```text
JWT
Secure Cookies
HttpOnly Cookies
SameSite Protection
```

Recommended defaults:

```yaml
security:
  access_token_lifetime_minutes: 480
  cookie_secure: true
  cookie_httponly: true
  cookie_samesite: strict
```

## Authorization

Backend must enforce role checks.

Restrictions may never rely solely on frontend controls.

## CSRF Protection

Because authentication uses cookies, CSRF protection must be implemented for state-changing operations.

State-changing operations include:

```text
POST
PUT
PATCH
DELETE
```

## Input Validation

Validate:

* Form input
* Uploaded files
* Date ranges
* User data
* Match data
* Ranking filters

Prevent:

* SQL Injection
* XSS
* CSRF
* File Upload Attacks
* Path Traversal
* Unsafe redirects

## Logging

Log:

* Login attempts
* Failed logins
* Match changes
* User changes
* Administrative actions

Passwords and secrets must never be logged.

## Error Handling

The system must provide:

* Consistent API error messages
* User-friendly UI error messages
* Validation error responses
* Unhandled exception logging
* Friendly error pages

Unhandled exceptions must not expose sensitive technical details to users.

***

# Backup and Restore

Administrators must be able to create and restore backups.

## Backup Content

Backup must include:

```text
SQLite database file
Uploaded club logo
Configuration-relevant application data
```

## Backup Requirements

* Manual database backup
* Manual restore from backup
* Backup file download
* Restore confirmation step
* Audit log entry for backup and restore operations

## Recommended Storage Paths

```text
/data/database.db
/uploads
/logs
/backups
```

***

# Docker Deployment

The application must be fully containerized.

Required files:

```text
Dockerfile
docker-compose.yml
```

## Services

Required services:

```text
elo
```

The SQLite database must be stored in a persistent Docker volume.

## Docker Volumes

Use Docker-standard folder structures.

Recommended internal paths:

```text
/data
/uploads
/logs
/backups
```

Example volumes:

```yaml
volumes:
  elo_data:
  elo_uploads:
  elo_logs:
  elo_backups:
```

## Version Display

The currently running version must be visible in the UI.

Display:

```text
Version
Git Commit SHA
Build Date
```

Example footer:

```text
v1.2.3 (a1b2c3d) - Build 2026-07-21
```

The version information should be injected during the GitHub Actions build process.

***

# GitHub Requirements

The project must be designed for GitHub-based development.

Repository must contain:

```text
README.md
Dockerfile
docker-compose.yml
.env.example
config.yaml.example
requirements.txt
.gitignore
app/
tests/
.github/workflows/
```

Secrets must never be committed.

***

# GitHub Container Registry

A new release must start the workflow to build and publish the Docker image.

Required image:

```text
ghcr.io/reserve85/EloRankingSystem:main
```

This image must be accessible from the Docker Compose file.

Example:

```yaml
services:
  elowebapp:
    image: ghcr.io/reserve85/EloRankingSystem:main
```

***

# GitHub Actions / CI-CD

The repository must contain GitHub Actions workflows.

Required workflow steps:

```text
Install dependencies
Run tests
Run linter
Run security checks if possible
Build Docker image
Publish Docker image to GitHub Container Registry
Create or update release artifact
```

Pull requests must pass all tests before merge.

Recommended workflow files:

```text
.github/workflows/test.yml
.github/workflows/docker-publish.yml
.github/workflows/release.yml
```

***

# Testing Requirements

Automated tests are mandatory.

Preferred testing framework:

```text
pytest
```

## Elo Tests

Required tests:

* Rating increase after win
* Rating decrease after loss
* Correct expected score calculation
* Correct K factor handling
* Correct default rating handling

## Ranking Tests

Required tests:

* Ranking generation
* Position change calculation
* Elo change calculation
* Date range filtering
* Inactive players excluded from active ranking

## Inactive Player Tests

Required tests:

* Player becomes inactive after threshold period
* Inactive player hidden from ranking
* Player automatically reactivated after new match
* Inactive player retains Elo rating
* Inactive player remains available in reports

## Match Tests

Required tests:

* Match creation
* Match validation
* Player A cannot equal Player B
* Historical match edit triggers recalculation
* Historical match delete triggers recalculation
* Recalculation is chronological and deterministic

## Permission Tests

Required tests:

* USER permissions
* ADMIN permissions
* SYSTEM permissions
* USER cannot access admin functionality
* USER cannot edit users
* USER cannot delete matches
* ADMIN can manage application data
* SYSTEM has highest privileges

## Security Tests

Recommended tests:

* Passwords are hashed
* Login with invalid credentials fails
* Disabled users cannot log in
* Unauthorized access is blocked
* Role checks are enforced on backend routes

## Minimum Coverage

Target:

```text
80% test coverage
```

***

# Database Model

The application should include at least the following tables:

```text
users
players
matches
club_settings
audit_log
```

Optional:

```text
backups
ranking_snapshots
```

## users

```text
id
username
password_hash
role
active
created_at
updated_at
last_login_at
```

## players

```text
id
name
start_elo
current_elo
active
disabled
last_match_date
created_at
updated_at
```

## matches

```text
id
date
player_a_id
player_b_id
winner_id
loser_id
elo_before_a
elo_before_b
elo_after_a
elo_after_b
elo_change_a
elo_change_b
created_by
created_at
updated_at
```

## club\_settings

```text
id
club_name
club_logo_path
default_elo
k_factor
inactivity_months
created_at
updated_at
```

## audit\_log

```text
id
timestamp
user_id
username
action
entity_type
entity_id
old_value
new_value
ip_address
user_agent
```

***

# API Documentation

FastAPI OpenAPI documentation must be available.

Required endpoints:

```text
/docs
/redoc
```

Access to API documentation may be restricted in production if required.

***

# Non-Functional Requirements

## Maintainability

The application must be cleanly structured and maintainable.

Requirements:

* No business logic in templates
* No business logic directly in routes
* Services contain business logic
* Repositories handle database access
* Tests cover business-critical logic
* Configuration is centralized

## Performance

The system should support at least:

```text
500 players
50,000 matches
```

Typical page response time should be below:

```text
2 seconds
```

for normal club usage.

## Accessibility

The user interface should follow basic accessibility best practices.

Recommended target:

```text
WCAG AA where possible
```

## Usability

The application should be usable by non-technical club administrators.

Important UI requirements:

* Clear navigation
* Clear error messages
* Confirmation dialogs for destructive actions
* Mobile-friendly forms
* Searchable and sortable tables

***

# README Requirements

The project must contain a complete `README.md`.

The README must include:

```text
Project overview
Features
Screenshots placeholder
Technology stack
Installation instructions
Docker deployment
Configuration
Environment variables
Default system user setup
Backup procedure
Restore procedure
Development setup
Testing instructions
Release process
GitHub Actions explanation
Security notes
License information
```

## README Installation Section Must Include

```text
Clone repository
Copy .env.example to .env
Copy config.yaml.example to config.yaml
Adjust configuration
Start using docker compose
Open application in browser
Login with configured system user
Change default password
```

***

# Expected Final Deliverable

The final deliverable is a production-ready application that provides:

* Elo-based ranking system
* Responsive web interface
* Player management
* User management
* Club management
* Match management
* Automatic inactive player detection
* Automatic player reactivation
* Historical Elo recalculation
* Ranking reporting
* PDF export
* Secure authentication
* Secure authorization
* Audit logging
* Backup and restore
* Docker deployment
* SQLite database
* Automated tests
* Complete GitHub repository structure
* GitHub Actions CI/CD
* GitHub Container Registry image publishing
* Complete README.md with installation instructions
* Clean and maintainable architecture
* Clear separation of concerns
* Long-term maintainability

***

# Important Implementation Notes for Coding Agent

The historical Elo recalculation is one of the most important parts of this project.

Do not implement Elo ratings only as a simple update on the two players of the latest match.

The application must be able to reproduce and recalculate historical Elo states when older matches are edited or deleted.

All business-critical operations must be covered by tests.

Security must be implemented in the backend and must not rely only on frontend visibility rules.

Docker deployment must persist all data using volumes.

The application must be usable after cloning the repository and running Docker Compose with minimal manual setup.

```