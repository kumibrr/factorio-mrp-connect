# Physical Odoo production flow

The requested flow is Odoo-driven. Factorio remains read-only and cannot create
business output by running a recipe. Each supported manufacturing order gets a
stable, isolated physical lane: raw-material box → powered inserter → TODO belt
→ input inserter → processing machine → output inserter → belt → next machine
→ final production-complete box. Existing center summaries and BOM links remain
an overview; physical lanes carry workpiece markers rather than stock records.

Machines have separate native input/output inventories. Scripts convert incoming
markers into output only up to accepted work-order output, or full completion.
Input inserters wait until the operation is running or has reported output;
ready/blocked work stays visible on its incoming belt. Native inventory and belt
capacity provide backpressure; scripts never inject directly onto belts. Material
warnings hold the raw-material feed. Terminal cancellation removes its lane.

Markers represent the first operation's required quantity less carried output.
There are at most 200 markers per lane; fractional/large quantities are scaled
and explicitly labelled. Carried backorder output is not produced again. Lanes
follow actual work-order dependencies; ambiguous, branched, cyclic, unequal-batch
or missing dependencies produce a visible warning instead of inventing routing.

Persist entity references, lane positions and per-operation release counts through
save/load. Repeated snapshots never reseed existing work. Quantity/routing changes
rebuild only the affected lane; deletion/reset cleans only tracked entities.
Obstructions keep source details available and are retried without destroying
unrelated entities. A partially built lane never feeds items.

Machine labels show state, recorded elapsed time, expected duration, and estimated
remaining time when both are known. An explicitly labelled observed running timer
uses unpaused game ticks only while source/connection are healthy; it is distinct
from Odoo's recorded duration and cannot claim wall-clock freshness. GUI shows the
same timing evidence. Completion-box contents are operation-complete markers,
not posted Odoo inventory.

Validation covers pure routing/scaling/timing logic and real Factorio 2.0.77
transport, output gating, full belts, shortage holds, idempotence, ownership and
save/load. Desktop GUI acceptance remains a separate licensed-client check.
