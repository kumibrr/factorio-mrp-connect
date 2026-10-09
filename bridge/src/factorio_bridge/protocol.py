"""Byte-bounded canonical snapshot framing and per-connection authority."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from uuid import UUID, uuid4

from .contracts import WireMessage, snapshot_bytes
from .store import StoredSnapshot


@dataclass
class Session:
    token: str
    hello_nonce: str
    session_id: UUID
    source_id: UUID
    scope_id: str
    accepted_revision: int | None = None
    last_heartbeat_ack: float = 0
    heartbeat_sequence: int = 0
    heartbeat_sent_at: float = 0
    heartbeat_acked_sequence: int = -1
    revision: int | None = None
    snapshot_id: str | None = None
    frames: list[bytes] = field(default_factory=list)
    next_index: int = 0
    pending: dict[int, tuple[float, int]] = field(default_factory=dict)
    acknowledged: set[int] = field(default_factory=set)
    begin_sent_at: float | None = None
    begin_attempts: int = 0

    def envelope(self, kind: str) -> dict:
        return dict(version=1, type=kind, token=self.token, hello_nonce=self.hello_nonce,
                    session_id=str(self.session_id), source_id=str(self.source_id), scope_id=self.scope_id)


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def encode_message(payload: dict) -> bytes:
    model = WireMessage.validate_python(payload)
    encoded = json_bytes(model.model_dump(mode='json'))
    if len(encoded) > 1024:
        raise ValueError('UDP envelope exceeds 1024 UTF-8 bytes')
    return encoded


def encode_frames(stored: StoredSnapshot, session: Session) -> list[bytes]:
    """Split on Unicode characters, including the envelope's JSON escaping cost.

    Snapshot IDs identify attempts; they are opaque UUIDs, never content hashes.
    No frames escape this function until both total bounds have been checked.
    """
    meta = stored.snapshot.meta
    if meta.source_id != session.source_id or meta.scope_id != session.scope_id:
        raise ValueError('Snapshot source does not match session binding')
    canonical = snapshot_bytes(stored.snapshot)
    if len(canonical) > 262144:
        raise ValueError('Snapshot exceeds size limit')
    text = canonical.decode('utf-8')
    identifier = str(uuid4())
    base = dict(session.envelope('snapshot_chunk'), revision=stored.revision, snapshot_id=identifier)
    chunks = []
    offset = 0
    while offset < len(text):
        if len(chunks) == 512:
            raise ValueError('Snapshot exceeds 512 chunks')
        envelope = dict(base, index=len(chunks))
        low, high = 0, min(1024, len(text) - offset)
        while low < high:
            middle = (low + high + 1) // 2
            encoded = json_bytes(dict(envelope, data=text[offset:offset + middle]))
            if len(encoded) <= 1024:
                low = middle
            else:
                high = middle - 1
        if low == 0:
            raise ValueError('Session identity leaves no room for snapshot data')
        chunks.append(encode_message(dict(envelope, data=text[offset:offset + low])))
        offset += low
    begin = dict(session.envelope('snapshot_begin'), revision=stored.revision,
                 snapshot_id=identifier, chunk_count=len(chunks), byte_length=len(canonical))
    return [encode_message(begin), *chunks]
