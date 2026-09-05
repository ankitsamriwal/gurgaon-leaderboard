# Backup & restore drill

Part of Phase 9 (`docs/07-implementation-plan.md`): "Backups configured
and a restore drill actually performed once." This documents the drill
actually run against this build, the commands used, and what was verified
— not a hypothetical procedure.

## What was verified (2026-09-05)

1. Seeded a marker row (`users` table, a fixed UUID) into the working
   dev database alongside pre-existing data.
2. Took a full logical backup with `pg_dump` in custom format:
   ```bash
   pg_dump -h <host> -U postgres -Fc gurgaon_leaderboard -f gurgaon_leaderboard.dump
   ```
3. Created a **separate, fresh database** (never touched the original)
   and restored into it:
   ```bash
   createdb -h <host> -U postgres gurgaon_leaderboard_restore_drill
   pg_restore -h <host> -U postgres -d gurgaon_leaderboard_restore_drill gurgaon_leaderboard.dump
   ```
4. Confirmed against the restored database:
   - All 14 tables present.
   - `SELECT count(*) FROM users` matched the source exactly.
   - The marker row came back byte-for-byte (id, display_name, email).
   - `\d projects` showed the primary key, the partial unique index on
     `rera_number`, the `status` check constraint, and both foreign keys
     — schema fidelity, not just row data.
5. Dropped the drill database and deleted the dump file — this was a
   drill, not a retained backup.

## What this doesn't cover

This validates that `pg_dump`/`pg_restore` round-trips this schema
correctly — the mechanism a real backup system would rely on. It does
**not** stand in for:

- A real, scheduled backup system (e.g. managed Postgres automated
  backups, WAL archiving for point-in-time recovery) — that's an infra
  choice for whoever hosts this (`docs/00`'s "Any container platform").
- Restoring under production load or verifying an actual RPO/RTO target.
- A drill against a database anywhere near production size.

## Running it again

```bash
# 1. Back up
pg_dump -h $DB_HOST -U postgres -Fc gurgaon_leaderboard -f backup.dump

# 2. Restore into a scratch database
createdb -h $DB_HOST -U postgres gurgaon_leaderboard_drill
pg_restore -h $DB_HOST -U postgres -d gurgaon_leaderboard_drill backup.dump

# 3. Verify, then tear down
psql -h $DB_HOST -U postgres -d gurgaon_leaderboard_drill -c "SELECT count(*) FROM users;"
dropdb -h $DB_HOST -U postgres gurgaon_leaderboard_drill
```

Whatever hosting platform is chosen should schedule step 1 automatically
(nightly at minimum, matching the reconciliation job's cadence) and this
drill should be re-run periodically against that real backup, not just
once at build time.
