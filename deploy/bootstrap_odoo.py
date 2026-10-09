"""Trusted local Odoo-shell provisioning; never an RPC/public addon interface."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODE = 'provision'
INPUT = Path('/var/lib/odoo/factorio-bootstrap-input.json')
OUTPUT = Path('/var/lib/odoo/factorio-bootstrap-result.json')
if env.cr.dbname != 'factorio_demo':
    raise RuntimeError('bootstrap only targets the demo database')

from odoo.addons.factorio_connect.models.automation import configure_automations
from factorio_connect_common.redaction import install_redaction

payload = json.loads(INPUT.read_text())
install_redaction([payload['admin_password'], payload['operator_password'], payload['webhook_token']])
bot = env.ref('factorio_connect_demo.integration_user')
config = env.ref('factorio_connect_demo.integration_config')
source_id = env['ir.config_parameter'].get_str('database.uuid')
if config.source_id != source_id:
    raise RuntimeError('database UUID differs from existing seed binding; explicit reset/re-pair required')
# This invokes the same export security gate, including additive effective grants.
env['factorio.factory'].with_user(bot).get_snapshot()
previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else None
managed_name = 'factorio-connect local bridge (30 days)'
keys = env['res.users.apikeys'].search([('user_id', '=', bot.id), ('name', '=', managed_name)])
try:
    if MODE == 'revoke':
        if not previous or not payload['rotate']:
            raise RuntimeError('explicit rotation required before managed-key revocation')
        old = keys.filtered(lambda row: row.id != previous['key_id'])
        old._remove()
        env.cr.commit()
    else:
        if previous and not payload['rotate']:
            if previous['source_id'] != source_id or previous['bot_id'] != bot.id:
                raise RuntimeError('persisted key identity differs from demo; explicit reset required')
            if env['res.users.apikeys']._check_credentials(scope='rpc', key=previous['api_key']) != bot.id:
                raise RuntimeError('bot key is expired/revoked; use --rotate-api-key')
            result = previous
        else:
            expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
            key = env['res.users.apikeys'].with_user(bot).sudo()._generate('rpc', managed_name, expires)
            record = env['res.users.apikeys'].search([('user_id', '=', bot.id), ('name', '=', managed_name)], order='id desc', limit=1)
            result = {'api_key': key, 'key_id': record.id, 'bot_id': bot.id, 'source_id': source_id, 'scope_id': f'company:{config.company_id.id}/warehouse:{config.warehouse_id.id}', 'key_expires': expires.isoformat() + 'Z'}
        if not previous:
            env.ref('base.user_admin').password = payload['admin_password']
            env.ref('factorio_connect_demo.operator').password = payload['operator_password']
        config.write({'odoo_base_url': payload['public_url'], 'webhook_url': payload['webhook_origin'] + '/odoo/events/' + payload['webhook_token'], 'enabled': True})
        rules = configure_automations(env, config)
        if len(rules) != 14:
            raise RuntimeError('expected exactly 14 demo automations')
        # Durable replacement is stored before any previous key is revoked.
        env.cr.commit()
        descriptor = os.open(OUTPUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(result, stream, sort_keys=True)
finally:
    if MODE == 'revoke' or not payload['rotate']:
        INPUT.unlink(missing_ok=True)
