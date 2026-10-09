import asyncio
import time
from uuid import UUID

import httpx

from factorio_bridge.app import create_app
from factorio_bridge.coordinator import RefreshCoordinator
from factorio_bridge.settings import Settings
from test_coordinator import rig, settle


def settings(tmp_path):
    return Settings(odoo_base_url='http://127.0.0.1:8069', api_key='private-key', webhook_token='test-token', source_id=UUID('12345678-1234-5678-1234-567812345679'), scope_id='company:1/warehouse:1', cache_path=tmp_path / 'cache.sqlite')


def test_webhook_returns_before_blocked_source_read(tmp_path, pumpworks_payload):
    async def scenario():
        entered = asyncio.Event()
        async def fetch():
            entered.set()
            await asyncio.Event().wait()
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        app = create_app(settings(tmp_path), coordinator)
        async with app.router.lifespan_context(app):
            await entered.wait()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                started = time.monotonic()
                response = await client.post('/odoo/events/test-token', json={'_model': 'mrp.workorder', '_id': 1, '_action': 'Factorio workorder'})
                assert response.status_code == 202
                assert time.monotonic() - started < .25
                assert coordinator.health.refreshing
                health = (await client.get('/healthz')).json()
                assert health['source_ok'] is False
                assert 'private-key' not in str(health)
                assert 'test-token' not in str(health)
    asyncio.run(scenario())


def test_invalid_token_payload_and_oversize_never_schedule_reads(tmp_path, pumpworks_payload):
    async def scenario():
        async def fetch():
            raise AssertionError('Invalid requests scheduled source IO')
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        app = create_app(settings(tmp_path), coordinator)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            payload = {'_model': 'mrp.workorder', '_id': 1, '_action': 'Factorio workorder'}
            assert (await client.post('/odoo/events/wrong', json=payload)).status_code == 404
            for invalid in [{**payload, '_id': True}, {**payload, '_model': 'res.users'}, {**payload, 'secret': 'x'}, {**payload, '_action': ''}]:
                assert (await client.post('/odoo/events/test-token', json=invalid)).status_code == 422
            assert (await client.post('/odoo/events/test-token', content=b'x' * 4097)).status_code == 413
            assert (await client.post('/odoo/events/test-token', content=b'{')).status_code == 422
        assert not coordinator.dirty
    asyncio.run(scenario())
