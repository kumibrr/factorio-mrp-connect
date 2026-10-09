from datetime import datetime
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

from ..seed.service import seed_demo, verify_demo


@tagged('post_install', '-at_install')
class TestSeed(TransactionCase):
    T0 = datetime(2026, 10, 9, 10, 0)

    def fixture(self, key):
        return self.env.ref('factorio_connect_demo.' + key)

    # Catches wrong workflow order, missing fixtures and reservation arithmetic.
    def test_baseline_inventory_and_all_states(self):
        report = seed_demo(self.env, now=self.T0)
        self.assertEqual(report.counts, {'products': 10, 'boms': 2, 'centers': 4, 'mos': 8, 'wos': 22})
        expected = {
            'blank': (40, 0, 40), 'housing': (86, 34, 52), 'motor': (28, 28, 0),
            'shaft': (86, 34, 52), 'bearing': (172, 68, 104), 'seal': (86, 34, 52),
            'fastener': (86, 34, 52), 'carton': (86, 34, 52), 'impeller': (46, 34, 12), 'pump': (14, 0, 14),
        }
        location = self.fixture('location_stock')
        for key, balance in expected.items():
            quants = self.env['stock.quant'].search([('product_id', '=', self.fixture('product_' + key).id), ('location_id', '=', location.id)])
            actual = (sum(quants.mapped('quantity')), sum(quants.mapped('reserved_quantity')))
            self.assertEqual((*actual, actual[0] - actual[1]), balance, key)
        for key, state in {'impeller_done': 'done', 'pump_done': 'done', 'partial_done': 'done', 'partial_backorder': 'confirmed', 'ready': 'confirmed', 'running': 'progress', 'shortage': 'confirmed', 'cancelled': 'cancel'}.items():
            self.assertEqual(self.fixture('mo_' + key).state, state, key)
        for key in ('partial_backorder', 'ready', 'running', 'shortage'):
            for operation, state in [('assemble', 'progress' if key == 'running' else 'ready'), ('inspect', 'blocked'), ('pack', 'blocked')]:
                self.assertEqual(self.fixture('wo_' + key + '_' + operation).state, state)
        open_entries = self.env['mrp.workcenter.productivity'].search([('workorder_id', 'in', [self.fixture(k).id for k in report.fixture_ids if k.startswith('wo_')]), ('date_end', '=', False)])
        self.assertEqual(open_entries.workorder_id, self.fixture('wo_running_assemble'))
        self.assertEqual(self.fixture('wo_running_assemble').qty_produced, 0)
        self.assertEqual(verify_demo(self.env, baseline=True).counts, report.counts)

    # Catches fabricated split siblings or finishing an entire ten-unit MO.
    def test_real_four_plus_six_backorder(self):
        report = seed_demo(self.env, now=self.T0)
        self.assertEqual(report.invariants.get('partial_done'), 4)
        self.assertEqual(report.invariants['partial_backorder'], 6)
        self.assertEqual(report.invariants['posted_pumps'], 14)
        self.assertEqual(report.invariants['missing_motors'], 6)
        done, remainder = self.fixture('mo_partial_done'), self.fixture('mo_partial_backorder')
        self.assertEqual(done.production_group_id, remainder.production_group_id)
        self.assertGreater(remainder.backorder_sequence, done.backorder_sequence)
        self.assertEqual((done.product_qty, remainder.product_qty), (4, 6))

    # Catches ordinary reruns that replenish consumed opening stock.
    def test_rerun_does_not_post_twice(self):
        first = seed_demo(self.env, now=self.T0)
        move_ids = self.env['stock.move'].search([]).ids
        second = seed_demo(self.env, now=self.T0)
        self.assertEqual(second.fixture_ids, first.fixture_ids)
        self.assertEqual(self.env['stock.move'].search([]).ids, move_ids)
        self.assertEqual(second.invariants['posted_pumps'], 14)

    # Catches resetting operator changes or incorrectly demanding baseline on rerun.
    def test_rerun_preserves_operator_edits(self):
        seed_demo(self.env, now=self.T0)
        self.fixture('mo_ready').action_cancel()
        self.fixture('wc_packing').name = 'Operator packing station'
        seed_demo(self.env, now=self.T0)
        self.assertEqual(self.fixture('mo_ready').state, 'cancel')
        self.assertEqual(self.fixture('wc_packing').name, 'Operator packing station')
        with self.assertRaisesRegex(ValidationError, 'mo_ready.state'):
            verify_demo(self.env, baseline=True)

    # Failure after real stock posting must undo the whole bootstrap transaction.
    def test_failed_seed_rolls_back(self):
        original = type(self.env['mrp.production']).button_mark_done
        def fail_after_post(record):
            original(record)
            raise RuntimeError('injected completion failure')
        before = (self.env['stock.move'].search_count([]), self.env['product.product'].search_count([]), self.env.company.name)
        with patch.object(type(self.env['mrp.production']), 'button_mark_done', fail_after_post):
            with self.assertRaisesRegex(RuntimeError, 'injected completion failure'):
                seed_demo(self.env, now=self.T0)
        self.assertEqual((self.env['stock.move'].search_count([]), self.env['product.product'].search_count([]), self.env.company.name), before)
        self.assertFalse(self.env.ref('factorio_connect_demo.seed_manifest', raise_if_not_found=False))

    # Real PostgreSQL read-only verification and effective bot permissions.
    def test_verify_and_bot_export_are_readonly(self):
        seed_demo(self.env, now=self.T0)
        self.env.flush_all()
        self.env.cr.execute('SAVEPOINT seed_readonly')
        self.env.cr.execute('SET TRANSACTION READ ONLY')
        try:
            report = verify_demo(self.env, baseline=True)
            self.assertEqual(seed_demo(self.env, now=self.T0).fixture_ids, report.fixture_ids)
            snapshot = self.env['factorio.factory'].with_user(self.fixture('integration_user')).get_snapshot()
            self.assertEqual(len(snapshot['manufacturing_orders']), 8)
            self.assertEqual(len(snapshot['work_orders']), 22)
            self.assertEqual(len(snapshot['products']), 10)
            self.assertEqual(report.invariants['motor_reserved'], 28)
            motor = next(r for r in snapshot['material_demands'] if r['mo_id'] == self.fixture('mo_shortage').id and r['product_id'] == self.fixture('product_motor').id)
            self.assertEqual((motor['demand_qty'], motor['reserved_qty'], motor['unreserved_qty']), (8, 2, 6))
            self.assertEqual(next(u for u in snapshot['units'] if u['id'] == self.fixture('uom_unit').id)['rounding'], 1)
        finally:
            self.env.cr.execute('ROLLBACK TO SAVEPOINT seed_readonly')
            self.env.cr.execute('RELEASE SAVEPOINT seed_readonly')

    # Catches silently rebuilding a missing XML identity on an initialized rerun.
    def test_missing_fixture_is_named_and_not_recreated(self):
        seed_demo(self.env, now=self.T0)
        self.env['ir.model.data'].search([('module', '=', 'factorio_connect_demo'), ('name', '=', 'wo_ready_assemble')]).unlink()
        move_ids = self.env['stock.move'].search([]).ids
        with self.assertRaisesRegex(ValidationError, 'wo_ready_assemble'):
            seed_demo(self.env, now=self.T0)
        self.assertEqual(self.env['stock.move'].search([]).ids, move_ids)

    # Catches a verifier trusting a damaged manifest that omits required fixtures.
    def test_incomplete_manifest_is_named(self):
        seed_demo(self.env, now=self.T0)
        manifest = self.fixture('seed_manifest')
        manifest.fixture_ids = {key: value for key, value in manifest.fixture_ids.items() if key != 'attendance_fri_pm'}
        with self.assertRaisesRegex(ValidationError, 'attendance_fri_pm'):
            verify_demo(self.env, baseline=False)

    # Catches lost T0 business inputs when generated remainder inherits actual start.
    def test_planned_business_dates_use_seed_time(self):
        from datetime import timedelta
        seed_demo(self.env, now=self.T0)
        for key, hours in {'impeller_done': 1, 'pump_done': 1, 'partial_done': 4, 'partial_backorder': 4, 'ready': 2, 'running': 1, 'shortage': -1, 'cancelled': 3}.items():
            self.assertEqual(self.fixture('mo_' + key).date_deadline, self.T0 + timedelta(hours=hours), key)
        for key, hours in {'partial_backorder': 0, 'ready': 1, 'shortage': -2, 'cancelled': 1}.items():
            self.assertEqual(self.fixture('mo_' + key).date_start, self.T0 + timedelta(hours=hours), key)
