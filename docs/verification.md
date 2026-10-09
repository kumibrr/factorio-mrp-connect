# Verification evidence

Acceptance date: 2026-10-09. Runtime evidence and simulated checks are recorded
separately. `published_revision` and `applied_revision` are bridge publication
numbers, never an invented Odoo revision. `source_read_at` belongs to the source
snapshot; `last_success_at` is the bridge's completion time and is distinct.

## Reproduce

```sh
./scripts/check bridge
./scripts/check odoo --tags /factorio_connect,/factorio_connect_demo
./scripts/check lua
./scripts/check e2e
./scripts/check factorio --binary /tmp/factorio-connect-2.0.77/factorio/bin/x64/factorio
./scripts/package-mod
git diff --check
```

Full e2e freshly calls `./scripts/smoke-demo --isolated-test`; a saved passing
report cannot substitute. Named setup/reset-only pytest selections remain
offline. The smoke CLI's default is a read-only check of deployed health and
actual receiver acknowledgment; commit timing and seed invariants are unknown
in that mode. Its explicit isolated mode performs the native scenarios and
returns a structured pass/fail report, with timestamp/revision/delivery/seed
fields and evidence paths. A failure exits nonzero and retains its report.

The live project is exactly `factorio-connect-tests`, database `factorio_tests`,
network `172.29.0.0/24` with gateway `172.29.0.1`, Odoo host port 8169,
bridge HTTP 8875 and loopback UDP bridge/client 34300/34301. All targeted
resources must carry both the project label and `io.factorio-connect.owner`.
The harness refuses a pre-existing project rather than reseeding it; cleanup
removes only resources from its labelled test project. It never stops or seeds
a `factorio-connect-demo` instance. Production defaults and database guards
remain `factorio_demo`.

The development Docker daemon is rootless. An explicitly test-only Compose
adapter shares the bridge and UDP observer with the isolated Odoo network
namespace. Pausing/unpausing the labelled Odoo container keeps that namespace
alive while genuinely suspending source service. The bridge restarts with the
same durable cache volume. This is backend evidence; physical rootful desktop
networking remains unexecuted.

The Python UDP adapter delegates handshake, raw JSON/source validation,
bounded assembly, production `state.accept`, atomic application acknowledgment,
timeout and heartbeat
recovery decisions to the unchanged production Lua receiver. It is a test
socket adapter, not a Factorio engine UDP dispatcher or GUI client.

## Passed

| Command | Result | Elapsed wall time | Evidence |
| --- | --- | --- | --- |
| `./scripts/check bridge` | 134 passed | 19.58 s | `runtime/task9-bridge-final.log` |
| `./scripts/check odoo --tags /factorio_connect,/factorio_connect_demo` | 0 failed, 0 errors of 25 runner tests | 181.41 s | `runtime/task9-odoo-final.log` |
| `./scripts/check e2e` | 25 passed, including all five native scenarios | 223.87 s | `runtime/smoke-report-9Ysvnb.json`, `runtime/task9-e2e-final.log` |
| `./scripts/check lua` | 40 passed, 0 failed | 4.24 s | `runtime/task9-lua-final.log` |
| `./scripts/check factorio --binary …/factorio` | create + two independent save loads passed | 4.39 s | `runtime/surface-smoke-zgllhnmp/report.json` |
| Native engine wire output → pinned Pydantic | 3/3 safe-max envelopes accepted | — | `runtime/task9-native-wire-python.log` |

Odoo's module statistics separately list 20 addon tests and 11 demo tests
(including inherited/transitive cases); its authoritative final result reports
25 runner tests. The command also passed 8 client/cache cases and 48 schema
cases, and real bearer JSON2 export/graph checks denied writes with HTTP 403.
Native seed read: ten products, two BOMs, four centers, eight MOs, 22 WOs,
14 posted pumps and six missing motors. The live client/cache probe retained
`source_read_at=2026-10-09T17:54:44.217945+00:00` across SQLite restart while
bridge revisions advanced from 1 to 2.

The native engine produced four stations, 102 protected belts and 27 persistent
render objects. It loaded the save twice and retained unrelated entities.
Its injected fixture snapshot proves rendering/ownership behavior; it does
not prove a live engine source acknowledgment. Actual native JSON helper output
from the new wire codec preserved sequence 9007199254740991, quoted/braced/Unicode
token text, exact maximum-ID record URLs and maximum-ID source scope validation.
The same raw envelope bytes were accepted by strict Pydantic in Python 3.12.

The final isolated live run (18:09:33–18:12:49 UTC) recorded:

| Scenario | Source/receiver evidence | Result |
| --- | --- | --- |
| Distinct commit | independent transaction sees Assembly before commit and new name afterward; native HTTP202 receipt; read `2026-10-09T18:11:29.259231Z`, published/applied 4/4 | 0.570508 s |
| Distinct rollback | independent transaction and receiver retain committed name; zero HTTP202 receipts and no rolled-back name in accepted history | passed |
| Missed notification | all14 rules inactive in independent transaction; zero receipts; full reconciliation applies rename; all14 restored | 20.219690 s |
| Native +6 motor adjustment + `action_assign` | unreserved6→0, on-hand/reserved34/34, posted pumps14; published/applied6/6 | 0.880540 s |
| Bridge restart with paused Odoo | cached/source/receiver revision6 and original `2026-10-09T18:12:07.105988Z` retained, sourcefalse/receiverunverified | passed |
| Source recovery | accepted revision7, fresh read `2026-10-09T18:12:45.595110Z`, receiververified; revision/timestamp logs contain no tokens | passed |

Raw evidence: `runtime/live-smoke-iwe83316/{bootstrap.log,orm.log,bridge.log,receiver.json,final-health.json}`.
The cached timestamp did not renew while Odoo was unavailable. Cleanup left no
containers, volumes or networks with the test project label. `git diff --check`
passed. Runtime artifacts are temporary; the measured facts above remain in
this committed record.

Versions and pins:

- Factorio 2.0.77 build 84539, Linux x64 headless; official archive SHA-256
  `c4efc11529f74d37c96933e291e0db73fd9f5aa4738913d9301b24680b3e947f`.
- Odoo Community `20.0-20260926`, image manifest
  `sha256:a54b6a68e1816f57c3f22f611e049246ca274ab86bc9fb24fc021a21c850209e`.
- PostgreSQL 17.11, manifest
  `sha256:3cec7eb015ba8adb28139fa5c83b8489cdf0e666e53dfdf20f598ae0cc8739e3`.
- Python 3.12.12 base manifest
  `sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c`;
  test image `sha256:bb2ce4731058dbcc4b5dfe7478d7af1698d5ed9242c08ac88c22620da2c9bec9`.
- Lua 5.2.4, pytest 9.0.2 and Pydantic 2.12.5; exact dependency hashes remain
  in the committed [locks](../bridge/requirements-dev.lock).
- Docker Engine 29.8.0 (rootless), Compose 5.5.1.
- Installable mod `dist/factorio-connect_0.1.0.zip`, SHA-256
  `abfdd3e1066047265dcab2f7fc81f2874f49d2138693dc81917c2fd720b08237`.

The optional Odoo `markdown2 is not installed` warning remains visible and
unsuppressed. A webhook failure/rollback log is intentionally induced by the
native addon test; the final Odoo result has zero errors. These diagnostics
are distinct from unavailable GUI checks.

## Failed during development

- Database/context regression tests first failed on the missing guarded
  database seam and omitted isolated context. The corrected helper rejects a
  production `factorio_tests` target and loads labelled test credentials.
- The first live harness run failed when credential reload lost its project
  context; the focused regression reproduced the ownership failure before the
  context fix passed.
- A successful native smoke report was initially mode-0600 from `mktemp`,
  so the isolated pytest UID could not read its metadata. The check now makes
  only this secret-free report readable (0644); operator secret permissions
  remain unchanged.
- The next harness run could not read mode-0700 host-owned credentials using an
  explicit host UID inside rootless Docker. Native client logs identified the
  mapping failure. The adapter now uses the normal container identity without
  changing state permissions or daemon privileges.
- A test adapter used a stale, pre-edit collection name (`centers`); native
  client logs identified the mismatch with the `work_centers` contract. The
  adapter now reads the delivered source schema.
- The first complete pipeline attempt suppressed only one watched model, so a
  native receipt still occurred; disabling all 14 demo rules in distinct shells
  now brackets the full missed-webhook observation. Compose also tried to start
  paused Odoo as a bridge dependency; restarting only the inspected labelled
  bridge container preserves the actual outage and namespace. A subsequent
  run caught the HTTP listener startup race after direct container start; the
  harness now explicitly waits for listener readiness before observing faults.
- A native engine fixture initially required the codec during `on_init`; Factorio
  rejects runtime `require`. Moving fixture imports to control-file parsing
  fixed that test-only failure.
- Native engine probing found that JSON serialization and `%.0f` round the
  maximum safe integer to 9007199254740992. The narrow outgoing wire codec and
  identifier formatting now use validated `%d`, preserving the existing domain.
- The health source timestamp and publication/application timestamp logs were
  missing. Focused tests failed first, then passed after their narrow additions.

These are corrected development failures, not passing runtime scenarios.

## Unexecuted

The licensed graphical single-player client is unavailable. All actual GUI
acceptance remains unexecuted: baseline/detail panels, operation start/finish,
shortage resolution, partial/backorder inspection, missed-event recovery,
bridge/source outage indicators, source-age stale behavior, pause/save/reload,
rename/archive/add-center, power/material independence and source-authority
re-pair behavior. The installable mod and exact ordered checks are supplied in
[the walkthrough](demo-walkthrough.md#single-player-gui-acceptance-record-requires-the-licensed-client).
Five-second live GUI change delivery and actual native inbound Lua UDP dispatch
are not established by the backend client.

The checksum-verified 2.0.77 headless tooling previously aborted an inbound UDP
probe before callback dispatch (`TickClosure.cpp:91`). This is a headless
observation and does not establish failure in interactive single-player. No
alternate production server/RCON topology was introduced.

The rootful production topology, real desktop-to-host UDP and licensed GUI
acceptance are the remaining acceptance dependencies. No full backup/restore
execution is claimed here.
