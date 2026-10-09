from odoo import fields, models


class DemoManifest(models.Model):
    _name = 'factorio.demo.manifest'
    _description = 'Transactional PumpWorks seed manifest'

    seed_version = fields.Integer(required=True)
    initialized_at = fields.Datetime(required=True)
    initialized = fields.Boolean(default=False)
    company_id = fields.Many2one('res.company', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    fixture_ids = fields.Json(required=True)
    baseline = fields.Json(required=True)
