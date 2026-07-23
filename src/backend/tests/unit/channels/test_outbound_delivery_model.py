from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)


def test_outbound_delivery_model_schema_contract() -> None:
    table = ChannelOutboundDelivery.__table__

    assert set(table.columns) == {
        "id",
        "connection_id",
        "external_event_id",
        "delivery_kind",
        "response_digest",
        "status",
        "attempts",
        "provider_message_id",
        "last_error",
        "created_at",
        "updated_at",
        "sent_at",
    }
    assert table.columns.external_event_id.type.length == 255
    assert table.columns.delivery_kind.type.length == 32
    assert table.columns.response_digest.type.length == 64
    assert table.columns.status.type.length == 32
    assert table.columns.provider_message_id.type.length == 255

    unique = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "uq_channel_outbound_delivery_event_kind"
    )
    assert [column.name for column in unique.columns] == [
        "connection_id",
        "external_event_id",
        "delivery_kind",
    ]

    indexes = {index.name: [column.name for column in index.columns] for index in table.indexes}
    assert indexes["ix_channel_outbound_delivery_status_updated"] == ["status", "updated_at"]
    assert indexes["ix_channel_outbound_delivery_connection_id"] == ["connection_id"]


def test_outbound_delivery_enums_are_bounded() -> None:
    assert {kind.value for kind in ChannelOutboundDeliveryKind} == {
        "acknowledgement",
        "response",
    }
    assert {status.value for status in ChannelOutboundDeliveryStatus} == {
        "reserved",
        "sent",
        "failed",
    }
