from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import FactoryCase


@tagged('post_install', '-at_install')
class TestPermissions(FactoryCase):
    # Catches read-only grants accidentally inheriting business writes.
    def test_effective_bot_permissions(self):
        snapshot = self.snapshot()
        self.assertEqual(snapshot.get('meta', {}).get('company_id'), self.company.id)
        for model, record, values in [
            ('mrp.production', self.mo, {'origin': 'unauthorized'}),
            ('mrp.workorder', self.mo.workorder_ids, {'name': 'unauthorized'}),
            ('mrp.workcenter', self.center, {'name': 'unauthorized'}),
            ('mrp.bom', self.bom, {'product_qty': 2}),
            ('stock.move', self.mo.move_raw_ids, {'product_uom_qty': 1}),
            ('stock.quant', self.env['stock.quant'].search([('product_id', '=', self.component.id)]), {'quantity': 1}),
            ('product.product', self.product, {'name': 'unauthorized'}),
        ]:
            with self.subTest(model=model):
                with self.assertRaises(AccessError), self.env.cr.savepoint():
                    record.with_user(self.bot).write(values)
                with self.assertRaises(AccessError), self.env.cr.savepoint():
                    record.with_user(self.bot).unlink()
                with self.assertRaises(AccessError), self.env.cr.savepoint():
                    self.env[model].with_user(self.bot).create({})
        with self.assertRaises(AccessError):
            self.env['ir.config_parameter'].with_user(self.bot).search([])
        with self.assertRaises(AccessError):
            self.foreign_mo.with_user(self.bot).read(['name'])
        with self.assertRaises(AccessError):
            self.config.with_user(self.bot).write({'warehouse_id': self.foreign_warehouse.id})
        with self.assertRaises(AccessError):
            self.bot.with_user(self.bot).write({'factorio_config_id': False})
        with self.assertRaises(AccessError):
            self.config.with_user(self.bot).read(['webhook_url'])
        with self.assertRaises(TypeError):
            self.env['factorio.factory'].with_user(self.bot).get_snapshot(company_id=self.foreign_company.id)

    def test_export_denies_unconfigured_and_ordinary_users(self):
        with self.assertRaises(AccessError):
            self.env['factorio.factory'].get_snapshot()
        self.bot.factorio_config_id = False
        with self.assertRaises(AccessError):
            self.snapshot()

    # Catches accidentally permitting an account with additive app writes.
    def test_export_rejects_inherited_business_writes(self):
        self.bot.group_ids += self.env.ref('mrp.group_mrp_user')
        with self.assertRaises(AccessError):
            self.snapshot()

    def test_config_rejects_invalid_identity_and_scope(self):
        for values in [{'source_id': 'invalid UUID'}, {'terminal_days': -1},
                       {'warehouse_id': self.foreign_warehouse.id}, {'odoo_base_url': 'file:///tmp/local'}]:
            with self.subTest(values=values), self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.config.write(values)

    # Catches same-company warehouse data leaking through the bot ACL.
    def test_bot_cannot_read_other_warehouse_locations(self):
        warehouse = self.env['stock.warehouse'].create({'name': 'Other warehouse', 'code': 'OTHER', 'company_id': self.company.id})
        with self.assertRaises(AccessError):
            warehouse.lot_stock_id.with_user(self.bot).read(['name'])

    # Catches a narrow additive grant that does not include MO/stock writes.
    def test_export_rejects_operation_only_write_grant(self):
        self.env['ir.access'].create({
            'name': 'Accidental operation update',
            'model_id': self.env['ir.model']._get('mrp.routing.workcenter').id,
            'group_id': self.env.ref('factorio_connect.group_factory_reader').id,
            'operation': 'u',
        })
        with self.assertRaises(AccessError):
            self.snapshot()
