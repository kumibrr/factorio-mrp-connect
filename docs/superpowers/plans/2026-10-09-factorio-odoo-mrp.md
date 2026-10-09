# Odoo MRP Factorio Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a documented Linux local demo in which Odoo MRP updates an automatically generated, operationally accurate single-player Factorio factory view.

**Architecture:** A read-only Odoo Community addon exports one transactional factory snapshot. Built-in post-commit webhooks and a 60-second reconciliation drive a Python bridge, which delivers acknowledged, chunked localhost UDP snapshots to a Factorio mod. A separate demo addon seeds production through valid Odoo workflows.

**Tech Stack:** Odoo 20.0 Community, PostgreSQL 17, Python 3.12, FastAPI, HTTPX, Pydantic, SQLite, pytest, Factorio 2.0.77 base game, Lua 5.2-compatible modules, Linux Docker Engine and Compose.

**Spec:** [System design](../specs/2026-10-09-factorio-odoo-mrp-design.md) and [complete seed specification](../specs/2026-10-09-factorio-odoo-mrp-seed-data.md). Read both before executing. The user's “Continue” approved these written specifications; this plan is the next review artifact.

## Global Constraints

- Odoo 20.0 Community; PostgreSQL 17; Python 3.12; Factorio 2.0.77 baseline; base game only.
- Linux local demo; single-player client; no deployed Factorio server, RCON, Enterprise module, or Space Age dependency.
- Odoo is authoritative; Factorio never changes manufacturing orders, inventory, or work-order status.
- Generate the dedicated `odoo-factory` surface; only modify mod-owned entities.
- Odoo HTTP is `127.0.0.1:8069`; database is `factorio_demo`; PostgreSQL has no published host port.
- Compose network is `172.28.0.0/24`, gateway `172.28.0.1`; bridge uses Linux host networking.
- Bridge HTTP binds `172.28.0.1:8765`; webhook path is `/odoo/events/<webhook-token>`.
- Bridge UDP is `127.0.0.1:34200`; game Lua UDP is `127.0.0.1:34199`; launch with `--enable-lua-udp 34199`.
- Initial/reconnect snapshot and full reconciliation every 60 seconds; terminal MO retention is seven days, preserving selected split-group relationships.
- Webhook response `202` targets 250 ms; debounce 250 ms with a maximum one-second wait; one serialized source read.
- Source-read failure retry delays are 1, 2, 4, 8, 16, then 30 seconds.
- UDP envelope maximum 1,024 UTF-8 bytes; snapshot maximum 256 KiB and 512 chunks.
- At most eight unacknowledged chunks and 100 outgoing data frames/second; one-second retries, eight attempts, ten-second session retry/assembly expiry.
- Heartbeat every five seconds; 15-second bridge/session timeout; source data stale after 90 seconds; paused UI cannot advance freshness.
- Seeds: ten products, two BOMs, four centers, eight resulting MOs, 22 WOs, 14 posted pumps, six missing motors.
- Create seed states through ORM/workflow actions; no direct computed-state or reservation writes.
- API key belongs to a dedicated effective read-only user; no blanket `sudo()` in export; no API key/webhook token in mod data.
- Pin runtime images by digest and Python dependencies by exact version/hash before acceptance; never use moving `latest` tags.
- Run relevant tests once after each change; broaden only for new changes/failures or the final integration gate. Record actual runtime evidence separately from simulated checks.

## Review Focus

1. Archived centers referenced by active WOs and old terminal backorder siblings: preserve necessary references without crossing company/warehouse scope; Task 2 tests this.
2. Unknown states, missing values, zero operation denominators, and negative real stock: retain truthful labels/values and avoid division errors or fabricated zeroes; Tasks 1 and 7 test this.
3. Unicode/escaped text near datagram limits and incomplete/reordered/duplicate packets: preserve exact text, bound memory, and apply only complete newer state; Tasks 5 and 6 test this.
4. Reloaded saves, bridge restarts, and changed source identity: distinguish retained data from verified current data, negotiate fresh sessions, and require explicit re-pairing for a different source; Tasks 4 and 6 test this.
5. Indirect stock changes, rolled-back transactions, and token-bearing log exceptions: show committed source truth, recover missing notifications, and redact secrets; Tasks 2, 4, and 9 test this.

---

## Execution context and file map

The repository currently contains only README, its icon, the two approved specs,
and this plan. There is no existing app flow to preserve. It is already a linked
T3 worktree on `t3code/factorio-odoo-mrp-sync`; confirm that at execution time
instead of creating an unnecessary nested worktree. Docker daemon and Compose
were available when planning. Odoo, Factorio, Lua, and `uv` were not installed
locally; use isolated, pinned test/runtime containers instead of host-wide installs.

This is one integration with shared interfaces, delivered in nine independently
testable tasks. It does not need separate subsystem design approvals: the
approved specifications already define their seams. Each task owns its narrow
tests; the final task proves the complete workflow.

| Area/files | Responsibility |
| --- | --- |
| `bridge/pyproject.toml`, `requirements*.in`, `requirements*.lock` | Runtime/dev dependencies, package/test configuration and reproducible dependency lock |
| `bridge/src/factorio_bridge/contracts.py`, `contracts/` | Validated snapshot models, generated schema and canonical demo/test vectors |
| `odoo-addons/factorio_connect/models/config.py`, `factory.py`, `snapshot.py` | Administrative scope, public read-only endpoint, one-cursor export |
| `odoo-addons/factorio_connect/models/automation.py`, `logging.py`, `security/` | Webhook configuration, token redaction, effective permissions |
| `odoo-addons/factorio_connect_demo/data/factory.json`, `seed/`, `models/manifest.py` | Static records, workflow creation, inventory invariants and idempotent manifest |
| `bridge/src/factorio_bridge/odoo.py`, `coordinator.py`, `store.py`, `app.py`, `settings.py`, `logging.py` | Source client, serialized refresh loop, SQLite cache, HTTP entry point/configuration/redaction |
| `bridge/src/factorio_bridge/protocol.py`, `udp.py` | Byte-bounded framing, sessions, acknowledgments, retransmission and heartbeat |
| `factorio-mod/{info.json,data.lua,settings.lua,control.lua}` | Mod definition, fixed prototypes/settings and lifecycle adapter |
| `factorio-mod/scripts/{receiver.lua,state.lua,validation.lua}` | Pure receiver/state logic and normalized snapshot validation |
| `factorio-mod/scripts/{layout.lua,view_model.lua,surface.lua,gui.lua}` | Stable placement, truthful station data, owned game entities and operator UI |
| `deploy/{compose.yaml,Dockerfile.odoo,Dockerfile.bridge,Dockerfile.tests,versions.env,odoo.conf}` | Isolated, pinned local services/test tooling and network configuration |
| `scripts/{check,bootstrap-demo,seed-demo,package-mod,reset-demo,smoke-demo}` | Exact documented interfaces for verification, setup, packaging and explicit reset |
| `tests/{lua,e2e,factorio-smoke}` and package-specific tests | Pure Lua cases, real integration tests, real-engine smoke fixtures |
| `docs/{local-demo,demo-walkthrough,architecture,troubleshooting,reset,verification}.md` | Verified operator/developer guides and acceptance evidence |

Addon packages also create `__init__.py`, `__manifest__.py`, subpackage
initializers, necessary views, ACL CSV/rule XML, and test initializers in their
own tasks. Include them in each task's commit; no separate scaffolding task.

## Shared interfaces to freeze in Task 1

The canonical root `Snapshot` has `meta`, `units`, `products`, `work_centers`,
`manufacturing_orders`, `work_orders`, `boms`, `material_demands`, and `stock`.
Collections are arrays sorted by source ID; optional values are null, not omitted
business-state guesses. Exports are ordinary dictionaries; the bridge validates
them into the Pydantic model.

| Model | Fields required by consumers |
| --- | --- |
| `SnapshotMeta` | `schema_version=1`, `source_id` (database UUID), `scope_id`, `company_id`, `warehouse_id`, `source_read_at` (UTC), `odoo_major=20`, `odoo_base_url` (configured public URL) |
| `Unit` | `id`, `name`, positive `rounding` |
| `Product` | `id`, `name`, `code`, `unit_id` |
| `WorkCenter` | `id`, `name`, `code`, `active`, `capacity`, `calendar_id`, nullable `raw_working_state` |
| `ManufacturingOrder` | `id`, `reference`, `origin`, `product_id`, `unit_id`, `requested_qty`, nullable `reported_qty`, `posted_qty`, `raw_state`, nullable dates/readiness/availability, `group_id`, `backorder_sequence` |
| `WorkOrder` | `id`, `mo_id`, `center_id`, `operation_id`, `unit_id`, `sequence`, `dependency_ids`, `raw_state`, nullable `output_qty`, `carried_qty`, `required_qty`, `remaining_qty`, `ready_qty`, `expected_minutes`, `elapsed_minutes` |
| `Bom` | `id`, `product_id`, `unit_id`, `output_qty`, `components` (product/unit/quantity/operation), `operations` (ID/center/sequence/dependency IDs) |
| `MaterialDemand` | `id` (move ID), `mo_id`, `product_id`, `unit_id`, `demand_qty`, `remaining_demand_qty`, `reserved_qty`, `picked_qty`, `posted_consumed_qty`, `unreserved_qty`, nullable `forecast_qty` and `availability_state`, `source_location_id` |
| `StockBalance` | `product_id`, `location_id`, `unit_id`, `on_hand_qty`, `reserved_qty`, `free_qty` |

`source_id` is stored in admin-only integration configuration during bootstrap;
the export does not grant broad `ir.config_parameter` reads to obtain it.
`scope_id` is the stable string `company:<id>/warehouse:<id>`.
Keep quantities finite, respect unit rounding, and permit signed stock/free
balances when the source actually reports them. References between exported
collections must resolve; calendar/location/group IDs are scoped source metadata
whose permissions/scope are checked by the Odoo exporter.
Unknown raw states are valid data and receive an explicit unknown label.

Protocol envelopes use `version=1`, `type`, `token`, `hello_nonce`, `session_id`,
`source_id`, `scope_id`, and message-specific fields. Client hello uses no bound
session. Handshake is initial hello -> hello_challenge (fresh bridge UUID,
echoed initial nonce, null session) -> final hello (challenge_id and hello_nonce
equal that UUID) -> hello_ack (fresh session UUID, echoed final nonce).
Restored saves can repeat initial nonces; external challenges provide freshness.
Pending challenges: maximum eight, ten-second wall-clock expiry, duplicate initial
idempotence. Only valid final confirmation triggers source refresh/authority;
older issuance cannot replace a newer confirmed challenge. Confirmed final nonce
history retains 4096 digests without eviction; current final retries remain
idempotent at capacity, new admission requires explicit bridge restart.
Integer identities/revisions/sequences/scope IDs are capped at 9007199254740991
and integer JSON tokens are required. Native receiver shape inspection preserves
null/required-field/array/object distinctions before helpers decode. Snapshot
messages carry `revision`, `snapshot_id`,
`chunk_count`, `byte_length`; chunks carry zero-based `index` and UTF-8 string
`data`. Acks identify the exact session/snapshot/index. Heartbeats identify a
sequence and include `source_read_at`, `source_age_seconds`, and source health.
Persist the source binding separately from connection sessions. Reset a transient
recovery fence on every handshake/load/resume: accept snapshots/ack heartbeats
immediately; verified health requires four increasing distinct current-session
heartbeat sequences and latest healthy source-read time matching the accepted
snapshot (up to 20 seconds). Trusted localhost buffering permits at most three
unacknowledged old heartbeats before the bridge 15-second timeout. Current-final
idempotent hello never extends liveness. No adversarial replay authenticity or
wall-clock freshness from game ticks is claimed.

### Task 1: Validated contracts and isolated test entry points

**Files:** Create `bridge/pyproject.toml`, `bridge/requirements.in`,
`bridge/requirements-dev.in`, both `.lock` files,
`bridge/src/factorio_bridge/__init__.py`, `contracts.py`,
`contracts/snapshot-v1.schema.json`, `contracts/wire-v1.schema.json`,
`contracts/fixtures/pumpworks-v1.json`, `bridge/tests/conftest.py`,
`bridge/tests/test_contracts.py`,
`deploy/Dockerfile.tests`, `deploy/versions.env`, `scripts/check`, and `.gitignore`.

**Interfaces:** Produces the models above;
`validate_snapshot(payload: dict) -> Snapshot` and
`snapshot_bytes(snapshot: Snapshot) -> bytes` (canonical UTF-8 JSON).
`./scripts/check bridge [pytest-arguments...]` runs pytest in the pinned test
container with repository fixtures mounted read-only. Later tasks extend
`check` with `odoo`, `lua`, `factorio`, and `e2e` modes.
The `pumpworks_payload` pytest fixture loads a fresh copy of the canonical JSON
for each test; later package tests reuse it through `conftest.py`.

- [ ] **Step 1:** Add only the package/test configuration and container wrapper
  needed for pytest collection. Resolve Python 3.12/test-image digests and hashed
  dependency locks; record provenance in `deploy/versions.env`. No app code yet.
- [ ] **Step 2:** Write `test_pumpworks_contract_counts_and_motor_shortage`,
  `test_unknown_state_and_null_are_preserved`, `test_zero_and_negative_stock`,
  `test_rejects_nonfinite_or_dangling_snapshot`, and
  `test_serialization_roundtrips_unicode`. Build the canonical fixture from the
  seed tables, with 10 products/4 centers/8 MOs/22 WOs and motor demand8/reserved2.
  Assertions include `shortage.unreserved_qty == 6`, total posted pumps14,
  unchanged unknown raw state/nulls, and legitimate stock `-2 / 1 / -3`.

  ```python
  def test_pumpworks_contract_counts_and_motor_shortage(pumpworks_payload):
      snapshot = validate_snapshot(pumpworks_payload)
      assert (len(snapshot.products), len(snapshot.work_centers),
              len(snapshot.manufacturing_orders), len(snapshot.work_orders)) == (10, 4, 8, 22)
      assert sum(row.unreserved_qty for row in snapshot.material_demands) == 6
  ```
- [ ] **Step 3:** Run `./scripts/check bridge -q tests/test_contracts.py`;
  expect failing contract imports/validation assertions, not a broken container.
- [ ] **Step 4:** Implement the exact model/serialization interfaces and generate
  the committed schemas from those models. Enforce finite numbers, reference
  integrity and units; keep optional source values truthful. Protocol schema
  names/fields follow the shared-interface section, not a second dialect.
- [ ] **Step 5:** Run the same command; all contract cases pass. Verify schema
  regeneration has no diff and no secret/ignored runtime artifact is staged.
- [ ] **Step 6:** Commit the contract and its test/tooling files with
  `feat: define factory snapshot and transport contracts`.

### Task 2: Read-only Odoo export and runnable backend test environment

**Files:** Create the integration addon initializers/manifest,
`models/config.py`, `models/factory.py`, `models/snapshot.py`,
`security/groups.xml`, `security/ir.model.access.csv`, `security/rules.xml`,
`views/config.xml`, `tests/test_snapshot.py`, `tests/test_permissions.py`,
`deploy/Dockerfile.odoo`, `deploy/odoo.conf`, and `deploy/compose.yaml`;
extend `deploy/versions.env` and `scripts/check`.

**Interfaces:** Consumes the Task 1 dictionary/schema.
`factorio.factory.get_snapshot() -> dict` is `@api.model`/`@api.readonly`, with
no caller-supplied scope. Internal
`build_snapshot(env, config, source_read_at: datetime) -> dict` uses one cursor.
`factorio.integration.config` stores `company_id`, `warehouse_id`, `source_id`,
`enabled`, `terminal_days=7`, `odoo_base_url=http://127.0.0.1:8069`, and admin-only
webhook configuration.
`./scripts/check odoo --tags TAGS` tests an isolated `factorio_tests` database,
never the operator's demo database.

- [ ] **Step 1:** Verify availability of a concrete official Odoo 20 build/image
  and PostgreSQL 17 artifact; pin digests/checksums, mount addons, and add the
  Odoo test mode to `check`. Keep the existing Docker network/localhost contract.
  If the chosen official artifact does not exist, use an official pinned 20.0
  source build; do not silently substitute another Odoo major.
- [ ] **Step 2:** Write real Odoo tests `test_export_contract`,
  `test_reported_output_is_distinct_from_posted`,
  `test_archived_center_and_old_backorder_sibling_are_resolved`,
  `test_export_is_readonly_one_cursor`, and `test_effective_bot_permissions`.
  Create a second company in tests and assert no leakage; preserve selected
  group siblings outside the seven-day terminal window. Assert business
  create/write/unlink denied for the bot and configured scope cannot be changed
  through method arguments or context.

  ```python
  def test_effective_bot_permissions(self):
      snapshot = self.env['factorio.factory'].with_user(self.bot).get_snapshot()
      assert snapshot['meta']['company_id'] == self.demo_company.id
      assert self.foreign_mo.id not in {row['id'] for row in snapshot['manufacturing_orders']}
      with self.assertRaises(AccessError):
          self.demo_mo.with_user(self.bot).write({'origin': 'unauthorized'})
  ```
- [ ] **Step 3:** Run `./scripts/check odoo --tags /factorio_connect`;
  expect the new behavior assertions to fail on the minimal addon shell.
- [ ] **Step 4:** Implement the models, ACLs, rules, config view, and mapper. Include
  active centers plus inactive centers needed by selected WOs. Derive posted
  output from done finished moves; derive per-MO material reservations from its
  move lines, retaining picked/posted distinctions and forecast evidence. Read
  computed availability on each export; normalize all quantities/units. Map WO
  `required_qty` from `qty_to_produce`, retaining carried output separately.
- [ ] **Step 5:** Run the same Odoo checks plus
  `./scripts/check bridge -q tests/test_contracts.py`. Validate a real JSON-2
  response against the shared schema, with bearer auth and `X-Odoo-Database`;
  all tests pass and the endpoint performs no business writes.
- [ ] **Step 6:** Commit with `feat: export scoped read-only Odoo factory snapshots`.

### Task 3: Reproducible PumpWorks catalog and production workflow seeds

**Files:** Create the demo addon initializers/manifest,
`data/factory.json`, `models/manifest.py`, `seed/catalog.py`, `seed/stock.py`,
`seed/production.py`, `seed/service.py`, and `tests/test_seed.py`;
create `scripts/seed-demo` and extend `scripts/check` as necessary.

**Interfaces:** Consumes the Odoo config/export from Task 2.
`seed_demo(env, *, now: datetime) -> SeedReport` runs once transactionally;
`verify_demo(env, *, baseline: bool) -> SeedReport` performs no business writes.
`SeedReport` contains `seed_version`, `fixture_ids`, `counts` (products/BOMs/centers/
MOs/WOs), and `invariants` with `posted_pumps`, `missing_motors`,
`motor_on_hand`, `motor_reserved`, `motor_free`, `partial_done`,
`partial_backorder`. `factorio.demo.manifest` persists version1, T0, initialization status
and generated XML-ID relationships. `seed-demo --verify-baseline` checks the
normative seed; ordinary rerun preserves later operator edits.

- [ ] **Step 1:** Write `test_baseline_inventory_and_all_states`,
  `test_real_four_plus_six_backorder`, `test_rerun_does_not_post_twice`,
  `test_rerun_preserves_operator_edits`, and `test_failed_seed_rolls_back`.
  Assert all named fixtures, eight MOs/22 WOs, final motor28/reserved28/free0,
  shortage MO8/reserved2/missing6, pump stock14, and one open Assembly timer.

  ```python
  def test_real_four_plus_six_backorder(self):
      report = seed_demo(self.env, now=self.T0)
      assert report.invariants['partial_done'] == 4
      assert report.invariants['partial_backorder'] == 6
      assert report.invariants['posted_pumps'] == 14
      assert report.invariants['missing_motors'] == 6
  ```
- [ ] **Step 2:** Run `./scripts/check odoo --tags /factorio_connect_demo`;
  expect failing seed interfaces/outcome assertions.
- [ ] **Step 3:** Implement catalog/stock records exactly from the seed tables,
  aliasing core/generated prerequisites instead of duplicating them. Implement
  the documented completion/backorder sequence with public actions; register
  seven initial MOs plus the generated remainder and resolve WOs by operation.
  Preserve no-output running10; reserve shortage8 last; process returned workflow
  actions rather than forcing computed states.
- [ ] **Step 4:** Implement manifest/failure rollback and read-only verification;
  add the CLI wrapper that targets `factorio_demo` and fails with named invariant
  differences. Passwords/API tokens are not static JSON fixture fields.
- [ ] **Step 5:** Run both addon suites and contract tests. Check every row of the
  seed inventory table through actual Odoo, not just arithmetic in Python.
  Verify effective bot export sees the seeded records without extra rights.
- [ ] **Step 6:** Commit with `feat: seed PumpWorks through real manufacturing workflows`.

### Task 4: Built-in notifications and serialized bridge refreshes

**Files:** Create integration `models/automation.py`, `logging.py`,
`tests/test_automation.py`; create bridge `settings.py`, `logging.py`, `odoo.py`,
`store.py`, `coordinator.py`, `app.py`, `__main__.py`,
`tests/test_webhooks.py`, `test_coordinator.py`, `test_store.py`,
`test_odoo_client.py`; update manifests/initializers and dependencies/locks.

**Interfaces:**
`configure_automations(env, config) -> dict[str, int]` creates/updates the 14
rule/action pairs specified in the seed companion.
`OdooClient.get_snapshot() -> Awaitable[Snapshot]` makes exactly one JSON-2 call.
`SnapshotStore.save(snapshot: Snapshot) -> StoredSnapshot` atomically allocates
an increasing revision; `load_latest() -> StoredSnapshot | None` retains original
source-read time. `StoredSnapshot` has `revision` and `snapshot`.
`RefreshCoordinator(fetch, store, publish, clock)` exposes async `start()`,
`stop()`, `notify(reason: str)`, and `request_initial()`; `publish` accepts one
`StoredSnapshot`. Its health includes last success, last error, source age and
dirty/read status. Define `Clock` in `coordinator.py` with `monotonic() -> float`,
`utcnow() -> datetime`, and async `sleep(seconds: float)`; `SystemClock` uses the
standard clock/asyncio APIs and tests supply an explicitly advanced fake.
Define `BridgeHealth` in `coordinator.py` with `source_ok`,
nullable `source_age_seconds`, `last_success_at`, `last_error`, and `refreshing`;
its wire representation contains no credentials. `create_app(settings, coordinator) -> FastAPI` owns webhook
and `/healthz` entry points; it does not wait for delivery on webhook requests.

- [ ] **Step 1:** Write tests `test_fourteen_scoped_rules_and_empty_business_fields`,
  `test_webhook_payload_and_postcommit_registration`,
  `test_success_failure_rollback_logs_redact_url_token`,
  `test_webhook_returns_before_blocked_source_read`,
  `test_bursts_debounce_but_do_not_starve`,
  `test_changes_during_read_trigger_followup`,
  `test_reconciliation_recovers_missed_event`,
  `test_retries_keep_old_source_timestamp`, and
  `test_cache_restart_and_wrong_source_are_not_fresh`. Use a fake monotonic
  clock; pin all timing values from Global Constraints. Invalid token/payload
  requests must not schedule reads; source errors never overwrite valid cache.

  ```python
  async def test_webhook_returns_before_blocked_source_read(client, blocked_fetch):
      response = await client.post('/odoo/events/test-token', json={
          '_model': 'mrp.workorder', '_id': 1, '_action': 'Factorio workorder'})
      assert response.status_code == 202
      assert not blocked_fetch.finished.is_set()
  ```
- [ ] **Step 2:** Run both `./scripts/check odoo --tags /factorio_connect` and
  `./scripts/check bridge -q`; expect failures for the unimplemented interfaces.
- [ ] **Step 3:** Implement rules using Odoo's built-in webhook action and exact
  `_model`/`_id`/`_action` metadata; configure domains/empty update-field filters
  as specified. Install handler-level redaction before any token-bearing URL
  can log. Do not build a custom event queue or call source HTTP inside a write.
- [ ] **Step 4:** Implement bridge settings, redaction, one-call source client,
  SQLite store, serialized coordinator, fast HTTP handler and lifecycle entry
  point. Use bounded HTTP/body timeouts and fake-clock-compatible scheduling.
  Cached source data remains explicitly unverified until a successful new read.
- [ ] **Step 5:** Run the same commands; all new cases pass. Demonstrate a real
  seeded read by the bot, and reload cached data without changing its source
  timestamp. The final task will prove committed versus rolled-back HTTP delivery
  through real separate transactions, beyond callback-registration tests.
- [ ] **Step 6:** Commit with `feat: refresh factory snapshots from webhooks and reconciliation`.

### Task 5: Reliable bounded UDP bridge transport

**Files:** Create bridge `protocol.py`, `udp.py`, `tests/test_protocol.py`,
`tests/test_udp.py`, and `contracts/fixtures/wire-v1.json`;
update bridge lifecycle/publisher integration in `app.py`.

**Interfaces:** Consumes `Snapshot`, `StoredSnapshot` and coordinator health.
`encode_frames(stored: StoredSnapshot, session: Session) -> list[bytes]` emits
byte-bounded messages. `UdpDelivery(settings, clock)` exposes `start()`, `stop()`,
`set_snapshot(stored: StoredSnapshot)`, `set_health(health: BridgeHealth)`, and
`handle_packet(data: bytes, addr: tuple[str, int])`. `Session` stores nonce,
UUID, source/scope identity, accepted revision and acknowledgment state.
The coordinator publisher queues `set_snapshot`; it never waits for the game.

- [ ] **Step 1:** Write `test_unicode_and_escaping_fit_1024_bytes`,
  `test_rejects_oversize_before_publishing`, `test_eight_frame_window_and_rate`,
  `test_missing_chunk_retries_until_ack`, `test_wrong_token_session_ack_ignored`,
  `test_superseded_revision_cannot_roll_back`,
  `test_heartbeat_ack_timeout_negotiates_new_session`, and
  `test_restart_cache_timestamp_is_preserved`. Include accented/emoji/quote-heavy
  strings near the byte limit, 256-KiB boundary, 512-chunk boundary, and a fixed
  packet-loss/reordering schedule.

  ```python
  def test_unicode_and_escaping_fit_1024_bytes(unicode_snapshot, session):
      frames = encode_frames(StoredSnapshot(revision=2, snapshot=unicode_snapshot), session)
      assert all(len(frame) <= 1024 for frame in frames)
      chunks = [json.loads(frame) for frame in frames
                if json.loads(frame)['type'] == 'snapshot_chunk']
      restored = ''.join(row['data'] for row in sorted(chunks, key=lambda row: row['index']))
      assert restored.encode('utf-8') == snapshot_bytes(unicode_snapshot)
  ```
- [ ] **Step 2:** Run `./scripts/check bridge -q tests/test_protocol.py tests/test_udp.py`;
  expect failures for framing/state-machine behavior.
- [ ] **Step 3:** Implement UTF-8 boundary/JSON-overhead-aware chunks, token/source
  binding, echoed hello nonce, UUID sessions, exact chunk acks, bounded sliding
  window, retry/expiry and heartbeat handling. Sessions cannot change source
  identity automatically. No snapshot revision is applied through an ack for
  another session/snapshot.
- [ ] **Step 4:** Connect the source publisher and health to the delivery service;
  bind only localhost UDP and the configured private-gateway HTTP address.
  Add a loopback fake-client test that reconstructs identical canonical bytes
  despite losses and acknowledges application only after complete validation.
  Extend `/healthz` with `latest_revision` from the snapshot store and
  `applied_revision` from the current session's accepted application ack;
  a newly negotiated/unverified session has no applied revision yet.
- [ ] **Step 5:** Run the bridge suite; verify actual loopback delivery plus fake
  clock limits. Emit shared wire vectors for the Lua receiver tests.
- [ ] **Step 6:** Commit with `feat: deliver acknowledged factory snapshots over localhost UDP`.

### Task 6: Factorio receiver, validation and save-safe state

**Files:** Create `factorio-mod/info.json`, `settings.lua`, `control.lua`,
`scripts/receiver.lua`, `scripts/state.lua`, `scripts/validation.lua`,
`tests/lua/run.lua`, `test_receiver.lua`, `test_state.lua`, `fixtures.lua`;
extend test container and `scripts/check` with a Lua 5.2 runner.

**Interfaces:** Consumes wire vectors and canonical snapshot shape.
`receiver.new(config, callbacks)` returns `on_message(message, tick)`,
`on_tick(tick, ticks_played)`, and `reset_connection()`; callbacks send a decoded
envelope, decode assembled JSON, and apply one validated snapshot.
`validation.validate(snapshot) -> boolean, error_or_nil` mirrors shared
constraints without importing Python. `state.accept(snapshot, revision)` swaps
normalized data atomically. Persistent `storage.factorio_connect` holds the
accepted snapshot/revision, source binding and entity slots; connection state is
unverified after load. `state.reset_binding()` clears the accepted source/data
only after an explicit local re-pair action; owned entities are reconciled by
Task 7, without deleting unrelated entities. Runtime settings are `fc-bridge-port` (34200) and
`fc-pairing-token`; no Odoo credentials exist in settings.
Mod metadata is `name=factorio-connect`, `version=0.1.0`,
`factorio_version=2.0`, with a base-game dependency floor of 2.0.77. Reject
unsupported game majors before accepting source updates.

- [ ] **Step 1:** Write Lua cases `complete_out_of_order_applies_once`,
  `partial_bad_length_or_reference_keeps_previous`,
  `wrong_nonce_session_token_and_lower_revision_are_rejected`,
  `assembly_limits_and_expiry_bound_memory`,
  `reload_starts_unverified_without_changing_storage_during_on_load`,
  `pause_delta_invalidates_connection`, and
  `source_change_requires_explicit_binding_reset`.

  ```lua
  -- complete_out_of_order_applies_once: fixture supplies a bound session,
  -- callbacks counting applications, and the shared decoded chunk vectors.
  for _, message in ipairs(fixture.reordered_messages) do
      receiver_instance.on_message(message, 10)
  end
  receiver_instance.on_message(fixture.duplicate_chunk, 11)
  assert(fixture.apply_count == 1)
  assert(fixture.applied_revision == fixture.latest_revision)
  ```
- [ ] **Step 2:** Run `./scripts/check lua`; expect receiver/state assertions to
  fail after the lightweight harness loads, without requiring a game install.
- [ ] **Step 3:** Implement pure Lua receiver/validation/state modules with the
  shared message names and all fixed limits. JSON codec/clock/sender are injected
  so engine globals do not contaminate pure tests. Preserve partial/null source
  data faithfully; reject incomplete references before replacing valid state.
- [ ] **Step 4:** Implement the Factorio lifecycle adapter using
  `helpers.table_to_json`, `helpers.json_to_table`, `helpers.send_udp`,
  `helpers.recv_udp`, `on_udp_packet_received`, and tick handling. Require all
  modules at top level; use `storage`, not legacy `global`. `on_load` only
  restores transient references/handlers; mutate persistent state on a running
  event. Compare played/map tick advancement for pause recovery; use fresh
  session health to avoid buffered old heartbeats claiming freshness.
- [ ] **Step 5:** Run `./scripts/check lua` and the bridge protocol cases;
  both implementations accept the same valid vectors and reject the same
  malformed ones. Actual helpers/engine lifecycle checks belong to Task 9.
- [ ] **Step 6:** Commit with `feat: receive and persist verified snapshots in the Factorio mod`.

### Task 7: Automatic surface, workflow connections and truthful operator GUI

**Files:** Create `factorio-mod/data.lua`, `prototypes/stations.lua`,
`scripts/layout.lua`, `view_model.lua`, `surface.lua`, `gui.lua`,
`locale/en/factorio-connect.cfg`, `tests/lua/test_layout.lua`,
`test_view_model.lua`, `test_surface.lua`, `test_gui.lua`; extend `control.lua`.

**Interfaces:** Consumes accepted snapshots from Task 6.
`view_model.build(snapshot, health) -> view` defines center/order counts,
quantity/time labels, history, dependency/material evidence and synchronization.
`view.centers[center_id]` contains `running_count`, `ready_count`, `waiting_count`,
`material_warning_count`, `raw_state_label`, and order detail rows.
`layout.reconcile(work_centers, slots) -> slots, changes` assigns deterministic
stable positions. `surface.reconcile(view, slots, owned_entities)` applies only
mod-owned entity/render changes. `gui.show(player, view, center_id)` and
`gui.update(player, view)` expose operator detail/legend/freshness/record URL.

- [ ] **Step 1:** Write `seeded_counts_and_six_motor_reason`,
  `center_done_means_running`, `unknown_null_and_zero_are_truthful`,
  `quantities_not_summed_across_operations_or_products`,
  `new_center_does_not_move_existing_slots`,
  `rename_archive_and_repeat_snapshot_are_idempotent`,
  `cycle_warns_without_losing_valid_view`, and
  `power_and_unrelated_entities_do_not_change_source_truth`.
  Test the seed's Assembly running1/ready3, Inspection/Packing waiting4,
  shortage8/reserved2/missing6, split4+6, and pump stock14.

  ```lua
  -- seeded_counts_and_six_motor_reason
  local view = view_model.build(seed_snapshot, healthy)
  local assembly = view.centers[fixture.assembly_id]
  assert(assembly.running_count == 1)
  assert(assembly.ready_count == 3)
  assert(assembly.material_warning_count == 1)
  assert(assembly.raw_state_label == "In Progress")
  assert(view.centers[fixture.inspection_id].waiting_count == 4)
  ```
- [ ] **Step 2:** Run `./scripts/check lua`; expect these new behavior cases to fail.
- [ ] **Step 3:** Register machining/assembly/inspection/packing/generic station
  prototypes using base-game assets; implement stable surface ownership/layout.
  Stations are protected displays, without native production recipes. Connect
  deduplicated center operation/BOM relationships with labelled belt visuals.
  An inactive referenced center remains identifiable, explicitly archived.
- [ ] **Step 4:** Implement view model and GUI with text/icons plus the specified
  green/blue/amber/gray palette. Keep raw statuses, readiness, material warnings,
  posted/reported output and time/quantity progress separate. Include terminal
  history, legend, surface jump, current source timestamp, health states and a
  selectable/copyable Odoo record URL; do not assume a nonexistent browser API.
  Provide an explicit confirmed local re-pair control using `state.reset_binding`;
  this changes only the generated view, never Odoo business data.
  Sanitize source rich-text/control tags for plain labels without losing Unicode.
- [ ] **Step 5:** Run Lua tests against engine spies that check user-visible
  state and ownership, not private implementation steps. Add a real-engine
  prototype/surface smoke fixture for Task 9 to exercise without GUI simulation.
- [ ] **Step 6:** Commit with `feat: generate the operational factory surface and detail view`.

### Task 8: Reproducible local stack, packaging and operator documentation

**Files:** Create `deploy/Dockerfile.bridge`, `scripts/bootstrap-demo`,
`scripts/package-mod`, `scripts/reset-demo`, `docs/local-demo.md`,
`demo-walkthrough.md`, `architecture.md`, `troubleshooting.md`, `reset.md`;
update Compose, `versions.env`, README and `.gitignore`;
create `tests/e2e/test_setup.py` and `test_reset_contract.py`.

**Interfaces:** `bootstrap-demo` validates the Linux/version/port/subnet context
and that Docker uses the local host (a remote daemon cannot share client localhost),
starts/configures the project-labelled services, creates outside-git secrets,
seeds the demo, mints the scoped bot API key, installs automation URLs and writes
bridge runtime configuration without printing secrets.
`package-mod` produces deterministic
`dist/factorio-connect_0.1.0.zip`, containing only mod runtime assets.
`reset-demo --confirm factorio-connect-demo` targets this project's demo
volumes/view only; normal bootstrap/seed never invokes it. No automatic copy
over an unrelated Factorio save or existing different-version mod.

- [ ] **Step 1:** Write tests `test_compose_matches_linux_socket_contract`,
  `test_bootstrap_rerun_preserves_seed_and_secrets`,
  `test_package_has_expected_root_and_no_secrets`, and
  `test_reset_rejects_missing_confirmation_or_unlabelled_target`. Assert no exposed
  PostgreSQL port; Odoo loopback publication; bridge host mode/private-gateway
  bind; configured game/bridge UDP ports; digest-pinned runtime images.

  ```python
  def test_compose_matches_linux_socket_contract(compose_config):
      services = compose_config['services']
      assert not services['postgres'].get('ports')
      assert services['bridge']['network_mode'] == 'host'
      assert services['odoo']['ports'][0]['host_ip'] == '127.0.0.1'
      assert str(services['odoo']['ports'][0]['published']) == '8069'
  ```
- [ ] **Step 2:** Run `./scripts/check e2e -q tests/e2e/test_setup.py tests/e2e/test_reset_contract.py`;
  expect assertions to fail before these script/Compose interfaces exist.
- [ ] **Step 3:** Implement bridge image/Compose service, generated secret files,
  project labels/persistence, health checks and exact bootstrap/package/reset
  scripts. Bootstrap records the database UUID into admin config, generates
  runtime API/pairing tokens, and enables the 14 automations after seed commit.
- [ ] **Step 4:** Write the actual guides using verified script commands. Include
  launching the separately installed game with `--enable-lua-udp 34199`, setting
  pairing token/bridge port, loading the mod, entering the dedicated surface,
  checking the baseline and each seed walkthrough. Cover credentials/key
  rotation, subnet/port/version/permission failures, snapshots too large,
  lost webhooks, pause/buffer loss, backup and explicit reset.
- [ ] **Step 5:** Run setup/package/reset tests and execute the clean local path
  in an isolated project instance. Record exact software pins and expected
  startup/seed/health output; verify documented URLs/configuration match reality.
- [ ] **Step 6:** Commit with `feat: package and document the reproducible Linux demo`.

### Task 9: Real integration, game-engine verification and final evidence

**Files:** Create `scripts/smoke-demo`,
`tests/e2e/test_live_pipeline.py`, `test_outages.py`,
`tests/factorio-smoke/{info.json,control.lua}`, and `docs/verification.md`;
extend `scripts/check` for actual Factorio checks and update any affected guides.

**Interfaces:** `smoke-demo` reads known source/game acknowledgments and emits
a structured pass/fail report with `source_read_at`, `published_revision`,
`applied_revision`, `commit_delivery_seconds`, and `seed` invariants. Revisions
refer to bridge publications, not an invented Odoo revision field.
`./scripts/check factorio --binary PATH` uses the pinned real engine
for mod-load/prototype/surface/save checks; `./scripts/check e2e` exercises the
real Odoo/bridge pipeline using an explicit isolated test project/database.
Real single-player GUI acceptance remains distinct from Lua spies/headless
engine checks. Headless tooling, if used, is test-only, not a change to the
single-player/UDP deployed architecture.

The isolated live-test project is `factorio-connect-tests`, database
`factorio_tests`, subnet/gateway `172.29.0.0/24` / `172.29.0.1`, Odoo host port
8169, HTTP port 8875, and UDP bridge/client ports 34300/34301. Apply these as
explicit configuration overrides and discard only resources labelled for this
test project. A running `factorio-connect-demo` instance is never stopped,
reseeded, or reset by a test command.

- [ ] **Step 1:** Write live tests `test_committed_change_reaches_applied_snapshot`,
  `test_rolled_back_change_never_notifies_or_appears`,
  `test_missed_webhook_recovers_within_65_seconds`,
  `test_restarts_and_source_outage_preserve_last_truth`, and
  `test_real_stock_adjustment_clears_six_motor_warning`. Use real distinct database
  transactions and a UDP test client with the production receiver contract.
  Verify protocol logs identify revisions/timestamps without logging tokens.

  ```python
  def test_committed_change_reaches_applied_snapshot(smoke_report):
      assert smoke_report['applied_revision'] == smoke_report['published_revision']
      assert smoke_report['commit_delivery_seconds'] <= 5
      assert smoke_report['seed']['posted_pumps'] == 14
      assert smoke_report['seed']['missing_motors'] == 6
  ```
- [ ] **Step 2:** Run `./scripts/check e2e`; expect the new tests to expose any
  missing connection/recovery behavior. Fix actual failures in the owning
  module, with a focused regression case; do not bypass assertions or source
  validation to make the smoke path pass.
- [ ] **Step 3:** Implement the smoke fixtures/report and run
  `./scripts/check bridge`, `./scripts/check odoo --tags /factorio_connect,/factorio_connect_demo`,
  `./scripts/check lua`, `./scripts/check e2e`, and the real-engine command.
  Download official test tooling only with pinned version/checksum; an absent
  runtime is reported as unexecuted, never a passing fake engine result.
- [ ] **Step 4:** In an actual separately installed single-player client, perform
  baseline, operation start/finish, shortage resolution, partial/backorder
  inspection, missed-event recovery, bridge/source outage, pause/save/reload,
  rename/archive/add-center, and source-authority checks. Verify five-second
  healthy change delivery and stale/disconnected/resynchronizing behavior.
  If the licensed graphical client is unavailable, provide the installable mod
  and exact walkthrough, mark these checks unexecuted, and identify that
  remaining acceptance dependency explicitly.
- [ ] **Step 5:** Record test counts, versions/digests, seed invariants, engine
  evidence and actual GUI evidence in `docs/verification.md`, with separate
  passed/failed/unexecuted categories. Confirm README's status and guides
  describe delivered behavior, then run `git diff --check` and required tests
  affected by the final changes.
- [ ] **Step 6:** Commit with `test: verify the live Odoo to Factorio demo pipeline`.

## Self-review and execution handoff

Spec coverage: Tasks 1/2 own snapshot truth/scope/permissions; Task 3 owns all
seed records/workflows/balances; Task 4 owns notification/reconciliation/cache
semantics; Tasks 5/6 own bounded reliable transport and lifecycle; Task 7 owns
the generated view; Task 8 owns local setup/packaging/docs/reset; Task 9 owns
every runtime acceptance scenario and honest evidence. Review Focus cases are
assigned to named tests above. No product implementation has been performed
while writing this plan.

Recommend **native execution** for these nine tasks: implement in this session,
preserve the shared contract through the tightly connected components, and run
one fresh whole-branch review at the end. Subagent-driven execution is available
if the user prefers a fresh implementer/reviewer gate for each task. Both retain
the same task checks, runtime acceptance and documentation requirements.

The user reviews this written plan and chooses the execution method before
implementation. After that review, apply the required execution/worktree/TDD
skills; continue through all authorized tasks and report any real acceptance
dependency accurately.
