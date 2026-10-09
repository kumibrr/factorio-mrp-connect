"""Canonical bytes, real JSON overhead, and wire authority boundaries."""
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from factorio_bridge.contracts import Snapshot, WireMessage, snapshot_bytes
from factorio_bridge.protocol import Session, encode_frames
from factorio_bridge.store import StoredSnapshot


@pytest.fixture
def session(pumpworks_payload):
    return Session(token='pairing-secret', hello_nonce='fresh-nonce',
                   session_id=UUID('12345678-1234-5678-1234-567812345678'),
                   source_id=UUID(pumpworks_payload['meta']['source_id']),
                   scope_id=pumpworks_payload['meta']['scope_id'])


def stored(payload, revision=2):
    return StoredSnapshot(revision, Snapshot.model_validate(payload))


def test_unicode_and_escaping_fit_1024_bytes(pumpworks_payload, session):
    pumpworks_payload['products'][0]['name'] = ('Málaga😀"\\\n' * 1500)
    snapshot = stored(pumpworks_payload)
    frames = encode_frames(snapshot, session)
    assert all(len(frame) <= 1024 for frame in frames)
    decoded = [json.loads(frame) for frame in frames]
    for row in decoded:
        WireMessage.validate_python(row)
    chunks = decoded[1:]
    restored = ''.join(row['data'] for row in chunks).encode()
    assert restored == snapshot_bytes(snapshot.snapshot)
    assert decoded[0]['byte_length'] == len(restored)
    assert decoded[0]['chunk_count'] == len(chunks)
    assert [row['index'] for row in chunks] == list(range(len(chunks)))


def sized_snapshot(payload, size, character='a'):
    payload['products'][0]['name'] = 'x'
    base = len(snapshot_bytes(Snapshot.model_validate(payload)))
    payload['products'][0]['name'] = character * (size - base + 1)
    return stored(payload)


def test_canonical_256_kib_boundary(pumpworks_payload, session):
    snapshot = sized_snapshot(pumpworks_payload, 262144)
    assert len(snapshot_bytes(snapshot.snapshot)) == 262144
    assert len(encode_frames(snapshot, session)) <= 513
    pumpworks_payload['products'][0]['name'] += 'a'
    with pytest.raises(ValueError, match='size'):
        encode_frames(stored(pumpworks_payload), session)


def test_512_chunk_boundary_counts_json_quote_overhead(pumpworks_payload, session):
    # Canonical quotes require a second escape when embedded in a chunk envelope.
    low, high = 1, 120000
    while low < high:
        middle = (low + high + 1) // 2
        pumpworks_payload['products'][0]['name'] = '"' * middle
        try:
            encode_frames(stored(pumpworks_payload), session)
        except ValueError:
            high = middle - 1
        else:
            low = middle
    pumpworks_payload['products'][0]['name'] = '"' * low
    frames = encode_frames(stored(pumpworks_payload), session)
    assert len(frames) == 513
    assert len(snapshot_bytes(stored(pumpworks_payload).snapshot)) < 262144
    pumpworks_payload['products'][0]['name'] += '"'
    with pytest.raises(ValueError, match='chunks'):
        encode_frames(stored(pumpworks_payload), session)


@pytest.mark.parametrize('identity', [{}, {'session_id': None, 'source_id': None, 'scope_id': None}])
def test_initial_hello_can_omit_unbound_identity(identity):
    WireMessage.validate_python(dict(version=1, type='hello', token='pairing', hello_nonce='fresh', **identity))


@pytest.mark.parametrize('identity', [
    {'source_id': '12345678-1234-5678-1234-567812345679'},
    {'scope_id': 'company:1/warehouse:1'},
    {'session_id': '12345678-1234-5678-1234-567812345678'},
])
def test_hello_rejects_partial_binding_or_bound_session(identity):
    with pytest.raises(ValidationError):
        WireMessage.validate_python(dict(version=1, type='hello', token='pairing', hello_nonce='fresh', **identity))


def test_bound_ack_still_requires_identity():
    with pytest.raises(ValidationError):
        WireMessage.validate_python(dict(version=1, type='heartbeat_ack', token='pairing', hello_nonce='fresh', sequence=1))


def test_shared_vectors_are_reconstructable_and_shape_expectations_hold():
    from pathlib import Path
    vectors = json.loads((Path(__file__).resolve().parents[2] / 'contracts/fixtures/wire-v1.json').read_text())
    canonical = vectors['canonical_snapshot_utf8'].encode()
    frames = vectors['frames']
    assert ''.join(row['data'] for row in frames[1:]).encode() == canonical
    assert frames[0]['byte_length'] == len(canonical)
    assert frames[0]['chunk_count'] == len(frames) - 1
    assert snapshot_bytes(Snapshot.model_validate_json(canonical)) == canonical
    for case in vectors['cases']:
        if case['shape_valid']:
            WireMessage.validate_python(case['payload'])
            WireMessage.validate_json(case['payload_json'])
        else:
            with pytest.raises(ValidationError):
                WireMessage.validate_python(case['payload'])
            with pytest.raises(ValidationError):
                WireMessage.validate_json(case['payload_json'])


def test_committed_hello_schema_rejects_partial_source_binding():
    from pathlib import Path
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).resolve().parents[2] / 'contracts/wire-v1.schema.json').read_text())
    hello = dict(version=1, type='hello', token='pairing', hello_nonce='fresh')
    validator = Draft202012Validator(schema)
    validator.validate(hello)
    assert list(validator.iter_errors(dict(hello, source_id='12345678-1234-5678-1234-567812345679')))
    assert list(validator.iter_errors(dict(hello, source_id=None, scope_id='company:1/warehouse:1')))


def test_shared_raw_snapshot_shape_vectors():
    from pathlib import Path
    vectors=json.loads((Path(__file__).resolve().parents[2]/'contracts/fixtures/snapshot-validation-v1.json').read_text())
    for case in vectors:
        if case['valid']:
            Snapshot.model_validate_json(case['json'])
        else:
            with pytest.raises(ValidationError):
                Snapshot.model_validate_json(case['json'])
