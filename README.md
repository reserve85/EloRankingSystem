# Elo Ranking System

A dart club ranking system using the [Elo Rating System](https://en.wikipedia.org/wiki/Elo_rating_system).

## Features

- Elo-based ranking system for dart club players
- Player management
- User management with role-based access control (SYSTEM, ADMIN, USER)
- Match management with automatic Elo recalculation
- Historical Elo tracking
- Automatic inactive player handling
- PDF ranking report export
- Audit logging
- Backup and restore
- Responsive web interface (Bootstrap 5 / Tabler UI)
- Docker deployment with GitHub Container Registry

## Technology Stack

- **Backend:** Python 3.12+, FastAPI
- **ORM:** SQLAlchemy
- **Database:** SQLite (designed for future PostgreSQL migration)
- **Migrations:** Alembic
- **Frontend:** Bootstrap 5, Tabler UI, Jinja2, DataTables
- **PDF:** reportlab
- **Auth:** JWT with Argon2 password hashing, secure HttpOnly cookies
- **Testing:** pytest, pytest-cov, httpx

## Installation

### Prerequisites

- Python 3.12+
- pip

### Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/reserve85/EloRankingSystem.git
   cd EloRankingSystem
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/macOS
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy configuration files:
   ```bash
   copy .env.example .env        # Windows
   copy config.yaml.example config.yaml
   # cp .env.example .env        # Linux/macOS
   # cp config.yaml.example config.yaml
   ```

5. Edit `.env` and `config.yaml` with your settings. **Change default passwords!**

6. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

7. Open your browser at `http://localhost:8000`

8. API docs available at `http://localhost:8000/docs`

### Docker Deployment

1. Build and start:
   ```bash
   docker compose up -d
   ```

2. Open `http://localhost:8000`

3. Login with the configured system user credentials.

> **Important:** Change the default system user password immediately after first login.

## Configuration

Configuration is loaded with the following priority (highest wins):

1. **Environment variables** (set in shell)
2. **`.env` file** values
3. **`config.yaml`** values
4. **Default values** defined in the application

### Environment Variables (.env)

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Application name | `Elo Ranking System` |
| `APP_ENV` | Application environment | `development` |
| `APP_DEBUG` | Debug mode | `false` |
| `CONFIG_PATH` | Path to config.yaml | `config.yaml` |
| `DATABASE_URL` | Database connection string | `sqlite:///./data/database.db` |
| `DEFAULT_ELO` | Default Elo rating for new players | `1200` |
| `K_FACTOR` | Elo K-factor (rating sensitivity) | `32` |
| `INACTIVITY_MONTHS` | Months before player is considered inactive | `3` |
| `SYSTEM_USER_USERNAME` | System admin username | `system` |
| `SYSTEM_USER_PASSWORD` | System admin password | `change_me` |
| `JWT_SECRET` | JWT signing secret | `change_me` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | Token lifetime in minutes | `480` |
| `COOKIE_SECURE` | Secure cookie flag | `false` |
| `COOKIE_HTTPONLY` | HttpOnly cookie flag | `true` |
| `COOKIE_SAMESITE` | SameSite cookie policy | `lax` |
| `DATA_DIR` | Data storage path | `./data` |
| `UPLOAD_DIR` | Upload storage path | `./uploads` |
| `LOG_DIR` | Log storage path | `./logs` |
| `BACKUP_DIR` | Backup storage path | `./backups` |

### YAML Configuration (config.yaml)

Copy `config.yaml.example` to `config.yaml` and adjust club-specific settings. The YAML file is organized into sections:

| Section | Keys | Description |
|---------|------|-------------|
| `app` | `name`, `environment`, `debug` | Application identity |
| `elo` | `default_rating`, `k_factor` | Elo system parameters |
| `ranking` | `inactivity_months` | Inactive player threshold |
| `system_user` | `username`, `password` | Host administrator credentials |
| `security` | `jwt_secret`, `jwt_algorithm`, `access_token_lifetime_minutes`, `cookie_secure`, `cookie_httponly`, `cookie_samesite` | Authentication & security |
| `storage` | `data_dir`, `upload_dir`, `log_dir`, `backup_dir` | File storage paths |

Values in `.env` or environment variables always override values in `config.yaml`.

See `config.yaml.example` for the full reference.

## Development Setup

1. Follow the installation steps above.

2. Run tests:
   ```bash
   pytest
   ```

3. Run tests with coverage:
   ```bash
   pytest --cov=app --cov-report=html
   ```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_health.py

# Run with verbose output
pytest -v
```

## Project Structure

```
app/
├── api/
│   ├── routes/       # API route handlers
│   └── dependencies/ # FastAPI dependencies
├── auth/             # Authentication logic
├── core/             # Configuration, database, utilities
├── models/           # SQLAlchemy ORM models
├── schemas/          # Pydantic validation schemas
├── services/         # Business logic layer
├── repositories/     # Database access layer
├── templates/        # Jinja2 HTML templates
├── static/           # CSS, JS, images
├── reports/          # PDF report generation
├── migrations/       # Alembic migrations
└── main.py           # FastAPI application entry point

tests/
├── conftest.py       # Test fixtures and configuration
├── test_health.py    # Health endpoint tests
└── ...

requirements.txt      # Python dependencies
pyproject.toml        # Project config, pytest, coverage settings
.env.example          # Environment variable template
config.yaml.example   # YAML configuration template
Dockerfile            # Container image definition
docker-compose.yml    # Docker Compose configuration
.gitignore            # Git ignore rules
```

## Security Notes

- All passwords are hashed using Argon2
- JWT tokens are stored in secure HttpOnly cookies
- CSRF protection is implemented for state-changing operations
- Role-based access control is enforced on the backend
- Never commit `.env`, `config.yaml`, or database files
- Change all default passwords before deploying to production

## License

See [LICENSE](LICENSE) for details.