Run `./scripts/check-factorio-surface --binary /path/to/factorio` with Factorio
2.0.77. The runner creates a unique directory under ignored `runtime/` (or
`--artifacts DIR`), copies the mod and its isolated smoke dependency, generates
a Lua fixture from the canonical PumpWorks snapshot, and uses only `--create`
and two `--benchmark` save loads. Logs, a fresh save, and `report.json` remain in
that directory. It never reads or modifies the user's saves or deployment.

The engine checks all five prototype registrations, four stable protected
stations, removal of decorative workflow belts, native text render handles, actual rename/idempotence,
tracked cleanup preserving an unrelated chest, seeded display counts and stock,
and serialized entity/render identity across two loads. This is a synthetic
snapshot fixture. It does not establish live Odoo/UDP behavior or execute a GUI.
Task 9 still requires the licensed single-player client for actual GUI acceptance.

Physical-flow acceptance additionally runs 12,001 ticks on each save load using
real prototype inventories, powered inserters and moving belts. It checks a full
TODO belt leaves work in the source box, ready work stays on its belt, shortage
holds the source feed, no elapsed ticks invent output, partial output releases
exactly three markers, downstream stages stay gated, and all 80 completed markers
reach the final box. A separately initialized partial-output lane is saved with
three released markers; both loads preserve its entity identity and release
ledger without duplicating output. This validates persisted partial state, not a
mid-benchmark server save. Same-snapshot reconciliation preserves lane identity
and does not refill the source box. `report.json` contains production evidence
for both benchmark runs. Desktop GUI appearance remains unexecuted.

Connected-network acceptance adds a native four-operation diamond. One branch
finishes while the other is held; the join must retain the first receipt and
release nothing until both arrive. All four final markers must then reach the
completion box. A component order retains 60 completion receipts in its existing
output box with no return route, while assembly receives a conserved allocation of 10 component kits
and the separately mirrored posted stock remains 46. A crossing-route fixture
checks that newly placed underground pairs do not steal an existing pair's
connection. Compact-flow acceptance additionally checks the seeded production
uses fewer than 300 belts and no more than 27 production boxes; posted-stock
display boxes are separate. Serial stages share one row with 16-tile spacing.
A three-stage order without materials has exactly two boxes and 26 belt tiles,
with intermediate work carried directly between machines. Actual branched orders
retain 24-tile spacing for their local receipt ports.
Component allocations form one kit feed per operation. Real kit and workpiece
items enter the same assembler through separate inserters, while the total ten
allocated kit markers remain conserved across source, belts, inserter hands and
assembler inventory. Native ingredient-buffer limits can leave some kits waiting
on the belt. Both loads check network entity identity and dispatch idempotence.
Network and physical-flow probes update on the mod's six-tick cadence while
native belts and inserters continue moving every tick. Their evidence appears
under `network` and `production` in each load's report.

The skin probe discovers base-machine appearances and an assembler supplied by
the dependent smoke mod. It swaps a partially released machine to that skin,
resets it, and swaps it back, retaining real input/output inventories, recipe,
component-kit feed targets, ledger and the lane. The fixture machine's name
contains `underground-belt` to check appearance names cannot change routing types.
It checks station render handles survive replacement and
the small Packing station retains its collision footprint. Both loads verify
the saved production/station choices and entity identity. `report.json` records
skin evidence for creation and both loads. The headless runner has no GUI player;
Lua GUI tests simulate events, and desktop hover/selector acceptance remains in
the demo walkthrough.
