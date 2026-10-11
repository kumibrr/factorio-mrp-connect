# PumpWorks walkthrough

Start with [local setup](local-demo.md) and
`./scripts/seed-demo --verify-baseline`. Baseline is ten products, two BOMs,
four centers, eight MOs and 22 WOs. Pump stock is 14 posted units; the partial
split has completed 4 and remaining 6; the shortage order needs six more motors.
The initial states are:

| Station | Active work | History |
| --- | --- | --- |
| Machining | Idle | Impeller60 done |
| Assembly | Running10; ready10, backorder6 and shortage8 | Pump10 and partial4 done; cancelled5 |
| Inspection | Four dependency-blocked orders | Completed/cancelled operations |
| Packing | Four dependency-blocked orders | Completed/cancelled operations |

Click a station for its own work-center details. Click a production machine for
only its manufacturing order and work order, including quantities, dependencies,
material evidence and timing. Use your normal **Open entity GUI** control
(left click by default). Hovering does not open or switch panels. Use **Close**
or Escape to dismiss the panel. **Odoo factory** or **Factory
overview** opens the full overview.

Use **Machine skin** in the machine panel to choose an available appearance from
the base game or installed mods. The native selector lists compatible machine
graphics, including assemblers, furnaces, drills, labs, power equipment and
containers. Skins use a static first frame, scaled to fit the existing machine;
their recipes, power requirements and behavior are not imported. Each choice is
saved separately for that station or production work order. **Reset to default**
restores its original appearance. Changing a skin preserves inventories, recipe,
production ledger, timers, belt connections and collision footprint. Snapshot
refreshes, lane reconstruction and save/reload retain the choice; removing a mod
that supplies a chosen skin falls back to the default. Confirmed local re-pair
clears these local choices along with the generated view.

Assembly's raw center status `done` means In Progress here. Shortage Assembly
is operation-ready and material-short simultaneously; blocked Inspection and
Packing are waiting for predecessors. No Factorio inventory or power determines
these states. Order origin markers identify scenarios regardless of generated
MO sequence numbers.

Production below the overview uses compact left-to-right order flows. A normal
Assembly → Inspection → Packing sequence stays on one row. Parallel dependency
steps occupy neighboring rows; their routes split locally and converge at one
consuming machine. Use **Jump to production area** to visit work at the selected
center; running work takes priority. Each order retains its machine identities.
Normal stages connect directly by straight belts, with one initial input box
and one final output box. Extra receipt boxes appear only at actual forks and
joins; the work-center summaries no longer draw a second belt network.

Component completion stays in the producer's output box and is associated with
its product area without a long return belt. Odoo allocations for
impellers, housing, motors, shafts, bearings, seals and fasteners combine into
one **Components × 7** feed at Assembly; cartons form a separate kit feed at
Packing. A kit is prepared only when every constituent allocation is available.
Its short belt feeds the top of the same machine that receives workpieces from
the left. Both inputs must physically arrive before Odoo-reported output can
release work. The assignments come from source BOM operations. A dependency fork
sends a completion receipt down each successor path; a merge waits for every
predecessor.

Raw workpieces enter TODO belts through inserters. Ready/blocked operations
leave them there; running operations admit them to their machines. Full native
belts stop their feed inserters, and the shortage order holds its raw feed until
its material warning clears. Machines release markers only up to Odoo-recorded
output, or when Odoo reports that operation done. Items then pass through output
inserters and direct belts to the next machine. Forks and joins use local receipt
buffers to retain separate dependency evidence.

Markers represent visual workpieces, complete component kits, or dependency
receipts, rather than posted business inventory. Labels show each order's scaled
quantity per workpiece. Order details show every component quantity and its own unit.
Batches use at most 200 workpiece markers. Branch receipts represent the same
workpiece's dependency completion and do not create extra product. The backorder
represents only its six outstanding units. Shared stock displays follow Odoo
stock snapshots independently of operation-complete receipts. Product routing
does not claim supplier-order provenance absent from the snapshot. Cancelled
MOs have no physical network; cycles, missing dependencies, ambiguous component
assignments and unequal batches retain source details with a routing warning.

World labels show the operation, state and released-marker count. Order details
retain recorded elapsed/expected duration and remaining estimates. **Observed
running** counts unpaused game time while sync is healthy. Existing saves replace
the previous routed web on the
next reconciliation. Ordinary snapshots and reloads preserve inventories,
entities and counters. Changed quantities/routing/centers, new producer
connections, and downward output/allocation corrections rebuild affected orders;
unrelated entities remain intact.

The following exact commands use the `demo` wrapper from local setup, run
trusted local Odoo ORM actions as administrator and commit business changes.
They are alternatives to the Manufacturing UI; no raw state/reservation writes
are used. Define:

```sh
demo_shell() { demo exec -T odoo /entrypoint.sh odoo shell -d factorio_demo --no-http; }
```

Treat each scenario below as independent unless its text specifies a sequence.
To return to baseline use [explicit reset](reset.md), bootstrap and re-pair;
a seed rerun deliberately keeps your changes. Healthy unpaused webhook updates
target five seconds; missed notifications recover within 65 seconds. Observe
source-read timestamp/revision in `/healthz`, `applied_revision`, and game status.
These are acceptance targets; GUI/live delivery has not been verified on the
current host.

## Finish running Assembly, then start ready Assembly

```sh
demo_shell <<'PY'
mo = env.ref('factorio_connect_demo.mo_running')
mo.qty_producing = 10
mo.set_qty_producing()
env.ref('factorio_connect_demo.wo_running_assemble').button_finish()
env.cr.commit()
PY
```

Running10 Assembly becomes done with 10 operation output, Inspection becomes
ready. Finished stock remains 14 because the MO has not been posted. MO reported
output, operation output and posted output remain separate panel fields.
Then release/use the Assembly slot:

```sh
demo_shell <<'PY'
env.ref('factorio_connect_demo.wo_ready_assemble').button_start()
env.cr.commit()
PY
```

Ready10 becomes running; no simulated quantity grows over time.

## Resolve the six-motor shortage (from baseline)

```sh
demo_shell <<'PY'
product = env.ref('factorio_connect_demo.product_motor')
location = env.ref('factorio_connect_demo.location_stock')
quant = env['stock.quant'].search([('product_id', '=', product.id), ('location_id', '=', location.id)])
quant.ensure_one()
quant.with_context(inventory_mode=True).inventory_quantity = 34
result = quant.action_apply_inventory()
assert not isinstance(result, dict), 'inventory workflow requires attention'
env.ref('factorio_connect_demo.mo_shortage').action_assign()
env.cr.commit()
PY
```

Motor on-hand/reserved becomes34/34, shortage8's reservation becomes8 and its
six-motor warning clears. Other components/dependencies are unchanged by this
specific action. Confirm that the material warning clears in the game's detail.

## Inspect the partial split (from baseline)

```sh
demo_shell <<'PY'
for key in ('mo_partial_done', 'mo_partial_backorder'):
    mo = env.ref('factorio_connect_demo.' + key)
    print(key, mo.name, mo.product_qty, mo.state, mo.production_group_id.id, mo.backorder_sequence)
env.cr.rollback()
PY
```

The two actual generated references share one production group: completed 4,
outstanding 6. Posted pump stock is 14. A synthetic single order at 40% would
misrepresent the split; the panel retains both records and their relationship.

## Complete the remainder (from baseline)

```sh
demo_shell <<'PY'
from odoo.addons.factorio_connect_demo.seed.production import complete
complete(env.ref('factorio_connect_demo.mo_partial_backorder'), 6)
env.cr.commit()
PY
```

This helper uses `set_qty_producing`, public WO start/finish actions and
`button_mark_done`. Six more pumps are posted: pump stock becomes 20, the
remainder leaves active queues and appears in history with its completed sibling.

## Cancel ready10 (from baseline)

```sh
demo_shell <<'PY'
env.ref('factorio_connect_demo.mo_ready').action_cancel()
env.cr.commit()
PY
```

Its operations leave active queues and its component reservations release.
History retains the cancelled order; no posted finished stock is invented.

## Miss a webhook, then recover

In this dedicated demo only, disable native demo rules around one committed
center rename. This deliberately suppresses its notification:

```sh
demo_shell <<'PY'
from odoo.addons.factorio_connect.models.automation import MODELS
rules = env['base.automation'].browse([env.ref('factorio_connect_demo.automation_' + key).id for key in MODELS])
rules.write({'active': False})
env.ref('factorio_connect_demo.wc_assembly').name = 'Assembly reconciliation check'
env.cr.commit()
rules.write({'active': True})
env.cr.commit()
PY
```

Within 65 seconds, the 60-second authoritative read should rename the same station
without duplicating it. Restore its name via the normal work-center UI or ORM;
that subsequent rename may use webhooks normally. Check that all 14 rules are
active after this experiment.

## Source, transport, pause and authority checks

Use `demo stop odoo` while game/bridge run. Retain the last view with source
failure, then stale after 90 seconds. `demo up -d --wait odoo` restores fresh
source reads. Use `demo --profile bridge stop bridge` to show disconnected/stale;
`demo --profile bridge up -d --wait bridge` restarts a full handshake and read.

Pause or save/reload the dedicated map while an Odoo operation changes. The
frozen pause screen cannot update its indicator. On resume/load expect
resynchronizing, latest complete data, then four current increasing heartbeat
sequences with matching successful source timestamp before healthy status.
This verification can take twenty seconds. Dropped buffers cannot justify
showing an old cached read as fresh.

Remove game power/materials around the display: Odoo quantities remain the
recorded truth. Confirm that every station remains visible when idle and that
unrelated entities are preserved. Use the confirmed Local re-pair action only
when intentionally changing saved source authority; it clears tracked display
and binding, never Odoo or unowned entities.

## Single-player GUI acceptance record (requires the licensed client)

These steps remain unexecuted on the development host. Use the packaged
`dist/factorio-connect_0.1.0.zip`, a separate base-only Factorio 2.0.77 mod
folder/save, the rootful deployment from local setup, and the private pairing
settings. Launch with `--enable-lua-udp 34199`. Record real elapsed seconds,
`source_read_at`, published/applied revisions, screenshots and the game log for
each check; keep tokens out of evidence. `./scripts/smoke-demo` reads deployed
health and the receiver's actual application acknowledgment without changing
business data. It does not measure a new commit or verify seed invariants.

1. Confirm ten products, two BOMs, four stations, eight MOs, 22 WOs, 14 posted
   pumps and the six-motor warning. Select every station and inspect idle,
   running, dependency-blocked and material-short records.
   Hover over Assembly machines and verify no menu opens. Click two different
   Assembly machines and verify each panel shows only its own MO/WO. Hover another
   machine and verify the open panel stays on the clicked machine.
   Open **Machine skin**; keep the selector
   open through a source refresh. Choose a furnace and an installed-mod machine
   appearance, then reset one to default. Check inventories and release counts
   before/after, save/reload and verify each machine's choice. Repeat on the small
   Packing overview station and confirm its footprint and labels stay intact.
2. Execute the finish/start commands above. Confirm the running Assembly's
   operation output becomes 10, Inspection becomes ready, then ready Assembly
   starts. Measure each healthy committed change reaching the unpaused game
   within five seconds; posted pump stock stays 14.
3. From a reset baseline, execute the +6 motor inventory adjustment and native
   `action_assign`. Confirm on-hand/reserved 34/34 and the warning clears within
   five seconds. Inspect the actual completed4/backorder6 split and matching
   production group, without replacing them with one percentage.
4. Run the missed-webhook command above; confirm the existing station renames
   within 65 seconds and all 14 native rules are restored.
5. Stop/restart the bridge and stop/restart Odoo as above. Confirm last truth
   remains visible, transport disconnection and source failure are distinct,
   source age advances past 90 seconds without renewing the cached timestamp,
   and recovery resynchronizes before four current heartbeat sequences establish
   health. Confirm the same source/scope binding survives.
6. Pause the game while committing a source change. The paused screen remains
   frozen; resume must resynchronize. Save, exit and load the same save twice;
   require a new bridge challenge each time and no partial/old session apply.
7. Rename Assembly using Odoo, archive it, then add a center in the configured
   company. The renamed station retains its identity, the archived station
   displays its archived state, and the new idle center gets a stable station.
   Inspect unrelated Nauvis entities before/after. For an exact ORM alternative:

   ```sh
   demo_shell <<'PY'
   center = env.ref('factorio_connect_demo.wc_assembly')
   center.name = 'Assembly GUI acceptance'
   env.cr.commit()
   center.active = False
   env.cr.commit()
   env['mrp.workcenter'].create({'name': 'Added GUI center', 'company_id': center.company_id.id})
   env.cr.commit()
   PY
   ```

8. Remove game power/materials and alter game entities; confirm Odoo quantities,
   stock and WO states do not change. Present an alternate source/scope binding
   and require rejection until the deliberate Local re-pair action. Re-pair must
   affect only mod-owned displays and saved binding.

Capture pass/fail and timestamps for each step in `docs/verification.md`. Backend
Lua/socket checks and headless surface checks do not replace this GUI record.
