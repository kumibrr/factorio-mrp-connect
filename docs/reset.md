# Backup and explicit demo reset

`./scripts/seed-demo` is nonmutating after initial seed. It validates the manifest
and keeps operator changes; `--verify-baseline` detects deviations. Restoring
baseline requires an explicit reset. A reset discards this project's entire
`factorio_demo` database and integration cache, including walkthrough changes.
It never accesses a Factorio save or another project's Docker resources.

Use the `demo` shell wrapper from [local setup](local-demo.md). Store backups
outside the checkout in a protected directory. Stop the bridge and Odoo to
prevent business changes during backup, while PostgreSQL stays running:

```sh
backup="$HOME/.local/share/factorio-connect/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -m 700 "$backup"
umask 077
demo --profile bridge stop bridge odoo
demo exec -T db pg_dump -U odoo -Fc factorio_demo > "$backup/database.dump"
cp -a "$HOME/.local/share/factorio-connect/demo" "$backup/operator-state"
demo run --rm -T --no-deps --entrypoint tar odoo -C /var/lib/odoo -czf - . > "$backup/odoo-data.tar.gz"
demo --profile bridge up -d --wait odoo bridge
```

Also save a separate copy of your dedicated Factorio save/mod settings using
the game UI or file manager. Backups contain credentials and customer/demo
business data; keep the directory private. For a custom `FACTORIO_STATE_DIR`,
substitute that directory in the `cp` command. SQLite revision history lives in
the separate `bridge-data` volume; the commands above back up the Odoo database,
filestore and operator state. Preserve the SQLite cache's
revision history with a matched backup whenever possible. An ordinary bridge
restart with its durable cache recovers automatically and performs a fresh
source read.

If the cache is deleted/recreated or restored behind the revision in the game
save, use the Factory panel's **Local re-pair…** action and **Confirm local
re-pair** after restarting the bridge. This is required even when the restored
Odoo database UUID is unchanged. The save rejects lower revisions; an equal
revision cannot replace its business data or source timestamp. Confirmed local
re-pair clears the saved revision and binding, then accepts a fresh complete
snapshot. It clears only mod-owned display entities and leaves Odoo untouched.

Inspect ownership before reset:

```sh
docker volume ls --filter label=com.docker.compose.project=factorio-connect
docker ps -a --filter label=com.docker.compose.project=factorio-connect
./scripts/reset-demo --confirm factorio-connect-demo
./scripts/bootstrap-demo
./scripts/seed-demo --verify-baseline
```

Every container, volume and network selected by the Compose project label must
also have `io.factorio-connect.owner=factorio-connect-demo`. Reset inspects every
target before deleting any and refuses a missing confirmation, wrong project
or unlabelled target. It removes only enumerated labelled targets, never uses a
Docker prune and never discovers game directories. Do not relabel an unrelated
resource just to pass this gate. Expected output starts `Reset owned demo
resources for factorio-connect; game saves untouched`.

Reset preserves operator passwords, removes the previous database/API binding,
and rotates webhook/pairing tokens. Bootstrap creates a new database UUID and
fresh bot key. Privately set the new pairing token in the dedicated save and
use the Factory panel's confirmed local re-pair action to clear the old tracked
binding/display. This removes only mod-owned display entities; Odoo is untouched.
An unowned colliding surface still requires manual resolution.

To restore a backup, first stop Odoo/bridge and retain a separate backup of the
current data. Restore `database.dump` into a clean owned project database using
PostgreSQL `pg_restore -U odoo -d factorio_demo --clean --if-exists` through the
`demo exec -T db` wrapper. Restore `odoo-data.tar.gz` into the owned `odoo-data`
volume via a one-shot Odoo container with `--entrypoint tar`; restore the matching
operator-state directory, then bootstrap. Restoring the matched database UUID,
filestore and credential state preserves source identity. It does not guarantee
that an older or recreated bridge cache advances beyond the game's saved
revision: follow the confirmed local re-pair procedure above in that case,
even with the same UUID. If the saved bot key
expired, explicitly rotate it. Never restore into an unrelated database/volume.
