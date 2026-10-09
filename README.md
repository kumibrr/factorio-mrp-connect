<img src="assets/icon.svg" width="64" height="64" alt="">

# factorio-connect

Reflect a self-hosted Odoo MRP factory automatically in Factorio: work centers,
work orders, production quantities, BOM dependencies, and material availability.
Odoo supplies the production truth; Factorio supplies the operational view.

The project currently contains a design specification. The mod, bridge,
Odoo addons, Docker setup, and runnable demo are implementation deliverables.

## Specifications

- [System design](docs/superpowers/specs/2026-10-09-factorio-odoo-mrp-design.md):
  agreed scope, architecture, webhook and UDP behavior, visualization,
  documentation contract, and acceptance criteria.
- [Complete demo seed specification](docs/superpowers/specs/2026-10-09-factorio-odoo-mrp-seed-data.md):
  factory records, products, BOMs, inventory, production scenarios, seeding
  workflow, expected balances, and verification walkthrough.

The first demo targets Linux, Odoo 20 Community in Docker Compose, and a
separately installed single-player Factorio 2.0 client. Odoo webhooks trigger
updates; a full refresh every 60 seconds recovers missed notifications.

Created in [T3 Code](https://t3.codes).
