"""Run only from scripts/check against its disposable seeded Odoo database."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from factorio_bridge.odoo import OdooClient
from factorio_bridge.settings import Settings
from factorio_bridge.store import SnapshotStore


async def probe():
    private = json.loads(Path('/odoo/factorio-json2-probe.json').read_text())
    configured = Settings(odoo_base_url='http://odoo:8069', database='factorio_tests', api_key=private['key'], webhook_token='isolated-test-token', pairing_token='isolated-test-pairing', source_id=private['source_id'], scope_id=private['scope_id'])
    async with httpx.AsyncClient(trust_env=False) as http:
        for attempt in range(60):
            try:
                ready = await http.get('http://odoo:8069/web/login?db=factorio_tests', timeout=2)
                if ready.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(.5)
        else:
            raise RuntimeError('Isolated Odoo did not become ready')
        snapshot = await OdooClient(configured, http).get_snapshot()
    assert (len(snapshot.products), len(snapshot.boms), len(snapshot.work_centers), len(snapshot.manufacturing_orders), len(snapshot.work_orders)) == (10, 2, 4, 8, 22)
    assert sum(row.posted_qty for row in snapshot.manufacturing_orders if row.product_id == private['fixtures']['product_pump']['id']) == 14
    demand = next(row for row in snapshot.material_demands if row.mo_id == private['fixtures']['mo_shortage']['id'] and row.product_id == private['fixtures']['product_motor']['id'])
    assert demand.unreserved_qty == 6
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'cache.sqlite'
        store = SnapshotStore(path, source_id=configured.source_id, scope_id=configured.scope_id)
        store.save(snapshot)
        reopened = SnapshotStore(path, source_id=configured.source_id, scope_id=configured.scope_id)
        loaded = reopened.load_latest()
        assert loaded.revision == 1
        assert loaded.snapshot.meta.source_read_at == snapshot.meta.source_read_at
        assert reopened.save(snapshot).revision == 2
    print('Live OdooClient seeded bot read: products=10 BOMs=2 centers=4 MOs=8 WOs=22 posted_pumps=14 missing_motors=6; SQLite restart retained source_read_at=' + snapshot.meta.source_read_at.isoformat() + '; revisions=1,2')


if __name__ == '__main__':
    asyncio.run(probe())
