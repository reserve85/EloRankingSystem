# Implementation Plan — Fix #2: Store k_factor Per Match + Clean Up Dead Settings Code

## Overview

Two changes:
1. **Store `k_factor` per match** for deterministic historical Elo recalculation.
   Currently `_recalculate_elo_timeline` uses the global `settings.k_factor`,
   so changing K in the env silently recalculates all affected history with the
   new value. Storing K per match makes recalculation deterministic.
2. **Remove dead settings code** — GUI inputs for `k_factor`, `default_elo`,
   `inactivity_months` were already removed from `admin.html`. Dead JS and
   API endpoint fields are cleaned up.

**k_factor semantics**: when a match is created, the current `settings.k_factor`
is captured and stored in the match record. For recalculation, each match uses
its own stored k_factor. `default_elo` and `inactivity_months` continue to come
from `settings` singleton (env/config).

---

## Files

| File | Action | Purpose |
|------|--------|---------|
| `app/models/match.py` | MODIFY | Add `k_factor` column |
| `app/migrations/versions/` | NEW | Alembic migration |
| `app/services/match.py` | MODIFY | Store k_factor on create, use per-match k_factor in recalc |
| `app/templates/admin.html` | MODIFY | Remove dead JS |
| `app/api/routes/settings.py` | MODIFY | Remove dead schemas and PUT route |
| `tests/test_templates.py` | MODIFY | Update for simplified response |
| `tests/test_audit.py` | MODIFY | Update settings audit test |
| `tests/test_settings_effective.py` | **NEW** | k_factor determinism tests |
| `README.md` | MODIFY | Document behavior |

---

## Model Change — `app/models/match.py`

Add after `elo_change_b` (line 64):
```python
k_factor: Mapped[float] = mapped_column(
    Float, nullable=False, default=32.0, server_default="32.0"
)
```
`server_default="32.0"` backfills existing rows during migration.

---

## Migration

Alembic migration adding `k_factor` to `matches`:
```python
op.add_column("matches", sa.Column("k_factor", sa.Float(),
    nullable=False, server_default="32.0"))
```

---

## Service Changes — `app/services/match.py`

**`create_match`**: add `k_factor=float(settings.k_factor)` to `Match(...)`.

**`_recalculate_elo_timeline`**: change `calculate_match_elo(...)` to pass
`k_factor=m.k_factor` (per-match) instead of using the global default.
Remove `from app.core.config import settings` import.

---

## Dead Code Cleanup

**`admin.html`**: remove `loadClubSettings()` (lines 873-880),
`saveClubSettings()` (lines 881-890), and the `// --- Club Settings ---`
comment.

**`settings.py` route**: remove `SettingsUpdate` schema,
remove `update_settings` PUT route, simplify `SettingsResponse`
(keep only `id`, `club_name`, `club_logo_path`, `club_logo_dark_path`).
Keep `GET /settings/` and logo/QR routes.

---

## Testing — `tests/test_settings_effective.py` (NEW)

- `test_new_match_stores_current_k_factor` — K=48 → match.k_factor==48.0
- `test_recalc_uses_match_k_factor_not_global` — create with K=32, change
  to K=16, recalc → Elo stays at K=32 values
- `test_player_create_uses_config_default_elo` — monkeypatch default_elo
- `test_ranking_uses_config_inactivity_months` — monkeypatch inactivity

Existing tests: `TestSettingsAPI` and `TestSettingsAudit` need updates.

---

## Implementation Order

1. Add `k_factor` to `app/models/match.py`
2. Create Alembic migration
3. Modify `app/services/match.py` — store + use per-match k_factor
4. Remove dead JS from `app/templates/admin.html`
5. Simplify `app/api/routes/settings.py`
6. Update `tests/test_templates.py` and `tests/test_audit.py`
7. Create `tests/test_settings_effective.py`
8. Lint + pytest
9. Update `README.md`