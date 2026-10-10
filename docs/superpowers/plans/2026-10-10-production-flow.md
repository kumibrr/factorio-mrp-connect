# Physical Production Flow Implementation Plan

**Goal:** Display Odoo production using native boxes, inserters, belts and machines.
**Spec:** ../specs/2026-10-10-production-flow-design.md
**Architecture:** Pure flow planning and timing in scripts/production.lua;
owned physical entities and transport gating in scripts/production_surface.lua.
The existing surface/control/GUI integrate these modules.
**Tech stack:** Factorio 2.0.77, Lua 5.2, existing snapshot v1.

- [x] Add failing Lua tests for dependency routing, backorder quantities, bounded
  scaling, unsupported flows, output budgets and truthful timing.
- [x] Implement production planning; expose dependency IDs and source units in
  the view model. Run focused Lua tests.
- [x] Add an engine fixture that asserts native machine inventories, real item
  transport, ready/running/done gates, partial output, belt backpressure and final
  completion. Run it to establish failure against decorative displays.
- [x] Add workpiece items, locked recipes, void-powered inserters and assembler
  prototypes with native input/output inventories.
- [x] Build stable owned lanes and apply Odoo output budgets. Integrate tick
  updates, machine selection and cleanup. Run Lua and native-engine checks.
- [x] Expose running/expected/remaining/observed timing on machines and GUI;
  revise the legend and walkthrough to explain visual marker semantics.
- [x] Review changes, fix findings, run final Lua/engine/packaging checks and
  document evidence and the desktop GUI limitation.

Verified: 59 Lua tests; 9 packaging/harness tests; native Factorio create plus two
12,001-tick save loads with backpressure, partial output, ready/shortage holds,
completion and persisted partial ledger checks. Archive generated and checked.
Independent review findings fixed. Desktop GUI acceptance remains unexecuted.
