import asyncio
import time
from uuid import UUID

import httpx

from factorio_bridge.app import create_app
from factorio_bridge.coordinator import RefreshCoordinator
from factorio_bridge.settings import Settings
from test_coordinator import rig, settle, wait_until


def settings(tmp_path):
    return Settings(odoo_base_url='http://127.0.0.1:8069', api_key='private-key', webhook_token='test-token', pairing_token='pairing-secret', source_id=UUID('12345678-1234-5678-1234-567812345679'), scope_id='company:1/warehouse:1', cache_path=tmp_path / 'cache.sqlite')


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


def test_udp_lifecycle_reconnect_and_health_revisions(tmp_path, pumpworks_payload, caplog):
    caplog.set_level('INFO')
    from factorio_bridge.udp import UdpDelivery
    from factorio_bridge.contracts import Snapshot
    import json
    async def scenario():
        entered = asyncio.Event()
        async def fetch():
            entered.set()
            await asyncio.Event().wait()
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        saved = store.save(Snapshot.model_validate(pumpworks_payload))
        configured = settings(tmp_path).model_copy(update={'udp_port': 0, 'game_udp_port': 34201})
        delivery = UdpDelivery(configured, clock)
        coordinator.publish = delivery.enqueue
        app = create_app(configured, coordinator, delivery)
        async with app.router.lifespan_context(app):
            await entered.wait()
            assert delivery._transport is not None
            await wait_until(lambda: delivery.latest is not None)
            assert delivery.latest.revision == saved.revision
            # Reconnect must immediately override even a future source retry.
            coordinator.dirty = False
            coordinator._retry_at = 30
            delivery.handle_packet(json.dumps(dict(version=1, type='hello', token='pairing-secret', hello_nonce='initial')).encode(), ('127.0.0.1', 34201))
            await settle()
            assert not coordinator.dirty and coordinator._retry_at == 30
            challenge = next(iter(delivery._pending_challenges))
            delivery.handle_packet(json.dumps(dict(version=1, type='hello', token='pairing-secret', hello_nonce=challenge, challenge_id=challenge)).encode(), ('127.0.0.1', 34201))
            await settle()
            assert coordinator.dirty and coordinator._retry_at is None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                health = (await client.get('/healthz')).json()
                assert health['latest_revision'] == 1
                assert health['source_read_at'] == '2026-10-09T12:00:00+00:00'
                assert health['applied_revision'] is None
                assert 'pairing-secret' not in str(health)
                # Current exact ack can report applied only after all chunks sent.
                while delivery.session.next_index < len(delivery.session.frames) - 1:
                    for index in list(delivery.session.pending):
                        row = dict(delivery.session.envelope('chunk_ack'), snapshot_id=delivery.session.snapshot_id, index=index)
                        delivery.handle_packet(json.dumps(row).encode(), ('127.0.0.1', 34201))
                row = dict(delivery.session.envelope('snapshot_applied'), revision=1, snapshot_id=delivery.session.snapshot_id)
                delivery.handle_packet(json.dumps(row).encode(), ('127.0.0.1', 34201))
                health = (await client.get('/healthz')).json()
                assert health['applied_revision'] == 1
                delivery.handle_packet(json.dumps(dict(version=1, type='hello', token='pairing-secret', hello_nonce='reconnect')).encode(), ('127.0.0.1', 34201))
                assert (await client.get('/healthz')).json()['applied_revision'] == 1
                challenge = next(iter(delivery._pending_challenges))
                delivery.handle_packet(json.dumps(dict(version=1, type='hello', token='pairing-secret', hello_nonce=challenge, challenge_id=challenge)).encode(), ('127.0.0.1', 34201))
                assert (await client.get('/healthz')).json()['applied_revision'] is None
        assert delivery._transport is None
        assert delivery.session is None
    asyncio.run(scenario())
    assert 'applied_revision=1 source_read_at=2026-10-09T12:00:00+00:00' in caplog.text
