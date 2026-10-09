"""Map native Odoo 20 source records; no writes, new cursors, or elevation."""
from collections import defaultdict
from datetime import timedelta, timezone

from odoo.exceptions import ValidationError


def _date(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _quantity(value, source_unit, product):
    return product.uom_id.round(source_unit._compute_quantity(value, product.uom_id, round=False))


def _capacity(center):
    # This scalar is DEFAULT capacity, not effective capacity for every product.
    # Native _get_capacity(product, unit, default_capacity=1) uses this fallback.
    defaults = center.capacity_ids.filtered(lambda row: not row.product_id)
    values = {row.capacity or 1.0 for row in defaults}
    if len(values) > 1:
        raise ValidationError('Work center has differing default capacities by unit; the scalar contract cannot represent them.')
    return values.pop() if values else 1.0


def build_snapshot(env, config, source_read_at):
    company_id, warehouse_id = config.company_id.id, config.warehouse_id.id
    scope = [('company_id', '=', company_id), ('picking_type_id.warehouse_id', '=', warehouse_id)]
    cutoff = (source_read_at - timedelta(days=config.terminal_days)).replace(tzinfo=None)
    mos = env['mrp.production'].search(scope + [
        '|', ('state', 'not in', ['done', 'cancel']),
        '|', '&', ('state', '=', 'done'), ('date_finished', '>=', cutoff),
        '&', ('state', '=', 'cancel'), ('write_date', '>=', cutoff),
    ])
    if mos.production_group_id:
        mos |= env['mrp.production'].search(scope + [('production_group_id', 'in', mos.production_group_id.ids)])
    wos = env['mrp.workorder'].search([('production_id', 'in', mos.ids)])
    boms = env['mrp.bom'].search([('company_id', 'in', [False, company_id]), ('active', '=', True), ('type', '=', 'normal')])
    boms |= mos.bom_id | wos.operation_id.bom_id
    centers = env['mrp.workcenter'].search([('company_id', 'in', [False, company_id]), ('active', '=', True)])
    centers |= wos.workcenter_id | boms.operation_ids.workcenter_id
    demands = env['stock.move'].search([('raw_material_production_id', 'in', mos.ids)])
    locations = env['stock.location'].search([('id', 'child_of', config.warehouse_id.view_location_id.id), ('usage', '=', 'internal')])
    quants = env['stock.quant'].search([('location_id', 'in', locations.ids), ('company_id', '=', company_id)])
    bom_products = {}
    for bom in boms:
        products = bom.product_id or bom.product_tmpl_id.product_variant_ids
        if len(products) != 1:
            raise ValidationError('A multi-variant BOM cannot be represented by the single-product snapshot contract.')
        bom_products[bom.id] = products
    products = mos.product_id | demands.product_id | quants.product_id | boms.bom_line_ids.product_id
    for product in bom_products.values():
        products |= product
    units = products.uom_id
    quantum = 10.0 ** -env['decimal.precision'].precision_get('Product Unit')
    snapshot = {
        'meta': {'schema_version': 1, 'source_id': config.source_id,
                 'scope_id': f'company:{company_id}/warehouse:{warehouse_id}',
                 'company_id': company_id, 'warehouse_id': warehouse_id,
                 'source_read_at': source_read_at.isoformat(), 'odoo_major': 20,
                 'odoo_base_url': config.odoo_base_url},
        'units': [{'id': unit.id, 'name': unit.name, 'rounding': quantum} for unit in units.sorted('id')],
        'products': [{'id': product.id, 'name': product.name, 'code': product.default_code or None,
                      'unit_id': product.uom_id.id} for product in products.sorted('id')],
        'work_centers': [{'id': center.id, 'name': center.name, 'code': center.code or None,
                          'active': center.active, 'capacity': _capacity(center),
                          'calendar_id': center.resource_calendar_id.id or None,
                          'raw_working_state': center.working_state or None} for center in centers.sorted('id')],
        'manufacturing_orders': [], 'work_orders': [], 'boms': [], 'material_demands': [], 'stock': [],
    }
    for mo in mos.sorted('id'):
        posted = sum(move.quantity_product_uom for move in mo.move_finished_ids
                     if move.state == 'done' and move.product_id == mo.product_id)
        snapshot['manufacturing_orders'].append({
            'id': mo.id, 'reference': mo.name, 'origin': mo.origin or None, 'product_id': mo.product_id.id,
            'unit_id': mo.product_id.uom_id.id, 'requested_qty': _quantity(mo.product_qty, mo.uom_id, mo.product_id),
            'reported_qty': _quantity(mo.qty_produced, mo.uom_id, mo.product_id),
            'posted_qty': mo.product_id.uom_id.round(posted), 'raw_state': mo.state,
            'planned_start_at': _date(mo.date_start), 'deadline_at': _date(mo.date_deadline),
            'started_at': _date(mo.date_start) if mo.state in ('progress', 'to_close', 'done') else None,
            'finished_at': _date(mo.date_finished) if mo.state == 'done' else None,
            'readiness_state': mo.reservation_state or None, 'availability_state': mo.components_availability_state or None,
            'group_id': mo.production_group_id.id or None, 'backorder_sequence': mo.backorder_sequence,
        })
    for wo in wos.sorted('id'):
        if not wo.operation_id:
            raise ValidationError('A work order without a source BOM operation cannot be represented.')
        row = {'id': wo.id, 'mo_id': wo.production_id.id, 'center_id': wo.workcenter_id.id,
               'operation_id': wo.operation_id.id, 'unit_id': wo.production_id.product_id.uom_id.id,
               'sequence': wo.sequence, 'dependency_ids': sorted(wo.blocked_by_workorder_ids.ids),
               'raw_state': wo.state, 'expected_minutes': wo.duration_expected, 'elapsed_minutes': wo.duration}
        for exported, native in [('output_qty', 'qty_produced'), ('carried_qty', 'qty_reported_from_previous_wo'),
                                 ('required_qty', 'qty_to_produce'), ('remaining_qty', 'qty_remaining'), ('ready_qty', 'qty_ready')]:
            row[exported] = _quantity(wo[native], wo.uom_id, wo.production_id.product_id)
        snapshot['work_orders'].append(row)
    for bom in boms.sorted('id'):
        product = bom_products[bom.id]
        snapshot['boms'].append({
            'id': bom.id, 'product_id': product.id, 'unit_id': product.uom_id.id,
            'output_qty': _quantity(bom.product_qty, bom.uom_id, product),
            'components': [{'product_id': line.product_id.id, 'unit_id': line.product_id.uom_id.id,
                            'quantity': _quantity(line.product_qty, line.uom_id, line.product_id),
                            'operation_id': line.operation_id.id or None} for line in bom.bom_line_ids.sorted('id')],
            'operations': [{'id': operation.id, 'center_id': operation.workcenter_id.id, 'sequence': operation.sequence,
                            'dependency_ids': sorted(operation.blocked_by_operation_ids.ids)}
                           for operation in bom.operation_ids.sorted('id')],
        })
    for move in demands.sorted('id'):
        product = move.product_id
        demand = product.uom_id.round(move.product_qty)
        posted = product.uom_id.round(move.quantity_product_uom) if move.state == 'done' else 0.0
        open_lines = move.move_line_ids.filtered(lambda line: line.state not in ('done', 'cancel'))
        reserved = product.uom_id.round(sum(line.quantity_product_uom for line in open_lines if not line.picked))
        picked = product.uom_id.round(sum(line.quantity_product_uom for line in open_lines if line.picked))
        remaining = max(demand - posted - picked, 0.0) if move.state not in ('done', 'cancel') else 0.0
        snapshot['material_demands'].append({
            'id': move.id, 'mo_id': move.raw_material_production_id.id, 'product_id': product.id,
            'unit_id': product.uom_id.id, 'demand_qty': demand, 'remaining_demand_qty': remaining,
            'reserved_qty': reserved, 'picked_qty': picked, 'posted_consumed_qty': posted,
            'unreserved_qty': product.uom_id.round(max(remaining - reserved, 0.0)),
            # Native forecast_availability is already in product UOM in Odoo20.
            'forecast_qty': product.uom_id.round(move.forecast_availability) if move.state not in ('done', 'cancel') else None,
            'availability_state': move.state, 'source_location_id': move.location_id.id,
        })
    balances = defaultdict(lambda: [0.0, 0.0])
    for quant in quants:
        balance = balances[(quant.product_id.id, quant.location_id.id)]
        balance[0] += quant.quantity
        balance[1] += quant.reserved_quantity
    for (product_id, location_id), (on_hand, reserved) in sorted(balances.items()):
        unit = products.browse(product_id).uom_id
        on_hand, reserved = unit.round(on_hand), unit.round(reserved)
        snapshot['stock'].append({'product_id': product_id, 'location_id': location_id, 'unit_id': unit.id,
                                  'on_hand_qty': on_hand, 'reserved_qty': reserved, 'free_qty': unit.round(on_hand - reserved)})
    return snapshot
