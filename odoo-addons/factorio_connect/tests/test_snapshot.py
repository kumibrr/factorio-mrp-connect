from datetime import timedelta
from unittest.mock import patch

from odoo import fields, sql_db
from odoo.tests import tagged

from .common import FactoryCase


@tagged('post_install', '-at_install')
class TestSnapshot(FactoryCase):
    # Catches missing records, guessed quantities, and caller-selected scope.
    def test_export_contract(self):
        snapshot = self.snapshot(allowed_company_ids=[self.foreign_company.id], company_id=self.foreign_company.id,
                                 warehouse_id=self.foreign_warehouse.id, active_test=True)
        self.assertEqual(snapshot.get('meta', {}).get('company_id'), self.company.id)
        self.assertEqual(snapshot['meta']['scope_id'], f'company:{self.company.id}/warehouse:{self.warehouse.id}')
        self.assertEqual(snapshot['meta']['source_id'], self.config.source_id)
        mos = {row['id']: row for row in snapshot['manufacturing_orders']}
        self.assertIn(self.mo.id, mos)
        self.assertNotIn(self.foreign_mo.id, mos)
        self.assertEqual(mos[self.mo.id]['requested_qty'], 10)
        demand = next(row for row in snapshot['material_demands'] if row['mo_id'] == self.mo.id)
        self.assertEqual((demand['demand_qty'], demand['reserved_qty'], demand['unreserved_qty']), (20, 20, 0))
        self.assertTrue(snapshot['work_orders'])
        self.assertEqual(snapshot['work_orders'][0]['required_qty'], 10)
        self.assertEqual(set(snapshot), {'meta', 'units', 'products', 'work_centers', 'manufacturing_orders',
                                         'work_orders', 'boms', 'material_demands', 'stock'})

    # Catches counting picked output as posted stock.
    def test_reported_output_is_distinct_from_posted(self):
        self.mo.qty_producing = 4
        self.mo.set_qty_producing()
        self.mo.workorder_ids.button_start()
        self.mo.workorder_ids.button_finish()
        self.mo.move_finished_ids.picked = True
        self.mo.move_raw_ids.picked = True
        self.mo.invalidate_recordset(['qty_produced'])
        self.env.flush_all()
        snapshot = self.snapshot()
        row = next(row for row in snapshot.get('manufacturing_orders', []) if row['id'] == self.mo.id) if snapshot else {}
        self.assertEqual(row.get('reported_qty'), 4)
        self.assertEqual(row['posted_qty'], 0)
        demand = next(row for row in snapshot['material_demands'] if row['mo_id'] == self.mo.id)
        self.assertEqual(demand['posted_consumed_qty'], 0)
        self.assertGreater(demand['picked_qty'], 0)

    # Catches dropped older split siblings and substituted current BOM centers.
    def test_archived_center_and_old_backorder_sibling_are_resolved(self):
        self.warehouse.manu_type_id.create_backorder = 'always'
        self.mo.qty_producing = 4
        self.mo.set_qty_producing()
        self.mo.workorder_ids.button_start()
        self.mo.workorder_ids.button_finish()
        self.mo.button_mark_done()
        siblings = self.mo.production_group_id.production_ids - self.mo
        self.assertEqual(len(siblings), 1)
        self.mo.date_finished = fields.Datetime.now() - timedelta(days=30)
        self.center.active = False
        self.bom.active = False
        new_center = self.env['mrp.workcenter'].create({'name': 'New Assembly', 'company_id': self.company.id})
        self.bom.operation_ids.workcenter_id = new_center
        self.env.flush_all()
        snapshot = self.snapshot()
        self.assertIn(self.mo.id, [row['id'] for row in snapshot.get('manufacturing_orders', [])])
        self.assertIn(siblings.id, [row['id'] for row in snapshot['manufacturing_orders']])
        centers = {row['id']: row for row in snapshot['work_centers']}
        self.assertFalse(centers[self.center.id]['active'])
        wo = next(row for row in snapshot['work_orders'] if row['mo_id'] == self.mo.id)
        self.assertEqual(wo['center_id'], self.center.id)
        operation = next(row for row in snapshot['boms'][0]['operations'] if row['id'] == wo['operation_id'])
        self.assertEqual(operation['center_id'], new_center.id)

    # A real PostgreSQL read-only transaction catches business writes and commits.
    def test_export_is_readonly_one_cursor(self):
        self.env.flush_all()
        self.env.cr.execute('SHOW transaction_isolation')
        self.assertEqual(self.env.cr.fetchone()[0], 'repeatable read')
        self.env.cr.execute('SELECT txid_current(), pg_backend_pid()')
        before = self.env.cr.fetchone()
        self.env.cr.execute('SAVEPOINT readonly_probe')
        self.env.cr.execute('SET TRANSACTION READ ONLY')
        try:
            with patch.object(sql_db.Connection, 'cursor', side_effect=AssertionError('Exporter opened another cursor')):
                snapshot = self.snapshot()
            self.assertEqual(snapshot.get('meta', {}).get('company_id'), self.company.id)
            self.env.cr.execute('SELECT txid_current(), pg_backend_pid()')
            self.assertEqual(self.env.cr.fetchone(), before)
        finally:
            self.env.cr.execute('ROLLBACK TO SAVEPOINT readonly_probe')
            self.env.cr.execute('RELEASE SAVEPOINT readonly_probe')

    def test_nondefault_uom_and_signed_stock(self):
        dozen = self.env.ref('uom.product_uom_dozen')
        mo = self.env['mrp.production'].create({
            'product_id': self.product.id, 'product_qty': 1, 'uom_id': dozen.id,
            'bom_id': self.bom.id, 'company_id': self.company.id,
            'picking_type_id': self.warehouse.manu_type_id.id,
        })
        mo.action_confirm()
        mo.action_assign()
        negative_product = self.env['product.product'].create({'name': 'Negative stock evidence', 'is_storable': True})
        self.env['stock.quant'].create({'product_id': negative_product.id, 'location_id': self.warehouse.lot_stock_id.id,
                                       'inventory_quantity': -2}).action_apply_inventory()
        self.env.flush_all()
        snapshot = self.snapshot()
        row = next(row for row in snapshot['manufacturing_orders'] if row['id'] == mo.id)
        self.assertEqual((row['requested_qty'], row['unit_id']), (12, self.unit.id))
        wo = next(row for row in snapshot['work_orders'] if row['mo_id'] == mo.id)
        self.assertEqual(wo['required_qty'], 12)
        demand = next(row for row in snapshot['material_demands'] if row['mo_id'] == mo.id)
        self.assertEqual(demand['demand_qty'], 24)
        balance = next(row for row in snapshot['stock'] if row['product_id'] == negative_product.id)
        self.assertEqual((balance['on_hand_qty'], balance['free_qty']), (-2, -2))
