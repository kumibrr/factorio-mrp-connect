# PumpWorks demo: complete Odoo seed specification

Date: 2026-10-09

Status: approved normative companion to the [system design](2026-10-09-factorio-odoo-mrp-design.md).
Values below are required seed outcomes, not claims
that an Odoo instance has already been seeded.

## Fixture identity and initialization

Load Odoo without its generic demo data. Install `mrp`, `stock`,
`base_automation`, `factorio_connect`, and `factorio_connect_demo`; resolve
their normal dependency modules through Odoo. No Enterprise modules, purchasing
workflow, sales orders, accounting entries, or external equipment are required.

All demo-owned records have stable XML IDs in `factorio_connect_demo`. Tables
below show each ID suffix. Aliases for core/generated records point to the
existing record rather than creating a duplicate. Numeric database IDs and
Odoo-generated MO names are intentionally not fixed.

The seed runner stores a versioned seed manifest with `seed_version=1`, the
selected company/warehouse, UTC initialization time `T0`, fixture IDs, generated
MO/WO relationships, and expected assertions. A successfully initialized seed
rerun only checks identity/completeness; it neither posts inventory again nor
overwrites subsequent operator edits. A partial seed initialization rolls back
its business-data transaction. Missing or conflicting fixtures produce an
actionable error instead of silent duplication.

## Company, warehouse, units, and configuration

| XML ID suffix | Model | Required value or relationship |
| --- | --- | --- |
| `company` | `res.company` | Reuse the clean database's main company; name `PumpWorks Demo`; EUR currency |
| `warehouse` | `stock.warehouse` | Reuse/configure its single warehouse; name `PumpWorks`; code `PUMP`; company above |
| `location_view` | `stock.location` | Alias warehouse view location; parent of the warehouse's internal locations |
| `location_stock` | `stock.location` | Alias warehouse stock location, `PUMP/Stock`; `usage=internal` |
| `location_production` | `stock.location` | Resolve the company's virtual production location; `usage=production` |
| `location_inventory` | `stock.location` | Resolve the inventory-adjustment location used by opening adjustments; `usage=inventory` |
| `manufacturing_type` | `stock.picking.type` | Warehouse manufacturing operation type; source/destination `PUMP/Stock`; one-step manufacturing; backorders `always` |
| `uom_unit` | `uom.uom` | Alias standard Unit; quantity rounding 1; all products/BOMs/orders use it |
| `category_components` | `product.category` | `PumpWorks / Components`; standard default category configuration |
| `category_manufactured` | `product.category` | `PumpWorks / Manufactured`; standard default category configuration |
| `route_manufacture` | `stock.route` | Resolve warehouse Manufacture route; used only by the two manufactured products |
| `calendar` | `resource.calendar` | `PumpWorks Day Shift`; timezone `Europe/Madrid`; company above |

Currency, units, virtual locations, the warehouse hierarchy, and the Manufacture
route are normal Odoo prerequisites. Resolve their official defaults and validate
relationships; do not seed competing copies. The integration snapshot includes
only internal locations under the selected warehouse. Virtual locations exist
for posting production/inventory movements and are excluded from on-hand totals.

Enable work orders and operation dependencies. Use no Make To Order route,
reordering rules, scheduled replenishment, alternative BOMs, variants, lots,
serial numbers, or scrap. Consequently the runner, rather than procurement,
creates the intended MOs. All seed products are stock-managed goods:
`type='consu'`, `is_storable=True`, `tracking='none'`. Nominal standard costs are
zero; this dataset makes no financial valuation claim.

The calendar has exactly ten demo attendance records, IDs
`attendance_mon_am`, `attendance_mon_pm`, through `attendance_fri_am` and
`attendance_fri_pm`: weekdays Monday–Friday, 08:00–12:00 and 13:00–17:00 local
time. No weekend attendance or holiday overrides are seeded.

## Users and integration configuration

| XML ID suffix | Model | Required purpose |
| --- | --- | --- |
| `operator` | `res.users` | Login `demo.operator`; internal manufacturing/inventory operator; only the demo company; timezone `Europe/Madrid`; language `en_US` |
| `integration_user` | `res.users` | Login `factorio.bridge`; custom read-only integration group; only the demo company; language `en_US` |
| `integration_config` | Integration addon's configuration | Selected company/warehouse, enabled export, terminal retention 7 days, webhook target from runtime environment |
| `seed_manifest` | Demo addon's manifest | Seed version/time/record identities and baseline assertion metadata |

The bootstrap administrator loads/configures fixtures. The operator performs
the walkthrough. The integration user reads snapshots and has no business
create/write/delete rights. Generate both users' credentials and the scoped
API key during bootstrap, outside fixture files. API keys, passwords, webhook
tokens, UDP pairing tokens, and localhost paths are runtime configuration,
not committed seed literals.

## Products and opening stock

One product template and its single generated variant exist per row. ID suffixes
identify the variants; corresponding template IDs use the suffix `_template`.
Opening stock is posted once through inventory adjustments at `PUMP/Stock`,
before production. It is not the final stock after the scenario workflows.

| XML ID suffix | SKU | Name | Category | Supply | Opening units |
| --- | --- | --- | --- | --- | ---: |
| `product_blank` | `PW-BLANK` | Impeller blank | Components | Purchased material | 100 |
| `product_housing` | `PW-HOUSING` | Pump housing | Components | Purchased material | 100 |
| `product_motor` | `PW-MOTOR` | Electric motor | Components | Purchased material | 42 |
| `product_shaft` | `PW-SHAFT` | Pump shaft | Components | Purchased material | 100 |
| `product_bearing` | `PW-BEARING` | Bearing | Components | Purchased material | 200 |
| `product_seal` | `PW-SEAL` | Seal kit | Components | Purchased material | 100 |
| `product_fastener` | `PW-FASTENER` | Fastener kit | Components | Purchased material | 100 |
| `product_carton` | `PW-CARTON` | Shipping carton | Components | Purchased material | 100 |
| `product_impeller` | `PW-IMPELLER` | Machined impeller | Manufactured | Manufacture | 0 |
| `product_pump` | `PW-PUMP` | Finished pump | Manufactured | Manufacture | 0 |

The eight nonzero opening adjustments use manifest keys
`opening_<product-suffix>` and Odoo's inventory-apply workflow. Zero-stock products
need no artificial zero-quantity move. Generated quants/move IDs are captured in
the manifest as applicable; their database counts are not fixed because Odoo
can merge/split stock records.

## Work centers, resources, and timing reasons

| XML ID suffix | Code | Name | Capacity | Efficiency | Setup/cleanup minutes |
| --- | --- | --- | ---: | ---: | --- |
| `wc_machining` | `MACH` | Machining | 1 | 100% | 0 / 0 |
| `wc_assembly` | `ASSY` | Assembly | 1 | 100% | 0 / 0 |
| `wc_inspection` | `INSP` | Inspection | 1 | 100% | 0 / 0 |
| `wc_packing` | `PACK` | Packing | 1 | 100% | 0 / 0 |

Each center is active, belongs to the demo company, uses `calendar`, and has
zero hourly cost and no alternate center. Alias each automatically generated
`resource.resource` as `resource_machining`, `resource_assembly`,
`resource_inspection`, or `resource_packing`; no duplicate physical resource is
added.

Resolve and alias the normal timing reasons selected by Odoo's timer workflow:
`loss_productive` with `loss_type=productive` and `loss_performance` with
`loss_type=performance`. Use the standard records installed by MRP rather than
creating competing reasons. Productivity records come from the work-order
start/finish actions described below. At baseline, only the running Assembly
operation has an open productivity entry; all completed operations' entries
are closed. Exact closed-entry counts/durations are not fixed, since Odoo may
split productive and performance time.

## BOMs, component lines, and operation dependencies

Both BOMs have `type=normal`, output quantity 1 Unit, the demo company and
manufacturing operation type, noncontinuous production, and
`ready_to_produce=all_available`. The seed consumes exactly the listed component
quantities through standard validation; it does not assume an older-version
configurable BOM consumption-mode field.

`bom_impeller` produces `product_impeller`:

| Component line ID suffix | Component | Units per impeller | Consuming operation |
| --- | --- | ---: | --- |
| `bom_impeller_blank` | Impeller blank | 1 | Machine impeller |

`bom_pump` produces `product_pump`:

| Component line ID suffix | Component | Units per pump | Consuming operation |
| --- | --- | ---: | --- |
| `bom_pump_housing` | Pump housing | 1 | Assemble pump |
| `bom_pump_motor` | Electric motor | 1 | Assemble pump |
| `bom_pump_shaft` | Pump shaft | 1 | Assemble pump |
| `bom_pump_bearing` | Bearing | 2 | Assemble pump |
| `bom_pump_seal` | Seal kit | 1 | Assemble pump |
| `bom_pump_fastener` | Fastener kit | 1 | Assemble pump |
| `bom_pump_impeller` | Machined impeller | 1 | Assemble pump |
| `bom_pump_carton` | Shipping carton | 1 | Pack pump |

Four `mrp.routing.workcenter` operation records are required:

| Operation ID suffix | BOM | Name | Center | Sequence | Manual cycle minutes | Predecessor |
| --- | --- | --- | --- | ---: | ---: | --- |
| `operation_machine` | Impeller | Machine impeller | Machining | 10 | 2 | None |
| `operation_assemble` | Pump | Assemble pump | Assembly | 10 | 5 | None |
| `operation_inspect` | Pump | Inspect pump | Inspection | 20 | 2 | Assemble pump |
| `operation_pack` | Pump | Pack pump | Packing | 30 | 1 | Inspect pump |

Use manual cycle-time computation. Enable `allow_operation_dependencies` and
populate `blocked_by_operation_ids` on pump operations. Odoo generates the WO
dependency graph; do not substitute sequence numbers for explicit dependencies.
[Community operation source](https://github.com/odoo/odoo/blob/20.0/addons/mrp/models/mrp_routing.py).

The intended station graph is Machining → Assembly → Inspection → Packing.
The first edge expresses the impeller BOM supply dependency, not observed
transport or a claimed parent-child relationship between manually created MOs.

## Manufacturing scenarios and stable references

The runner creates seven initial MOs. Partial completion generates an eighth.
MO names use Odoo's normal sequence; each initial order has the stable `origin`
shown below. Preserve/set the partial sibling's editable origin to the same
`FC-DEMO/PARTIAL` marker for demo lookup. Keep Odoo's generated split references.

| MO XML ID suffix | Origin | Product | Initial request | Baseline requested / posted units | Baseline MO state |
| --- | --- | --- | ---: | --- | --- |
| `mo_impeller_done` | `FC-DEMO/IMPELLER-DONE` | Impeller | 60 | 60 / 60 | `done` |
| `mo_pump_done` | `FC-DEMO/PUMP-DONE` | Pump | 10 | 10 / 10 | `done` |
| `mo_partial_done` | `FC-DEMO/PARTIAL` | Pump | 10 before split | 4 / 4 | `done` |
| `mo_partial_backorder` | `FC-DEMO/PARTIAL` | Pump | Generated remainder | 6 / 0 | `confirmed` |
| `mo_ready` | `FC-DEMO/READY` | Pump | 10 | 10 / 0 | `confirmed` |
| `mo_running` | `FC-DEMO/RUNNING` | Pump | 10 | 10 / 0 | `progress` |
| `mo_shortage` | `FC-DEMO/SHORTAGE` | Pump | 8 | 8 / 0 | `confirmed` |
| `mo_cancelled` | `FC-DEMO/CANCELLED` | Pump | 5 | 5 / 0 | `cancel` |

All orders have standard priority, no lots, and stock source/destination
`PUMP/Stock`. No unrelated child MOs are generated. The partial pair shares
Odoo's production group and has generated backorder sequence values. Its
original request is represented by the resulting compatible quantities 4+6;
the completed MO's own requested quantity is now 4, not 10.

Planned starts are editable business inputs, not synthetic timer logs:

| Scenario | Planned start before workflow actions | Deadline |
| --- | --- | --- |
| Completed impeller/pump | `T0` | `T0 + 1 hour` |
| Partial original and generated remainder | `T0` | `T0 + 4 hours` |
| Ready | `T0 + 1 hour` | `T0 + 2 hours` |
| Running | `T0` | `T0 + 1 hour` |
| Shortage | `T0 - 2 hours` | `T0 - 1 hour` |
| Cancelled | `T0 + 1 hour` | `T0 + 3 hours` |

The baseline shortage is also overdue, by comparison with its deadline.
Actual start/completion times and timer durations come from workflow actions
and will differ by seed execution time. Do not force a calendar slot or promise
an exact computed duration. The overdue indicator is separate from Odoo's
material availability enum.

## Required workflow execution order

Execute with the demo company context and a manufacturing-capable seed user.
Flush/recompute through Odoo's ORM before validating; never update computed MO
states, quant reservations, or WO states directly to produce the desired view.

1. Create/resolve configuration, users, products, centers, BOMs, and operations.
   Apply the opening inventory adjustments through Odoo's inventory workflow.
2. Create the impeller MO60; confirm and reserve. Set editable
   `qty_producing=60`, call `set_qty_producing()`, start/finish its machining
   operation, then complete the MO with `button_mark_done()`.
3. Create pump MO10 for completed production; confirm/reserve, set producing
   quantity 10 through the same public workflow, start/finish Assembly,
   Inspection, Packing in order, and complete the MO. This consumes ten of each
   single-unit component and twenty bearings.
4. Create the partial pump MO10; confirm/reserve. Set `qty_producing=4` and
   call `set_qty_producing()`. Start/finish all three operations for those four
   units, then call `button_mark_done()`. With backorders configured `always`,
   use the normal automatic split workflow; assert a completed MO4 and an
   outstanding sibling MO6. Assign stable XML IDs to both and their WOs, and
   reserve the remainder's components. Handle any returned workflow action;
   do not bypass validation using arbitrary state writes.
5. Create/confirm/reserve ready pump MO10, then running pump MO10. Start only
   the running order's Assembly WO with `button_start()`. Do not record output
   or finish that operation: it remains at zero produced units and preserves
   reservations for ten pumps.
6. Create/confirm the cancelled MO5, attempt normal reservation, then cancel
   using `action_cancel()`. Confirm its reservations have been released.
7. Create/confirm shortage MO8 and reserve last. Only two motors remain
   reservable, leaving six motors missing. Reserve all its other components.
8. Resolve generated stock/productivity/group records into the manifest,
   validate all baseline invariants, and finalize the seed version once.
   Configure/enable webhook actions and trigger the initial bridge refresh
   after committed seed data is available.

The partial workflow uses source-verified Odoo 20 public actions.
[MO completion and split workflow](https://github.com/odoo/odoo/blob/20.0/addons/mrp/models/mrp_production.py),
[WO start/finish](https://github.com/odoo/odoo/blob/20.0/addons/mrp/models/mrp_workorder.py),
[backorder wizard](https://github.com/odoo/odoo/blob/20.0/addons/mrp/wizard/mrp_production_backorder.py).
Actual generated outcomes must still be checked in runtime integration tests.

## Expected work orders and Factorio view

Assign each generated WO the XML ID suffix `wo_<scenario>_<operation>`, removing
the table IDs' `mo_` and `operation_` prefixes.
Examples: `wo_running_assemble`, `wo_partial_backorder_inspect`,
`wo_impeller_done_machine`. Resolve by MO and operation ID, not translated
display name. There are 22 WOs: one impeller operation plus three operations
for each of seven resulting pump MOs.

| MO scenario | Machining WO | Assembly WO | Inspection WO | Packing WO |
| --- | --- | --- | --- | --- |
| Impeller done60 | `done`, 60 output | Not applicable | Not applicable | Not applicable |
| Pump done10 | Not applicable | `done`, 10 output | `done`, 10 output | `done`, 10 output |
| Partial done4 | Not applicable | `done`, 4 output | `done`, 4 output | `done`, 4 output |
| Backorder6 | Not applicable | `ready`, 0 output | `blocked`, 0 output | `blocked`, 0 output |
| Ready10 | Not applicable | `ready`, 0 output | `blocked`, 0 output | `blocked`, 0 output |
| Running10 | Not applicable | `progress`, 0 output | `blocked`, 0 output | `blocked`, 0 output |
| Shortage8 | Not applicable | `ready`, 0 output; material warning | `blocked`, 0 output | `blocked`, 0 output |
| Cancelled5 | Not applicable | `cancel` | `cancel` | `cancel` |

The ready state on the shortage's first WO is intentional: it has no unfinished
operation predecessor. It is not evidence that its materials are available.
The MO's reservation status is waiting/`confirmed`, with unavailable components.
Inspection/Packing are dependency blocked. Odoo's WO state and time/quantity
semantics are distinct. [WO computations](https://github.com/odoo/odoo/blob/20.0/addons/mrp/models/mrp_workorder.py).

Expected stations:

- Machining: idle, with completed impeller60 in history.
- Assembly: one running order; three ready orders (backorder6, ready10,
  shortage8), of which shortage8 has a material warning; completed pump10 and
  partial4 plus cancelled5 in history. Its raw center working state is `done`,
  which is labelled In Progress in this model.
- Inspection: four dependency-blocked active orders; completed/cancelled history.
- Packing: four dependency-blocked active orders; completed/cancelled history.

All four stations remain visible when idle. Show the partial sibling references
as completed4 and outstanding6, rather than a fabricated single MO at 40%.
Finished stock is 14 pumps; operation outputs from Assembly/Inspection/Packing
are not added together as three separate finished outputs.

## Inventory and reservation invariants

At baseline, 60 blanks have been consumed into impellers and 14 pumps posted.
Outstanding component demand is for ready10 + running10 + backorder6 +
shortage8 = 34 pumps. Cancelled5 reserves nothing.

| SKU | Opening | Posted consumed | Posted produced | On hand | Reserved | Free |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `PW-BLANK` | 100 | 60 | 0 | 40 | 0 | 40 |
| `PW-HOUSING` | 100 | 14 | 0 | 86 | 34 | 52 |
| `PW-MOTOR` | 42 | 14 | 0 | 28 | 28 | 0 |
| `PW-SHAFT` | 100 | 14 | 0 | 86 | 34 | 52 |
| `PW-BEARING` | 200 | 28 | 0 | 172 | 68 | 104 |
| `PW-SEAL` | 100 | 14 | 0 | 86 | 34 | 52 |
| `PW-FASTENER` | 100 | 14 | 0 | 86 | 34 | 52 |
| `PW-CARTON` | 100 | 14 | 0 | 86 | 34 | 52 |
| `PW-IMPELLER` | 0 | 14 | 60 | 46 | 34 | 12 |
| `PW-PUMP` | 0 | 0 | 14 | 14 | 0 | 14 |

These totals cover `PUMP/Stock`, with no other internal stock locations seeded.
For each row, `on_hand = opening - consumed + produced` and
`free = on_hand - reserved`. Negative stock is not part of this scenario.

Motor reservation by order:

| MO | Motor demand | Reserved motors | Unreserved demand |
| --- | ---: | ---: | ---: |
| Ready10 | 10 | 10 | 0 |
| Running10 | 10 | 10 | 0 |
| Backorder6 | 6 | 6 | 0 |
| Shortage8 | 8 | 2 | 6 |

Each nonmotor component is fully reserved for all four outstanding MOs;
bearings require twice the pump quantity. Explain the shortage as six motors
missing against the shortage MO's own demand, not eight missing because global
free quantity is zero. Preserve move-line reservation and picked/posted
consumption distinctions when reading live data.

## Automation records

Create one scoped create/update automation and one linked webhook server action
per model below. ID suffixes are `automation_<key>` and `webhook_<key>`.
Use the integration configuration to generate the target URL with its runtime
token. Set no selected business fields: built-in `_model`, `_id`, and `_action`
metadata requests a scope refresh. There is no custom payload-signature or retry
queue requirement in this demo.

| Key | Model | Relevant changes |
| --- | --- | --- |
| `workcenter` | `mrp.workcenter` | Create, name/code, archive, capacity/calendar |
| `production` | `mrp.production` | Orders, quantities, state, dates, BOM/group |
| `workorder` | `mrp.workorder` | State, output, center, dependencies |
| `productivity` | `mrp.workcenter.productivity` | Timer start/end and loss association |
| `loss` | `mrp.workcenter.productivity.loss` | Availability/time reason changes |
| `bom` | `mrp.bom` | Output, active configuration, dependency settings |
| `bom_line` | `mrp.bom.line` | Components, quantity, consuming operation |
| `operation` | `mrp.routing.workcenter` | Center, sequence, dependencies, timing |
| `product` | `product.product` | Variant identifier and stock-related fields |
| `template` | `product.template` | Name, stock management, product configuration |
| `unit` | `uom.uom` | Unit name, precision/conversion |
| `move` | `stock.move` | Demands, picked/done/cancelled state, locations |
| `move_line` | `stock.move.line` | Reservations, quantities, locations |
| `quant` | `stock.quant` | On-hand/reserved changes and inventory application |

That is 14 automation rules and 14 server actions. For models with a company
field, include the demo company and shared records (`company_id=False`). For
quants, additionally restrict locations to descendants of `location_stock`.
For shared models without a company field, conservatively refresh the selected
scope. Do not filter on active status, so archiving still triggers a refresh.
Use no update-field filter: every create/update meeting the domain notifies.
Deletion, direct SQL stock
maintenance, calendar changes, and nonstored computations are covered by full
reconciliation even if no rule fires.

## Verification walkthrough contract

The implemented guide must give exact UI navigation or runnable commands for
each action and identify the source order by origin/XML ID, not a hardcoded
sequence number. The following scenarios can be verified independently from
the baseline; reset requirements and post-action balances must be explicit.

| Check | Odoo action | Expected Factorio result |
| --- | --- | --- |
| Initial load | Read committed seeded factory | Four stations, 8 MOs/22 WOs in detail, 14 posted pumps, six-motor warning |
| Finish an operation | Finish running10 Assembly | Its operation shows completed10; Inspection becomes ready; MO output/stock posting remains separately labelled |
| Start work | After releasing the running Assembly slot, start ready10 Assembly | Assembly shows that order running, without simulated output growth |
| Resolve shortage | From baseline, adjust motor stock from 28 to 34 through inventory workflow; reserve shortage8 | Its motor reservation becomes8 and the six-motor warning clears; all 34 motors are reserved |
| Inspect partial output | Open the two partial references | Completed order4 and remaining order6; posted pump stock14 before further production |
| Complete remainder | From baseline, complete backorder6 through all three operations and close the MO | Six more pumps posted; pump stock20; remainder leaves active queues |
| Cancel | From baseline, cancel ready10 through normal action | It leaves active queues; its component reservations release |
| Missed webhook | Suppress delivery of one test notification after a committed change | 60-second reconciliation corrects the view within 65 seconds |
| Source outage | Stop Odoo while bridge/game run | Retained view shows source failure/staleness; recovered source read restores health |
| Transport outage | Stop bridge or drop UDP, then restore | Disconnected/stale state followed by a latest full snapshot |
| Pause/save/reload | Pause or reload while Odoo changes | Resynchronizing on resume/load; latest complete state replaces the retained view |
| Source authority | Remove game power or materials | Odoo-recorded status/quantities remain authoritative |

Record source snapshot revision/timestamp and applied-game acknowledgment during
verification. Healthy unpaused webhook-driven changes target five seconds in
the seeded demo. Seed verification must compare records, relationships, and
inventory against this document; a screenshot alone is insufficient.

## Reset and completion requirements

The future seed command exposes separate nonmutating verification and explicit
demo reset operations. Reset is never part of an ordinary seed rerun. Document
the exact project-labelled database/bridge volumes and Factorio demo save,
backup instructions, and how to restore the baseline without targeting unrelated
databases, containers, or saves. Changing the source database identity requires
new pairing/full initialization of the mod's dedicated demo view.

The seed is accepted only after an actual Odoo 20 run proves the required states,
8 MOs/22 WOs, product/BOM/center identities, backorder linkage, inventory and
reservation balances, automation configuration, read-only export permissions,
and idempotent rerun. Any source-version difference is resolved by changing the
workflow and reviewing the resulting fixture contract, not by forcing a
computed field to the expected value.
