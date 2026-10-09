"""Version-one source snapshot and UDP envelopes.

Unknown source states remain strings. Optional business values are required
nullable fields so absent source evidence never becomes invented zero output.
JSON Schema describes shape; cross-record integrity is enforced by Snapshot.
Regenerate schemas with ``python -m factorio_bridge.contracts <output-dir>``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, model_validator

Id = Annotated[int, Field(strict=True, gt=0)]
Sequence = Annotated[int, Field(strict=True, ge=0)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Quantity = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1)]
Scope = Annotated[str, Field(pattern=r"^company:[1-9][0-9]*/warehouse:[1-9][0-9]*$")]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must include UTC timezone")
    return value


UTCDateTime = Annotated[datetime, AfterValidator(_utc)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SnapshotMeta(Contract):
    schema_version: Literal[1]
    source_id: UUID
    scope_id: Scope
    company_id: Id
    warehouse_id: Id
    source_read_at: UTCDateTime
    odoo_major: Literal[20]
    odoo_base_url: Annotated[str, Field(pattern=r"^https?://[^/\s]+(?:/[^\s]*)?$")]

    @model_validator(mode="after")
    def scope_matches_ids(self):
        if self.scope_id != f"company:{self.company_id}/warehouse:{self.warehouse_id}":
            raise ValueError("scope_id does not match company and warehouse")
        return self


class Unit(Contract):
    id: Id
    name: Text
    rounding: Positive


class Product(Contract):
    id: Id
    name: Text
    code: str | None
    unit_id: Id


class WorkCenter(Contract):
    id: Id
    name: Text
    code: str | None
    active: bool
    capacity: Positive
    calendar_id: Id | None
    raw_working_state: str | None


class ManufacturingOrder(Contract):
    id: Id
    reference: Text
    origin: str | None
    product_id: Id
    unit_id: Id
    requested_qty: Quantity
    reported_qty: Quantity | None
    posted_qty: Quantity
    raw_state: Text
    planned_start_at: UTCDateTime | None
    deadline_at: UTCDateTime | None
    started_at: UTCDateTime | None
    finished_at: UTCDateTime | None
    readiness_state: str | None
    availability_state: str | None
    group_id: Id | None
    backorder_sequence: Sequence | None


class WorkOrder(Contract):
    id: Id
    mo_id: Id
    center_id: Id
    operation_id: Id
    unit_id: Id
    sequence: Sequence
    dependency_ids: list[Id]
    raw_state: Text
    output_qty: Quantity | None
    carried_qty: Quantity | None
    required_qty: Quantity | None
    remaining_qty: Quantity | None
    ready_qty: Quantity | None
    expected_minutes: Quantity | None
    elapsed_minutes: Quantity | None


class BomComponent(Contract):
    product_id: Id
    unit_id: Id
    quantity: Quantity
    operation_id: Id | None


class BomOperation(Contract):
    id: Id
    center_id: Id
    sequence: Sequence
    dependency_ids: list[Id]


class Bom(Contract):
    id: Id
    product_id: Id
    unit_id: Id
    output_qty: Positive
    components: list[BomComponent]
    operations: list[BomOperation]


class MaterialDemand(Contract):
    id: Id
    mo_id: Id
    product_id: Id
    unit_id: Id
    demand_qty: Quantity
    remaining_demand_qty: Quantity
    reserved_qty: Quantity
    picked_qty: Quantity
    posted_consumed_qty: Quantity
    unreserved_qty: Quantity
    forecast_qty: Finite | None
    availability_state: str | None
    source_location_id: Id


class StockBalance(Contract):
    product_id: Id
    location_id: Id
    unit_id: Id
    on_hand_qty: Finite
    reserved_qty: Quantity
    free_qty: Finite


def _indexed(rows, label):
    result = {row.id: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate {label} ID")
    return result


def _reference(mapping, identifier, label):
    if identifier not in mapping:
        raise ValueError(f"unresolved {label} ID {identifier}")
    return mapping[identifier]


def _acyclic(rows, label):
    """Validate local dependencies without imposing sequence-based guesses."""
    visited, visiting = set(), set()

    def visit(identifier):
        if identifier in visiting:
            raise ValueError(f"cyclic {label} dependencies")
        if identifier in visited:
            return
        visiting.add(identifier)
        row = _reference(rows, identifier, label)
        if len(set(row.dependency_ids)) != len(row.dependency_ids):
            raise ValueError(f"duplicate {label} dependency")
        for predecessor in row.dependency_ids:
            visit(predecessor)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in rows:
        visit(identifier)


class Snapshot(Contract):
    meta: SnapshotMeta
    units: list[Unit]
    products: list[Product]
    work_centers: list[WorkCenter]
    manufacturing_orders: list[ManufacturingOrder]
    work_orders: list[WorkOrder]
    boms: list[Bom]
    material_demands: list[MaterialDemand]
    stock: list[StockBalance]

    @model_validator(mode="after")
    def validate_graph_and_units(self):
        collections = ("units", "products", "work_centers", "manufacturing_orders",
                       "work_orders", "boms", "material_demands")
        indexes = {name: _indexed(getattr(self, name), name) for name in collections}
        units, products = indexes["units"], indexes["products"]
        mos, wos = indexes["manufacturing_orders"], indexes["work_orders"]
        centers = indexes["work_centers"]

        def quantities(row, names):
            unit = _reference(units, row.unit_id, "unit")
            rounding = Decimal(str(unit.rounding))
            for name in names:
                value = getattr(row, name)
                if value is not None:
                    ratio = Decimal(str(value)) / rounding
                    # Source floats can have small representation error at a unit boundary.
                    if abs(ratio - ratio.to_integral_value()) > Decimal("0.00000001"):
                        raise ValueError(f"{name} does not respect unit rounding")

        def consistent(row, actual, expected, label):
            tolerance = Decimal(str(units[row.unit_id].rounding)) * Decimal("0.00000001")
            if abs(Decimal(str(actual)) - expected) > tolerance:
                raise ValueError(f"inconsistent {label}")

        def product_unit(row):
            product = _reference(products, row.product_id, "product")
            if row.unit_id != product.unit_id:
                raise ValueError("quantity must be normalized to product unit")

        for product in self.products:
            _reference(units, product.unit_id, "unit")
        for mo in self.manufacturing_orders:
            product_unit(mo)
            quantities(mo, ("requested_qty", "reported_qty", "posted_qty"))
        operations = {}
        product_operations = {}
        for bom in self.boms:
            product_unit(bom)
            quantities(bom, ("output_qty",))
            local_ops = _indexed(bom.operations, "BOM operation")
            _acyclic(local_ops, "BOM operation")
            for op in bom.operations:
                _reference(centers, op.center_id, "center")
                if op.id in operations:
                    raise ValueError("duplicate BOM operation ID")
                operations[op.id] = op
                product_operations.setdefault(bom.product_id, set()).add(op.id)
            for component in bom.components:
                product_unit(component)
                quantities(component, ("quantity",))
                if component.operation_id is not None:
                    _reference(local_ops, component.operation_id, "component operation")
            bom.operations.sort(key=lambda row: row.id)
            bom.components.sort(key=lambda row: (row.product_id, row.operation_id or 0))
        _acyclic(wos, "work order")
        for wo in self.work_orders:
            mo = _reference(mos, wo.mo_id, "MO")
            _reference(centers, wo.center_id, "center")
            operation = _reference(operations, wo.operation_id, "operation")
            if wo.operation_id not in product_operations.get(mo.product_id, set()):
                raise ValueError("WO operation does not produce MO product")
            if operation.center_id != wo.center_id or wo.unit_id != mo.unit_id:
                raise ValueError("WO center or unit does not match source operation/MO")
            for identifier in wo.dependency_ids:
                if _reference(wos, identifier, "WO dependency").mo_id != wo.mo_id:
                    raise ValueError("WO predecessor belongs to another MO")
            quantities(wo, ("output_qty", "carried_qty", "required_qty", "remaining_qty", "ready_qty"))
        for demand in self.material_demands:
            _reference(mos, demand.mo_id, "MO")
            product_unit(demand)
            quantities(demand, ("demand_qty", "remaining_demand_qty", "reserved_qty", "picked_qty",
                               "posted_consumed_qty", "unreserved_qty", "forecast_qty"))
            expected_unreserved = max(Decimal(str(demand.remaining_demand_qty))
                                      - Decimal(str(demand.reserved_qty)), Decimal(0))
            consistent(demand, demand.unreserved_qty, expected_unreserved, "unreserved demand")
        stock_keys = set()
        for balance in self.stock:
            product_unit(balance)
            quantities(balance, ("on_hand_qty", "reserved_qty", "free_qty"))
            consistent(balance, balance.free_qty, Decimal(str(balance.on_hand_qty))
                       - Decimal(str(balance.reserved_qty)), "free stock")
            key = (balance.product_id, balance.location_id)
            if key in stock_keys:
                raise ValueError("duplicate stock balance")
            stock_keys.add(key)
        for name in collections:
            getattr(self, name).sort(key=lambda row: row.id)
        self.stock.sort(key=lambda row: (row.product_id, row.location_id))
        return self


def validate_snapshot(payload: dict) -> Snapshot:
    return Snapshot.model_validate(payload)


def snapshot_bytes(snapshot: Snapshot) -> bytes:
    return json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class Envelope(Contract):
    version: Literal[1]
    token: Text
    hello_nonce: Text
    session_id: UUID
    source_id: UUID
    scope_id: Scope

    @model_validator(mode="after")
    def bounded_utf8_envelope(self):
        data = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        if len(data.encode("utf-8")) > 1024:
            raise ValueError("UDP envelope exceeds 1024 UTF-8 bytes")
        return self


class Hello(Envelope):
    type: Literal["hello"]
    session_id: None


class HelloAck(Envelope):
    type: Literal["hello_ack"]


class SnapshotBegin(Envelope):
    type: Literal["snapshot_begin"]
    revision: Id
    snapshot_id: Text
    chunk_count: Annotated[int, Field(strict=True, ge=1, le=512)]
    byte_length: Annotated[int, Field(strict=True, ge=1, le=262144)]


class SnapshotChunk(Envelope):
    type: Literal["snapshot_chunk"]
    revision: Id
    snapshot_id: Text
    index: Annotated[int, Field(strict=True, ge=0, lt=512)]
    data: str


class ChunkAck(Envelope):
    type: Literal["chunk_ack"]
    snapshot_id: Text
    index: Annotated[int, Field(strict=True, ge=0, lt=512)]


class SnapshotApplied(Envelope):
    type: Literal["snapshot_applied"]
    revision: Id
    snapshot_id: Text


class Heartbeat(Envelope):
    type: Literal["heartbeat"]
    sequence: Sequence
    source_read_at: UTCDateTime | None
    source_age_seconds: Quantity | None
    source_ok: bool
    last_success_at: UTCDateTime | None = None
    last_error: str | None = None
    refreshing: bool = False


class HeartbeatAck(Envelope):
    type: Literal["heartbeat_ack"]
    sequence: Sequence


class ResyncRequest(Envelope):
    type: Literal["resync_request"]


WireEnvelope = Annotated[Union[Hello, HelloAck, SnapshotBegin, SnapshotChunk, ChunkAck,
                              SnapshotApplied, Heartbeat, HeartbeatAck, ResyncRequest],
                         Field(discriminator="type")]
WireMessage = TypeAdapter(WireEnvelope)


def _write_schemas(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    for filename, schema in (("snapshot-v1.schema.json", Snapshot.model_json_schema()),
                             ("wire-v1.schema.json", WireMessage.json_schema())):
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (destination / filename).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import sys
    _write_schemas(Path(sys.argv[1]))
