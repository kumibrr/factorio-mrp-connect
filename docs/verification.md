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

For isolated native webhook diagnosis, set `FACTORIO_TEST_WEBHOOK_DEBUG=1` on
a focused live/outage E2E invocation. It enables only the native `ir_actions`
logger's DEBUG level and captures `odoo.log` with model/id/action metadata;
webhook URLs remain redacted. The isolated smoke fixture also sets the guarded
`FACTORIO_TEST_DISABLE_CRON=1`, using native `max_cron_threads=0` to keep background
scheduler commits outside its controlled transaction observations. All14 native
rules remain configured and manual ORM/workflows remain native; the missed-event
scenario still disables/restores its rules explicitly. Production defaults are unchanged.
Production bootstrap rejects both flags, as do
missing or mismatched explicit backend-test contexts. Normal configuration is
unchanged.

The live project is exactly `factorio-connect-tests`, database `factorio_tests`,
network `172.29.0.0/24` with gateway `172.29.0.1`, Odoo host port 8169,
bridge HTTP 8875 and loopback UDP bridge/client 34300/34301. All targeted
resources carry the project label, `io.factorio-connect.owner`, and a fresh
`io.factorio-connect.test-run` UUID. Native Odoo check and isolated smoke hold the
same local-user project lock through inspection, execution and cleanup. Both
refuse pre-existing targets before mutation; cleanup verifies every target
against all three identities before removing only enumerated resources. It never stops or seeds
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
- Installable mod at the original Task 9 verification,
  `dist/factorio-connect_0.1.0.zip`, SHA-256
  `abfdd3e1066047265dcab2f7fc81f2874f49d2138693dc81917c2fd720b08237`.

The optional Odoo `markdown2 is not installed` warning remains visible and
unsuppressed. A webhook failure/rollback log is intentionally induced by the
native addon test; the final Odoo result has zero errors. These diagnostics
are distinct from unavailable GUI checks.

## Final review fix verification

The final combined fix wave distinguishes disconnected/recovering transport,
bridge-reported source freshness, and source errors in the GUI. Lua tests exercise
receiver timeout, reconnect fence, load/resume and old failed source reads without
using running ticks as source wall-clock age. The confirmed local re-pair regression
keeps saved revision 1000 against lower/equal fresh snapshots, then accepts a fresh
same-UUID revision 1 only after local confirmation. Ordinary durable-cache restart
still accepts an advancing revision automatically. These are production Lua modules
and GUI handlers with mocked engine objects, not a licensed GUI execution.

| Covering command | New result | Raw evidence |
| --- | --- | --- |
| `./scripts/check bridge -q` | 142 passed | `runtime/final-fix-bridge-complete.log` |
| `./scripts/check lua` | 45 passed, 0 failed | `runtime/final-fix-lua-final.log` |
| `./scripts/check lua test_control` after strengthened recovery assertions | 3 passed, 0 failed | `runtime/final-fix-control-final.log` |
| `./scripts/check e2e -q tests/e2e/test_setup.py` after fixture controls | 33 passed | `runtime/final-fix-setup-controlled.log` |
| `FACTORIO_TEST_WEBHOOK_DEBUG=1 ./scripts/check e2e -q tests/e2e/test_live_pipeline.py tests/e2e/test_outages.py` after fixture controls | 5 passed after fresh native smoke | `runtime/final-fix-e2e-controlled.log`, `runtime/smoke-report-g2TFsa.json` |
| `./scripts/check odoo` | 0 failures/errors of 25 native tests; 8 client/cache and 48 schema cases; live scoped seed/bearer checks passed, write denied HTTP403 | `runtime/final-fix-odoo-native.log` |
| `./scripts/check factorio --binary …/factorio` | create and two loads passed | `runtime/final-fix-factorio-native.log`, `runtime/surface-smoke-8zvnzvto/report.json` |

Native Odoo cleanup left zero containers, volumes and networks for the exact
newly owned test project (`runtime/final-fix-odoo-cleanup.log`). The offline native
entry-point regressions also refuse pre-existing and wrongly owned targets before
mutation, refuse cleanup after a run-label mismatch (including a late volume),
and prove check/smoke lock contention in both orders. During the new actual smoke
lifecycle, a second native check exited 2 with an active-run refusal
(`runtime/final-fix-live-contention.log`).

The first fresh focused live/outage E2E command completed its native source,
receiver and outage/recovery stages but exited 1 at the rollback receipt assertion;
pytest was not reached. Report `runtime/smoke-report-0EjbLB.json` is failed and
retained, with raw `runtime/final-fix-e2e-live.log` and
`runtime/live-smoke-hn76o72x/{orm.log,bridge.log,receiver.json}`. Its rollback
observation counted one HTTP202 receipt, although distinct transactions and the
receiver retained the committed name and never accepted the rolled-back name.
The committed native callback logged success before the rollback window; the
rollback callback logged cancellation. The initial receipt cannot be individually attributed from those logs; this is
not a passing live rollback check. Current-run label
verification and cleanup completed and left no exact-project resources.

One fresh diagnostic run then passed all five focused live/outage checks
(`runtime/final-fix-e2e-diagnostic.log`, `runtime/smoke-report-q0pcIi.json`). Its
native Odoo metadata log identifies an independent procurement scheduler batch:
it emits a stock.move.line id66 event and commits at 19:04:54.574, just after the
rollback shell's mrp.workcenter id2 hook was cancelled at 19:04:52.616. That proves
an unrelated background writer can affect the aggregate receipt count. The first
run's metadata-free receipt is not retroactively identified; this is the likely
cause, with that limitation. Diagnostic metadata-only keys and redacted URL paths
were checked (`runtime/final-fix-diagnostic-attribution.log`). The final fresh fixture
run with guarded native cron threads disabled passed all five focused checks,
including zero rollback receipts and no rolled-back name in accepted state. Its
native config probe reported cron0 and all14 rules active; the Odoo service log
contains no scheduler job markers. The initial 31 offline setup/reset checks
passed before diagnostic controls; the latest 33-case setup suite covers both
production flag refusals. This controlled fixture does not establish production
scheduler behavior and keeps the zero-receipt assertion.

Fresh final runtime evidence (19:09:55–19:13:25 UTC): commit delivery 1.241991 s
with published/applied revision4; missed notification reconciliation 19.276416 s;
native stock/reservation update 1.059353 s with published/applied revision6.
Outage retained revision6 and `2026-10-09T19:12:43.573883Z`; recovery accepted
revision7 and `2026-10-09T19:13:21.271955Z`. These are backend adapter timings,
not actual GUI delivery. Raw logs are in `runtime/live-smoke-pe0juiag`; the final
audit confirms 58 metadata-only events, redacted URL paths, native cron0/rules14,
and zero exact-project resources after cleanup (`runtime/final-fix-controlled-audit.log`).

The regenerated current distributable `dist/factorio-connect_0.1.0.zip` has
SHA-256 `1f024a0750eb9e6e9b299e483c1834f77ac53021ece275b9c537bdee3e3b15e3`.
All 16 runtime assets compare byte-for-byte with source and all ZIP CRCs validate
(`runtime/final-fix-package.log`). Only the obsolete five receiver replay examples
and one obsolete bridge replay example were retired; every retained fixture field
is unchanged (`runtime/final-fix-fixture-audit.log`), and current challenge/case
coverage still executes in Python and Lua. Runtime pins and normative seed semantics
are unchanged. The optional Markdown warning remains visible and unsupported.

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
