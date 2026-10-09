"""Boundary tests: catch lost source values, malformed graphs and unsafe serialization."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from factorio_bridge.contracts import Snapshot, WireMessage, snapshot_bytes, validate_snapshot


def test_pumpworks_contract_counts_and_motor_shortage(pumpworks_payload):
    snapshot = validate_snapshot(pumpworks_payload)
    assert (len(snapshot.products), len(snapshot.work_centers),
            len(snapshot.manufacturing_orders), len(snapshot.work_orders)) == (10, 4, 8, 22)
    motors = [row for row in snapshot.material_demands if row.mo_id == 7 and row.product_id == 3]
    assert len(motors) == 1
    assert (motors[0].demand_qty, motors[0].reserved_qty, motors[0].unreserved_qty) == (8, 2, 6)
    assert sum(row.unreserved_qty for row in snapshot.material_demands) == 6
    assert sum(mo.posted_qty for mo in snapshot.manufacturing_orders if mo.product_id == 10) == 14
    assert [(mo.requested_qty, mo.posted_qty) for mo in snapshot.manufacturing_orders if mo.group_id == 3] == [(4, 4), (6, 0)]
    assert next(row for row in snapshot.stock if row.product_id == 10).on_hand_qty == 14


def test_unknown_state_and_null_are_preserved(pumpworks_payload):
    pumpworks_payload["work_orders"][0]["raw_state"] = "future_odoo_state"
    pumpworks_payload["work_orders"][0]["output_qty"] = None
    pumpworks_payload["manufacturing_orders"][0]["reported_qty"] = None
    pumpworks_payload["work_centers"][0]["raw_working_state"] = None
    result = json.loads(snapshot_bytes(validate_snapshot(pumpworks_payload)))
    assert result["work_orders"][0]["raw_state"] == "future_odoo_state"
    assert result["work_orders"][0]["output_qty"] is None
    assert result["manufacturing_orders"][0]["reported_qty"] is None
    assert result["work_centers"][0]["raw_working_state"] is None


def test_zero_and_negative_stock(pumpworks_payload):
    pumpworks_payload["stock"][0].update(on_hand_qty=-2, reserved_qty=1, free_qty=-3)
    pumpworks_payload["work_orders"][0]["elapsed_minutes"] = 0
    snapshot = validate_snapshot(pumpworks_payload)
    assert (snapshot.stock[0].on_hand_qty, snapshot.stock[0].reserved_qty, snapshot.stock[0].free_qty) == (-2, 1, -3)
    assert snapshot.work_orders[0].elapsed_minutes == 0


@pytest.mark.parametrize("mutation", [
    lambda p: p["stock"][0].update(on_hand_qty=float("nan")),
    lambda p: p["work_orders"][0].update(elapsed_minutes=float("inf")),
    lambda p: p["products"][0].update(unit_id=999),
    lambda p: p["work_orders"][0].update(mo_id=999),
    lambda p: p["work_orders"][0].update(center_id=999),
    lambda p: p["work_orders"][1].update(operation_id=999),
    lambda p: p["work_orders"][2].update(dependency_ids=[999]),
    lambda p: p["boms"][0]["components"][0].update(product_id=999),
    lambda p: p["material_demands"][0].update(product_id=999),
    lambda p: p["units"][0].update(rounding=0),
    lambda p: p["stock"][0].update(on_hand_qty=0.5),
    lambda p: p["products"].append(copy.deepcopy(p["products"][0])),
    lambda p: p["meta"].update(scope_id="company:2/warehouse:1"),
    lambda p: p["meta"].update(source_read_at="2026-10-09T12:00:00"),
    lambda p: p["meta"].update(source_read_at="2026-10-09T12:00:00+02:00"),
])
def test_rejects_nonfinite_or_dangling_snapshot(pumpworks_payload, mutation):
    mutation(pumpworks_payload)
    with pytest.raises(ValidationError):
        validate_snapshot(pumpworks_payload)


def test_serialization_roundtrips_unicode(pumpworks_payload):
    pumpworks_payload["products"][0]["name"] = "Impulsor — Málaga ⚙"
    snapshot = validate_snapshot(pumpworks_payload)
    encoded = snapshot_bytes(snapshot)
    assert "Impulsor — Málaga ⚙".encode() in encoded
    assert snapshot_bytes(validate_snapshot(json.loads(encoded))) == encoded
    assert encoded == json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False,
                                 sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def test_snapshot_orders_collections_by_source_id(pumpworks_payload):
    pumpworks_payload["products"].reverse()
    snapshot = validate_snapshot(pumpworks_payload)
    assert [row.id for row in snapshot.products] == list(range(1, 11))


def test_committed_schema_validates_fixture(pumpworks_payload):
    root = Path(__file__).resolve().parents[2] / "contracts"
    schema = json.loads((root / "snapshot-v1.schema.json").read_text())
    Draft202012Validator(schema).validate(pumpworks_payload)
    bad = copy.deepcopy(pumpworks_payload)
    bad["products"][0]["id"] = "not-an-id"
    assert list(Draft202012Validator(schema).iter_errors(bad))


@pytest.mark.parametrize("message", [
    {"type": "hello", "session_id": None},
    {"type": "hello_ack"},
    {"type": "snapshot_begin", "revision": 1, "snapshot_id": "abc", "chunk_count": 2, "byte_length": 100},
    {"type": "snapshot_chunk", "revision": 1, "snapshot_id": "abc", "index": 0, "data": "Málaga"},
    {"type": "chunk_ack", "snapshot_id": "abc", "index": 0},
    {"type": "snapshot_applied", "revision": 1, "snapshot_id": "abc"},
    {"type": "heartbeat", "sequence": 1, "source_ok": False, "source_read_at": None,
     "source_age_seconds": None, "last_success_at": None, "last_error": "Odoo unavailable", "refreshing": False},
    {"type": "heartbeat_ack", "sequence": 1},
    {"type": "resync_request"},
])
def test_wire_roundtrip_and_schema(message):
    payload = dict(version=1, token="test-pairing", hello_nonce="request-1",
                   session_id="12345678-1234-5678-1234-567812345678",
                   source_id="12345678-1234-5678-1234-567812345679", scope_id="company:1/warehouse:1")
    payload.update(message)
    model = WireMessage.validate_python(payload)
    result = json.loads(model.model_dump_json())
    for key, value in payload.items():
        assert result[key] == value
    schema = json.loads((Path(__file__).resolve().parents[2] / "contracts/wire-v1.schema.json").read_text())
    Draft202012Validator(schema).validate(result)


@pytest.mark.parametrize("updates", [
    {"version": 2}, {"type": "surprise"}, {"session_id": None},
    {"index": -1}, {"index": 512}, {"revision": 0},
])
def test_wire_rejects_invalid_chunk(updates):
    payload = dict(version=1, type="snapshot_chunk", token="test-pairing", hello_nonce="request-1",
                   session_id="12345678-1234-5678-1234-567812345678",
                   source_id="12345678-1234-5678-1234-567812345679", scope_id="company:1/warehouse:1",
                   revision=1, snapshot_id="abc", index=0, data="{}")
    payload.update(updates)
    with pytest.raises(ValidationError):
        WireMessage.validate_python(payload)


@pytest.mark.parametrize("mutation", [
    lambda p: p["work_orders"][2].update(dependency_ids=[5]),
    lambda p: p["work_orders"][1].update(dependency_ids=[3]),
    lambda p: p["boms"][1]["operations"][0].update(dependency_ids=[4]),
    lambda p: p["boms"][0]["components"][0].update(operation_id=4),
    lambda p: p["material_demands"][0].update(unit_id=999),
    lambda p: p["manufacturing_orders"][0].update(requested_qty=-1),
    lambda p: p["stock"][0].update(reserved_qty=-1),
])
def test_rejects_incompatible_graph_or_quantity(pumpworks_payload, mutation):
    mutation(pumpworks_payload)
    with pytest.raises(ValidationError):
        validate_snapshot(pumpworks_payload)


def test_wire_rejects_oversized_utf8_envelope():
    with pytest.raises(ValidationError):
        WireMessage.validate_python(dict(version=1, type="snapshot_chunk", token="test-pairing",
            hello_nonce="request-1", session_id="12345678-1234-5678-1234-567812345678",
            source_id="12345678-1234-5678-1234-567812345679", scope_id="company:1/warehouse:1",
            revision=1, snapshot_id="abc", index=0, data="⚙" * 400))


@pytest.mark.parametrize("mutation", [
    lambda p: p["material_demands"][-10].update(unreserved_qty=99),
    lambda p: p["stock"][0].update(free_qty=99),
])
def test_rejects_misleading_balance_or_unreserved_demand(pumpworks_payload, mutation):
    mutation(pumpworks_payload)
    with pytest.raises(ValidationError):
        validate_snapshot(pumpworks_payload)
