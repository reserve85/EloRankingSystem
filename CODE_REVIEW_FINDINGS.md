# Code Review Findings — Elo Ranking System

**Date:** 2026-09-04
**Scope:** Full codebase review (`app/`, `tests/`, infra files), branch `main`
**Method:** Review-team pass covering correctness, security, architecture, code quality, testing/reliability, and UX concerns. Findings below are concrete, ranked by severity.

## Verification performed

| Check | Result |
|-------|--------|
| Full pytest suite | ✅ **798 passed** in ~265 s (`python -m pytest`) |
| Ruff lint (`ruff check app tests`) | ✅ All checks passed (default rule set) |
| Test side-effect audit | ⚠️ Confirmed: every test run recreates `test.db`, `test_legal.db`, `test_statistics.db`, `data/database.db` (+ SQLite `-wal`/`-shm`) plus `__pycache__`, `.pytest_cache`, `.ruff_cache` |
| Security review | ⚠️ Plaintext password in QR auto-login URL, unenforced default secrets, proxy/forwarded-header blind spots |

**Severity legend:** 🔴 High (security/credential loss, data loss, or app-breaking) · 🟠 Medium (reproducible bugs, reliability, security hygiene) · 🟡 Low (UX, maintainability, minor bugs).

---

## 🔴 High severity

### H1. QR code auto-login embeds the plaintext password in the URL
- **Category:** Security
- **Location:** `app/api/routes/settings.py:273` (URL construction), `app/api/routes/auth.py:95-119` (`GET /auth/auto-login?u=...&p=...`)
- **Problem:** The "generate QR code" feature serializes the user's *actual password* into the link that is encoded in the QR:
  ```python
  url = f"{base_url}/auth/auto-login?u={data.username}&p={data.password}"
  ```
  The QR credentials are passed as `GET` query parameters and are functionally permanent — they stay valid until the user's password changes.
- **Evidence:** `app/templates/admin.html:1118-1131` sends `{username, password}` to `/settings/qrcode`; the server verifies the password (`app/api/routes/settings.py:250-253`) and embeds it in the URL (`:273`). `auto_login` then authenticates purely from `u`/`p` query params (`app/api/routes/auth.py:100-105`).
- **Impact:** Plaintext passwords leak into web-server/proxy access logs, browser history, `Referer` headers on subsequent navigation, and analytics. On a shared machine the QR code itself or its printout is a working, non-expiring login credential. Any log compromise = account compromise.
- **Recommendation:** Encode a short-lived, single-use signed token (e.g. HMAC/JWT with the user id + nonce, stored/expiring) instead of the raw password. Keep the QR as a convenience login, not a credential duplicate.
- **Status:** ✅ **Accepted tradeoff** (owner decision, 2026-09-04): the QR auto-login is only used by club members to log in and create matches; the club threat model accepts this. No change planned.

### H2. Known default secrets are not enforced — SYSTEM account and JWT forgeable out of the box
- **Category:** Security
- **Location:** `app/core/config.py:152-157` (`system_user_password` / `jwt_secret` default to `"change_me"`), `app/auth/service.py:68-100` (provisions SYSTEM from config), `app/auth/jwt.py:40-44` (tokens signed with configured secret)
- **Problem:** There is no startup validation that refuses to run with the default `change_me` value (outside explicit development mode). If a deployment forgets to set `.env`, the SYSTEM (host-admin) account is created with the publicly known password `"change_me"`, and JWT tokens can be forged by anyone, including with `role=SYSTEM` (`app/auth/jwt.py:32-38`, `app/auth/dependencies.py:120-141`).
- **Evidence:** `.env.example:44-49` and `config.yaml.example:36-46` only *tell* the operator to change them; nothing enforces it. `provision_system_user` runs automatically in the app lifespan (`app/main.py:36-41`).
- **Impact:** Default-config deployment = fully compromised authentication/authorization.
- **Recommendation:** In `get_settings()`/startup, hard-fail when `APP_ENV != "development"` (or `APP_ENV == "production"`) and `jwt_secret`/`system_user_password` are still the documented defaults. Provide a generated-secret bootstrap script.
- **Status:** ✅ **Fixed** (owner decision, 2026-09-04, superseding the earlier accepted-tradeoff note): the operator originally accepted the tradeoff, then decided to implement it. See **M1-aligned implementation log (H2)** below.

---

## 🟠 Medium severity

### M1. Test suite litters the working tree with database files (your hint)
- **Category:** Testing / hygiene
- **Location:** `tests/conftest.py:28-34` (file DB `sqlite:///./test.db` despite the comment "Use in-memory SQLite for tests"), `tests/test_legal.py:12-38`, `tests/test_statistics.py:17-46` (own engines on `./test_legal.db` / `./test_statistics.db`), app lifespan `app/main.py:33-41` → `app/core/database.py:64-112` (`init_db()` runs against the *real* engine on every `TestClient` start)
- **Problem:** Every test run creates/persists four SQLite files in the repository root/working tree:
  - `test.db` — from the conftest engine;
  - `test_legal.db`, `test_statistics.db` — from duplicated per-module engines/fixtures;
  - `data/` + `data/database.db` (+ transient `-wal`/`-shm`) — because `with TestClient(app):` runs the lifespan, which calls `init_db()` on the production `DATABASE_URL`.
  Plus the usual `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, and the manual `tests/private_livesystem_test/{data,uploads,logs,backups,config}` leftovers.
- **Evidence:** The files are present in the workspace right now. A controlled run against a throwaway `DATABASE_URL` confirmed the lifespan creates the DB file plus `-wal`/`-shm` side files at startup. These files are all git-ignored, so `git status` stays clean while the workspace keeps filling up.
- **Impact:** Continuous workspace pollution, CWD-dependent behavior (paths are relative `./*.db`), stale-schema risk across runs, duplicated fixture code that can drift from `conftest.py`.
- **Recommendation:**
  1. Switch the conftest engine to a true in-memory SQLite (`sqlite://` with `poolclass=StaticPool`, `connect_args={"check_same_thread": False}`) — this matches the existing comment and drops `test.db` entirely.
  2. Remove the duplicated engines/fixtures in `test_legal.py` / `test_statistics.py` and reuse the conftest `db_session`/`client` fixtures (or point them at a shared in-memory engine).
  3. Isolate the app lifespan during tests: monkeypatch `DATABASE_URL` to an in-memory/tmp URL or stub `init_db()` and `provision_system_user()` so `data/` is never touched by pytest. The private-livesystem-test harness is a separate manual tool; clean it up or move its outputs into an ignored scratch dir.
- **Status:** ✅ **Fixed** (2026-09-04):
  - `tests/conftest.py` now runs the whole suite on `sqlite://` with `StaticPool`, sets `DATABASE_URL`/`DATA_DIR`/`UPLOAD_DIR`/`LOG_DIR` to throwaway values *before* app import, and stubs the lifespan's `init_db()` / `provision_system_user()` in the `client` fixture.
  - Duplicated engines/fixtures removed from `tests/test_legal.py` and `tests/test_statistics.py`.
  - `tests/test_config.py::test_storage_section_mapping` made hermetic (delenv of the shared storage vars).
  - Stale `test.db`, `test_legal.db`, `test_statistics.db` deleted from the working tree.
  - Verified: **798 passed** in ~41 s (previously ~265 s), no `*.db` files created, `data/database.db` untouched.

### M2. `init_db()` swallows migration failures and keeps the app running on an un-migrated schema
- **Category:** Reliability
- **Location:** `app/core/database.py:95-112`
- **Problem:** In scenarios 2 and 3 a failed `command.upgrade(...)` is only logged (`logger.error`) and the application continues to start. Requests then hit a schema that does not match the models (missing columns/tables), producing confusing 500s later.
- **Impact:** Silent data/schema drift in production; hard to diagnose.
- **Recommendation:** Fail fast on migration errors (or at minimum surface the failure via `/health` and a non-zero exit). Startup should not proceed on an unknown schema state.

### M3. CWD-relative paths break when the app is launched from another directory
- **Category:** Reliability / correctness
- **Location:** `app/main.py:77` (`StaticFiles(directory="app/static")`), `app/core/database.py:83` (`Config("alembic.ini")`), `alembic.ini:6` (`script_location = app/migrations`), `alembic.ini:16` (`prepend_sys_path = .`)
- **Problem:** Static files and Alembic configuration resolve relative to the current working directory. Running `uvicorn app.main:app` from anywhere except the project root silently breaks CSS/JS (static mount) and potentially database migrations.
- **Impact:** Confusing production failures triggered purely by the launch directory.
- **Recommendation:** Anchor these to `BASE_DIR`/`__file__` (like `app/core/templates.py:7` already does): absolute `StaticFiles(directory=str(BASE_DIR / "app/static"))`, `Config(str(BASE_DIR / "alembic.ini"))`, and absolute `script_location`/`prepend_sys_path` in `alembic.ini`.

### M4. Deleting a user who authored matches raises an unhandled 500
- **Category:** Correctness / robustness
- **Location:** `app/api/routes/users.py:82-86` (`delete_user`), constraint in `app/models/match.py:82-84` (`created_by` FK → `users.id`)
- **Problem:** `db.delete(user); db.commit()` violates the `matches.created_by` foreign key if the user created any match. Because `PRAGMA foreign_keys=ON` is only registered on the production engine (`app/core/database.py:38-45`) — the test engines set no pragma — the suite never exercises this path and it stays red/green-light invisible.
- **Impact:** Reproducible 500 on a normal admin action; no clean error.
- **Recommendation:** Either soft-delete users, or check `matches` for `created_by == user_id` first and return a clear 400, or set the references to NULL before deleting. Also register the FK pragma on the test engines so tests catch such cases.

### M5. Score validation on update uses the *global* `best_of_legs`, not the match's stored format
- **Category:** Correctness (bug)
- **Location:** `app/schemas/match.py:206-220` vs `app/services/match.py:157-165`
- **Problem:** `MatchUpdate.validate_scores` validates `(player1_score, player2_score)` against `settings.best_of_legs` when `best_of_legs` is not supplied in the request, while the service computes the winner with the *stored* `match.best_of_legs`. For matches created with a non-default format these disagree.
- **Evidence:** A match created as best-of-3 (valid scores `2:0/2:1/...`) cannot be updated to a legal score like `2:1` — the schema validates it as a best-of-5 score (wins needed 3) and rejects it with 422, even though the service would accept it.
- **Impact:** Legitimate updates of non-default-format matches are rejected (or, in the reverse direction, invalid scores could pass schema but the model stays inconsistent).
- **Recommendation:** The update validator needs the existing match's `best_of_legs`; validate with the effective value (either load the match in the validator via a DB dependency, or move score validation into the service where the stored format is known).

### M6. Rate limiting and audit logging ignore `X-Forwarded-For`
- **Category:** Security / operations
- **Location:** `app/core/rate_limit.py:21-24` (`get_remote_address`), `app/services/audit.py:113-127` (`get_client_info`)
- **Problem:** The app is documented/imaged to run behind a reverse proxy (`README.md`, `X-Forwarded-*` handling in `app/api/routes/settings.py:265-269`), but the limiter key and audit IP use `request.client.host` — the proxy's address.
- **Impact:** Behind a proxy, the 20/min login and 30/min auto-login budgets become *global* budgets shared by all users (a few members can lock everyone out or, conversely, a brute forcer gets 20 tries per minute per proxy), and audit IPs are useless.
- **Recommendation:** Add `ProxyHeadersMiddleware` (Starlette) with a trusted proxy configuration, or make the key/audit functions honor `X-Forwarded-For` when a known proxy is present.

### M7. Duplicate-match check is skipped on update
- **Category:** Correctness
- **Location:** `app/services/match.py:148-193` (`update_match` never calls `check_duplicate`; create path `:95-107` does)
- **Problem:** Editing a match (date and/or scores) to collide with an existing identical match is allowed silently, while the same data through `POST /matches/` returns 409.
- **Impact:** Inconsistent duplicate protection; history can end up with exact duplicate rows.
- **Recommendation:** Run the same `check_duplicate(..., exclude_match_id=match_id)` in `update_match` and return 409.

---

## 🟡 Low severity

### L1. Front-end renders database values through `innerHTML` without escaping
- **Location:** `app/templates/dashboard.html:742,830`; `app/templates/admin.html:474,527,651`
- **Problem:** Player names and match data are concatenated into HTML strings (`tbody.innerHTML += '<tr>…'+p.name+'…'`). A player name containing markup (e.g. `<img onerror=…>`) would be interpreted as HTML.
- **Impact:** Stored-XSS window. Mitigated only by the fact that player creation is ADMIN-only and names are short. Still, defense-in-depth: build rows with `textContent`/`createElement` instead of string interpolation.

### L2. Health check does not validate the database
- **Location:** `app/api/routes/health.py:10-16`; `Dockerfile:35-36` (HEALTHCHECK hits `/health`)
- **Problem:** `/health` returns `healthy` even if the database files are corrupt, locked, or unreachable — exactly the runtime failure an orchestrator should restart.
- **Impact:** Stale/unreachable service keeps receiving traffic and is never restarted.
- **Recommendation:** Run a cheap `SELECT 1` against the engine in the health endpoint.

### L3. `docker-compose.yml` bind-mounts `./config.yaml`, which Docker auto-creates as a directory if missing
- **Location:** `docker-compose.yml:21`; `app/core/config.py:36-39`
- **Problem:** When `config.yaml` does not exist on the host, the mount is created as an empty directory; `load_yaml_config()` then `open()`s a directory and the import-time `settings = get_settings()` (`app/core/config.py:211`) crashes with `IsADirectoryError`, so the container never starts.
- **Impact:** First-time `docker compose up` fails with a confusing error unless the operator copied the example file first.
- **Recommendation:** Mount a named volume initialized with the example, or start the container from a directory that guarantees the file; at minimum guard `load_yaml_config` against directories and log a clear message.

### L4. Default export period of the PDF report differs from the on-screen ranking
- **Location:** `app/api/routes/rankings.py:41-45` (current month) vs `app/api/routes/reports.py:37-41` (previous month)
- **Problem:** The dashboard ranking defaults to the current month, while the PDF export silently defaults to the *previous* completed month (`first_of_current - 1 day`).
- **Impact:** Confusing UX — the exported PDF does not match the ranking the user just looked at.
- **Recommendation:** Align both defaults (or make the PDF default explicit in the UI).

### L5. Global mutable settings singleton is mutated by tests and by config import
- **Location:** `tests/conftest.py:17-25` (`settings.csrf_enabled = False`, `limiter.enabled = False`); `app/core/config.py:200-207` (YAML values pushed into `os.environ` at import) and `:211` (module-level singleton)
- **Problem:** Import-time side effects make test isolation fragile; toggling global settings leaks across tests unless carefully reset (there are dedicated `csrf_enabled`/`rate_limiting_enabled` fixtures that do re-enable, but the default is "security disabled in tests").
- **Impact:** A test in another module that accidentally relies on CSRF being on would silently pass/fail based on import order. Config values persist in `os.environ` for the whole process.
- **Recommendation:** Use dependency injection / a settings fixture that saves and restores state per test; avoid mutating process-global env in `get_settings`.

### L6. `log_dir`/`LOG_DIR` is documented and configured but never used
- **Location:** `app/core/config.py:177`; `README.md:286`, `docker-compose.yml:28`, `.env.example:59`, `Dockerfile:29`
- **Problem:** No logging/handlers write into `log_dir`; uvicorn logs go to stdout, and nothing in the app initializes a file handler.
- **Impact:** Misleading configuration surface; operators may expect logs in `/logs` and find an empty volume.
- **Recommendation:** Either wire a rotating `FileHandler` at startup or remove the knob and document stdout logging.

### L7. `log_event()` commits its own transaction
- **Location:** `app/services/audit.py:59-60`
- **Problem:** Every audit call commits; callers that already committed (e.g. `app/api/routes/players.py:25-33` after `create_player`) end up with two transaction boundaries per logical operation.
- **Impact:** Makes atomic multi-write operations (e.g. entity + audit together) hard to guarantee and can mask rollback intentions.
- **Recommendation:** Let callers own the transaction; have `log_event` only `add()` (flush if IDs are needed) and commit at the caller's boundary, consistent with the repository pattern used elsewhere (Fix #7 convention).

---

## Summary / recommended action order

> **Accepted tradeoffs (owner, 2026-09-04):** H1 (QR password-in-URL) and H2 (default secrets) are intentionally accepted — the QR / SYSTEM account are only used for club member logins to create matches. Not on the fix list.

1. **M1 (your hint):** move the test suite to real in-memory SQLite and stop the app lifespan from touching `data/` during tests — the `test.db`/`test_legal.db`/`test_statistics.db`/`data/database.db` clutter disappears.
2. **M2–M6:** fail-fast migrations, CWD-independent paths, guard user deletion, fix update-time score validation, honor proxy headers.
3. **M7 + L1–L7:** duplicate checks on update, HTML-escape rendering, DB-aware health, compose/config robustness, and cleanup of dead config/transaction patterns.

---

## M1 implementation log (2026-09-04)

**M1 — FIXED.** The test suite no longer writes database files into the working tree.

Changes:
- `tests/conftest.py`: sets `DATABASE_URL`/`DATA_DIR`/`UPLOAD_DIR`/`LOG_DIR` to throwaway values **before** importing app modules; switched the shared engine to true in-memory SQLite (`sqlite://` + `StaticPool`); stubs `init_db()`/`provision_system_user()` in the `client` fixture so the TestClient lifespan never touches the production engine.
- `tests/test_legal.py`, `tests/test_statistics.py`: removed duplicated engines and `db_session`/`client` fixtures (now inherited from conftest).
- `tests/test_config.py`: `test_storage_section_mapping` made hermetic (delenv the shared storage keys, which `_yaml_to_env_defaults` skips when already set).
- Deleted the stale `test.db`, `test_legal.db`, `test_statistics.db` artifacts from the working tree. The real `data/database.db` was left untouched.

Verification:
- Full suite: **798 passed** (~40-41 s vs. ~265 s before — an extra ~6x speedup).
- No `*.db` files created at the repo root after a run; `data/database.db` mtime unchanged.
- `ruff check tests/` clean.

---

## H2 implementation log (2026-09-04)

**H2 — FIXED.** Default/weak secrets are enforced (fail-fast) and the SYSTEM bootstrap password is forced to change on first login. The two secrets were deliberately split because they have different security lives:

- **`JWT_SECRET`** is the token-signing key; with the default, anyone can forge a token with `role=SYSTEM` without any credential. It has no runtime self-healing — the operator *must* set a unique one.
- **`SYSTEM_USER_PASSWORD`** is only a **one-shot bootstrap**: `provision_system_user()` hashes it once on a fresh DB and never re-applies it; the SYSTEM user can already change it in-app via `/password/change`. The fix therefore enforces a strong *bootstrap* and then makes it single-use.

Changes:

- **Fail-fast startup** (`app/core/config.py`): `get_settings()` now calls `_validate_security_defaults()`, which raises `RuntimeError` when `APP_ENV != "development"` and `JWT_SECRET`/`SYSTEM_USER_PASSWORD` are empty or any documented placeholder (`change_me`, `CHANGE_ME_GENERATE_RANDOM`, `CHANGE_ME_HERE`, …). Development is exempt so local dev/tests are unchanged.
- **Forced password change** (`must_change_password` flag):
  - `app/models/user.py` + new Alembic migration `d0e1f2a3b4c5` (`users.must_change_password`, SQLite `server_default 0`).
  - Set `True` on SYSTEM provisioning (`app/auth/service.py`) and on admin password resets (`app/api/routes/password.py`, `app/api/routes/users.py`); cleared on successful self-service `/password/change`.
  - Surfaced in `POST /auth/login` and `GET /auth/me`; login JS redirects to `/ui/change-password`; the change-password page shows a "temporary setup password" warning and returns to the dashboard afterwards.
  - Enforced server-side: `ensure_password_changed` dependency (`app/auth/dependencies.py`) applied to the auth-gated API routers in `app/main.py`; `/ui/dashboard` and `/ui/admin` redirect to the change-password page until the password is set. Auth/password/health and the change-password page are exempt by design.
- `tests/test_config.py`: `TestSecurityDefaultEnforcement` (unit + `get_settings()` integration).
- `tests/test_auth.py`: `TestMustChangePassword` (provision sets flag, login/me expose it, endpoint blocked with 403, dashboard redirects, page reachable, change unblocks).
- `tests/test_password.py`: admin reset forces the flag.
- `.env.example` / `config.yaml.example`: comments updated to document the fail-fast bootstrap; `tests/private_livesystem_test/docker-compose.yml` bootstrap swapped off the placeholder so the manual harness still starts.

Verification: full suite **814 passed** (~41 s); `ruff check` clean on all changed files; fresh-DB `alembic upgrade head` ends at `d0e1f2a3b4c5` with `users.must_change_password` present; `data/database.db` untouched.

> Note for deployments using `portainer_compose.yaml` / the documented example values: the app will now **refuse to start** in production until `JWT_SECRET` (and `SYSTEM_USER_PASSWORD` for fresh installs) are replaced with real randomized values (`openssl rand -hex 32`) — this is the intended fail-fast.
