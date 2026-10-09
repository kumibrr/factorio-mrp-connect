"""Administrative configuration of native postcommit webhook notifications."""
from odoo import Command, models
from odoo.exceptions import AccessError

from ..logging import install_redaction

MODELS = {
    'workcenter': 'mrp.workcenter', 'production': 'mrp.production',
    'workorder': 'mrp.workorder', 'productivity': 'mrp.workcenter.productivity',
    'loss': 'mrp.workcenter.productivity.loss', 'bom': 'mrp.bom',
    'bom_line': 'mrp.bom.line', 'operation': 'mrp.routing.workcenter',
    'product': 'product.product', 'template': 'product.template', 'unit': 'uom.uom',
    'move': 'stock.move', 'move_line': 'stock.move.line', 'quant': 'stock.quant',
}
_NAMESPACE = 'factorio_connect_demo'


def _upsert(env, key, model, values):
    record = env.ref(f'{_NAMESPACE}.{key}', raise_if_not_found=False)
    if record and record.exists():
        if record._name != model:
            raise ValueError('Automation XML identity refers to another model')
        record.write(values)
    else:
        record = env[model].create(values)
        identity = env['ir.model.data'].search([('module', '=', _NAMESPACE), ('name', '=', key)])
        if identity:
            identity.write({'model': model, 'res_id': record.id})
        else:
            env['ir.model.data'].create({'module': _NAMESPACE, 'name': key, 'model': model, 'res_id': record.id, 'noupdate': True})
    return record


def configure_automations(env, config) -> dict[str, int]:
    if not env.su and not env.user.has_group('base.group_system'):
        raise AccessError('Only administrators may configure factory notifications')
    config.ensure_one()
    install_redaction()
    identifiers = {}
    for key, model in MODELS.items():
        domain = []
        if 'company_id' in env[model]._fields:
            domain.append(('company_id', 'in', [False, config.company_id.id]))
        if model == 'stock.quant':
            domain.append(('location_id', 'child_of', config.warehouse_id.lot_stock_id.id))
        model_id = env['ir.model']._get_id(model)
        # Keep disabled while replacing configuration so no half-configured rule runs.
        rule = _upsert(env, 'automation_' + key, 'base.automation', {
            'name': 'Factorio ' + key, 'model_id': model_id,
            'trigger': 'on_create_or_write', 'active': False,
            'filter_domain': repr(domain), 'filter_pre_domain': '[]',
            'trigger_field_ids': [Command.clear()], 'log_webhook_calls': False,
        })
        action = _upsert(env, 'webhook_' + key, 'ir.actions.server', {
            'name': 'Factorio ' + key, 'model_id': model_id, 'state': 'webhook',
            'base_automation_id': rule.id, 'webhook_url': config.webhook_url or False,
            'webhook_field_ids': [Command.clear()],
        })
        rule.write({'action_server_ids': [Command.set([action.id])], 'active': bool(config.enabled and config.webhook_url)})
        identifiers[key] = rule.id
    return identifiers


class ServerAction(models.Model):
    _inherit = 'ir.actions.server'

    def _run_action_webhook(self, eval_context=None):
        # Attach to every current handler before native logging or deferred callbacks.
        # Delivery/payload/timeout remain Odoo's native postcommit implementation.
        install_redaction()
        return super()._run_action_webhook(eval_context)
