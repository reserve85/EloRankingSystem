# Code Review Findings — Elo Ranking System

# #2 — DB Settings Ignored + k_factor Not Stored Per Match
**Severity:** 🔴 CRITICAL | **Category:** Bug | **File:** `app/services/match.py`, `app/models/match.py`, `app/templates/admin.html`

**Problem**
1. `k_factor` is not stored per match. `_recalculate_elo_timeline` uses the global `settings.k_factor`, so changing K in env silently recalculates all affected history with the new value. Not deterministic.
2. The GUI inputs for `k_factor`, `default_elo`, `inactivity_months` were already removed from `admin.html`. Dead JS functions and API endpoint fields still reference them.

**How to fix**
Store `k_factor` per match (captured from `settings` at creation time). Use per-match k_factor in recalculation for deterministic results. Remove dead JS/API code. `default_elo` and `inactivity_months` remain env/config-only. **Status: see `implementation_plan_fix2.md` for detailed plan.**

---

# #3 — No CSRF Protection
**Severity:** 🔴 CRITICAL | **Category:** Security | **File:** All state-changing routes

**Problem**
The README claims "CSRF protection is implemented for state-changing operations" but there is zero CSRF protection in the codebase. JWT tokens are stored in HttpOnly cookies with `SameSite=lax`, which only blocks cross-site top-level navigations. Same-site injected forms or XHR requests still send the cookie.

**How to fix**
Implement double-submit cookie CSRF pattern: generate a `csrf_token` cookie (non-HttpOnly so JS can read it), require the same value in an `X-CSRF-Token` header on all POST/PUT/PATCH/DELETE requests, validate via constant-time `hmac.compare_digest`. Register as FastAPI middleware. Add `apiFetch()` helper in `base.html` that reads the cookie and injects the header. Switch all 13 mutating `fetch()` calls in templates to `apiFetch()`. Exempt `/auth/login` and `/auth/auto-login`.

---

# #4 — No Rate Limiting on Authentication Endpoints
**Severity:** 🟠 HIGH | **Category:** Security | **File:** `app/api/routes/auth.py`, `app/api/routes/password.py`

**Problem**
Login, auto-login, password change, and password reset have zero rate limiting or brute-force protection. An attacker can make unlimited login attempts.

**How to fix**
Add `slowapi` library (`requirements.txt`). Decorate `login` with `@limiter.limit("20/minute")`, `auto_login` with `@limiter.limit("30/minute")`, and both password endpoints with `@limiter.limit("5/minute")`. Register `SlowAPIMiddleware` and the 429 exception handler in `main.py`.

---

# #5 — `lstrip("v")` Uses Character Set Stripping, Not Prefix Removal
**Severity:** 🟠 HIGH | **Category:** Bug | **File:** `app/core/version.py:23`

**Problem**
`str.lstrip("v")` strips *any character in the argument set*, not a prefix substring. If the version string were unexpected (e.g. `"version"`), it would become `"ersion"`. While semver strings are unlikely to hit this, the logic is incorrect.

**How to fix**
Replace `raw_version.lstrip("v")` with a true prefix-removal loop:
```python
version = raw_version
while version.startswith("v"):
    version = version[1:]
```
Output for real semver inputs (`v1.2.3`, `1.2.3`) is byte-identical to today.

---

# #6 — `delete_match` Creates Audit Log Before Deletion Succeeds
**Severity:** 🟠 HIGH | **Category:** Bug | **File:** `app/services/match.py:208-222`

**Problem**
The `MATCH_DELETED` audit log is committed to the database *before* the actual deletion and recalculation happen. If the deletion or recalculation fails, the audit log falsely records a deletion that didn't happen.

**How to fix**
Reorder `delete_match`: `get_match` → capture `affected_players` → `match_repo.delete(match)` → `_recalculate_elo_timeline(...)` → add `MATCH_DELETED` audit → **one** `self.db.commit()`. The audit is recorded only after the deletion and recalculation succeed.

---

# #7 — Double `commit()` Pattern in Repositories + Services
**Severity:** 🟠 HIGH | **Category:** Architecture | **File:** `app/repositories/match.py:51,57,64`, `app/repositories/player.py:51,57,64`, `app/services/match.py:132-143,183-190`

**Problem**
Repositories call `db.commit()` in every mutation method. The services that call them also perform additional operations and call `db.commit()` again. This creates partial-commit risk: if the process fails between commits, the database is in an inconsistent state (e.g. a match is committed but the recalculation is not).

**How to fix**
Remove `commit()` from repository methods. Replace with `flush()` + `refresh()` so that auto-generated IDs are available. Let the service layer manage transaction boundaries — commit once at the end of the logical operation.

---

# #8 — `check_same_thread: False` Applied Unconditionally
**Severity:** 🟡 MEDIUM | **Category:** Concurrency | **File:** `app/core/database.py:23`

**Problem**
The `check_same_thread: False` connect arg is SQLite-specific but is always applied, even when configured to use PostgreSQL/MySQL. For other databases, this flag has no meaning and connect_args should be empty.

**How to fix**
Apply conditionally:
```python
connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
```
Also guard the `PRAGMA` event listener with `if "sqlite" in settings.database_url`.

---

# #9 — Audit `_redact_secrets` Only Scans Top-Level Keys
**Severity:** 🟡 MEDIUM | **Category:** Security | **File:** `app/services/audit.py:76-96`

**Problem**
The redaction function only checks top-level dictionary keys for sensitive names. Nested dictionaries (e.g. `{"user": {"password": "..."}}`) will not be redacted.

**How to fix**
Replace `_redact_secrets` with a recursive version that walks nested dicts and lists via a helper `_redact_node(node, sensitive_keys)`. Top-level behavior is preserved (same `[REDACTED]` replacement), extended to nested structures.

---

# #10 — Logout Logs `user_id=0` for Missing JWT Payload
**Severity:** 🟡 MEDIUM | **Category:** Bug | **File:** `app/api/routes/auth.py:75`

**Problem**
`user_id=int(payload.get("sub", 0))` logs `user_id=0` instead of `None` when the JWT payload contains no `"sub"` key. User ID 0 doesn't exist and could be confused with a valid system user in audit logs.

**How to fix**
```python
sub = payload.get("sub")
user_id = int(sub) if sub is not None else None
```
`log_event` already accepts `Optional[int]` for `user_id`.

---

# #11 — `_recalculate_elo_timeline` Over-Expands Match Timeline
**Severity:** 🟡 MEDIUM | **Category:** Performance | **File:** `app/services/match.py:247-254`

**Problem**
Every call to `_recalculate_elo_timeline` loads **all matches ever played** into memory via `match_repo.get_all()`, then linearly scans for the index of the earliest affected match and slices. For large databases, this is extremely expensive and unnecessary.

**How to fix**
Replace with a bounded repository method `get_from_match(earliest_match)` that returns only matches where `(date, created_at, id) >= (earliest.date, earliest.created_at, earliest.id)`, ordered by `date ASC, created_at ASC, id ASC`. This is the identical set and order as the current `get_all()[start_idx:]` — same lexicographic boundary — but uses a filtered query instead of loading the full table. Byte-identical recalculation results. The redundant `matches_to_recalc.sort(...)` at line 271 (a no-op since `get_all()` already returns sorted) should also be removed.

---

# #12 — `_recalculate_elo_timeline` Resets All Players to `start_elo` (Wrong for Pre-Window History)
**Severity:** 🟡 MEDIUM | **Category:** Bug | **File:** `app/services/match.py:258-269`

**Problem**
Every player who appears in any match from the earliest affected match onward is reset to `start_elo` — even players whose match history extends *before* the window. This throws away their pre-window rating and corrupts all subsequent Elo snapshots in the window.

Concrete example (K=32): Eve beats Frank on Jan 5 → Frank = 1184. Alice beats Charlie on Jun 1. Charlie beats Frank on Jun 2. Delete the Jun 1 match. Recalculation window starts at Jun 2 (earliest affected match = Jun 2 for Charlie). Current code resets Frank to 1200 before the window — wrong. Frank's entering rating at Jun 2 should be 1184 (from his Jan 5 match). The error cascades to all later Charlie/Frank matches and never cancels (Elo expected-score function is strictly monotone).

The full window *scope* is correct and required — Elo is path-dependent and the ripple reaches the entire post-edit schedule. The bug is only in the *initialization* of players entering the window.

**How to fix**
*Boundary initialization*: for each in-window player, look up their **last match strictly before** `earliest_match` (using new `get_last_match_before(match, player_id)` repository method). If found, enter the window at that match's `elo_after_a`/`elo_after_b` for the player. If not found, fall back to `float(player.start_elo)`. This is mathematically equivalent to replaying all history from the beginning.

Additionally, fix a related edge case: if an affected player's **only match** is deleted and other players still have matches in the window, that player is left with stale `current_elo`/`last_match_date`/`active` status. After the recalculation loop completes, detect players with zero remaining matches in the entire history and reset them to `start_elo`, `last_match_date=None`, `active=False`.

Note: affected players (the ones directly involved in the changed match) always enter at `start_elo` — their entire history is inside the window by construction. For non-affected in-window players (who happened to play against an affected player), boundary init produces correct ratings that `start_elo` cannot.

---

# #13 — SQLite + WAL + Multiple Workers Write Contention
**Severity:** 🟡 MEDIUM | **Category:** Architecture | **File:** `app/core/database.py`

**Problem**
The application uses SQLite with WAL mode and `check_same_thread: False`. If run with multiple Uvicorn workers (`--workers > 1`), SQLite can experience write lock contention. The config shows single-instance Docker deployment which works fine, but this is fragile if anyone ever scales workers.

**How to fix**
Add a note to the README deployment section and `docker-compose.yml` comments: the application must run with a single worker (`--workers 1`) when using SQLite. For multi-worker deployments, migrate the database to PostgreSQL first.

---

# #14 — Dead Code: `get_current_user_or_redirect`
**Severity:** 🔵 LOW | **Category:** Code Quality | **File:** `app/auth/dependencies.py:145-170`

**Problem**
The `get_current_user_or_redirect` function is defined but never imported or referenced anywhere in the codebase. It also imports `RedirectResponse` which is used elsewhere but the import is for this specific function. Dead code increases maintenance surface and can cause confusion about which auth dependency to use.

**How to fix**
Delete the function (lines 145-170) and the now-unused `from fastapi.responses import RedirectResponse` import from `dependencies.py`. (Note: `RedirectResponse` is imported in `auth.py` route independently — verify that import is not the one being removed.)

---

# #15 — N+1 Queries in `RankingService.get_all_players_all_time_high_elo`
**Severity:** 🔵 LOW | **Category:** Performance | **File:** `app/services/ranking.py:457-513`

**Problem**
The review flagged this as an N+1 query issue. However, after tracing every line (445-513), the method makes exactly **2 queries** (all players, all matches) and then performs the ATH + inactivity computation **purely in memory** with zero additional database calls. The flagged loop is in-memory only.

**Verdict: FALSE POSITIVE — no fix needed.**

Note: a *different* method — `generate_ranking` — does have a real per-player query pattern (`_get_elo_at_date` ×2 + `_get_period_statistics` per player). That would be a separate future performance pass, not a bug.