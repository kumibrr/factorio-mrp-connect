# Troubleshooting

Use `./scripts/bootstrap-demo --check`, `./scripts/seed-demo --verify`, the
private-gateway `/healthz` endpoint and the `demo` wrapper in
[local setup](local-demo.md). Collect redacted service logs; never share a real
Compose config, container environment, secret files or save containing the token.

| Symptom | Check and remedy |
| --- | --- |
| Remote/rootless daemon rejected | Use the local rootful Linux Docker daemon. Rootless networking cannot satisfy the approved host/private-gateway topology here; this bootstrap does not change groups, privileges or architecture. |
| Foreign secret state directory | Bootstrap refuses nonempty unowned directories and mismatched project markers. Choose a new dedicated outside-git directory; do not overwrite unrelated operator state. |
| Port already occupied | Use `ss -lntup` to identify the owner. Choose unused Odoo/bridge/game ports before bootstrap and update both game setting and launch flag. Stop only your owned project. |
| Subnet overlaps another network | Inspect `docker network ls`/`inspect` without secret environment. Choose a free private subnet and its gateway consistently. Do not delete unrelated networks. |
| Odoo config cannot be read | Generated nonsecret config is mode0644; uid100/gid101 reads it. Keep outside-git credentials mode0600 and containing directory mode0700. Do not mount a root-only config into Odoo. |
| Seed shell attempts local PostgreSQL socket | Use the provided seed CLI; it invokes official `/entrypoint.sh` so DB arguments are supplied. Direct `docker exec ... odoo shell` bypasses that startup logic. |
| Odoo/bridge unsupported version | Use digest pins in `deploy/versions.env`, hash-locked Python 3.12 dependencies and Factorio 2.0.77. Do not replace them with moving latest tags. |
| No game connection | Launch with `--enable-lua-udp 34199`; check `fc-bridge-port=34200`, enabled mod, matching private pairing token and unpaused single-player game. Rootful bridge must share host localhost. |
| API HTTP401 / expired bot key | Check `metadata.json` expiry privately. Run `./scripts/bootstrap-demo --rotate-api-key`; rotation is explicit and limited to managed bot keys. |
| API HTTP403 / effective write groups | Keep `factorio.bridge` scoped and read-only. Remove unintended additive grants through admin security review; never add stock/manufacturing writes to bypass export checks. |
| Source UUID differs after restore | Restore matching DB/filestore/operator-state together, or explicitly reset and locally re-pair. A mismatched identity fails closed. |
| Bridge cache recreated/rolled back; saved view never advances | Compare `latest_revision` with the game's saved revision. Lower revisions are rejected and an equal revision cannot update the data/timestamp. Use Factory **Local re-pair…**, then **Confirm local re-pair**, even when the Odoo UUID is unchanged. Keep durable cache revision history for automatic ordinary restarts; see [recovery](reset.md). |
| Missing webhook | Inspect the 14 active rules and their redacted targets as admin. Native postcommit webhooks attempt once; the 60-second reconciliation recovers missed updates. |
| Pause/save/buffer loss | UDP receive buffers may overflow during pauses. Resume/reload starts resynchronizing and requests the latest complete snapshot. Healthy verification may take twenty seconds. |
| Stale view / source outage | `source_ok=false` or >90s source age means retained data. Restart Odoo and wait for a fresh source read; replaying cache never renews freshness. |
| Disconnected transport | Fifteen seconds without current heartbeats invalidates the session. Restart the bridge and check local ports; retain the last validated view until recovery. |
| Snapshot too large/invalid | Inspect secret-free bridge error category; reduce company/warehouse scope or retained history. Limits are 256KiB/512 chunks and 1024 bytes per envelope. Last valid state remains visible. |
| Reserved `odoo-factory` surface unavailable | The mod refuses an unowned surface or obstructing entity. Preserve it and choose another save or manually move/rename the unrelated content. Never ask the mod to adopt it. |
| Nonce history limit reached | At 4096 confirmed nonces, restart the bridge. Connection history resets; database UUID and source authority persist. |
| Optional markdown warning | The official pinned Odoo image lacks optional markdown2. It affects markdown rendering, not seed/export/bridge health. Keep the warning in diagnostics. |

A healthy HTTP listener does not establish an accepted game snapshot. Inspect
`latest_revision`, `applied_revision`, source time and the game's synchronization
indicator together. GUI/live-engine acceptance has not been executed on the
current development host; the installed headless engine cannot substitute for
the separately licensed single-player client's inbound UDP dispatch.
