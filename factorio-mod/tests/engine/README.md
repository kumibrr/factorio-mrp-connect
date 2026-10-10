Run `./scripts/check-factorio-surface --binary /path/to/factorio` with Factorio
2.0.77. The runner creates a unique directory under ignored `runtime/` (or
`--artifacts DIR`), copies the mod and its isolated smoke dependency, generates
a Lua fixture from the canonical PumpWorks snapshot, and uses only `--create`
and two `--benchmark` save loads. Logs, a fresh save, and `report.json` remain in
that directory. It never reads or modifies the user's saves or deployment.

The engine checks all five prototype registrations, four stable protected
stations, workflow belts, native text render handles, actual rename/idempotence,
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
completion box. A component order delivers 60 completion receipts into a shared
product area, while assembly receives only its 10 scaled allocation receipts
and the separately mirrored posted stock remains 46. A crossing-route fixture
checks that newly placed underground pairs do not steal an existing pair's
connection. Both loads check network entity identity and dispatch idempotence.
Network and physical-flow probes update on the mod's six-tick cadence while
native belts and inserters continue moving every tick. Their evidence appears
under `network` and `production` in each load's report.
