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


def test_shared_bridge_handshake_vector_outcomes():
    import asyncio
    from hashlib import sha256
    from pathlib import Path
    from types import SimpleNamespace
    from pydantic import SecretStr
    from factorio_bridge.udp import UdpDelivery
    from test_coordinator import FakeClock
    from test_udp import Network
    vectors=json.loads((Path(__file__).resolve().parents[2]/'contracts/fixtures/wire-v1.json').read_text())
    async def scenario():
        for case in vectors['cases']:
            if case.get('direction')!='bridge':
                continue
            context=case['context']; refreshes=[]
            config=SimpleNamespace(pairing_token=SecretStr(context['token']),source_id=UUID(context['source_id']),scope_id=context['scope_id'],game_udp_port=34199)
            d=UdpDelivery(config,FakeClock()); network=Network(); d._transport=network
            async def refresh(): refreshes.append('source-read')
            d.on_reconnect=refresh
            d.latest=stored(json.loads(vectors['canonical_snapshot_utf8']),vectors['expected_revision'])
            if context['session_id']:
                d.session=Session(config.pairing_token.get_secret_value(),context['pending_hello_nonce'],UUID(context['session_id']),config.source_id,config.scope_id,accepted_revision=context['applied_revision'])
                d._prepare(encode_frames(d.latest,d.session))
                d.session.next_index=1
                d.session.pending={0:(0,1)}
                d.session.begin_sent_at=0
                d.session.begin_attempts=2
            pending=context.get('pending_challenge')
            if pending:
                d._challenge_order=pending['order']
                d._pending_challenges[pending['challenge_id']]=(sha256(pending['initial_nonce'].encode()).digest(),pending['issued_at'],pending['order'])
            before=d.session
            transfer=None if before is None else before.snapshot_id
            frames=None if before is None else before.frames
            applied=d.applied_revision
            progress=None if before is None else (before.next_index,dict(before.pending),before.begin_sent_at,before.begin_attempts)
            d.handle_packet(case['payload_json'].encode(),('127.0.0.1',34199))
            await asyncio.sleep(0)
            responses=[r for r in network.rows if r['type'] in ('hello_challenge','hello_ack')]
            if responses and responses[0]['type']=='hello_challenge':
                outcome='issue_challenge_preserve_authority_and_source_read'
                assert d.session is before and d.applied_revision==applied and refreshes==[],case['name']
                if before is not None:
                    assert d.session.snapshot_id==transfer and d.session.frames is frames,case['name']
                    assert (before.next_index,before.pending,before.begin_sent_at,before.begin_attempts)==progress,case['name']
                assert responses[0]['hello_nonce']==case['payload']['hello_nonce']
                assert responses[0]['session_id'] is None
            elif responses and responses[0]['type']=='hello_ack':
                outcome='bind_fresh_session_and_request_initial_source_read'
                assert d.session is not before and d.applied_revision is None and refreshes==['source-read'],case['name']
                assert str(d.session.session_id)==responses[0]['session_id']
                assert d.session.hello_nonce==case['payload']['challenge_id']==case['payload']['hello_nonce']
            else:
                outcome='ignore_without_replacing_session'
                assert d.session is before and d.applied_revision==applied and refreshes==[],case['name']
            assert bool(responses)==case['accepted'],case['name']
            assert outcome==case['outcome'],case['name']
            await d.stop()
    asyncio.run(scenario())
