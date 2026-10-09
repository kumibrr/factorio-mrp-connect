import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from factorio_bridge.contracts import Snapshot
from factorio_bridge.coordinator import RefreshCoordinator
from factorio_bridge.store import SnapshotStore


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.origin = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
        self.sleepers = []

    def monotonic(self):
        return self.now

    def utcnow(self):
        return self.origin + timedelta(seconds=self.now)

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.sleepers.append((self.now + seconds, future))
        try:
            await future
        finally:
            self.sleepers = [(due, item) for due, item in self.sleepers if item is not future]

    async def advance(self, seconds):
        self.now += seconds
        for due, future in list(self.sleepers):
            if due <= self.now and not future.done():
                future.set_result(None)
        await settle()


async def settle():
    for _ in range(30):
        await asyncio.sleep(0)


async def wait_until(condition):
    async with asyncio.timeout(2):
        while not condition():
            await asyncio.sleep(.001)
    await settle()


def rig(tmp_path, payload, fetch):
    clock = FakeClock()
    published = []
    async def publish(stored):
        published.append(stored)
    store = SnapshotStore(tmp_path / 'cache.sqlite', source_id=UUID(payload['meta']['source_id']), scope_id=payload['meta']['scope_id'])
    return clock, published, store, RefreshCoordinator(fetch, store, publish, clock)


def test_bursts_debounce_but_do_not_starve(tmp_path, pumpworks_payload, caplog):
    caplog.set_level('INFO')
    async def scenario():
        starts = []
        async def fetch():
            starts.append(clock.now)
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        await coordinator.start()
        await wait_until(lambda: len(published) == 1)
        assert starts == [0]
        await coordinator.notify('event')
        await settle()
        await clock.advance(.249)
        assert starts == [0]
        await clock.advance(.001)
        await wait_until(lambda: len(published) == 2)
        assert starts == [0, .25]
        await coordinator.notify('event')
        await settle()
        for _ in range(9):
            await clock.advance(.1)
            await coordinator.notify('burst')
            await settle()
        assert len(starts) == 2
        await clock.advance(.1)
        assert len(starts) == 3
        assert starts[-1] <= 1.251
        await coordinator.stop()
    asyncio.run(scenario())
    assert 'published_revision=1 source_read_at=2026-10-09T12:00:00+00:00' in caplog.text


def test_changes_during_read_trigger_followup(tmp_path, pumpworks_payload):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0
        active = 0
        async def fetch():
            nonlocal calls, active
            calls += 1
            active += 1
            assert active == 1
            if calls == 1:
                entered.set()
                await release.wait()
            active -= 1
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        await coordinator.start()
        await entered.wait()
        await coordinator.notify('during read')
        await clock.advance(.3)
        assert calls == 1
        release.set()
        await wait_until(lambda: len(published) == 2)
        assert calls == 2
        assert [row.revision for row in published] == [1, 2]
        await coordinator.request_initial()
        await wait_until(lambda: len(published) == 3)
        assert calls == 3
        await coordinator.stop()
    asyncio.run(scenario())


def test_reconciliation_recovers_missed_event(tmp_path, pumpworks_payload):
    async def scenario():
        calls = 0
        async def fetch():
            nonlocal calls
            calls += 1
            payload = dict(pumpworks_payload)
            payload['products'] = [dict(row) for row in payload['products']]
            payload['products'][0]['name'] = f'Changed {calls}'
            return Snapshot.model_validate(payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        await coordinator.start()
        await wait_until(lambda: len(published) == 1)
        await clock.advance(59.999)
        assert len(published) == 1
        await clock.advance(.001)
        await wait_until(lambda: len(published) == 2)
        assert len(published) == 2
        assert published[-1].snapshot.products[0].name == 'Changed 2'
        await clock.advance(60)
        assert calls == 3
        await coordinator.stop()
    asyncio.run(scenario())


def test_retries_keep_old_source_timestamp(tmp_path, pumpworks_payload):
    async def scenario():
        fail = False
        starts = []
        async def fetch():
            starts.append(clock.now)
            if fail:
                raise RuntimeError('Bearer private-key http://bridge/odoo/events/private-token')
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        await coordinator.start()
        await wait_until(lambda: len(published) == 1)
        original = coordinator.latest.snapshot.meta.source_read_at
        fail = True
        await coordinator.request_initial()
        await settle()
        for delay in [1, 2, 4, 8, 16, 30, 30]:
            before = len(starts)
            await clock.advance(delay - .001)
            assert len(starts) == before
            await clock.advance(.001)
            assert len(starts) == before + 1
            assert coordinator.latest.snapshot.meta.source_read_at == original
            assert store.load_latest().revision == 1
        assert not coordinator.health.source_ok
        assert 'private-token' not in coordinator.health.last_error
        assert 'private-key' not in coordinator.health.last_error
        assert coordinator.health.source_age_seconds > 90
        fail = False
        await clock.advance(30)
        await wait_until(lambda: coordinator.health.source_ok)
        assert coordinator.health.source_ok
        assert coordinator.latest.revision == 2
        await coordinator.stop()
    asyncio.run(scenario())


def test_cache_restart_and_wrong_source_are_not_fresh(tmp_path, pumpworks_payload):
    async def scenario():
        entered = asyncio.Event()
        async def fetch():
            entered.set()
            await asyncio.Event().wait()
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        saved = store.save(Snapshot.model_validate(pumpworks_payload))
        await coordinator.start()
        await entered.wait()
        assert coordinator.latest.snapshot.meta.source_read_at == saved.snapshot.meta.source_read_at
        assert not coordinator.health.source_ok
        assert coordinator.health.last_success_at is None
        assert published == [saved]
        await coordinator.stop()
        other = SnapshotStore(tmp_path / 'cache.sqlite', source_id=UUID(int=1), scope_id='company:1/warehouse:1')
        other_coordinator = RefreshCoordinator(fetch, other, lambda _: None, clock)
        await other_coordinator.start()
        await settle()
        assert other_coordinator.latest is None
        assert other_coordinator.health.source_age_seconds is None
        await other_coordinator.stop()
    asyncio.run(scenario())


def test_reconnect_requests_immediate_read_even_during_retry(tmp_path, pumpworks_payload):
    async def scenario():
        failing = True
        calls = 0
        async def fetch():
            nonlocal calls
            calls += 1
            if failing:
                raise OSError('source unavailable')
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        await coordinator.start()
        await settle()
        assert calls == 1
        failing = False
        await coordinator.request_initial()
        await wait_until(lambda: coordinator.health.source_ok)
        assert calls == 2
        assert coordinator.health.source_ok
        await coordinator.stop()
    asyncio.run(scenario())


def test_sqlite_contention_keeps_webhook_fast_and_shutdown_drains_save(tmp_path, pumpworks_payload):
    """A real competing writer must not stall HTTP or outlive coordinator stop."""
    import sqlite3
    import threading
    import time
    import httpx
    from factorio_bridge.app import create_app
    from test_webhooks import settings

    async def scenario():
        fetched = asyncio.Event()
        async def fetch():
            fetched.set()
            await asyncio.sleep(0)
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        locked, release = threading.Event(), threading.Event()
        def hold_writer():
            with sqlite3.connect(store.path) as connection:
                connection.execute('BEGIN IMMEDIATE')
                locked.set()
                release.wait(.6)
                connection.rollback()
        writer = threading.Thread(target=hold_writer)
        writer.start()
        await asyncio.to_thread(locked.wait)
        app = create_app(settings(tmp_path), coordinator)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            async def request_during_save():
                await fetched.wait()
                started = time.monotonic()
                await asyncio.sleep(.01)
                response = await client.post('/odoo/events/test-token', json={'_model': 'mrp.workorder', '_id': 1, '_action': 'Factorio workorder'})
                return response, time.monotonic() - started
            request = asyncio.create_task(request_during_save())
            try:
                await coordinator.start()
                response, elapsed = await request
                assert response.status_code == 202
                print(f'Writer contention: webhook 202 in {elapsed * 1000:.3f} ms')
                assert elapsed < .25
                assert not release.is_set()
                assert coordinator.health.refreshing
                stopping = asyncio.create_task(coordinator.stop())
                await asyncio.sleep(.01)
                assert not stopping.done()
                assert published == []
                release.set()
                await asyncio.wait_for(stopping, 2)
                assert store.load_latest().revision == 1
                assert published == []
                assert not coordinator.health.refreshing
            finally:
                release.set()
                await coordinator.stop()
                await asyncio.to_thread(writer.join)
    asyncio.run(scenario())


def test_startup_cache_contention_does_not_block_health(tmp_path, pumpworks_payload):
    import sqlite3
    import threading
    import time
    import httpx
    from factorio_bridge.app import create_app
    from test_webhooks import settings

    async def scenario():
        async def fetch():
            await asyncio.Event().wait()
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        store.save(Snapshot.model_validate(pumpworks_payload))
        locked, release = threading.Event(), threading.Event()
        def hold_exclusive():
            with sqlite3.connect(store.path) as connection:
                connection.execute('BEGIN EXCLUSIVE')
                locked.set()
                release.wait(.6)
                connection.rollback()
        writer = threading.Thread(target=hold_exclusive)
        writer.start()
        await asyncio.to_thread(locked.wait)
        app = create_app(settings(tmp_path), coordinator)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            started = time.monotonic()
            startup = asyncio.create_task(coordinator.start())
            try:
                await asyncio.sleep(.01)
                health = await client.get('/healthz')
                assert health.status_code == 200
                elapsed = time.monotonic() - started
                print(f'Startup exclusive-lock contention: health 200 in {elapsed * 1000:.3f} ms')
                assert elapsed < .25
                assert not startup.done()
                release.set()
                await asyncio.wait_for(startup, 2)
                assert coordinator.latest.revision == 1
                assert not coordinator.health.source_ok
            finally:
                release.set()
                await startup
                await coordinator.stop()
                await asyncio.to_thread(writer.join)
    asyncio.run(scenario())


def test_stop_during_startup_drains_cache_read_without_starting_worker(tmp_path, pumpworks_payload):
    import sqlite3
    import threading
    async def scenario():
        calls = []
        async def fetch():
            calls.append('unexpected after shutdown')
            return Snapshot.model_validate(pumpworks_payload)
        clock, published, store, coordinator = rig(tmp_path, pumpworks_payload, fetch)
        store.save(Snapshot.model_validate(pumpworks_payload))
        locked, release = threading.Event(), threading.Event()
        def hold_exclusive():
            with sqlite3.connect(store.path) as connection:
                connection.execute('BEGIN EXCLUSIVE')
                locked.set()
                release.wait(.6)
                connection.rollback()
        writer = threading.Thread(target=hold_exclusive)
        writer.start()
        await asyncio.to_thread(locked.wait)
        startup = asyncio.create_task(coordinator.start())
        try:
            await asyncio.sleep(.01)
            stopping = asyncio.create_task(coordinator.stop())
            await asyncio.sleep(.01)
            assert not stopping.done()
            release.set()
            await asyncio.wait_for(stopping, 2)
            try:
                await startup
            except asyncio.CancelledError:
                pass
            assert calls == []
            assert published == []
        finally:
            release.set()
            startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
            await coordinator.stop()
            await asyncio.to_thread(writer.join)
    asyncio.run(scenario())
