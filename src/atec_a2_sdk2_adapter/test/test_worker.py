import time

from atec_a2_sdk2_adapter.safety import SafetyEnvelope, SafetyLimits
from atec_a2_sdk2_adapter.worker import SportCommandWorker


class FakeBackend:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append(("start",))

    def move(self, linear_x, angular_z):
        self.calls.append(("move", linear_x, angular_z))
        return 0

    def stop(self):
        self.calls.append(("stop",))
        return 0

    def close(self):
        self.calls.append(("close",))


def wait_until(predicate, timeout=0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.002)
    return False


def test_worker_stops_at_start_watchdog_and_shutdown_without_sdk():
    limits = SafetyLimits(
        command_timeout_s=0.04,
        control_period_s=0.005,
        rpc_timeout_s=0.005,
        sport_state_timeout_s=0.20,
        external_state_timeout_s=0.25,
    )
    safety = SafetyEnvelope(limits)
    now = time.monotonic()
    safety.set_automatic_mode(True, now)
    safety.set_manual_override(False, now)
    safety.set_estop(False, now)
    safety.update_sport_state(0, 3, now)
    safety.accept_command((0.08, 0.0, 0.0, 0.0, 0.0, 0.1), now)

    backend = FakeBackend()
    worker = SportCommandWorker(safety, backend, stop_refresh_period_s=0.01)
    worker.start()
    assert wait_until(lambda: any(call[0] == "move" for call in backend.calls))
    assert backend.calls[0] == ("start",)
    assert backend.calls[1] == ("stop",)

    assert wait_until(
        lambda: sum(call[0] == "stop" for call in backend.calls) >= 2,
        timeout=0.3,
    )
    assert worker.close(0.2)
    assert backend.calls[-2:] == [("stop",), ("close",)]


def test_process_once_never_moves_when_safety_state_is_unknown():
    safety = SafetyEnvelope(SafetyLimits())
    backend = FakeBackend()
    backend.start()
    worker = SportCommandWorker(safety, backend, stop_refresh_period_s=0.1)
    worker.process_once(now=10.0)
    assert backend.calls == [("start",), ("stop",)]


def test_zero_velocity_uses_stopmove_instead_of_move():
    safety = SafetyEnvelope(SafetyLimits())
    now = 10.0
    safety.set_backend_available(True, "test")
    safety.record_rpc_result(0, "startup_stop:0")
    safety.set_automatic_mode(True, now)
    safety.set_manual_override(False, now)
    safety.set_estop(False, now)
    safety.update_sport_state(0, 3, now)
    safety.accept_command((0.0, 0.0, 0.0, 0.0, 0.0, 0.0), now)

    backend = FakeBackend()
    backend.start()
    worker = SportCommandWorker(safety, backend, stop_refresh_period_s=0.1)
    worker.process_once(now=10.01)
    assert backend.calls == [("start",), ("stop",)]


def test_nonzero_stop_result_is_retried_on_next_control_decision():
    class StopFailBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.stop_results = iter((3104, 0))

        def stop(self):
            self.calls.append(("stop",))
            return next(self.stop_results)

    safety = SafetyEnvelope(SafetyLimits())
    backend = StopFailBackend()
    backend.start()
    worker = SportCommandWorker(safety, backend, stop_refresh_period_s=0.1)

    worker.process_once(now=10.0)
    worker.process_once(now=10.02)

    assert backend.calls == [("start",), ("stop",), ("stop",)]


def test_stop_exception_is_retried_on_next_control_decision():
    class StopExceptionBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.stop_calls = 0

        def stop(self):
            self.calls.append(("stop",))
            self.stop_calls += 1
            if self.stop_calls == 1:
                raise RuntimeError("transient_stop_failure")
            return 0

    safety = SafetyEnvelope(SafetyLimits())
    backend = StopExceptionBackend()
    backend.start()
    worker = SportCommandWorker(safety, backend, stop_refresh_period_s=0.1)

    worker.process_once(now=10.0)
    worker.process_once(now=10.02)

    assert backend.calls == [("start",), ("stop",), ("stop",)]


def test_shutdown_stop_retries_within_join_deadline():
    class ShutdownRetryBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.stop_results = iter((3104, 0))

        def stop(self):
            self.calls.append(("stop",))
            return next(self.stop_results)

    now = [10.0]

    def sleep(duration):
        now[0] += duration

    safety = SafetyEnvelope(SafetyLimits())
    backend = ShutdownRetryBackend()
    backend.start()
    worker = SportCommandWorker(
        safety,
        backend,
        stop_refresh_period_s=0.1,
        clock=lambda: now[0],
        sleeper=sleep,
    )
    worker._shutdown_deadline = 10.5

    worker._stop_for_shutdown()

    assert backend.calls == [("start",), ("stop",), ("stop",)]
    assert now[0] == 10.02


def test_shutdown_stop_does_not_retry_after_join_deadline():
    class StopFailBackend(FakeBackend):
        def stop(self):
            self.calls.append(("stop",))
            return 3104

    now = [10.0]
    safety = SafetyEnvelope(SafetyLimits())
    backend = StopFailBackend()
    backend.start()
    worker = SportCommandWorker(
        safety,
        backend,
        stop_refresh_period_s=0.1,
        clock=lambda: now[0],
        sleeper=lambda duration: now.__setitem__(0, now[0] + duration),
    )
    worker._shutdown_deadline = 10.01

    worker._stop_for_shutdown()

    assert backend.calls == [("start",), ("stop",)]


def test_worker_preserves_backend_start_failure_detail():
    class StartFailBackend(FakeBackend):
        def start(self):
            raise RuntimeError("missing_sdk")

    safety = SafetyEnvelope(SafetyLimits())
    worker = SportCommandWorker(
        safety, StartFailBackend(), stop_refresh_period_s=0.1
    )
    worker.start()
    assert wait_until(lambda: not worker.alive)
    snapshot = safety.snapshot(time.monotonic())
    assert not snapshot.backend_available
    assert snapshot.backend_detail == "worker_failed:missing_sdk"
