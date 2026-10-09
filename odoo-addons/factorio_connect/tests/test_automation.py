import ast
import io
import json
import logging
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged
from requests.exceptions import RequestException

from .common import FactoryCase


@tagged('post_install', '-at_install')
class TestAutomation(FactoryCase):
    def test_fourteen_scoped_rules_and_empty_business_fields(self):
        from ..models.automation import configure_automations
        ids = configure_automations(self.env, self.config)
        expected = {'workcenter': 'mrp.workcenter', 'production': 'mrp.production', 'workorder': 'mrp.workorder', 'productivity': 'mrp.workcenter.productivity', 'loss': 'mrp.workcenter.productivity.loss', 'bom': 'mrp.bom', 'bom_line': 'mrp.bom.line', 'operation': 'mrp.routing.workcenter', 'product': 'product.product', 'template': 'product.template', 'unit': 'uom.uom', 'move': 'stock.move', 'move_line': 'stock.move.line', 'quant': 'stock.quant'}
        self.assertEqual(set(ids), set(expected))
        for key, model in expected.items():
            rule = self.env.ref('factorio_connect_demo.automation_' + key)
            action = self.env.ref('factorio_connect_demo.webhook_' + key)
            self.assertEqual(rule.id, ids[key])
            self.assertEqual(rule.model_id.model, model)
            self.assertEqual(rule.trigger, 'on_create_or_write')
            self.assertFalse(rule.active)
            self.assertEqual(rule.action_server_ids, action)
            self.assertEqual(action.state, 'webhook')
            self.assertFalse(action.webhook_field_ids)
            self.assertFalse(rule.trigger_field_ids)
            if 'company_id' in self.env[model]._fields:
                self.assertIn(('company_id', 'in', [False, self.company.id]), ast.literal_eval(rule.filter_domain))
        quant = self.env.ref('factorio_connect_demo.automation_quant')
        self.assertIn(('location_id', 'child_of', self.warehouse.lot_stock_id.id), ast.literal_eval(quant.filter_domain))
        self.config.webhook_url = 'http://bridge/odoo/events/test-token'
        self.assertEqual(configure_automations(self.env, self.config), ids)
        rules = self.env['base.automation'].browse(list(ids.values()))
        self.assertTrue(all(rules.mapped('active')))
        production = self.env.ref('factorio_connect_demo.automation_production')
        self.assertFalse(self.foreign_mo.filtered_domain(ast.literal_eval(production.filter_domain)))
        self.assertTrue(self.mo.filtered_domain(ast.literal_eval(production.filter_domain)))
        with self.assertRaises(AccessError):
            configure_automations(self.env(user=self.bot), self.config.with_user(self.bot))

    def test_webhook_payload_and_postcommit_registration(self):
        from ..models.automation import configure_automations
        self.config.webhook_url = 'http://bridge/odoo/events/test-token'
        configure_automations(self.env, self.config)
        action = self.env.ref('factorio_connect_demo.webhook_workcenter')
        commits, rollbacks, requests = [], [], []
        class Response:
            def raise_for_status(self):
                return None
        def post(url, **kwargs):
            requests.append((url, kwargs))
            return Response()
        before_commit = len(self.env.cr.postcommit._funcs)
        before_rollback = len(self.env.cr.postrollback._funcs)
        with patch('requests.post', post):
            self.center.write({'name': 'Renamed assembly'})
            commits = list(self.env.cr.postcommit._funcs)[before_commit:]
            rollbacks = list(self.env.cr.postrollback._funcs)[before_rollback:]
            self.assertEqual(len(commits), 1)
            self.assertEqual(len(rollbacks), 1)
            self.assertEqual(requests, [])
            commits[0]()
        url, kwargs = requests[0]
        self.assertEqual(url, self.config.webhook_url)
        self.assertEqual(json.loads(kwargs['data']), {'_model': 'mrp.workcenter', '_id': self.center.id, '_action': f'{action.name}(#{action.id})'})
        self.assertEqual(kwargs['timeout'], 1)

    def test_success_failure_rollback_logs_redact_url_token(self):
        from ..models.automation import configure_automations
        from ..logging import install_redaction
        self.config.webhook_url = 'http://bridge/odoo/events/top-secret-token'
        configure_automations(self.env, self.config)
        logger = logging.getLogger('odoo.addons.base.models.ir_actions')
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        install_redaction()
        try:
            commits, rollbacks = [], []
            action = self.env.ref('factorio_connect_demo.webhook_workcenter')
            class Response:
                def raise_for_status(self):
                    return None
            before_commit = len(self.env.cr.postcommit._funcs)
            before_rollback = len(self.env.cr.postrollback._funcs)
            action.with_context(active_model='mrp.workcenter', active_id=self.center.id)._run_action_webhook({})
            commits = list(self.env.cr.postcommit._funcs)[before_commit:]
            rollbacks = list(self.env.cr.postrollback._funcs)[before_rollback:]
            with patch('requests.post', return_value=Response()):
                commits[0]()
            with patch('requests.post', side_effect=RequestException(self.config.webhook_url)):
                commits[0]()
            rollbacks[0]()
            try:
                raise RequestException(self.config.webhook_url)
            except RequestException:
                logger.exception('Traceback URL')
            output = stream.getvalue()
            self.assertNotIn('top-secret-token', output)
            self.assertIn('succeeded', output)
            self.assertIn('rollback', output)
            self.assertIn('Webhook call failed', output)
            self.assertIn('RequestException', output)
        finally:
            logger.setLevel(old_level)
            logger.removeHandler(handler)
