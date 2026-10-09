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
