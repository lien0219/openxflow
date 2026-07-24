from langflow.channels.services.outbound_delivery_metrics import (
    OutboundDeliveryMetricsCollector,
    outbound_delivery_metrics_snapshot,
    record_outbound_delivery_cleaned,
    record_outbound_delivery_failed,
    record_outbound_delivery_reserved,
    record_outbound_delivery_sent,
    record_outbound_delivery_state_error,
    record_outbound_delivery_suppressed,
    reset_outbound_delivery_metrics_for_testing,
    set_outbound_delivery_retained_depths,
)
from langflow.services.database.models.channel.outbound_delivery_model import ChannelOutboundDeliveryKind
from prometheus_client import CollectorRegistry, generate_latest


def setup_function() -> None:
    reset_outbound_delivery_metrics_for_testing()


def teardown_function() -> None:
    reset_outbound_delivery_metrics_for_testing()


def test_outbound_delivery_metrics_track_guard_outcomes_by_kind() -> None:
    record_outbound_delivery_reserved(ChannelOutboundDeliveryKind.RESPONSE)
    record_outbound_delivery_reserved(ChannelOutboundDeliveryKind.RESPONSE)
    record_outbound_delivery_suppressed(ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT)
    record_outbound_delivery_sent(ChannelOutboundDeliveryKind.RESPONSE)
    record_outbound_delivery_failed(ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT)
    record_outbound_delivery_state_error(ChannelOutboundDeliveryKind.RESPONSE)
    record_outbound_delivery_cleaned(ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT, 3)
    set_outbound_delivery_retained_depths(
        ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT,
        reserved=1,
        sent=2,
        failed=3,
    )
    set_outbound_delivery_retained_depths(
        ChannelOutboundDeliveryKind.RESPONSE,
        reserved=4,
        sent=5,
        failed=6,
    )

    snapshot = outbound_delivery_metrics_snapshot()

    assert snapshot.reserved_total == 2
    assert snapshot.suppressed_total == 1
    assert snapshot.sent_total == 1
    assert snapshot.failed_total == 1
    assert snapshot.state_errors_total == 1
    assert snapshot.cleaned_total == 3
    assert snapshot.retained_reserved == 5
    assert snapshot.retained_sent == 7
    assert snapshot.retained_failed == 9
    assert snapshot.by_kind["response"].reserved_total == 2
    assert snapshot.by_kind["acknowledgement"].cleaned_total == 3
    assert snapshot.by_kind["response"].retained_failed == 6


def test_outbound_delivery_metrics_reject_unknown_kind_and_negative_depths() -> None:
    try:
        record_outbound_delivery_reserved("unknown")
    except ValueError as exc:
        assert "Unsupported outbound delivery kind" in str(exc)
    else:
        raise AssertionError("unknown delivery kind was accepted")

    try:
        set_outbound_delivery_retained_depths(
            ChannelOutboundDeliveryKind.RESPONSE,
            reserved=-1,
            sent=0,
            failed=0,
        )
    except ValueError as exc:
        assert "must be non-negative" in str(exc)
    else:
        raise AssertionError("negative retained delivery depth was accepted")


def test_outbound_delivery_metrics_collector_exposes_bounded_kind_labels() -> None:
    record_outbound_delivery_reserved(ChannelOutboundDeliveryKind.RESPONSE)
    record_outbound_delivery_suppressed(ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT)
    record_outbound_delivery_sent(ChannelOutboundDeliveryKind.RESPONSE)
    set_outbound_delivery_retained_depths(
        ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT,
        reserved=1,
        sent=2,
        failed=3,
    )
    set_outbound_delivery_retained_depths(
        ChannelOutboundDeliveryKind.RESPONSE,
        reserved=4,
        sent=5,
        failed=6,
    )

    registry = CollectorRegistry(auto_describe=True)
    registry.register(OutboundDeliveryMetricsCollector())
    rendered = generate_latest(registry).decode()

    assert 'openxflow_channel_outbound_delivery_reserved_total{delivery_kind="response"} 1.0' in rendered
    assert 'openxflow_channel_outbound_delivery_reserved_total{delivery_kind="acknowledgement"} 0.0' in rendered
    assert 'openxflow_channel_outbound_delivery_suppressed_total{delivery_kind="acknowledgement"} 1.0' in rendered
    assert 'openxflow_channel_outbound_delivery_sent_total{delivery_kind="response"} 1.0' in rendered
    assert 'openxflow_channel_outbound_delivery_failed_total{delivery_kind="response"} 0.0' in rendered
    assert 'openxflow_channel_outbound_delivery_state_errors_total{delivery_kind="response"} 0.0' in rendered
    assert 'openxflow_channel_outbound_delivery_cleaned_total{delivery_kind="response"} 0.0' in rendered
    assert 'openxflow_channel_outbound_delivery_retained_reserved{delivery_kind="response"} 4.0' in rendered
    assert 'openxflow_channel_outbound_delivery_retained_sent{delivery_kind="acknowledgement"} 2.0' in rendered
    assert 'openxflow_channel_outbound_delivery_retained_failed{delivery_kind="response"} 6.0' in rendered
    assert 'delivery_kind="unknown"' not in rendered
