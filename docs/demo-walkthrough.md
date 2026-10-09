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

Select each station for order references, quantities and material evidence.
Assembly's raw center status `done` means In Progress here. Shortage Assembly
is operation-ready and material-short simultaneously; blocked Inspection and
Packing are waiting for predecessors. No Factorio inventory or power determines
these states. Order origin markers identify scenarios regardless of generated
MO sequence numbers.

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
