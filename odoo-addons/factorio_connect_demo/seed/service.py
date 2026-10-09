"""Transactional initialization and nonmutating, named-invariant verification."""
from dataclasses import dataclass
from datetime import timedelta, timezone

from odoo.exceptions import ValidationError

from .catalog import Fixtures, NAMESPACE, create_catalog, required_keys, specification
from .stock import post_opening_stock
from .production import create_production


@dataclass(frozen=True)
class SeedReport:
    seed_version: int
    fixture_ids: dict
    counts: dict
    invariants: dict


def seed_demo(env, *, now):
    manifest = env.ref(f'{NAMESPACE}.seed_manifest', raise_if_not_found=False)
    if manifest:
        return verify_demo(env, baseline=False)
    # The lock prevents simultaneous first-run catalog and opening-stock posting.
    # It protects this transaction only and is released by commit/rollback.
    with env.cr.savepoint():
        env.cr.execute("SELECT pg_advisory_xact_lock(hashtext('factorio_connect_demo.seed'))")
        manifest = env.ref(f'{NAMESPACE}.seed_manifest', raise_if_not_found=False)
        if manifest:
            return verify_demo(env, baseline=False)
        if env['ir.model.data'].search_count([('module', '=', NAMESPACE), ('model', 'not in', ['ir.model', 'ir.model.fields', 'ir.access'])]):
            raise ValidationError('seed_manifest: orphaned demo identities; restore the demo backup or reset explicitly')
        if now.tzinfo:
            now = now.astimezone(timezone.utc).replace(tzinfo=None)
        fixtures = Fixtures(env)
        company = env.ref('base.main_company')
        env = env(context=dict(env.context, allowed_company_ids=[company.id], company_id=company.id, lang='en_US', tz='UTC'))
        fixtures.env = env
        spec = create_catalog(env, fixtures)
        post_opening_stock(env, fixtures, spec)
        create_production(env, fixtures, spec, now)
        manifest = fixtures.create('seed_manifest', 'factorio.demo.manifest', {'seed_version': 1, 'initialized_at': now, 'company_id': fixtures['company'].id, 'warehouse_id': fixtures['warehouse'].id, 'fixture_ids': dict(fixtures.ids), 'baseline': spec})
        manifest.fixture_ids = fixtures.ids
        env.flush_all()
        report = _verify_demo(env, baseline=True, initializing=True)
        manifest.initialized = True
        return report


def verify_demo(env, *, baseline):
    return _verify_demo(env, baseline=baseline)


def _verify_demo(env, *, baseline, initializing=False):
    manifest = env.ref(f'{NAMESPACE}.seed_manifest', raise_if_not_found=False)
    if not manifest or manifest.seed_version != 1 or (not manifest.initialized and not initializing):
        raise ValidationError('seed_manifest: missing, incomplete, or unsupported seed version')
    errors = []
    spec = specification()
    for key in sorted(required_keys(spec) - manifest.fixture_ids.keys()):
        errors.append(key + ': missing required manifest identity')
    records = {}
    for key, entry in manifest.fixture_ids.items():
        # Reservation lines/quants are lifecycle records: cancellation and
        # consumption may legitimately unlink them. Keep their initial IDs as
        # history, but never recreate them on a rerun. Stable catalog/MO/WO
        # identities remain mandatory; baseline reads current inventory/moves.
        if entry['model'] in ('stock.move.line', 'stock.quant') and not env[entry['model']].browse(entry['id']).exists():
            continue
        record = env.ref(f'{NAMESPACE}.{key}', raise_if_not_found=False)
        if not record or record._name != entry['model'] or record.id != entry['id'] or not record.exists():
            errors.append(key + ': missing or conflicting fixture identity')
        else:
            records[key] = record
    if errors:
        raise ValidationError('\n'.join(errors))
    r = records
    counts = {'products': sum(k.startswith('product_') and not k.endswith('_template') for k in r), 'boms': sum(k in ('bom_pump', 'bom_impeller') for k in r), 'centers': sum(k.startswith('wc_') for k in r), 'mos': sum(k.startswith('mo_') for k in r), 'wos': sum(k.startswith('wo_') for k in r)}
    stock = {}
    for product in spec['products']:
        quants = env['stock.quant'].search([('product_id', '=', r[product['id']].id), ('location_id', '=', r['location_stock'].id)])
        on_hand = sum(quants.mapped('quantity'))
        reserved = sum(quants.mapped('reserved_quantity'))
        stock[product['id']] = {'on_hand': on_hand, 'reserved': reserved, 'free': on_hand - reserved}
    motor = r['mo_shortage'].move_raw_ids.filtered(lambda m: m.product_id == r['product_motor'])
    reserved_motor = sum(motor.move_line_ids.filtered(lambda line: not line.picked).mapped('quantity'))
    posted_pumps = sum(env['stock.move'].search([('product_id', '=', r['product_pump'].id), ('production_id', 'in', [r[k].id for k in r if k.startswith('mo_')]), ('state', '=', 'done')]).mapped('quantity'))
    invariants = {'posted_pumps': posted_pumps, 'missing_motors': max(sum(motor.mapped('product_uom_qty')) - reserved_motor, 0), 'motor_on_hand': stock['product_motor']['on_hand'], 'motor_reserved': stock['product_motor']['reserved'], 'motor_free': stock['product_motor']['free'], 'partial_done': r['mo_partial_done'].product_qty, 'partial_backorder': r['mo_partial_backorder'].product_qty}

    def check(name, actual, expected):
        if actual != expected:
            errors.append(f'{name}: expected {expected!r}, observed {actual!r}')

    check('counts', counts, {'products': 10, 'boms': 2, 'centers': 4, 'mos': 8, 'wos': 22})
    if baseline:
        check('company.name', r['company'].name, 'PumpWorks Demo')
        check('company.currency', r['company'].currency_id, env.ref('base.EUR'))
        check('warehouse.scope', r['warehouse'].company_id, r['company'])
        check('warehouse.name', r['warehouse'].name, 'PumpWorks')
        check('warehouse.code', r['warehouse'].code, 'PUMP')
        check('warehouse.manufacture_steps', r['warehouse'].manufacture_steps, 'mrp_one_step')
        check('location_stock', r['warehouse'].lot_stock_id, r['location_stock'])
        check('location_view', r['warehouse'].view_location_id, r['location_view'])
        check('location_stock.usage', r['location_stock'].usage, 'internal')
        check('location_production.usage', r['location_production'].usage, 'production')
        check('location_inventory.usage', r['location_inventory'].usage, 'inventory')
        picking = r['manufacturing_type']
        check('manufacturing_type.warehouse', picking.warehouse_id, r['warehouse'])
        check('manufacturing_type.backorders', picking.create_backorder, 'always')
        check('manufacturing_type.source', picking.default_location_src_id, r['location_stock'])
        check('manufacturing_type.destination', picking.default_location_dest_id, r['location_stock'])
        check('uom_unit', r['uom_unit'], env.ref('uom.product_uom_unit'))
        check('uom_unit.digits', env['decimal.precision'].search([('name', '=', 'Product Unit')]).digits, 0)
        check('calendar.name', r['calendar'].name, 'PumpWorks Day Shift')
        check('calendar.company_timezone', r['company'].tz, 'Europe/Madrid')
        check('calendar.company', r['calendar'].company_id, r['company'])
        check('calendar.attendances', len(r['calendar'].attendance_ids), 10)
        for day, key in enumerate(('mon', 'tue', 'wed', 'thu', 'fri')):
            for period, start, end in (('am', 8, 12), ('pm', 13, 17)):
                attendance = r[f'attendance_{key}_{period}']
                check(f'attendance_{key}_{period}', (attendance.calendar_id.id, attendance.dayofweek, attendance.hour_from, attendance.hour_to), (r['calendar'].id, str(day), start, end))
        for product in spec['products']:
            p = r[product['id']]
            for field, expected in [('default_code', product['sku']), ('name', product['name']), ('type', 'consu'), ('is_storable', True), ('tracking', False), ('store_by', 'quantity'), ('standard_price', 0), ('uom_id', r['uom_unit']), ('company_id', r['company']), ('categ_id', r['category_' + product['category']]), ('product_tmpl_id', r[product['id'] + '_template'])]:
                check(product['id'] + '.' + field, p[field], expected)
            check(product['id'] + '.routes', p.route_ids.ids, [r['route_manufacture'].id] if product['category'] == 'manufactured' else [])
            check(product['id'] + '.stock', stock[product['id']], product['baseline'])
        for category in ('components', 'manufactured'):
            check('category_' + category, r['category_' + category].name, 'PumpWorks / ' + category.title())
        for center in spec['centers']:
            wc = r[center['id']]
            for field, expected in [('name', center['name']), ('code', center['code']), ('company_id', r['company']), ('resource_calendar_id', r['calendar']), ('resource_id', r[center['resource']]), ('active', True), ('time_efficiency', 100), ('time_start', 0), ('time_stop', 0), ('costs_hour', 0)]:
                check(center['id'] + '.' + field, wc[field], expected)
            check(center['resource'] + '.timezone', wc.resource_id.tz, 'Europe/Madrid')
            check(center['id'] + '.alternatives', bool(wc.alternative_workcenter_ids), False)
            check(center['id'] + '.capacity', wc._get_capacity(r['product_pump'], r['uom_unit'])[0], 1)
        check('loss_productive.type', r['loss_productive'].loss_type, 'productive')
        check('loss_performance.type', r['loss_performance'].loss_type, 'performance')
        for bom in spec['boms']:
            b = r[bom['id']]
            for field, expected in [('product_id', r[bom['product']]), ('company_id', r['company']), ('type', 'normal'), ('product_qty', 1), ('uom_id', r['uom_unit']), ('picking_type_id', picking), ('ready_to_produce', 'all_available'), ('continuous', False), ('allow_operation_dependencies', True)]:
                check(bom['id'] + '.' + field, b[field], expected)
            check(bom['id'] + '.lines', set(b.bom_line_ids.ids), {r[line['id']].id for line in bom['lines']})
            for line in bom['lines']:
                actual = r[line['id']]
                check(line['id'], (actual.bom_id.id, actual.product_id.id, actual.product_qty, actual.uom_id.id, actual.operation_id.id), (b.id, r[line['product']].id, line['quantity'], r['uom_unit'].id, r[line['operation']].id))
        for operation in spec['operations']:
            op = r[operation['id']]
            for field, expected in [('name', operation['name']), ('bom_id', r[operation['bom']]), ('workcenter_id', r[operation['center']]), ('sequence', operation['sequence']), ('time_mode', 'manual'), ('time_cycle_manual', operation['minutes'])]:
                check(operation['id'] + '.' + field, op[field], expected)
            check(operation['id'] + '.predecessor', op.blocked_by_operation_ids.ids, [r[operation['predecessor']].id] if operation['predecessor'] else [])
        for scenario in spec['scenarios']:
            key = scenario['id']
            mo = r[key]
            for field, expected in [('state', scenario['state']), ('origin', scenario['origin']), ('product_qty', scenario['quantity']), ('product_id', r[scenario['product']]), ('company_id', r['company']), ('uom_id', r['uom_unit']), ('location_src_id', r['location_stock']), ('location_dest_id', r['location_stock']), ('priority', '0')]:
                check(key + '.' + field, mo[field], expected)
            check(key + '.date_deadline', mo.date_deadline, manifest.initialized_at + timedelta(hours=scenario['deadline_hours']))
            if key in ('mo_partial_backorder', 'mo_ready', 'mo_shortage', 'mo_cancelled'):
                check(key + '.planned_start', mo.date_start, manifest.initialized_at + timedelta(hours=scenario['start_hours']))
            operations = ['machine'] if key == 'mo_impeller_done' else ['assemble', 'inspect', 'pack']
            check(key + '.workorders', len(mo.workorder_ids), len(operations))
            for index, operation in enumerate(operations):
                wo_key = 'wo_' + key.removeprefix('mo_') + '_' + operation
                wo = r[wo_key]
                expected_state = 'done' if scenario['state'] == 'done' else 'cancel' if scenario['state'] == 'cancel' else 'blocked' if index else 'progress' if key == 'mo_running' else 'ready'
                check(wo_key + '.state', wo.state, expected_state)
                check(wo_key + '.output', wo.qty_produced, scenario['quantity'] if scenario['state'] == 'done' else 0)
                check(wo_key + '.operation', wo.operation_id, r['operation_' + operation])
                check(wo_key + '.production', wo.production_id, mo)
                check(wo_key + '.dependencies', wo.blocked_by_workorder_ids.ids, [r['wo_' + key.removeprefix('mo_') + '_' + operations[index - 1]].id] if index else [])
            if key in ('mo_partial_backorder', 'mo_ready', 'mo_running', 'mo_shortage', 'mo_cancelled'):
                for line in spec['boms'][1]['lines']:
                    moves = mo.move_raw_ids.filtered(lambda m: m.product_id == r[line['product']])
                    reserved = sum(moves.move_line_ids.filtered(lambda l: not l.picked).mapped('quantity'))
                    expected = 0 if key == 'mo_cancelled' else 2 if key == 'mo_shortage' and line['product'] == 'product_motor' else scenario['quantity'] * line['quantity']
                    check(key + '.' + line['product'] + '.reserved', reserved, expected)
        check('partial.group', r['mo_partial_done'].production_group_id, r['mo_partial_backorder'].production_group_id)
        check('partial.sequence', r['mo_partial_backorder'].backorder_sequence > r['mo_partial_done'].backorder_sequence, True)
        timers = env['mrp.workcenter.productivity'].search([('workorder_id', 'in', [record.id for key, record in r.items() if key.startswith('wo_')]), ('date_end', '=', False)])
        check('productivity.open', timers.workorder_id.ids, [r['wo_running_assemble'].id])
        for key, login in [('operator', 'demo.operator'), ('integration_user', 'factorio.bridge')]:
            check(key + '.login', r[key].login, login)
            check(key + '.companies', r[key].company_ids.ids, [r['company'].id])
            check(key + '.language', r[key].lang, 'en_US')
        check('integration_user.binding', r['integration_user'].factorio_config_id, r['integration_config'])
        config = r['integration_config']
        check('integration_config.scope', (config.company_id.id, config.warehouse_id.id), (r['company'].id, r['warehouse'].id))
        check('integration_config.enabled', config.enabled, True)
        check('integration_config.terminal_days', config.terminal_days, 7)
        for key, expected in {'posted_pumps': 14, 'missing_motors': 6, 'motor_on_hand': 28, 'motor_reserved': 28, 'motor_free': 0, 'partial_done': 4, 'partial_backorder': 6}.items():
            check(key, invariants[key], expected)
    if errors:
        raise ValidationError('\n'.join(errors))
    return SeedReport(manifest.seed_version, manifest.fixture_ids, counts, invariants)
