"""Create the literal PumpWorks catalog; reuse Odoo prerequisites via XML aliases."""
import json
import secrets
from pathlib import Path
from uuid import uuid4

from odoo import Command
from odoo.exceptions import ValidationError


NAMESPACE = 'factorio_connect_demo'


def specification():
    return json.loads((Path(__file__).parent.parent / 'data' / 'factory.json').read_text())


def required_keys(spec):
    keys = set('company warehouse location_view location_stock location_production location_inventory manufacturing_type uom_unit category_components category_manufactured route_manufacture calendar operator integration_user integration_config seed_manifest loss_productive loss_performance'.split())
    for product in spec['products']:
        keys.update((product['id'], product['id'] + '_template'))
        if product['opening']:
            keys.add('opening_' + product['id'].removeprefix('product_'))
    for center in spec['centers']:
        keys.update((center['id'], center['resource']))
    for bom in spec['boms']:
        keys.add(bom['id'])
        keys.update(line['id'] for line in bom['lines'])
    keys.update(operation['id'] for operation in spec['operations'])
    keys.update(f'attendance_{day}_{period}' for day in ('mon', 'tue', 'wed', 'thu', 'fri') for period in ('am', 'pm'))
    for scenario in spec['scenarios']:
        key = scenario['id'].removeprefix('mo_')
        keys.update((scenario['id'], 'group_' + key))
        operations = ('machine',) if key == 'impeller_done' else ('assemble', 'inspect', 'pack')
        keys.update('wo_' + key + '_' + operation for operation in operations)
    return keys


class Fixtures:
    def __init__(self, env):
        self.env = env
        self.ids = {}

    def alias(self, key, record):
        if len(record) != 1 or not record.exists():
            raise ValidationError(f'{key}: expected exactly one existing {record._name} record')
        existing = self.env.ref(f'{NAMESPACE}.{key}', raise_if_not_found=False)
        if existing and (existing._name != record._name or existing.id != record.id):
            raise ValidationError(f'{key}: conflicting XML identity')
        if not existing:
            self.env['ir.model.data'].create({'module': NAMESPACE, 'name': key, 'model': record._name, 'res_id': record.id, 'noupdate': True})
        self.ids[key] = {'model': record._name, 'id': record.id}
        return record

    def create(self, key, model, values):
        return self.alias(key, self.env[model].create(values))

    def __getitem__(self, key):
        entry = self.ids[key]
        return self.env[entry['model']].browse(entry['id'])


def create_catalog(env, fixtures):
    spec = specification()
    company = fixtures.alias('company', env.ref('base.main_company'))
    company.write({'name': 'PumpWorks Demo', 'currency_id': env.ref('base.EUR').id, 'tz': 'Europe/Madrid'})
    warehouses = env['stock.warehouse'].search([('company_id', '=', company.id)])
    if len(warehouses) != 1:
        raise ValidationError('warehouse: seed requires one clean main-company warehouse')
    warehouse = fixtures.alias('warehouse', warehouses)
    warehouse.write({'name': 'PumpWorks', 'code': 'PUMP', 'manufacture_steps': 'mrp_one_step'})
    fixtures.alias('location_view', warehouse.view_location_id)
    fixtures.alias('location_stock', warehouse.lot_stock_id)
    picking = fixtures.alias('manufacturing_type', warehouse.manu_type_id)
    picking.write({'create_backorder': 'always', 'default_location_src_id': warehouse.lot_stock_id.id, 'default_location_dest_id': warehouse.lot_stock_id.id})
    route = fixtures.alias('route_manufacture', warehouse.manufacture_pull_id.route_id)
    route.product_selectable = True
    unit = fixtures.alias('uom_unit', env.ref('uom.product_uom_unit'))
    # Odoo20 quantum is the Product Unit decimal precision, not a UoM scalar.
    precision = env['decimal.precision'].search([('name', '=', 'Product Unit')])
    if len(precision) != 1:
        raise ValidationError('uom_unit: missing Product Unit decimal precision')
    precision.digits = 0
    calendar = fixtures.create('calendar', 'resource.calendar', {'name': 'PumpWorks Day Shift', 'company_id': company.id, 'attendance_ids': [Command.create({'dayofweek': str(day), 'hour_from': start, 'hour_to': end}) for day, key in enumerate(('mon', 'tue', 'wed', 'thu', 'fri')) for period, start, end in (('am', 8, 12), ('pm', 13, 17))]})
    for day, key in enumerate(('mon', 'tue', 'wed', 'thu', 'fri')):
        for period, start in (('am', 8), ('pm', 13)):
            fixtures.alias(f'attendance_{key}_{period}', calendar.attendance_ids.filtered(lambda a: a.dayofweek == str(day) and a.hour_from == start))
    for category in ('components', 'manufactured'):
        fixtures.create('category_' + category, 'product.category', {'name': 'PumpWorks / ' + category.title()})
    for product in spec['products']:
        if env['product.product'].search_count([('default_code', '=', product['sku'])]):
            raise ValidationError(product['id'] + ': conflicting SKU exists before initialization')
        p = fixtures.create(product['id'], 'product.product', {'name': product['name'], 'default_code': product['sku'], 'type': 'consu', 'is_storable': True, 'tracking': False, 'standard_price': 0, 'uom_id': unit.id, 'company_id': company.id, 'categ_id': fixtures['category_' + product['category']].id, 'route_ids': [Command.set([fixtures['route_manufacture'].id] if product['category'] == 'manufactured' else [])]})
        fixtures.alias(product['id'] + '_template', p.product_tmpl_id)
    fixtures.alias('location_production', fixtures['product_pump'].property_stock_production)
    fixtures.alias('location_inventory', fixtures['product_blank'].property_stock_inventory)
    for center in spec['centers']:
        wc = fixtures.create(center['id'], 'mrp.workcenter', {'name': center['name'], 'code': center['code'], 'company_id': company.id, 'resource_calendar_id': calendar.id, 'time_efficiency': 100, 'time_start': 0, 'time_stop': 0, 'costs_hour': 0})
        wc.resource_id.tz = 'Europe/Madrid'
        fixtures.alias(center['resource'], wc.resource_id)
    fixtures.alias('loss_productive', env.ref('mrp.block_reason7'))
    fixtures.alias('loss_performance', env.ref('mrp.block_reason4'))
    for bom in spec['boms']:
        product = fixtures[bom['product']]
        fixtures.create(bom['id'], 'mrp.bom', {'product_tmpl_id': product.product_tmpl_id.id, 'product_id': product.id, 'company_id': company.id, 'type': 'normal', 'product_qty': 1, 'uom_id': unit.id, 'picking_type_id': picking.id, 'ready_to_produce': 'all_available', 'allow_operation_dependencies': True, 'continuous': False})
    for operation in spec['operations']:
        fixtures.create(operation['id'], 'mrp.routing.workcenter', {'name': operation['name'], 'bom_id': fixtures[operation['bom']].id, 'workcenter_id': fixtures[operation['center']].id, 'sequence': operation['sequence'], 'time_mode': 'manual', 'time_cycle_manual': operation['minutes'], 'blocked_by_operation_ids': [Command.set([fixtures[operation['predecessor']].id] if operation['predecessor'] else [])]})
    for bom in spec['boms']:
        for line in bom['lines']:
            fixtures.create(line['id'], 'mrp.bom.line', {'bom_id': fixtures[bom['id']].id, 'product_id': fixtures[line['product']].id, 'product_qty': line['quantity'], 'uom_id': unit.id, 'operation_id': fixtures[line['operation']].id})
    for key, login, name, groups in [('operator', 'demo.operator', 'PumpWorks Operator', ['base.group_user', 'mrp.group_mrp_user', 'mrp.group_mrp_routings']), ('integration_user', 'factorio.bridge', 'Factorio Bridge', ['factorio_connect.group_factory_reader'])]:
        if env['res.users'].search_count([('login', '=', login)]):
            raise ValidationError(key + ': conflicting login exists before initialization')
        fixtures.create(key, 'res.users', {'name': name, 'login': login, 'password': secrets.token_urlsafe(32), 'company_id': company.id, 'company_ids': [Command.set([company.id])], 'group_ids': [Command.set([env.ref(g).id for g in groups])], 'tz': 'Europe/Madrid', 'lang': 'en_US'})
    parameters = env['ir.config_parameter']
    source_id = parameters.get_str('database.uuid')
    if not source_id:
        source_id = str(uuid4())
        parameters.set_str('database.uuid', source_id)
    config = fixtures.create('integration_config', 'factorio.integration.config', {'company_id': company.id, 'warehouse_id': warehouse.id, 'source_id': source_id, 'terminal_days': 7, 'enabled': True})
    fixtures['integration_user'].factorio_config_id = config
    return spec
