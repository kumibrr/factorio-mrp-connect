"""Live seeded bearer HTTP integration; isolated test database only."""
import json
from datetime import datetime, timezone
from dataclasses import asdict



def bootstrap(env):
    from odoo.addons.factorio_connect.tests.json2_probe import PROBE_FILE
    from ..seed.service import seed_demo, verify_demo
    if env.cr.dbname != 'factorio_tests':
        raise RuntimeError('Seed HTTP probe only permits the isolated factorio_tests database')
    report = seed_demo(env, now=datetime.now(timezone.utc))
    env.flush_all()
    # An ordinary rerun must preserve IDs and create no additional stock moves.
    before = env['stock.move'].search([]).ids
    assert seed_demo(env, now=datetime.now(timezone.utc)).fixture_ids == report.fixture_ids
    assert env['stock.move'].search([]).ids == before
    verify_demo(env, baseline=True)
    bot = env.ref('factorio_connect_demo.integration_user')
    key = env['res.users.apikeys'].with_user(bot).sudo()._generate('rpc', 'isolated seeded HTTP probe', None)
    env.cr.commit()
    PROBE_FILE.touch(mode=0o600)
    PROBE_FILE.write_text(json.dumps({'key': key, 'mo_id': env.ref('factorio_connect_demo.mo_ready').id, 'company_id': env.ref('factorio_connect_demo.company').id, 'fixtures': report.fixture_ids}))
    print('Committed seed report: ' + json.dumps(asdict(report), sort_keys=True))


def validate(snapshot, fixture):
    refs = fixture['fixtures']
    assert len(snapshot['products']) == 10
    assert len(snapshot['boms']) == 2
    assert len(snapshot['work_centers']) == 4
    assert len(snapshot['manufacturing_orders']) == 8
    assert len(snapshot['work_orders']) == 22
    expected = {'blank': (40, 0, 40), 'housing': (86, 34, 52), 'motor': (28, 28, 0), 'shaft': (86, 34, 52), 'bearing': (172, 68, 104), 'seal': (86, 34, 52), 'fastener': (86, 34, 52), 'carton': (86, 34, 52), 'impeller': (46, 34, 12), 'pump': (14, 0, 14)}
    for key, balance in expected.items():
        rows = [row for row in snapshot['stock'] if row['product_id'] == refs['product_' + key]['id']]
        actual = tuple(sum(row[field] for row in rows) for field in ('on_hand_qty', 'reserved_qty', 'free_qty'))
        assert actual == balance, (key, actual, balance)
    demand = next(row for row in snapshot['material_demands'] if row['mo_id'] == refs['mo_shortage']['id'] and row['product_id'] == refs['product_motor']['id'])
    assert (demand['demand_qty'], demand['reserved_qty'], demand['unreserved_qty']) == (8, 2, 6)
    assert sum(row['posted_qty'] for row in snapshot['manufacturing_orders'] if row['product_id'] == refs['product_pump']['id']) == 14


if __name__ == '__main__':
    import runpy
    from pathlib import Path
    probe = runpy.run_path(str(Path(__file__).parents[2] / 'factorio_connect' / 'tests' / 'json2_probe.py'))
    probe['fetch'](validate)
