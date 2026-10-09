"""Bridge challenge supplies authority independent of restored game state."""
import json
from test_udp import Network, ack
from test_webhooks import settings
from test_coordinator import FakeClock
from factorio_bridge.udp import UdpDelivery


def rig(tmp_path):
    d = UdpDelivery(settings(tmp_path), FakeClock())
    n = Network()
    d._transport = n
    return d, n


def send(d, nonce='saved-nonce', challenge=None):
    p = dict(version=1, type='hello', token='pairing-secret', hello_nonce=nonce)
    if challenge is not None:
        p['challenge_id'] = challenge
    d.handle_packet(json.dumps(p).encode(), ('127.0.0.1', d.settings.game_udp_port))


def confirm(d, challenge):
    send(d, challenge, challenge)


def test_initial_is_only_challenge_and_identical_save_reuse_is_fresh(tmp_path):
    d, n = rig(tmp_path)
    send(d)
    assert d.session is None
    assert n.rows[-1]['type'] == 'hello_challenge'
    a = n.rows[-1]['challenge_id']
    send(d)
    assert n.rows[-1]['challenge_id'] == a
    confirm(d, a)
    first = d.session.session_id
    assert d.session.hello_nonce == a
    send(d)
    b = n.rows[-1]['challenge_id']
    assert b != a
    assert d.session.session_id == first
    confirm(d, b)
    assert d.session.session_id != first


def test_reordered_old_confirmation_cannot_replace_newer_authority(tmp_path):
    d, n = rig(tmp_path)
    send(d, 'A'); a = n.rows[-1]['challenge_id']
    send(d, 'B'); b = n.rows[-1]['challenge_id']
    confirm(d, b); current = d.session.session_id
    confirm(d, a)
    assert d.session.session_id == current
    confirm(d, b)
    assert n.rows[-1]['type'] == 'hello_ack'
    assert d.session.session_id == current


def test_unknown_expired_missing_and_mismatched_confirmation_are_ignored(tmp_path):
    d, n = rig(tmp_path)
    confirm(d, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
    assert d.session is None
    send(d); a = n.rows[-1]['challenge_id']
    send(d, 'wrong-nonce', a)
    assert d.session is None
    d.clock.now = 10
    confirm(d, a)
    assert d.session is None
    send(d); b = n.rows[-1]['challenge_id']
    assert b != a
    confirm(d, b)
    current = d.session.session_id
    confirm(d, a)
    assert d.session.session_id == current


def test_pending_challenges_are_bounded_and_expire(tmp_path):
    d, n = rig(tmp_path)
    for i in range(9):
        send(d, f'n-{i}')
    challenges = [r for r in n.rows if r['type'] == 'hello_challenge']
    assert len(challenges) == 8
    d.clock.now = 10
    send(d, 'n-8')
    assert n.rows[-1]['hello_nonce'] == 'n-8'
    assert len(d._pending_challenges) == 1


def test_safe_integer_contract_and_scope_bounds():
    import pytest
    from pydantic import ValidationError
    from factorio_bridge.contracts import WireMessage
    from factorio_bridge.protocol import encode_message
    base=dict(version=1,type='heartbeat_ack',token='pairing-secret',hello_nonce='nonce',session_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',source_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',scope_id='company:1/warehouse:1',sequence=9007199254740991)
    assert WireMessage.validate_python(base).sequence==9007199254740991
    with pytest.raises(ValidationError): WireMessage.validate_python(dict(base,sequence=9007199254740992))
    with pytest.raises(ValidationError): WireMessage.validate_python(dict(base,scope_id='company:9007199254740992/warehouse:1'))
    with pytest.raises(ValidationError): WireMessage.validate_json(json.dumps(dict(base,sequence=1.0)))


def test_initial_and_old_final_preserve_transfer_and_applied(tmp_path,pumpworks_payload):
    from factorio_bridge.contracts import Snapshot
    from factorio_bridge.store import StoredSnapshot
    d,n=rig(tmp_path)
    send(d,'old'); old=n.rows[-1]['challenge_id']
    send(d,'current'); current=n.rows[-1]['challenge_id']; confirm(d,current)
    d.set_snapshot(StoredSnapshot(1,Snapshot.model_validate(pumpworks_payload)))
    sid=d.session.session_id; transfer=d.session.snapshot_id
    ack(d,'snapshot_applied',revision=1,snapshot_id=transfer)
    send(d,'delayed-initial')
    confirm(d,old)
    assert d.session.session_id==sid
    assert d.session.snapshot_id==transfer
    assert d.applied_revision==1


def test_refresh_runs_only_on_valid_final_confirmation(tmp_path):
    import asyncio
    async def scenario():
        d,n=rig(tmp_path); reads=[]
        async def refresh(): reads.append('read')
        d.on_reconnect=refresh
        send(d); challenge=n.rows[-1]['challenge_id']
        await asyncio.sleep(0)
        assert reads==[]
        confirm(d,challenge); await asyncio.sleep(0)
        assert reads==['read']
        confirm(d,challenge); await asyncio.sleep(0)
        assert reads==['read']
        await d.stop()
    asyncio.run(scenario())


def test_pre_recovery_heartbeat_emissions_bounded_and_final_retry_does_not_extend():
    from types import SimpleNamespace
    from pydantic import SecretStr
    d=UdpDelivery(SimpleNamespace(pairing_token=SecretStr('pairing-secret'),source_id=__import__('uuid').UUID('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),scope_id='company:1/warehouse:1',game_udp_port=34199),FakeClock())
    n=Network(); d._transport=n
    send(d); challenge=n.rows[-1]['challenge_id']; confirm(d,challenge)
    d.clock.now=5; d.tick()
    d.clock.now=9.999; ack(d,'heartbeat_ack',sequence=1)
    before=len([r for r in n.rows if r['type']=='heartbeat'])
    for now in (10,15,20): d.clock.now=now; d.tick()
    assert len([r for r in n.rows if r['type']=='heartbeat'])-before==3
    d.clock.now=22; confirm(d,challenge)
    assert d.session.last_heartbeat_ack==9.999
    d.clock.now=25; d.tick()
    assert d.session is None
    assert len([r for r in n.rows if r['type']=='heartbeat'])-before==3
