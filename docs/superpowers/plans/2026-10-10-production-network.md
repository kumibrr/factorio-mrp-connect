# Production Network Implementation Plan

**Goal:** Connect component supply, operation branches/merges and shared centers.
**Architecture:** Extend pure production planning with DAG and material edges;
use a pure grid router for isolated native belt paths, and owned surface entities
for transport and persistent dispatch ledgers.
**Tech Stack:** Lua 5.2, Factorio 2.0.77, existing snapshot v1.
**Spec:** ../specs/2026-10-10-production-network-design.md

- [x] Add failing planning tests for fork/join graphs, multiple roots, cycles,
  material assignment and scaled reservation budgets. Extend `production.plan`
  and expose BOM/product data from `view_model.build`.
- [x] Test and implement `production_routing.route(start,finish,occupied)`:
  grid paths avoid entities and cross belts using underground pairs.
- [x] Replace straight-line placement in `production_surface.reconcile` with
  stable center areas, shared product buffers and dedicated edge transport.
- [x] Test and implement dependency joins and bounded output fan-out in
  `production_surface.update`; retain clocks, ownership and source authority.
- [x] Extend native transport acceptance to actual branches, joins, shared
  supplies and crossing transport. Run Lua, engine and packaging checks.
- [x] Update walkthrough/architecture and record verification evidence.

Graph tests use a four-operation diamond with dependencies
`A -> B, A -> C, B+C -> D`; D must wait for both receipts. A missing/cyclic
predecessor must omit only its order. Material tests vary reserved quantities
without changing requested quantities. Engine tests retain ready, shortage,
partial output, backpressure and save/load checks while adding network behavior.

Final verification: 76 Lua cases passed; nine packaging/check-harness cases
passed; Factorio 2.0.77 creation and both 12,001-tick loads passed.
Native evidence: `runtime/surface-smoke-szbv9b_d/report.json`. The diamond
completes four markers, shared component receipts total 60, allocated receipts
total 10, and posted stock remains 46. The installable ZIP matches all 20
runtime source files. Independent review findings were addressed, including
material-assignment omission, center reassignment, producer routing identity,
underground isolation, receiver approach and obstruction recovery.
