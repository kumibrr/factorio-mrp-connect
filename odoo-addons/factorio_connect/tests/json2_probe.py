"""Isolated live HTTP probe. Executed by scripts/check, never on a demo DB."""
import json
import os
from pathlib import Path
from time import sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROBE_FILE = Path('/var/lib/odoo/factorio-json2-probe.json')


def bootstrap(env):
    from odoo import Command
    if env.cr.dbname != 'factorio_tests':
        raise RuntimeError('The live probe may only bootstrap factorio_tests.')
    company = env.company
    warehouse = env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
    unit = env.ref('uom.product_uom_unit')
    product = env['product.product'].create({'name': 'HTTP probe pump', 'is_storable': True, 'uom_id': unit.id})
    component = env['product.product'].create({'name': 'HTTP probe motor', 'is_storable': True, 'uom_id': unit.id})
    center = env['mrp.workcenter'].create({'name': 'HTTP probe assembly', 'company_id': company.id})
    bom = env['mrp.bom'].create({
        'product_tmpl_id': product.product_tmpl_id.id, 'product_id': product.id, 'company_id': company.id,
        'product_qty': 1, 'uom_id': unit.id,
        'operation_ids': [Command.create({'name': 'Assemble', 'workcenter_id': center.id})],
        'bom_line_ids': [Command.create({'product_id': component.id, 'product_qty': 2, 'uom_id': unit.id})],
    })
    env['stock.quant'].create({'product_id': component.id, 'location_id': warehouse.lot_stock_id.id,
                              'inventory_quantity': 50}).action_apply_inventory()
    mo = env['mrp.production'].create({'product_id': product.id, 'product_qty': 10, 'uom_id': unit.id,
                                      'bom_id': bom.id, 'picking_type_id': warehouse.manu_type_id.id})
    mo.action_confirm()
    mo.action_assign()
    config = env['factorio.integration.config'].create({
        'company_id': company.id, 'warehouse_id': warehouse.id,
        'source_id': env['ir.config_parameter'].get_str('database.uuid'),
    })
    bot = env['res.users'].create({
        'name': 'Live HTTP factory reader', 'login': 'factorio-http-probe',
        'company_id': company.id, 'company_ids': [Command.set([company.id])],
        'group_ids': [Command.set([env.ref('factorio_connect.group_factory_reader').id])],
        'factorio_config_id': config.id,
    })
    key = env['res.users.apikeys'].with_user(bot).sudo()._generate('rpc', 'isolated HTTP probe', None)
    env.cr.commit()
    PROBE_FILE.touch(mode=0o600)
    PROBE_FILE.write_text(json.dumps({'key': key, 'mo_id': mo.id, 'company_id': company.id}))


def fetch(validate=None):
    import psycopg2
    fixture = json.loads(PROBE_FILE.read_text())
    connection = psycopg2.connect(dbname='factorio_tests', user=os.environ['USER'],
                                  password=os.environ['PASSWORD'], host=os.environ['HOST'])
    def business_digest():
        with connection.cursor() as cursor:
            results = []
            for table in ('mrp_production', 'mrp_workorder', 'mrp_workcenter', 'mrp_bom',
                          'stock_move', 'stock_move_line', 'stock_quant', 'product_product'):
                cursor.execute(f"SELECT md5(string_agg(row_to_json(t)::text, ',' ORDER BY id)) FROM {table} t")
                results.append(cursor.fetchone())
            connection.commit()
            return results
    def call(model, method, data):
        request = Request(f'http://127.0.0.1:8069/json/2/{model}/{method}',
                          data=json.dumps(data).encode(), method='POST', headers={
                              'Content-Type': 'application/json', 'X-Odoo-Database': 'factorio_tests',
                              'Authorization': 'Bearer ' + fixture['key'],
                          })
        with urlopen(request, timeout=30) as response:
            assert response.status == 200
            return json.load(response)
    for _ in range(60):
        try:
            with urlopen('http://127.0.0.1:8069/web/login?db=factorio_tests', timeout=2):
                break
        except (OSError, HTTPError):
            sleep(1)
    before = business_digest()
    snapshot = call('factorio.factory', 'get_snapshot', {'context': {'warehouse_id': -1, 'active_test': True}})
    assert snapshot['meta']['company_id'] == fixture['company_id']
    if validate is None:
        assert len(snapshot['manufacturing_orders']) == 1
        row = snapshot['manufacturing_orders'][0]
        assert (row['requested_qty'], row['posted_qty']) == (10, 0)
        assert len(snapshot['work_orders']) == 1
        assert snapshot['material_demands'][0]['reserved_qty'] == 20
    else:
        validate(snapshot, fixture)
    assert before == business_digest(), 'JSON2 export changed business rows'
    try:
        call('mrp.production', 'write', {'ids': [fixture['mo_id']], 'vals': {'origin': 'forbidden'}})
    except HTTPError as error:
        assert error.code == 403, (error.code, error.read().decode())
    else:
        raise AssertionError('Bearer bot was able to write an MO')
    assert before == business_digest(), 'Denied bearer write changed business rows'
    connection.close()
    PROBE_FILE.unlink()
    print(json.dumps(snapshot, ensure_ascii=False))


if __name__ == '__main__':
    fetch()
