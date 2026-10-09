"""Opening counts use the inventory application workflow, exactly once."""
from odoo.exceptions import ValidationError


def post_opening_stock(env, fixtures, spec):
    for product in spec['products']:
        if not product['opening']:
            continue
        p = fixtures[product['id']]
        before = env['stock.move'].search([('product_id', '=', p.id)])
        quant = env['stock.quant'].with_context(inventory_mode=True).create({'product_id': p.id, 'location_id': fixtures['location_stock'].id, 'inventory_quantity': product['opening']})
        action = quant.action_apply_inventory()
        if isinstance(action, dict):
            raise ValidationError(product['id'] + ': opening inventory returned unexpected conflict action')
        fixtures.alias('opening_' + product['id'].removeprefix('product_'), quant)
        moves = env['stock.move'].search([('product_id', '=', p.id)]) - before
        for index, move in enumerate(moves.sorted('id'), 1):
            fixtures.alias('opening_move_' + product['id'].removeprefix('product_') + '_' + str(index), move)
