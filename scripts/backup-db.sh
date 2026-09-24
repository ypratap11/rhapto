#!/usr/bin/env bash
# Nightly-ish pg_dump of the Rhapto database, with retention, plus a restore procedure.
#
# WHAT THIS DOES
#   Dumps the `db` compose service's database (default: `rhapto`) with `pg_dump -Fc` (Postgres's
#   custom format: compressed, and restorable with pg_restore rather than needing psql to replay
#   plain SQL) into $BACKUP_DIR, named backup-<db>-<UTC timestamp>.dump. It then deletes dumps in
#   that directory older than $RETENTION_DAYS.
#
# RETENTION
#   Default 14 days (RETENTION_DAYS below). This script does not schedule itself -- wire it into
#   cron, systemd timers, or the host's existing job scheduler, e.g.:
#     0 3 * * * BACKUP_DIR=/var/backups/rhapto /path/to/scripts/backup-db.sh >> /var/log/rhapto-backup.log 2>&1
#   It also does not run against production on its own: it must be invoked, from the host that
#   can reach the `db` service (typically via `docker compose exec`), by someone who has the
#   credentials. Nothing here embeds a password; PGPASSWORD (or a .pgpass file) is the caller's.
#
# RESTORE (tested into a scratch database, never over a live one without a fresh dump first)
#   1. Create a throwaway database to restore into, so a bad dump or a mistake never touches the
#      real one:
#       createdb -h "$PGHOST" -U "$PGUSER" rhapto_restore_test
#   2. Restore the dump into it:
#       pg_restore -h "$PGHOST" -U "$PGUSER" -d rhapto_restore_test --no-owner --no-privileges \
#         /path/to/backup-rhapto-<timestamp>.dump
#   3. Verify (row counts, spot-check a few tables) before ever pointing production at a restored
#      dump. To actually restore onto the live database (only after the above passed and the app
#      is stopped): drop/recreate the target database, then pg_restore into it the same way.
#
# Requires: pg_dump/pg_restore matching (or newer than) the server's Postgres major version,
# and either PGPASSWORD/.pgpass or a trust/peer setup that lets pg_dump connect non-interactively.
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-rhapto}"
PGDATABASE="${PGDATABASE:-rhapto}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="$BACKUP_DIR/backup-${PGDATABASE}-${timestamp}.dump"

echo "backing up ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE} -> $dest"
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$dest"
echo "wrote $(du -h "$dest" | cut -f1) to $dest"

echo "pruning dumps in $BACKUP_DIR older than ${RETENTION_DAYS}d"
find "$BACKUP_DIR" -maxdepth 1 -name 'backup-*.dump' -mtime "+${RETENTION_DAYS}" -print -delete
