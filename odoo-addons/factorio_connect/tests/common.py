from uuid import uuid4

from odoo import Command
from odoo.tests.common import TransactionCase


class FactoryCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.unit = cls.env.ref('uom.product_uom_unit')
        cls.product = cls.env['product.product'].create({'name': 'Test pump', 'is_storable': True, 'uom_id': cls.unit.id})
        cls.component = cls.env['product.product'].create({'name': 'Test motor', 'is_storable': True, 'uom_id': cls.unit.id})
        cls.center = cls.env['mrp.workcenter'].create({'name': 'Assembly', 'company_id': cls.company.id})
        cls.bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.product.product_tmpl_id.id, 'product_id': cls.product.id,
            'company_id': cls.company.id, 'product_qty': 1, 'uom_id': cls.unit.id,
            'operation_ids': [Command.create({'name': 'Assemble', 'workcenter_id': cls.center.id, 'sequence': 10})],
            'bom_line_ids': [Command.create({'product_id': cls.component.id, 'product_qty': 2, 'uom_id': cls.unit.id})],
        })
        cls.env['stock.quant'].create({'product_id': cls.component.id, 'location_id': cls.warehouse.lot_stock_id.id,
                                     'inventory_quantity': 100}).action_apply_inventory()
        cls.config = cls.env['factorio.integration.config'].create({
            'company_id': cls.company.id, 'warehouse_id': cls.warehouse.id, 'source_id': str(uuid4()),
        })
        cls.bot = cls.env['res.users'].create({
            'name': 'Factory Reader', 'login': 'factory-test-reader',
            'company_id': cls.company.id, 'company_ids': [Command.set([cls.company.id])],
            'group_ids': [Command.set([cls.env.ref('factorio_connect.group_factory_reader').id])],
            'factorio_config_id': cls.config.id,
        })
        cls.mo = cls.make_mo(10)
        cls.foreign_company = cls.env['res.company'].create({'name': 'Foreign factory'})
        cls.foreign_warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.foreign_company.id)], limit=1)
        cls.foreign_mo = cls.env['mrp.production'].with_company(cls.foreign_company).create({
            'product_id': cls.product.id, 'product_qty': 3, 'uom_id': cls.unit.id,
            'company_id': cls.foreign_company.id, 'picking_type_id': cls.foreign_warehouse.manu_type_id.id,
        })
        cls.env.flush_all()

    @classmethod
    def make_mo(cls, qty):
        mo = cls.env['mrp.production'].create({
            'product_id': cls.product.id, 'product_qty': qty, 'uom_id': cls.unit.id,
            'bom_id': cls.bom.id, 'company_id': cls.company.id,
            'picking_type_id': cls.warehouse.manu_type_id.id,
        })
        mo.action_confirm()
        mo.action_assign()
        return mo

    def snapshot(self, **context):
        return self.env['factorio.factory'].with_user(self.bot).with_context(**context).get_snapshot()
