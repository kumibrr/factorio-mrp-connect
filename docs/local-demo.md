# Local Linux demo

Run commands from the checkout root. The supported desktop path is Linux x86_64,
local **rootful Docker Engine**, Compose >=2.24.0, host Python >=3.10, and a separately
owned single-player Factorio **2.0.77** client with base game only. Compose 5.5.1
also satisfies this minimum. Optional `env_file.required=false` requires
[Compose 2.24.0 or newer](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/). Docker Desktop, a remote Docker context and rootless Docker
cannot satisfy the approved private-gateway/localhost topology here. Bootstrap rejects
them rather than changing system privileges. No Factorio server or RCON is used.

[deploy/versions.env](../deploy/versions.env) fixes Odoo Community
20.0-20260926 (Python 3.12.3), PostgreSQL 17.11, and the bridge's Python
3.12.12 base by SHA-256 image digest. Python dependencies are exact hash-locked.
The bridge wheel is installed in its container and runs as uid 10001. Odoo runs
as uid 100/gid 101. The nonsecret config is readable by that process; generated
credentials are mode 0600 in a mode 0700 directory outside the checkout.

```sh
docker context show
docker compose version
./scripts/bootstrap-demo --check
./scripts/bootstrap-demo
./scripts/seed-demo --verify-baseline
./scripts/package-mod
```

`--check` prints `Preflight: local Linux daemon, Compose >=2.24.0, ownership, subnet
and ports checked`; it does not start persistent services. Bootstrap starts the
labelled database, installs the two addons, commits the real seed workflow,
configures the database UUID/company/warehouse binding, creates a 30-day scoped
bot RPC key, enables 14 native automations and starts the bridge. The final line
is `Demo ready: http://127.0.0.1:8069; seed committed; 14 automations enabled;
bridge healthy`. Official Odoo's optional `markdown2` warning can appear; this
pin does not include that optional renderer. The seed report includes
`"mos": 8`, `"wos": 22`, `"posted_pumps": 14.0` and the
six-motor shortage; fixture IDs are assigned by Odoo, never hardcoded.
Packaging prints `Packaged factorio-connect_0.1.0.zip (runtime assets only)`.

Open [Odoo](http://127.0.0.1:8069), database `factorio_demo`. Log in as
`demo.operator` for manufacturing, or `admin` for configuration. Bootstrap
stores their different passwords as `operator-password` and `admin-password`
under `$HOME/.local/share/factorio-connect/demo`; `master-password` is the
separate database-manager password. Use a local password manager or read these
files privately. Do not paste them into a ticket or shared terminal recording.
`FACTORIO_STATE_DIR=/absolute/outside-checkout/path` chooses another secret
location; use it consistently for bootstrap, seed and reset. Never run
`docker compose config` with real secret state when collecting diagnostics.

Normal bootstrap and seed reruns preserve existing credentials, fixture IDs,
posted stock and operator workflow changes. `--verify` checks the current seed
identities; `--verify-baseline` additionally checks the original workflow and
inventory. A changed walkthrough is expected to fail the baseline check.
Neither command restores old states. Missing/expired bot keys fail closed.

## Game installation and pairing

Check your separately installed executable with `factorio --version`; expect
`Version: 2.0.77`. Packaging does not copy mods, overwrite a save or start a game.
Use a dedicated mod directory and a new single-player save. Copy
`dist/factorio-connect_0.1.0.zip` into that directory manually after inspecting
its contents. Keep an existing different-version mod and unrelated saves in
their original directory; do not replace either automatically.

For an executable on your PATH, launch:

```sh
factorio --mod-directory "$HOME/.local/share/factorio-connect/mods" --enable-lua-udp 34199
```

Enable Factorio Connect in Mods, apply/restart, and create/load your dedicated
single-player save. In Settings → Mod settings → Map, set `fc-bridge-port` to
`34200` and `fc-pairing-token` to the private value in the outside-git
`pairing-token` file. Only that transport token belongs in the game; the Odoo
API key and webhook token never do. Save the map. Protect the save and mod
settings because they contain the pairing token.

Click the **Odoo factory** button, then **Jump to generated surface** once a validated snapshot
has created `odoo-factory`. Expect Machining → Assembly → Inspection → Packing,
with order details described in [the walkthrough](demo-walkthrough.md).
The four-stage handshake and four strictly increasing heartbeats can take up
to twenty seconds to verify recovery. A freshly loaded or resumed view remains
resynchronizing until current source evidence matches the accepted snapshot.
If a pre-existing unowned `odoo-factory` surface occupies the name, the mod
retains data and reports display unavailable. Use another dedicated save or
manually rename the unrelated surface; the mod never adopts or deletes it.

## Health and maintenance

```sh
curl --fail http://172.28.0.1:8765/healthz
./scripts/seed-demo --verify
./scripts/bootstrap-demo --rotate-api-key
```

Health is secret-free: `source_ok=true`, a recent `last_success_at`, small
`source_age_seconds`, and a snapshot `latest_revision` indicate successful
source reads. `applied_revision` remains null until a game accepts a snapshot;
HTTP/container health alone is not proof of live game delivery. Rotate before
the stored `metadata.json` expiry. Rotation creates and stores a replacement
for the same dedicated `factorio.bridge` user with scope `rpc` and 30-day expiry,
restarts the bridge, then revokes only older keys bearing the managed local
bridge name. It preserves the user's effective read-only groups. If interrupted,
rerun bootstrap to recover the stored replacement and explicitly rotate again
to finish managed-key cleanup. Never add manufacturing/stock write groups to
the bot to work around a permissions failure. Re-pairing the mod clears its
tracked display/binding only; it never modifies Odoo.

For Compose maintenance in this shell, define this credential-loading wrapper:

```sh
demo() {
  python3 - "$@" <<'PY'
import os, sys
sys.path.insert(0, 'scripts')
from demo_common import compose, environment, state_path
env = environment(state_path())
env['ODOO_CONFIG_FILE'] = str(state_path() / 'odoo.conf')
os.execvpe('docker', compose(env) + sys.argv[1:], env)
PY
}
demo --profile bridge ps
demo logs --tail 50 bridge
```

The wrapper passes credentials through the process environment, never command
arguments or output. Service logs apply the common redactor. Avoid dumping the
container environment. The standalone `factorio_connect` addon also needs the
single common redactor package (`bridge/src/factorio_connect_common`) on Odoo's
Python path; Compose mounts it automatically. Installing the addon alone
without that prerequisite is unsupported.

Port/subnet overrides must be supplied consistently before initial bootstrap:
`ODOO_SUBNET`, `ODOO_GATEWAY`, `ODOO_HTTP_PORT`, `BRIDGE_HTTP_PORT`,
`BRIDGE_UDP_PORT`, `GAME_UDP_PORT`. Bridge HTTP must bind a private IPv4 gateway.
Update the game's bridge setting and `--enable-lua-udp` port to match. Defaults
are `172.28.0.0/24`, `.1`, `8069`, `8765`, `34200`, `34199` respectively.

## Verification limits

Setup/package/reset checks run with:

```sh
./scripts/check e2e -q tests/e2e/test_setup.py tests/e2e/test_reset_contract.py
```
The current development host has only rootless Docker. An isolated
`factorio-connect-test-*` project (or `factorio-connect-tests`) may use
`--backend-test` with different ports and subnet. It generates an outside-git
override that shares the isolated Odoo network namespace, binds the bridge to
that container's inspected private IPv4 and reads Odoo on internal port 8069.
This proves backend provisioning/source reads only. On this host Docker 29.8.0
rootless host mode actually shares the physical host namespace, which lacks
the Compose private gateway; it cannot satisfy the approved desktop topology.
That flag is not a desktop deployment and is never accepted for the
production project. The licensed GUI client is absent here, so physical desktop
UDP, interactive panels and the complete live pipeline remain unexecuted;
Task9 owns that acceptance evidence.
