import math

import pytest

from atec_a2_sdk2_adapter.safety import (
    SafetyEnvelope,
    SafetyLimits,
    monotonic_receive_time,
)


def make_ready(envelope, now=10.0):
    envelope.set_backend_available(True, "test")
    envelope.record_rpc_result(0, "startup_stop:0")
    envelope.set_automatic_mode(True, now)
    envelope.set_manual_override(False, now)
    envelope.set_estop(False, now)
    envelope.update_sport_state(error_code=0, mode=3, received_at=now)


def test_unknown_and_stale_inputs_fail_closed():
    envelope = SafetyEnvelope(SafetyLimits())
    unknown = envelope.snapshot(10.0)
    assert not unknown.ready
    assert "automatic_mode_unknown" in unknown.ready_reasons
    assert "manual_override_unknown" in unknown.ready_reasons
    assert "estop_unknown" in unknown.ready_reasons
    assert "sport_state_unknown" in unknown.ready_reasons

    make_ready(envelope)
    assert envelope.snapshot(10.1).ready
    stale = envelope.snapshot(10.3)
    assert not stale.ready
    assert "automatic_mode_stale" in stale.ready_reasons
    assert "sport_state_stale" in stale.ready_reasons
    assert stale.fault_latched
    assert stale.fault_reason == "automatic_mode_stale"


@pytest.mark.parametrize(
    "setter,value,reason",
    [
        ("set_automatic_mode", False, "automatic_mode_disabled"),
        ("set_manual_override", True, "manual_override_active"),
        ("set_estop", True, "estop_active"),
    ],
)
def test_external_safety_states_fail_closed(setter, value, reason):
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    getattr(envelope, setter)(value, 10.01)
    snapshot = envelope.snapshot(10.02)
    assert not snapshot.ready
    assert reason in snapshot.ready_reasons


@pytest.mark.parametrize(
    "error_code,mode,reason",
    [
        (7, 3, "sport_error"),
        (0, 2, "sport_mode_not_allowed"),
        (None, 3, "sport_state_invalid"),
        (0, None, "sport_state_invalid"),
    ],
)
def test_sport_state_must_be_valid(error_code, mode, reason):
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    envelope.update_sport_state(error_code, mode, 10.01)
    snapshot = envelope.snapshot(10.02)
    assert not snapshot.ready
    assert reason in snapshot.ready_reasons


def test_command_is_clamped_then_expires():
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    accepted, reason = envelope.accept_command(
        (0.8, 0.0, 0.0, 0.0, 0.0, -0.9), 10.01
    )
    assert accepted
    assert not reason

    moving = envelope.snapshot(10.02)
    assert moving.ready
    assert moving.move_permitted
    assert moving.command.linear_x == pytest.approx(0.10)
    assert moving.command.angular_z == pytest.approx(-0.20)

    expired = envelope.snapshot(10.12)
    assert expired.ready
    assert not expired.move_permitted
    assert expired.stop_reason == "command_stale"


@pytest.mark.parametrize(
    "components,reason",
    [
        ((0.0, 0.01, 0.0, 0.0, 0.0, 0.0), "unsupported_nonzero_axis"),
        ((0.0, 0.0, -0.01, 0.0, 0.0, 0.0), "unsupported_nonzero_axis"),
        ((0.0, 0.0, 0.0, 0.01, 0.0, 0.0), "unsupported_nonzero_axis"),
        ((0.0, 0.0, 0.0, 0.0, -0.01, 0.0), "unsupported_nonzero_axis"),
        ((math.nan, 0.0, 0.0, 0.0, 0.0, 0.0), "non_finite_command"),
        ((0.0, 0.0, 0.0, 0.0, 0.0, math.inf), "non_finite_command"),
    ],
)
def test_invalid_commands_are_rejected(components, reason):
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    accepted, actual_reason = envelope.accept_command(components, 10.01)
    assert not accepted
    assert actual_reason == reason
    snapshot = envelope.snapshot(10.02)
    assert not snapshot.ready
    assert reason in snapshot.ready_reasons
    assert not snapshot.move_permitted


def test_rpc_failure_stays_latched_after_a_successful_stop_until_rearm():
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    envelope.record_rpc_result(3104, "move:3104")
    assert "backend_rpc_unhealthy" in envelope.snapshot(10.01).ready_reasons
    envelope.record_rpc_result(0, "stop_recovery:0")
    stopped = envelope.snapshot(10.02)
    assert not stopped.ready
    assert stopped.fault_latched
    assert stopped.fault_reason == "rpc_failure:3104"

    envelope.set_automatic_mode(False, 10.03)
    envelope.set_manual_override(False, 10.03)
    envelope.set_estop(False, 10.03)
    envelope.set_automatic_mode(True, 10.04)
    rearmed = envelope.snapshot(10.05)
    assert rearmed.ready
    assert not rearmed.fault_latched
    assert not rearmed.move_permitted
    assert rearmed.stop_reason == "command_missing"


def test_invalid_command_requires_automatic_mode_rearm_and_new_command():
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    envelope.accept_command((0.1, 0.01, 0.0, 0.0, 0.0, 0.0), 10.01)
    accepted, _ = envelope.accept_command(
        (0.1, 0.0, 0.0, 0.0, 0.0, 0.0), 10.02
    )
    assert accepted
    assert not envelope.snapshot(10.03).ready

    envelope.set_automatic_mode(False, 10.04)
    envelope.set_manual_override(False, 10.04)
    envelope.set_estop(False, 10.04)
    envelope.set_automatic_mode(True, 10.05)
    assert envelope.snapshot(10.06).stop_reason == "command_missing"
    envelope.accept_command((0.1, 0.0, 0.0, 0.0, 0.0, 0.0), 10.07)
    assert envelope.snapshot(10.08).move_permitted


def test_failed_rearm_requires_another_false_true_cycle_after_states_are_fresh():
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    envelope.set_estop(True, 10.01)
    envelope.set_estop(False, 10.02)
    envelope.set_automatic_mode(False, 10.02)
    envelope.set_automatic_mode(True, 10.30)
    assert envelope.snapshot(10.30).fault_latched

    envelope.set_manual_override(False, 10.31)
    envelope.set_estop(False, 10.31)
    envelope.update_sport_state(0, 3, 10.31)
    envelope.set_automatic_mode(True, 10.31)
    assert envelope.snapshot(10.31).fault_latched

    envelope.set_automatic_mode(False, 10.32)
    envelope.set_automatic_mode(True, 10.33)
    assert not envelope.snapshot(10.33).fault_latched


def test_authority_timeout_requires_rearm_and_a_new_command():
    envelope = SafetyEnvelope(SafetyLimits())
    make_ready(envelope)
    envelope.accept_command((0.08, 0.0, 0.0, 0.0, 0.0, 0.1), 10.01)
    assert envelope.snapshot(10.02).move_permitted

    stale = envelope.snapshot(10.30)
    assert stale.fault_latched
    assert stale.fault_reason == "automatic_mode_stale"
    assert stale.command is None

    envelope.set_automatic_mode(True, 10.31)
    envelope.set_manual_override(False, 10.31)
    envelope.set_estop(False, 10.31)
    envelope.update_sport_state(0, 3, 10.31)
    envelope.accept_command((0.08, 0.0, 0.0, 0.0, 0.0, 0.1), 10.31)
    assert not envelope.snapshot(10.32).move_permitted

    envelope.set_automatic_mode(False, 10.33)
    envelope.set_automatic_mode(True, 10.34)
    rearmed = envelope.snapshot(10.34)
    assert not rearmed.fault_latched
    assert rearmed.stop_reason == "command_missing"
    envelope.accept_command((0.08, 0.0, 0.0, 0.0, 0.0, 0.1), 10.35)
    assert envelope.snapshot(10.36).move_permitted


def test_dds_receive_timestamp_preserves_executor_queue_age():
    received_at = monotonic_receive_time(
        {"received_timestamp": 100_000_000_000},
        monotonic_now=500.0,
        wall_time_ns=100_250_000_000,
    )
    assert received_at == pytest.approx(499.75)


@pytest.mark.parametrize(
    "message_info,wall_time_ns",
    [
        ({}, 100),
        ({"received_timestamp": 0}, 100),
        ({"received_timestamp": "100"}, 100),
        ({"received_timestamp": 101}, 100),
    ],
)
def test_invalid_dds_receive_timestamps_fail_closed(message_info, wall_time_ns):
    with pytest.raises(ValueError):
        monotonic_receive_time(
            message_info,
            monotonic_now=1.0,
            wall_time_ns=wall_time_ns,
        )


def test_default_nominal_and_unmatched_rpc_paths_are_explicit():
    limits = SafetyLimits()
    assert limits.nominal_stop_request_latency_s == pytest.approx(0.14)
    assert limits.unmatched_rpc_return_path_s == pytest.approx(0.30)
    limits.validate()


def test_configuration_rejects_a_budget_over_200_ms():
    with pytest.raises(ValueError, match="exceeds nominal_stop_request_budget_s"):
        SafetyLimits(nominal_stop_request_budget_s=0.13).validate()
    with pytest.raises(ValueError, match="must not exceed"):
        SafetyLimits(nominal_stop_request_budget_s=0.21).validate()


@pytest.mark.parametrize(
    "override",
    [
        {"max_linear_x": 0.101},
        {"max_angular_z": 0.201},
        {"command_timeout_s": 0.081},
        {"control_period_s": 0.021},
        {"rpc_timeout_s": 0.021},
        {"sport_state_timeout_s": 0.201},
        {"external_state_timeout_s": 0.251},
        {"unsupported_axis_epsilon": 1.1e-6},
    ],
)
def test_configuration_cannot_raise_hardware_caps(override):
    with pytest.raises(ValueError, match="hardware cap"):
        SafetyLimits(**override).validate()


def test_configuration_can_only_narrow_official_sport_modes():
    SafetyLimits(allowed_sport_modes=(3,)).validate()
    SafetyLimits(allowed_sport_modes=(4,)).validate()
    with pytest.raises(ValueError, match="subset of modes 3 and 4"):
        SafetyLimits(allowed_sport_modes=(3, 11)).validate()
