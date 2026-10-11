# Connected production network

The approved change replaces isolated straight order lanes with work-center
areas connected by native belts. Operations retain their order identity and
Odoo output budgets. Directed acyclic work-order graphs support multiple roots,
fan-out and joins. A branch marker denotes completion of the same workpiece on
one dependency; a join consumes one marker from every predecessor. Branches do
not multiply business output. Cycles, missing predecessors and unequal batch
quantities remain explicit routing warnings.

Shared product buffers connect component production to consuming operations.
Material routes follow the operation assignments in the source BOM and display
Odoo reservation, picked and posted-consumption evidence. They carry scaled
allocation markers: one marker represents the material required for one order
workpiece. A consuming operation waits for all of its material/dependency
receipts. The buffer distinguishes operation-complete receipts from posted stock;
completed work alone never creates available Odoo inventory. Product routes do
not assert a supplier-order assignment absent from the snapshot.
Component output connects to a product/location buffer only when the destination
is unique. An unresolved material-operation assignment excludes the affected
physical order with a warning instead of bypassing its material receipt gate.

Place machines together by work center, stagger adjacent areas and route each
edge separately with underground crossings. Keep inventories, entities and
release/dispatch ledgers across repeated snapshots and save/load. Never mingle
order workpieces on a shared belt. Shared buffers provide the connection across
orders while dedicated branches retain ownership. Rebuild affected orders for
quantity/routing changes and output corrections; preserve unrelated entities.
An obstructed route cannot feed a partially built order.

Validate graph planning, branch/join conservation, material allocations,
crossings, idempotence, correction/deletion and real Factorio transport using
the existing Lua and Factorio 2.0.77 headless checks. GUI appearance requires a
licensed desktop client and remains separate from engine acceptance.
