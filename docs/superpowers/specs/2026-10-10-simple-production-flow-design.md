# Simple production flows

Replace the factory-wide web with compact left-to-right order flows. A serial
order stays on one row. Dependency branches occupy neighboring rows and merge
at a single consuming operation. Each order retains its physical machine
identity; several component inputs combine into that operation, rather than
introducing a shared-machine scheduler across manufacturing orders.

One component-kit feed per operation combines its BOM allocations. A kit marker
represents all material required for one scaled workpiece, and its dispatch
budget is the minimum of every constituent allocation budget. It enters the
same assembler as the workpiece through a second short native belt and inserter.
Both items must physically arrive before recorded Odoo output can release work.
Keep each constituent's allocation ledger, label and correction behavior. Source
details retain individual products and units. Posted stock remains independent.

Allocate stable non-overlapping order cells, with horizontal graph depth and
adjacent branch rows. Keep shared product-stock displays compact and retain
component completion associations. Remove per-component long transport routes
and verbose per-edge world labels. Simple seeded orders require no underground
belts between their own operations or for their local component feeds.

Preserve branch/join conservation, ready/shortage holds, native backpressure,
partial-output budgets, unrelated entities, same-snapshot identity and save/load.
Version the layout fingerprint so the next reconciliation replaces the old web.
Verify reduced belt counts and native kit/workpiece convergence alongside the
existing native branch/merge and stock-separation acceptance.

## Further simplification — 2026-10-11

User feedback identifies belt routes and extra boxes as the remaining clutter.
Use direct native belts wherever an operation has one successor and that
successor has one predecessor. Such edges omit dispatch and receipt boxes;
native output and gated input inserters connect the machines. A serial order
has only its initial input and final output boxes, plus any combined component
kit sources. Serial machines use 16-tile spacing. Actual forks and joins retain
separate receipt accounting and 24-tile spacing for their local ports.

Remove the inactive work-center overview belt network, which duplicates the
physical production flows. Associate completed components with the product area
through the producer's existing output box rather than a physical return belt.
Posted-stock mirrors and allocation budgets remain separate. The snapshot lacks
supplier-order provenance, so this association does not imply that a particular
producer supplied a particular reservation.

Version the layout fingerprint to rebuild older owned flows on reconciliation.
Keep unrelated entities, repeated-snapshot identity, save/load, downward
corrections, ready/blocked input gates and exact source-output limits.
