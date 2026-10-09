"""Build all scenarios using public manufacturing actions and generated splits."""
from datetime import timedelta
from odoo.exceptions import ValidationError


def register_workorders(fixtures, key, production):
    for wo in production.workorder_ids:
        operation = next((k for k, v in fixtures.ids.items() if k.startswith('operation_') and v['id'] == wo.operation_id.id), None)
        if not operation:
            raise ValidationError(key + ': generated workorder has unknown operation')
        fixtures.alias('wo_' + key.removeprefix('mo_') + '_' + operation.removeprefix('operation_'), wo)


def complete(production, quantity):
    production.qty_producing = quantity
    production.set_qty_producing()
    for wo in production.workorder_ids.sorted(lambda w: (w.operation_id.sequence, w.id)):
        wo.button_start()
        wo.button_finish()
    action = production.button_mark_done()
    # Always-backorder returns navigation to the generated MO; a wizard instead
    # means validation has not completed and must never be mistaken for success.
    if isinstance(action, dict) and action.get('res_model') not in ('mrp.production', None):
        raise ValidationError(f'{production.origin}: completion requires unexpected workflow {action.get("res_model")}')
    if production.state != 'done':
        raise ValidationError(production.origin + ': completion did not post manufacturing order')


def create_production(env, fixtures, spec, now):
    for scenario in spec['scenarios']:
        key = scenario['id']
        if key == 'mo_partial_backorder':
            original = fixtures['mo_partial_done']
            backorder = original.production_group_id.production_ids - original
            if len(backorder) != 1:
                raise ValidationError('mo_partial_backorder: automatic split did not yield one sibling')
            mo = fixtures.alias(key, backorder)
            mo.write({'origin': scenario['origin'], 'date_start': now + timedelta(hours=scenario['start_hours']), 'date_deadline': now + timedelta(hours=scenario['deadline_hours'])})
            mo.action_assign()
        else:
            product = fixtures[scenario['product']]
            mo = fixtures.create(key, 'mrp.production', {'product_id': product.id, 'product_qty': scenario['initial_quantity'], 'uom_id': fixtures['uom_unit'].id, 'bom_id': fixtures['bom_impeller' if scenario['product'] == 'product_impeller' else 'bom_pump'].id, 'company_id': fixtures['company'].id, 'picking_type_id': fixtures['manufacturing_type'].id, 'location_src_id': fixtures['location_stock'].id, 'location_dest_id': fixtures['location_stock'].id, 'date_start': now + timedelta(hours=scenario['start_hours']), 'date_deadline': now + timedelta(hours=scenario['deadline_hours']), 'origin': scenario['origin'], 'priority': '0'})
            mo.action_confirm()
            mo.action_assign()
            if scenario['state'] == 'done':
                complete(mo, scenario['quantity'])
            elif key == 'mo_running':
                mo.workorder_ids.filtered(lambda w: w.operation_id == fixtures['operation_assemble']).button_start()
            elif key == 'mo_cancelled':
                mo.action_cancel()
        register_workorders(fixtures, key, mo)
        fixtures.alias('group_' + key.removeprefix('mo_'), mo.production_group_id)
    for key in list(fixtures.ids):
        if not key.startswith('mo_'):
            continue
        mo = fixtures[key]
        for role, moves in [('raw', mo.move_raw_ids), ('finished', mo.move_finished_ids)]:
            for index, move in enumerate(moves.sorted('id'), 1):
                fixtures.alias(f'move_{key}_{role}_{index}', move)
                for line_index, line in enumerate(move.move_line_ids.sorted('id'), 1):
                    fixtures.alias(f'move_line_{key}_{role}_{index}_{line_index}', line)
        for wo in mo.workorder_ids:
            key_wo = next(k for k, v in fixtures.ids.items() if k.startswith('wo_') and v['id'] == wo.id)
            for index, timer in enumerate(wo.time_ids.sorted('id'), 1):
                fixtures.alias(f'productivity_{key_wo}_{index}', timer)
    quants = env['stock.quant'].search([('location_id', '=', fixtures['location_stock'].id), ('product_id', 'in', [fixtures[p['id']].id for p in spec['products']])])
    for product in spec['products']:
        for index, quant in enumerate(quants.filtered(lambda q: q.product_id == fixtures[product['id']]).sorted('id'), 1):
            fixtures.alias(f"quant_{product['id']}_{index}", quant)
