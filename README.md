<img src="assets/icon.svg" width="64" height="64" alt="">

# factorio-connect

View an Odoo MRP factory in Factorio: work centers, work orders, recorded
production, BOM dependencies and material availability. Compact production flows
carry workpieces left to right, with short local branches and merges where needed.
Normal stages connect directly by belts with only initial input and final output
boxes; extra receipt boxes are reserved for real forks and joins.
One component-kit feed combines each operation's allocated inputs into the same
machine, with native backpressure and running timers. Odoo supplies the
production truth; Factorio displays it and never writes business records.

The local demo targets Linux x86_64, local rootful Docker Engine, Compose >=2.24.0,
host Python >=3.10, Odoo 20 Community/PostgreSQL 17 and a separately owned
single-player Factorio 2.0.77 base-game client. Runtime image digests and exact
Python dependency hashes are committed. No Factorio server, RCON, Enterprise
module or Space Age is required.

From the repository root:

```sh
./scripts/bootstrap-demo --check
./scripts/bootstrap-demo
./scripts/seed-demo --verify-baseline
./scripts/package-mod
```

Open Odoo at `http://127.0.0.1:8069`. Credentials are generated outside git.
Install the packaged mod into a dedicated mod directory/save, launch the game
with `--enable-lua-udp 34199`, and privately configure the pairing token and
bridge port 34200 as described in [local setup](docs/local-demo.md).

- [Local setup, credentials, rotation and health](docs/local-demo.md)
- [PumpWorks baseline and operation walkthrough](docs/demo-walkthrough.md)
- [Architecture and source/transport semantics](docs/architecture.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Backup and explicit demo-only reset](docs/reset.md)
- [Approved design](docs/superpowers/specs/2026-10-09-factorio-odoo-mrp-design.md)
- [Normative seed data](docs/superpowers/specs/2026-10-09-factorio-odoo-mrp-seed-data.md)

Developer checks: `./scripts/check bridge`, `./scripts/check lua`,
`./scripts/check odoo`, `./scripts/check e2e`, and
`./scripts/check factorio --binary /path/to/factorio-2.0.77`.
The full e2e command creates and removes only labelled `factorio-connect-tests`
resources; it requires free test ports 8169/8875/34300/34301.
Setup tests and isolated backend provisioning are distinct from physical
desktop/live-game acceptance. The current development host has rootless Docker
and no licensed GUI client. Real isolated Odoo-to-bridge-to-production-Lua
receiver checks are delivered,
while physical desktop topology and single-player GUI acceptance remain
unexecuted. See [verification evidence](docs/verification.md). Normal bootstrap
rejects rootless Docker for the supported desktop path.
