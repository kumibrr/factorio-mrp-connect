# Simple Production Flow Implementation Plan

**Goal:** Compact normal production, with understandable local splits and merges.
**Architecture:** A pure order-cell layout gives graph depth and branch rows;
production surface transport combines material allocations into one native kit
feed per operation while preserving dependency gates and source authority.
**Tech Stack:** Lua 5.2, Factorio 2.0.77, snapshot v1.
**Spec:** ../specs/2026-10-10-simple-production-flow-design.md

- [x] Add failing regressions for straight compact chains, adjacent fork/merge
  operations, bounded layout size, and combined component feeds that wait for
  every allocation and both native assembler inputs.
- [x] Implement stable cells and local routes; add the component-kit item and
  recipe variants. Preserve per-material correction/dispatch accounting and
  operation entity identity on repeated snapshots.
- [x] Update native acceptance for kit/workpiece convergence, simpler layout,
  ready/shortage gates and save/load. Run Lua, Factorio and packaging checks.
- [x] Review the final change and update the walkthrough, architecture,
  verification evidence and installable mod archive.

Confirmed by the user: combine component inputs for each order, with simple local
splits and merges. Each order retains its machines.

Evidence: 81 Lua cases pass; the strengthened network regression passes all eight
focused cases. Nine packaging/check-harness cases pass. Native Factorio creation
and two 12,001-tick loads pass in `runtime/surface-smoke-dkg4c80a/report.json`,
with 390 production belts, 13 kit feeds, conserved allocations and native inputs
converging in one assembler. Independent review found no actionable findings.
The installable archive has 21 runtime files matching source byte-for-byte and
valid ZIP CRCs; its checksum is recorded in `docs/verification.md`.

## Further simplification — 2026-10-11

The user's belt/box feedback is addressed by direct one-to-one machine belts,
two boxes per ordinary serial order, local producer completion receipt aliases,
and removal of the duplicate decorative work-center network. Real fork/join
accounting and combined component inputs remain intact. Updated spec and
walkthrough describe these changes.

Verification: 83 Lua cases, nine packaging/check-harness cases, native creation
and both 12,001-tick loads pass. `runtime/surface-smoke-xx08xf1b/report.json`
records 251 production belts, 27 production boxes, 13 kit feeds and no decorative
belts; serial three-stage transport has two boxes and 26 belt tiles. Independent
review found no actionable Critical or Important findings. The regenerated
archive's 21 runtime files match source byte-for-byte and all ZIP CRCs validate.
