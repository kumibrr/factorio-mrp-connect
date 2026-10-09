"""Bounded sender and an actual loopback client under fixed loss/reordering."""
import asyncio
import json
from uuid import UUID

import pytest

from factorio_bridge.contracts import Snapshot, snapshot_bytes
from factorio_bridge.coordinator import BridgeHealth, SystemClock
from factorio_bridge.udp import UdpDelivery
from factorio_bridge.store import StoredSnapshot
from test_coordinator import FakeClock, settle, wait_until
from test_webhooks import settings


class Network:
    def __init__(self):
        self.rows = []
    def sendto(self, data, addr):
        self.rows.append(json.loads(data))


def rig(tmp_path, payload):
    config = settings(tmp_path).model_copy(update={'pairing_token': __import__('pydantic').SecretStr('pairing-secret'), 'udp_port': 34200, 'game_udp_port': 34199})
    clock = FakeClock()
    delivery = UdpDelivery(config, clock)
    network = Network()
    delivery._transport = network
    delivery.set_snapshot(StoredSnapshot(1, Snapshot.model_validate(payload)))
    hello(delivery)
    return clock, delivery, network


def hello(delivery, **updates):
    row = dict(version=1, type='hello', token='pairing-secret', hello_nonce='fresh')
    row.update(updates)
    delivery.handle_packet(json.dumps(row).encode(), ('127.0.0.1', delivery.settings.game_udp_port))


def ack(delivery, kind, allow_partial=False, **fields):
    if kind == 'snapshot_applied' and not allow_partial:
        while delivery.session.frames and delivery.session.next_index < len(delivery.session.frames) - 1:
            for index in list(delivery.session.pending):
                ack(delivery, 'chunk_ack', snapshot_id=delivery.session.snapshot_id, index=index)
    row = delivery.session.envelope(kind)
    row.update(fields)
    delivery.handle_packet(json.dumps(row).encode(), ('127.0.0.1', delivery.settings.game_udp_port))


def chunks(network):
    return [row for row in network.rows if row['type'] == 'snapshot_chunk']


def test_rejects_oversize_before_publishing(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    pumpworks_payload['products'][0]['name'] = 'a' * 262144
    with pytest.raises(ValueError):
        delivery.set_snapshot(StoredSnapshot(2, Snapshot.model_validate(pumpworks_payload)))
    assert delivery.latest.revision == 1
    assert {row['revision'] for row in chunks(network)} == {1}


def test_eight_frame_window_and_rate(tmp_path, pumpworks_payload):
    pumpworks_payload['products'][0]['name'] = 'a' * 150000
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    assert len(chunks(network)) == 8
    for _ in range(200):
        for row in chunks(network)[-8:]:
            ack(delivery, 'chunk_ack', snapshot_id=row['snapshot_id'], index=row['index'])
    data = [row for row in network.rows if row['type'].startswith('snapshot_')]
    assert len(data) == 100
    assert len(delivery.session.pending) <= 8
    clock.now = .999
    delivery.tick()
    assert len([row for row in network.rows if row['type'].startswith('snapshot_')]) == 100
    clock.now = 1
    delivery.tick()
    assert len([row for row in network.rows if row['type'].startswith('snapshot_')]) <= 200


def test_missing_chunk_retries_until_ack(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    first = chunks(network)[0]
    for row in chunks(network)[1:]:
        ack(delivery, 'chunk_ack', snapshot_id=row['snapshot_id'], index=row['index'])
    clock.now = 1
    delivery.tick()
    assert len([row for row in chunks(network) if row['index'] == first['index']]) == 2
    ack(delivery, 'chunk_ack', snapshot_id=first['snapshot_id'], index=first['index'])
    clock.now = 2
    delivery.tick()
    assert len([row for row in chunks(network) if row['index'] == first['index']]) == 2


@pytest.mark.parametrize('mutation', [
    {'token': 'wrong'}, {'session_id': str(UUID(int=2))}, {'hello_nonce': 'old'},
    {'source_id': str(UUID(int=3))}, {'scope_id': 'company:2/warehouse:1'},
    {'snapshot_id': 'wrong'}, {'revision': 99},
])
def test_wrong_token_session_ack_ignored(tmp_path, pumpworks_payload, mutation):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    begin = next(row for row in network.rows if row['type'] == 'snapshot_begin')
    fields = dict(revision=1, snapshot_id=begin['snapshot_id']) | mutation
    ack(delivery, 'snapshot_applied', **fields)
    assert delivery.applied_revision is None


def test_superseded_revision_cannot_roll_back(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    old = chunks(network)[0]['snapshot_id']
    pumpworks_payload['products'][0]['name'] = 'new source'
    delivery.set_snapshot(StoredSnapshot(2, Snapshot.model_validate(pumpworks_payload)))
    new = chunks(network)[-1]['snapshot_id']
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=old)
    assert delivery.applied_revision is None
    ack(delivery, 'snapshot_applied', revision=2, snapshot_id=new)
    assert delivery.applied_revision == 2
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=old)
    assert delivery.applied_revision == 2
    delivery.set_snapshot(StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload)))
    assert delivery.latest.revision == 2


def test_heartbeat_ack_timeout_negotiates_new_session(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    old = delivery.session.session_id
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    for now in [5, 10]:
        clock.now = now
        delivery.tick()
        ack(delivery, 'heartbeat_ack', sequence=999)
    assert delivery.session is not None
    clock.now = 15
    delivery.tick()
    assert delivery.session is None
    assert delivery.applied_revision is None
    hello(delivery, hello_nonce='new-nonce')
    assert delivery.session.session_id != old
    assert delivery.session.hello_nonce == 'new-nonce'


def test_restart_cache_timestamp_is_preserved(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    delivery.set_health(BridgeHealth(False, 100, None, 'OSError', False))
    clock.now = 5
    delivery.tick()
    row = next(row for row in network.rows if row['type'] == 'heartbeat')
    assert row['source_read_at'] == pumpworks_payload['meta']['source_read_at']
    assert row['source_age_seconds'] == 5
    assert row['source_ok'] is False


def test_loss_attempts_and_ten_second_expiry_are_bounded(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    first = chunks(network)[0]['index']
    for now in range(1, 11):
        clock.now = now
        delivery.tick()
    assert len([row for row in chunks(network) if row['index'] == first]) == 8
    assert delivery.session is None


def test_hello_retained_source_and_packet_address_reject_mismatch(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    old = delivery.session.session_id
    hello(delivery, source_id=str(UUID(int=3)), scope_id='company:1/warehouse:1')
    assert delivery.session.session_id == old
    row = delivery.session.envelope('resync_request')
    delivery.handle_packet(json.dumps(row).encode(), ('127.0.0.1', 1234))
    assert delivery.session.session_id == old
    delivery.handle_packet(b'x' * 1025, ('127.0.0.1', 34199))
    assert delivery.session.session_id == old


def test_loopback_delivery_with_fixed_packet_loss_and_reordering(tmp_path, pumpworks_payload):
    async def scenario():
        class Client(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport
                self.session = None
                self.begin = None
                self.parts = {}
                self.seen = {}
                self.completed = asyncio.Event()
                self.held = None
                self.begin_seen = 0
            def datagram_received(self, data, addr):
                row = json.loads(data)
                if row['type'] == 'hello_ack':
                    self.session = row
                elif row['type'] == 'snapshot_begin':
                    self.begin_seen += 1
                    if self.begin_seen == 1:
                        return
                    self.begin = row
                elif row['type'] == 'snapshot_chunk':
                    if self.begin is None:
                        return
                    index = row['index']
                    self.seen[index] = self.seen.get(index, 0) + 1
                    if index % 5 == 0 and self.seen[index] == 1:
                        return
                    if index == 1 and self.held is None:
                        self.held = row
                        return
                    self.accept(row, addr)
                    if self.held is not None and index != 1:
                        self.accept(self.held, addr)
                        self.held = None
            def accept(self, row, addr):
                self.parts[row['index']] = row['data']
                base = {key: self.session[key] for key in ('version', 'token', 'hello_nonce', 'session_id', 'source_id', 'scope_id')}
                self.transport.sendto(json.dumps(dict(base, type='chunk_ack', snapshot_id=row['snapshot_id'], index=row['index'])).encode(), addr)
                if self.begin and len(self.parts) == self.begin['chunk_count']:
                    restored = ''.join(self.parts[index] for index in range(self.begin['chunk_count'])).encode()
                    assert len(restored) == self.begin['byte_length']
                    validated = Snapshot.model_validate_json(restored)
                    assert snapshot_bytes(validated) == expected
                    self.transport.sendto(json.dumps(dict(base, type='snapshot_applied', revision=1, snapshot_id=row['snapshot_id'])).encode(), addr)
                    self.completed.set()
        loop = asyncio.get_running_loop()
        transport, client = await loop.create_datagram_endpoint(Client, local_addr=('127.0.0.1', 0))
        config = settings(tmp_path).model_copy(update={'pairing_token': __import__('pydantic').SecretStr('pairing-secret'), 'udp_port': 0, 'game_udp_port': transport.get_extra_info('sockname')[1]})
        delivery = UdpDelivery(config, SystemClock())
        expected = snapshot_bytes(Snapshot.model_validate(pumpworks_payload))
        delivery.set_snapshot(StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload)))
        try:
            await delivery.start()
            target = delivery._transport.get_extra_info('sockname')
            transport.sendto(json.dumps(dict(version=1, type='hello', token='pairing-secret', hello_nonce='loopback')).encode(), target)
            await asyncio.wait_for(client.completed.wait(), 6)
            await wait_until(lambda: delivery.applied_revision == 1)
            assert any(count > 1 for count in client.seen.values())
        finally:
            await delivery.stop()
            transport.close()
    asyncio.run(scenario())


def test_delivery_exhaustion_waits_ten_seconds_before_new_hello(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    clock.now = 5
    delivery.tick()
    ack(delivery, 'heartbeat_ack', sequence=1)
    for now in range(6, 14):
        clock.now = now
        delivery.tick()
    assert delivery.session is None
    hello(delivery, hello_nonce='retry')
    assert delivery.session is None
    clock.now = 21.999
    hello(delivery, hello_nonce='retry')
    assert delivery.session is None
    clock.now = 22
    hello(delivery, hello_nonce='retry')
    assert delivery.session is not None


def test_active_verified_session_survives_ten_seconds(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    original = delivery.session.session_id
    for now in (5, 10, 15, 20):
        clock.now = now
        delivery.tick()
        ack(delivery, 'heartbeat_ack', sequence=delivery.session.heartbeat_sequence)
    assert delivery.session.session_id == original
    assert delivery.applied_revision == 1


def test_unsent_heartbeat_ack_cannot_extend_liveness(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    clock.now = 4
    ack(delivery, 'heartbeat_ack', sequence=0)
    clock.now = 15
    delivery.tick()
    assert delivery.session is None


def test_hello_retries_echo_same_session_and_expired_nonce_cannot_rebind(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    original = delivery.session.session_id
    hello(delivery)
    assert delivery.session.session_id == original
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    clock.now = 15
    delivery.tick()
    hello(delivery)
    assert delivery.session is None
    hello(delivery, hello_nonce='fresh-next')
    assert delivery.session.session_id != original


def test_partial_send_cannot_ack_application(tmp_path, pumpworks_payload):
    pumpworks_payload['products'][0]['name'] = 'a' * 60000
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    ack(delivery, 'snapshot_applied', allow_partial=True, revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    assert delivery.applied_revision is None


def test_acks_for_unsent_chunks_and_different_snapshot_do_not_open_window(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    before = len(chunks(network))
    ack(delivery, 'chunk_ack', snapshot_id=chunks(network)[0]['snapshot_id'], index=500)
    ack(delivery, 'chunk_ack', snapshot_id='another', index=0)
    assert len(chunks(network)) == before
    assert len(delivery.session.pending) == 8


def test_publisher_enqueue_does_not_frame_on_http_loop(tmp_path, pumpworks_payload):
    async def scenario():
        import time
        pumpworks_payload['products'][0]['name'] = 'a' * 230000
        configured = settings(tmp_path)
        delivery = UdpDelivery(configured, FakeClock())
        pending = StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload))
        started = time.monotonic()
        await delivery.enqueue(pending)
        assert time.monotonic() - started < .025
        assert delivery.latest is None
    asyncio.run(scenario())


def test_late_heartbeat_cannot_revive_session_between_ticks(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=chunks(network)[0]['snapshot_id'])
    clock.now = 5
    delivery.tick()
    clock.now = 16
    ack(delivery, 'heartbeat_ack', sequence=1)
    assert delivery.session is None


def test_no_snapshot_heartbeat_is_unverified(tmp_path):
    delivery = UdpDelivery(settings(tmp_path), FakeClock())
    network = Network()
    delivery._transport = network
    hello(delivery)
    delivery.clock.now = 5
    delivery.tick()
    heartbeat = next(row for row in network.rows if row['type'] == 'heartbeat')
    assert heartbeat['source_read_at'] is None
    assert heartbeat['source_age_seconds'] is None
    assert not heartbeat['source_ok']
    assert delivery.applied_revision is None


def test_single_slot_publisher_supersedes_queued_revision(tmp_path, pumpworks_payload):
    async def scenario():
        configured = settings(tmp_path).model_copy(update={'udp_port': 0})
        delivery = UdpDelivery(configured, SystemClock())
        await delivery.enqueue(StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload)))
        pumpworks_payload['products'][0]['name'] = 'newest queued'
        await delivery.enqueue(StoredSnapshot(2, Snapshot.model_validate(pumpworks_payload)))
        try:
            await delivery.start()
            await wait_until(lambda: delivery.latest is not None)
            assert delivery.latest.revision == 2
            assert delivery.latest.snapshot.products[0].name == 'newest queued'
        finally:
            await delivery.stop()
    asyncio.run(scenario())


def test_shutdown_drains_framing_thread_without_publishing(tmp_path, pumpworks_payload, monkeypatch):
    import threading
    import factorio_bridge.udp as udp
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        original = udp.encode_frames
        def blocked(stored, session):
            entered.set()
            assert release.wait(2)
            return original(stored, session)
        configured = settings(tmp_path).model_copy(update={'udp_port': 0})
        delivery = UdpDelivery(configured, SystemClock())
        monkeypatch.setattr(udp, 'encode_frames', blocked)
        await delivery.start()
        await delivery.enqueue(StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload)))
        await asyncio.to_thread(entered.wait)
        stopping = asyncio.create_task(delivery.stop())
        try:
            await asyncio.sleep(.02)
            assert not stopping.done()
            assert delivery.latest is None
            release.set()
            await asyncio.wait_for(stopping, 2)
            assert delivery.latest is None
            assert delivery._transport is None
        finally:
            release.set()
            await delivery.stop()
    asyncio.run(scenario())


def test_lost_application_ack_retries_same_begin_then_stops(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    while delivery.session.pending:
        for index in list(delivery.session.pending):
            ack(delivery, 'chunk_ack', snapshot_id=delivery.session.snapshot_id, index=index)
    identifier = delivery.session.snapshot_id
    sent_chunks = len(chunks(network))
    clock.now = 1
    delivery.tick()
    begins = [row for row in network.rows if row['type'] == 'snapshot_begin']
    assert len(begins) == 2
    assert {row['snapshot_id'] for row in begins} == {identifier}
    assert len(chunks(network)) == sent_chunks
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=identifier)
    clock.now = 2
    delivery.tick()
    assert len([row for row in network.rows if row['type'] == 'snapshot_begin']) == 2
    assert delivery.applied_revision == 1


def test_long_nonce_without_snapshot_is_rejected_and_pump_keeps_running(tmp_path):
    async def scenario():
        clock = FakeClock()
        configured = settings(tmp_path).model_copy(update={'udp_port': 0})
        delivery = UdpDelivery(configured, clock)
        await delivery.start()
        try:
            hello(delivery, hello_nonce='x' * 700)
            assert delivery.session is None
            await clock.advance(5)
            assert not delivery._task.done()
            hello(delivery, hello_nonce='healthy-reconnect')
            session_id = delivery.session.session_id
            await clock.advance(5)
            assert not delivery._task.done()
            assert delivery.session.session_id == session_id
            assert delivery.session.heartbeat_sequence == 1
        finally:
            await delivery.stop()
    asyncio.run(scenario())


def test_delayed_old_hello_preserves_new_session_transfer_and_application(tmp_path, pumpworks_payload):
    clock, delivery, network = rig(tmp_path, pumpworks_payload)
    hello(delivery, hello_nonce='nonce-B')
    identifier = delivery.session.snapshot_id
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=identifier)
    session_id = delivery.session.session_id
    hello(delivery, hello_nonce='fresh')
    assert delivery.session.session_id == session_id
    assert delivery.session.snapshot_id == identifier
    assert delivery.applied_revision == 1
    hello(delivery, hello_nonce='nonce-C')
    assert delivery.session.session_id != session_id
    assert delivery.session.hello_nonce == 'nonce-C'


def test_heartbeat_serialization_failure_does_not_terminate_pump(tmp_path):
    async def scenario():
        clock = FakeClock()
        configured = settings(tmp_path).model_copy(update={'udp_port': 0})
        delivery = UdpDelivery(configured, clock)
        await delivery.start()
        try:
            hello(delivery, hello_nonce='first')
            delivery.set_health(BridgeHealth(False, None, clock.utcnow(), 'error' * 1000, False))
            await clock.advance(5)
            assert not delivery._task.done()
            hello(delivery, hello_nonce='recovered')
            delivery.set_health(BridgeHealth(False, None, None, None, False))
            await clock.advance(5)
            assert not delivery._task.done()
            assert delivery.session.heartbeat_sequence == 1
        finally:
            await delivery.stop()
    asyncio.run(scenario())


def test_nonce_history_cap_fails_closed_preserves_current_and_idempotent_hello(tmp_path, pumpworks_payload, caplog):
    delivery = UdpDelivery(settings(tmp_path), FakeClock())
    network = Network()
    delivery._transport = network
    for index in range(4096):
        hello(delivery, hello_nonce=f'nonce-{index}')
    assert delivery.session.hello_nonce == 'nonce-4095'
    delivery.set_snapshot(StoredSnapshot(1, Snapshot.model_validate(pumpworks_payload)))
    identifier = delivery.session.snapshot_id
    ack(delivery, 'snapshot_applied', revision=1, snapshot_id=identifier)
    session_id = delivery.session.session_id
    hello(delivery, hello_nonce='nonce-4096')
    assert delivery.session.session_id == session_id
    assert delivery.session.snapshot_id == identifier
    assert delivery.applied_revision == 1
    hello(delivery, hello_nonce='nonce-4095')
    assert network.rows[-1]['type'] == 'hello_ack'
    assert delivery.session.session_id == session_id
    hello(delivery, hello_nonce='nonce-0')
    assert delivery.session.session_id == session_id
    assert delivery.applied_revision == 1
    assert 'restart bridge' in caplog.text.lower()
    assert 'pairing-secret' not in caplog.text


def test_invalid_heartbeat_timestamp_drops_session_but_next_session_runs(tmp_path, caplog):
    async def scenario():
        clock = FakeClock()
        configured = settings(tmp_path).model_copy(update={'udp_port': 0})
        delivery = UdpDelivery(configured, clock)
        await delivery.start()
        try:
            hello(delivery, hello_nonce='invalid-telemetry-session')
            delivery.set_health(BridgeHealth(False, None, clock.utcnow().replace(tzinfo=None), None, False))
            await clock.advance(5)
            assert delivery.session is None
            assert not delivery._task.done()
            delivery.set_health(BridgeHealth(False, None, None, None, False))
            hello(delivery, hello_nonce='valid-telemetry-session')
            await clock.advance(5)
            assert not delivery._task.done()
            assert delivery.session.heartbeat_sequence == 1
            assert 'pairing-secret' not in caplog.text
        finally:
            await delivery.stop()
    asyncio.run(scenario())
