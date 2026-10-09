from datetime import datetime, timezone

from odoo import api, models
from odoo.exceptions import AccessError

from .snapshot import build_snapshot


class Factory(models.AbstractModel):
    _name = 'factorio.factory'
    _description = 'Read-only factory snapshot'

    @api.model
    @api.readonly
    def get_snapshot(self):
        # Discard all caller context before reading configuration or business data.
        env = self.env(context={})
        user = env.user
        if not user.has_group('factorio_connect.group_factory_reader'):
            raise AccessError('A dedicated factory reader is required.')
        config = user.factorio_config_id
        if not config or not config.enabled:
            raise AccessError('Factory export is not configured or enabled.')
        if config.company_id not in user.company_ids or config.warehouse_id.company_id != config.company_id:
            raise AccessError('Factory company and warehouse are not authorized.')
        # Additive access grants must never turn this API account into a writer.
        for model in (
            'factorio.integration.config', 'mrp.production', 'mrp.production.group', 'mrp.workorder',
            'mrp.workcenter', 'mrp.workcenter.capacity', 'mrp.workcenter.productivity',
            'mrp.workcenter.productivity.loss', 'mrp.workcenter.productivity.loss.type',
            'mrp.bom', 'mrp.bom.line', 'mrp.routing.workcenter',
            'stock.warehouse', 'stock.location', 'stock.picking.type', 'stock.move', 'stock.move.line', 'stock.quant',
            'product.product', 'product.template', 'product.category', 'uom.uom', 'decimal.precision',
            'resource.resource', 'resource.calendar', 'resource.calendar.attendance', 'resource.calendar.leaves', 'res.company',
        ):
            for operation in ('create', 'write', 'unlink'):
                if not env[model]._access_domain(operation).is_false():
                    raise AccessError('Factory reader has write-capable business permissions.')
        env = self.with_context({
            'allowed_company_ids': [config.company_id.id], 'active_test': False,
            'warehouse_id': config.warehouse_id.id,
            'location': config.warehouse_id.lot_stock_id.id, 'lang': 'en_US', 'tz': 'UTC',
        }).env
        return build_snapshot(env, config.with_env(env), datetime.now(timezone.utc))
