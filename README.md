# Elo Ranking System

A dart club ranking system using the [Elo Rating System](https://en.wikipedia.org/wiki/Elo_rating_system).

## Donate and become a Sponsor
[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://paypal.me/TobiasWKraft/5)

## Features

- **Elo-based ranking system** for dart club players with configurable K-factor and default rating
- **Player management** with enable/disable, initial Elo rating, and automatic inactive player detection
- **User management** with role-based access control (SYSTEM, ADMIN, USER)
- **Match management** with configurable match format (Best-of-1 to Best-of-21) and automatic Elo recalculation
- **Mixed match formats** — different formats can coexist (e.g., Best-of-5 and Best-of-9 matches in the same database)
- **Match format stored per match** — each match records its own Best-of-N for correct validation
- **Dart statistics** per match: 180s, High Finishes, Low Darts
- **Match statistics detail view** with per-player stats side by side
- **Player statistics view** (period and all-time) accessible from ranking table
- **Admin statistics editing** for match details
- **All Time Elo Rating chart** with interactive horizontal bar chart
- **Historical Elo tracking** with interactive line chart per player
- **Player statistics** with Match W/L, Legs W/L, match counts, 180s, High Finishes, Low Darts (period and all-time)
- **Impossible high finish validation** — blocks values that cannot be checked out with 3 darts (159, 162, 163, 165, 166, 168, 169)
- **Auto-fill score logic** — selecting a losing score auto-fills the opponent's winning score
- **Date range filtering** on rankings, match history, and PDF export
- **Automatic inactive player handling** based on interval-based match activity
- **Interval-based "Include inactive" checkbox** — checks if players were active in the selected date range
- **PDF ranking report export** with configurable date range
- **Audit logging** for all important actions
- **Responsive web interface** (Bootstrap 5 / Tabler UI) with mobile-friendly layout
- **Cookie consent banner** (EU compliance)
- **Impressum and Privacy Policy pages** (GDPR compliant)
- **QR code auto-login** — generate printable QR codes for USER accounts so members can log in by scanning (USER-only, admins blocked)
- **Real-time password strength validation** with ✅/❌ indicators on user creation and password reset
- **Client-side validation** blocks save for weak passwords or duplicate usernames
- **Docker deployment** with GitHub Container Registry
- **Portainer Stack deployment** support
- **Confirmation dialogs** on all modifying actions
- **Auto-refresh** of affected UI components after changes
- **Configurable date format** and timezone display

## Technology Stack

- **Backend:** Python 3.12+, FastAPI
- **ORM:** SQLAlchemy
- **Database:** SQLite (designed for future PostgreSQL migration)
- **Migrations:** Alembic
- **Frontend:** Bootstrap 5, Tabler UI, Jinja2, DataTables, Chart.js
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

#### Quick Start with Docker

1. Copy configuration files:
   ```bash
   cp .env.example .env
   cp config.yaml.example config.yaml
   ```

2. Edit `.env` and `config.yaml` with your settings. **Change default passwords!**

3. Build and start:
   ```bash
   docker compose build
   docker compose up -d
   ```

4. View logs:
   ```bash
   docker compose logs -f
   ```

5. Open `http://localhost:8000`

6. Login with the configured system user credentials (default: `system` / `change_me`).

7. **Change the default system user password immediately after first login.**

#### Using GitHub Container Registry Image

The pre-built image is available at:
```
ghcr.io/reserve85/elo_ranking_system:main
```

The `docker-compose.yml` is already configured to use this image. Only `docker compose up -d` is needed (no build required).

#### Docker Volumes

All data is persisted in Docker named volumes:

| Volume | Container Path | Purpose |
|--------|---------------|---------|
| `elo_data` | `/data` | SQLite database |
| `elo_uploads` | `/uploads` | Club logo uploads |
| `elo_logs` | `/logs` | Application logs |

#### Version Display

The running version is displayed in the UI footer:
```
v0.1.0 (a1b2c3d) - Build 2025-07-21
```

To build with version info:
```bash
GIT_COMMIT=$(git rev-parse --short HEAD) \
BUILD_DATE=$(date +%Y-%m-%d) \
APP_VERSION=0.1.0 \
docker compose build
```

#### Stopping and Restarting

```bash
docker compose down    # Stop
docker compose up -d   # Start
```

### Portainer Deployment

This application can be deployed via [Portainer](https://www.portainer.io/) Stacks, which is a common deployment method for NAS devices (Synology, QNAP, Unraid) and Docker hosts with a web UI.

#### Prerequisites

- Portainer installed and running on your Docker host
- Access to the Portainer web UI
- Internet access to pull the image from GitHub Container Registry

#### Steps

1. **Prepare your host directories** (recommended):
   ```bash
   mkdir -p /volume1/docker/elo/{data,uploads,logs}
   ```
   Adjust the base path (`/volume1/docker/elo/`) to match your system.

2. **Open Portainer** and navigate to **Stacks** > **Add Stack**.

3. **Name the stack** (e.g., `elo-ranking`).

4. **Paste the contents** of `portainer_compose.yaml` into the web editor. This file contains all environment variables inlined with comments describing each setting.

5. **Replace placeholder values**:
   - `JWT_SECRET=CHANGE_ME_GENERATE_RANDOM` — Generate a strong secret with `openssl rand -hex 32`
   - `SYSTEM_USER_PASSWORD=CHANGE_ME_HERE` — Set a strong admin password
   - `COOKIE_SECURE=false` — Set to `true` if using HTTPS
   - Adjust volume mount paths if needed (default: `/volume1/docker/elo/...`)

6. **Deploy the stack** by clicking the button.

7. **Open the application** at `http://your-host:8877`.

8. **Login** with the system user credentials you configured.

9. **Change the default system user password** immediately after first login.

#### Portainer Volume Paths

The `portainer_compose.yaml` uses bind mounts with example paths:

| Host Path (example) | Container Path | Purpose |
|---------------------|---------------|---------|
| `/volume1/docker/elo/data` | `/data` | SQLite database |
| `/volume1/docker/elo/uploads` | `/uploads` | Club logo uploads |
| `/volume1/docker/elo/logs` | `/logs` | Application logs |

Adjust the host paths to match your NAS or Docker host directory structure.

#### Differences from Standard Docker Compose

| Feature | `docker-compose.yml` | `portainer_compose.yaml` |
|---------|---------------------|--------------------------|
| Environment variables | Loaded from `.env` file | Inlined in YAML |
| Config file | Mounted from `config.yaml` | Not mounted (uses env vars) |
| Build context | Included | Not included (deployment only) |
| Port mapping | `8000:8000` | `8877:8000` |
| Volumes | Named volumes | Bind mounts |

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
| `CLUB_NAME` | Club name displayed in header and reports | `My Dart Club` |
| `APP_ENV` | Application environment | `development` |
| `APP_DEBUG` | Debug mode | `false` |
| `CONFIG_PATH` | Path to config.yaml | `config.yaml` |
| `TIMEZONE` | Timezone for date display (IANA format) | `Europe/Berlin` |
| `DATE_FORMAT` | Date format for display | `dd/MM/yyyy` |
| `APP_BASE_URL` | Public base URL for QR code behind reverse proxy (e.g. `https://darts.example.com`) | *(empty, uses request URL)* |
| `DATABASE_URL` | Database connection string | `sqlite:///./data/database.db` |
| `DEFAULT_ELO` | Default Elo rating for new players | `1200` |
| `K_FACTOR` | Elo K-factor (rating sensitivity) | `32` |
| `INACTIVITY_MONTHS` | Months before player is considered inactive | `3` |
| `HIGH_FINISH_MIN` | Minimum valid high finish score | `100` |
| `HIGH_FINISH_MAX` | Maximum valid high finish score | `170` |
| `LOW_DARTS_MIN` | Minimum valid low darts count | `9` |
| `LOW_DARTS_MAX` | Maximum valid low darts count | `21` |
| `BEST_OF_LEGS` | Default match format (must be odd: 1, 3, 5, 7, 9...21) | `5` |
| `CONTACT_COMPANY` | Company/club name for Impressum | `Company` |
| `CONTACT_NAME` | Contact person name for Impressum | `Max Mustermann` |
| `CONTACT_STREET` | Street address for Impressum | `Musterstrasse 1` |
| `CONTACT_CITY` | City for Impressum | `11111 Musterstadt` |
| `CONTACT_EMAIL` | Contact email for Impressum | `max.Mustermann@Muster.mu` |
| `SYSTEM_USER_USERNAME` | System admin username | `system` |
| `SYSTEM_USER_PASSWORD` | System admin password | `change_me` |
| `JWT_SECRET` | JWT signing secret | `change_me` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | Token lifetime in minutes | `480` |
| `COOKIE_SECURE` | Secure cookie flag | `true` |
| `COOKIE_HTTPONLY` | HttpOnly cookie flag | `true` |
| `COOKIE_SAMESITE` | SameSite cookie policy | `strict` |
| `DATA_DIR` | Data storage path | `./data` |
| `UPLOAD_DIR` | Upload storage path | `./uploads` |
| `LOG_DIR` | Log storage path | `./logs` |

### YAML Configuration (config.yaml)

Copy `config.yaml.example` to `config.yaml` and adjust club-specific settings. The YAML file is organized into sections:

| Section | Keys | Description |
|---------|------|-------------|
| `app` | `name`, `club_name`, `environment`, `debug`, `timezone`, `date_format` | Application identity & display |
| `elo` | `default_rating`, `k_factor` | Elo system parameters |
| `ranking` | `inactivity_months` | Inactive player threshold |
| `statistics` | `high_finish_min`, `high_finish_max`, `low_darts_min`, `low_darts_max`, `best_of_legs` | Dart statistics & match format validation |
| `legal` | `contact_company`, `contact_name`, `contact_street`, `contact_city`, `contact_email` | Impressum & Privacy page data |
| `system_user` | `username`, `password` | Host administrator credentials |
| `security` | `jwt_secret`, `jwt_algorithm`, `access_token_lifetime_minutes`, `cookie_secure`, `cookie_httponly`, `cookie_samesite` | Authentication & security |
| `storage` | `data_dir`, `upload_dir`, `log_dir` | File storage paths |

Values in `.env` or environment variables always override values in `config.yaml`.

See `config.yaml.example` for the full reference.

## Default System User

The system user is automatically provisioned on first startup from the configuration. It cannot be deleted or downgraded through the UI.

**You MUST change the default password before deploying to production.**

To configure:
```yaml
# config.yaml
system_user:
  username: system
  password: change_me
```
Or via environment variable:
```
SYSTEM_USER_USERNAME=system
SYSTEM_USER_PASSWORD=your_strong_password
```

## User Roles

| Role | Permissions |
|------|-------------|
| **SYSTEM** | Full access. Cannot be deleted or downgraded. |
| **ADMIN** | Manage players, users, matches, settings, exports. |
| **USER** | Create matches, view rankings. No admin access. |

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
├── test_elo.py       # Elo calculation tests
├── test_rankings.py  # Ranking generation tests
├── test_inactive_players.py  # Inactive player handling tests
├── test_matches.py   # Match management tests
├── test_statistics.py # Dart statistics tests
├── test_reports.py   # PDF report tests
├── test_templates.py # UI template tests
└── ...

requirements.txt      # Python dependencies
pyproject.toml        # Project config, pytest, coverage settings
.env.example          # Environment variable template
config.yaml.example   # YAML configuration template
Dockerfile            # Container image definition
docker-compose.yml    # Docker Compose configuration
portainer_compose.yaml # Portainer Stack deployment
.gitignore            # Git ignore rules
```

## GitHub Actions / CI/CD

The project includes three GitHub Actions workflows:

### test.yml — Tests on Push/PR

Triggers on every push to `main` and on pull requests:

1. Installs Python dependencies
2. Runs linter (`ruff`)
3. Runs all tests (`pytest`)

Pull requests must pass all tests before merge.

### docker-publish.yml — Docker Image Build

Triggers on push to `main` and on version tags (`v*`):

1. Builds the Docker image with version metadata (GIT_COMMIT, BUILD_DATE, APP_VERSION)
2. Publishes to GitHub Container Registry: `ghcr.io/reserve85/elo_ranking_system:main`
3. Uses GitHub Actions cache for faster builds

### release.yml — Release Publishing

Triggers when a GitHub release is published:

1. Builds Docker image with release version
2. Publishes to GHCR with three tags:
   - `ghcr.io/reserve85/elo_ranking_system:main`
   - `ghcr.io/reserve85/elo_ranking_system:<version>`
   - `ghcr.io/reserve85/elo_ranking_system:<git-sha>`
3. Uploads release info artifact

### Release Process

1. Create a new tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. Create a GitHub release from the tag.

3. The release workflow automatically:
   - Builds and publishes the Docker image
   - Tags it with the version number
   - Uploads release artifacts

### Required GitHub Secrets

No custom secrets are required. The workflows use the built-in `GITHUB_TOKEN` for GHCR authentication.

## Security Notes

- All passwords are hashed using Argon2
- JWT tokens are stored in secure HttpOnly cookies
- CSRF protection is implemented for state-changing operations
- Role-based access control is enforced on the backend
- Never commit `.env`, `config.yaml`, or database files
- Change all default passwords before deploying to production
- GitHub Actions secrets (`GITHUB_TOKEN`) are used automatically

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.
