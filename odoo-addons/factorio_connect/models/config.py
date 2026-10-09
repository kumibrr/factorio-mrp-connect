import re
from uuid import UUID

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class IntegrationConfig(models.Model):
    _name = 'factorio.integration.config'
    _description = 'Factory export configuration'
    _rec_name = 'warehouse_id'
    company_id = fields.Many2one('res.company', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    source_id = fields.Char(required=True)
    enabled = fields.Boolean(default=True)
    terminal_days = fields.Integer(default=7)
    odoo_base_url = fields.Char(default='http://127.0.0.1:8069', required=True)
    webhook_url = fields.Char(groups='base.group_system')


    @api.constrains('source_id', 'company_id', 'warehouse_id', 'terminal_days', 'odoo_base_url')
    def _validate_scope(self):
        for config in self:
            try:
                UUID(config.source_id)
            except (ValueError, TypeError, AttributeError) as error:
                raise ValidationError('Source identity must be the database UUID.') from error
            if config.warehouse_id.company_id != config.company_id:
                raise ValidationError('Warehouse must belong to the configured company.')
            if config.terminal_days < 0:
                raise ValidationError('Terminal retention cannot be negative.')
            if not re.fullmatch(r'https?://[^/\s]+(?:/[^\s]*)?', config.odoo_base_url):
                raise ValidationError('The Odoo public URL must be an HTTP or HTTPS URL.')


class Users(models.Model):
    _inherit = 'res.users'
    factorio_config_id = fields.Many2one('factorio.integration.config')
