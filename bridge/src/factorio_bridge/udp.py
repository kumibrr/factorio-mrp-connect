"""One localhost peer, bounded retries/window, and explicit application acks."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
import json
import secrets
import logging
from uuid import uuid4

from pydantic import ValidationError

from .contracts import WireMessage
from .coordinator import BridgeHealth
from .protocol import Session, encode_frames, encode_message


# Retain exact replay rejection without unbounded connection state. At the cap,
# current-session retries still work; explicit process restart clears history.
_NONCE_HISTORY_LIMIT = 4096
_ERROR_LABEL_CHARACTERS = 64


class _Receiver(asyncio.DatagramProtocol):
    def __init__(self, delivery):
        self.delivery = delivery

    def datagram_received(self, data, addr):
        self.delivery.handle_packet(data, addr)


class UdpDelivery:
    def __init__(self, settings, clock):
        self.settings, self.clock = settings, clock
        self.session: Session | None = None
        self.latest = None
        self.health = BridgeHealth(False, None, None, None, False)
        self.health_provider = None
        self.on_reconnect = None
        self._transport = None
        self._task = None
        self._publisher_task = None
        self._queued_snapshot = None
        self._publish_wake = asyncio.Event()
        self._retry_at = 0
        self._used_nonces = set()
        self._nonce_cap_logged = False
        self._reconnect_tasks = set()
        self._data_sent = deque()

    @property
    def applied_revision(self):
        return None if self.session is None else self.session.accepted_revision

    async def start(self):
        if self._task is not None:
            return
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _Receiver(self), local_addr=('127.0.0.1', self.settings.udp_port))
        self._task = asyncio.create_task(self._run())
        self._publisher_task = asyncio.create_task(self._publish_loop())

    async def stop(self):
        tasks = [*self._reconnect_tasks]
        if self._task is not None:
            tasks.append(self._task)
        if self._publisher_task is not None:
            tasks.append(self._publisher_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._task = None
        self._publisher_task = None
        self._reconnect_tasks.clear()
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self.session = None

    async def enqueue(self, stored):
        # Publication is a local bounded operation; source reads never await game IO.
        if self._queued_snapshot is None or stored.revision > self._queued_snapshot.revision:
            self._queued_snapshot = stored
            self._publish_wake.set()

    async def _publish_loop(self):
        while True:
            await self._publish_wake.wait()
            self._publish_wake.clear()
            stored, self._queued_snapshot = self._queued_snapshot, None
            if self.latest is not None and stored.revision <= self.latest.revision:
                continue
            while True:
                session = self.session
                pending = asyncio.create_task(asyncio.to_thread(encode_frames, stored, session or self._new_session('preflight')))
                try:
                    frames = await asyncio.shield(pending)
                except asyncio.CancelledError:
                    # Drain CPU work before stopping; it never mutates delivery state.
                    await asyncio.gather(pending, return_exceptions=True)
                    raise
                except ValueError:
                    logging.getLogger(__name__).warning('Snapshot revision %d exceeds transport bounds', stored.revision)
                    break
                if session is not self.session:
                    continue
                if self._queued_snapshot is not None and self._queued_snapshot.revision > stored.revision:
                    break
                self.latest = stored
                if session is not None:
                    self._prepare(frames)
                    self.tick()
                break

    def _new_session(self, nonce):
        now = self.clock.monotonic()
        return Session(self.settings.pairing_token.get_secret_value(), nonce, uuid4(),
                       self.settings.source_id, self.settings.scope_id,
                       last_heartbeat_ack=now, heartbeat_sent_at=now)

    def set_snapshot(self, stored):
        if self.latest is not None and stored.revision <= self.latest.revision:
            return
        frames = encode_frames(stored, self.session or self._new_session('preflight'))
        self.latest = stored
        if self.session is not None:
            self._prepare(frames)
            self.tick()

    def set_health(self, health):
        self.health = health

    def _prepare(self, frames):
        session = self.session
        begin = json.loads(frames[0])
        session.frames = frames
        session.revision = begin['revision']
        session.snapshot_id = begin['snapshot_id']
        session.next_index = 0
        session.pending.clear()
        session.acknowledged.clear()
        session.begin_sent_at = None
        session.begin_attempts = 0

    def _send(self, data, *, data_frame=False):
        if self._transport is None:
            return False
        now = self.clock.monotonic()
        while self._data_sent and self._data_sent[0] <= now - 1:
            self._data_sent.popleft()
        if data_frame and len(self._data_sent) >= 100:
            return False
        self._transport.sendto(data, ('127.0.0.1', self.settings.game_udp_port))
        if data_frame:
            self._data_sent.append(now)
        return True

    def _refresh_source(self):
        if self.on_reconnect is not None:
            task = asyncio.create_task(self.on_reconnect())
            self._reconnect_tasks.add(task)
            task.add_done_callback(self._reconnect_tasks.discard)

    def handle_packet(self, data: bytes, addr: tuple[str, int]):
        if addr != ('127.0.0.1', self.settings.game_udp_port) or len(data) > 1024:
            return
        try:
            message = WireMessage.validate_json(data)
        except (ValidationError, ValueError):
            return
        if not secrets.compare_digest(message.token.encode(), self.settings.pairing_token.get_secret_value().encode()):
            return
        if self.session is not None and self.clock.monotonic() - self.session.last_heartbeat_ack >= 15:
            self.session = None
        if message.type == 'hello':
            if self.clock.monotonic() < self._retry_at:
                return
            if message.source_id is not None and (message.source_id != self.settings.source_id or message.scope_id != self.settings.scope_id):
                return
            if self.session is not None and message.hello_nonce == self.session.hello_nonce:
                # Lost hello_ack must not reset an active assembly or session.
                self._send(encode_message(self.session.envelope('hello_ack')))
                return
            nonce_digest = sha256(message.hello_nonce.encode('utf-8')).digest()
            if nonce_digest in self._used_nonces:
                return
            if len(self._used_nonces) >= _NONCE_HISTORY_LIMIT:
                if not self._nonce_cap_logged:
                    logging.getLogger(__name__).warning('Handshake nonce history is full; restart bridge to accept a new nonce')
                    self._nonce_cap_logged = True
                return
            session = self._new_session(message.hello_nonce)
            try:
                self._preflight_control(session)
                frames = None if self.latest is None else encode_frames(self.latest, session)
                response = encode_message(session.envelope('hello_ack'))
            except ValueError:
                return
            self.session = session
            self._used_nonces.add(nonce_digest)
            self._send(response)
            if frames is not None:
                self._prepare(frames)
            self._refresh_source()
            self.tick()
            return
        session = self.session
        if session is None or (message.session_id, message.hello_nonce, message.source_id, message.scope_id) != (
                session.session_id, session.hello_nonce, session.source_id, session.scope_id):
            return
        if message.type == 'chunk_ack' and message.snapshot_id == session.snapshot_id:
            if message.index in session.pending:
                del session.pending[message.index]
                session.acknowledged.add(message.index)
        elif message.type == 'snapshot_applied':
            if message.snapshot_id == session.snapshot_id and message.revision == session.revision and session.frames and session.next_index == len(session.frames) - 1:
                session.accepted_revision = message.revision
                session.frames = []
                session.pending.clear()
        elif message.type == 'heartbeat_ack':
            if message.sequence > 0 and message.sequence == session.heartbeat_sequence and message.sequence > session.heartbeat_acked_sequence:
                session.heartbeat_acked_sequence = message.sequence
                session.last_heartbeat_ack = self.clock.monotonic()
        elif message.type == 'resync_request':
            if self.latest is not None:
                self._prepare(encode_frames(self.latest, session))
            self._refresh_source()
        self.tick()

    def _heartbeat_payload(self, session, sequence, health, source_at, age):
        return dict(session.envelope('heartbeat'), sequence=sequence,
                    source_read_at=None if source_at is None else source_at.isoformat().replace('+00:00', 'Z'),
                    source_age_seconds=age, source_ok=health.source_ok,
                    last_success_at=None if health.last_success_at is None else health.last_success_at.isoformat().replace('+00:00', 'Z'),
                    last_error=None if health.last_error is None else health.last_error[:_ERROR_LABEL_CHARACTERS],
                    refreshing=health.refreshing)

    def _preflight_control(self, session):
        # Reserve future timestamp/numeric fields and the worst JSON escaping of
        # a bounded error label, even when the initial cache/source is absent.
        maximum_date = datetime.max.replace(tzinfo=timezone.utc)
        health = BridgeHealth(False, None, maximum_date, '\0' * _ERROR_LABEL_CHARACTERS, False)
        encode_message(self._heartbeat_payload(session, 18446744073709551615,
                                               health, maximum_date, 1.7976931348623157e308))

    def tick(self):
        """A bad session envelope must not terminate the periodic service."""
        try:
            self._tick()
        except ValueError:
            logging.getLogger(__name__).warning('Session envelope could not be encoded; waiting for a fresh handshake')
            self.session = None

    def _tick(self):
        session = self.session
        if session is None:
            return
        now = self.clock.monotonic()
        if now - session.last_heartbeat_ack >= 15:
            self.session = None
            return
        if now - session.heartbeat_sent_at >= 5:
            health = self.health_provider() if self.health_provider is not None else self.health
            source_at = None if self.latest is None else self.latest.snapshot.meta.source_read_at
            age = None if source_at is None else max(0, (self.clock.utcnow() - source_at).total_seconds())
            session.heartbeat_sequence += 1
            row = self._heartbeat_payload(session, session.heartbeat_sequence, health, source_at, age)
            self._send(encode_message(row))
            session.heartbeat_sent_at = now
        if not session.frames:
            return
        if session.begin_sent_at is None or now - session.begin_sent_at >= 1:
            if session.begin_attempts >= 8:
                self._retry_at = now + 10
                self.session = None
                return
            if self._send(session.frames[0], data_frame=True):
                session.begin_sent_at = now
                session.begin_attempts += 1
        for index, (sent_at, attempts) in list(session.pending.items()):
            if now - sent_at >= 1:
                if attempts >= 8:
                    self._retry_at = now + 10
                    self.session = None
                    return
                if self._send(session.frames[index + 1], data_frame=True):
                    session.pending[index] = (now, attempts + 1)
        while len(session.pending) < 8 and session.next_index < len(session.frames) - 1:
            index = session.next_index
            if not self._send(session.frames[index + 1], data_frame=True):
                break
            session.pending[index] = (now, 1)
            session.next_index += 1

    async def _run(self):
        while True:
            self.tick()
            await self.clock.sleep(.01)
