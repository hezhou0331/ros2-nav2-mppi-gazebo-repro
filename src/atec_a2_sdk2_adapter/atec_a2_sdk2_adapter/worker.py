"""Dedicated SDK command worker; no blocking SDK call runs in a ROS callback."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .safety import SafetyEnvelope


class SportCommandWorker:
    def __init__(
        self,
        safety: SafetyEnvelope,
        backend: object,
        stop_refresh_period_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        event_factory: Callable[[], threading.Event] = threading.Event,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._safety = safety
        self._backend = backend
        self._stop_refresh_period_s = float(stop_refresh_period_s)
        self._clock = clock
        self._sleep = sleeper
        self._stop_event = event_factory()
        self._log = log or (lambda _message: None)
        self._thread: Optional[threading.Thread] = None
        self._last_action = ""
        self._last_stop_at: Optional[float] = None
        self._shutdown_deadline: Optional[float] = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("command worker may only be started once")
        self._thread = threading.Thread(
            target=self._run,
            name="a2_sdk2_command_worker",
            daemon=True,
        )
        self._thread.start()

    def close(self, join_timeout_s: float) -> bool:
        self._shutdown_deadline = self._clock() + float(join_timeout_s)
        self._stop_event.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=join_timeout_s)
        return not thread.is_alive()

    def process_once(self, now: Optional[float] = None) -> None:
        """Execute one worker decision; public to support SDK-free tests."""

        decision_time = self._clock() if now is None else now
        snapshot = self._safety.snapshot(decision_time)
        if snapshot.move_permitted:
            command = snapshot.command
            if command is None:
                raise RuntimeError("move-permitted snapshot has no command")
            if command.linear_x != 0.0 or command.angular_z != 0.0:
                self._call_move(command.linear_x, command.angular_z)
                return

        should_refresh_stop = (
            self._last_action != "stop"
            or self._last_stop_at is None
            or decision_time - self._last_stop_at >= self._stop_refresh_period_s
        )
        if should_refresh_stop:
            context = "zero_command" if snapshot.move_permitted else "unsafe_or_stale"
            self._call_stop(context, decision_time)

    def _run(self) -> None:
        backend_started = False
        failure_detail = ""
        try:
            self._backend.start()
            backend_started = True
            self._safety.set_backend_available(True, "sdk2_initialized")
            self._call_stop("startup", self._clock())
            while not self._stop_event.wait(self._safety.limits.control_period_s):
                self.process_once()
        except Exception as exc:
            failure_detail = f"worker_failed:{exc}"
            self._safety.set_backend_available(False, failure_detail)
            self._log(f"A2 SDK2 worker failed closed: {exc}")
        finally:
            if backend_started:
                self._stop_for_shutdown()
                try:
                    self._backend.close()
                except Exception as exc:
                    self._log(f"A2 SDK2 backend close failed: {exc}")
            self._safety.set_backend_available(
                False, failure_detail or "worker_stopped"
            )

    def _call_move(self, linear_x: float, angular_z: float) -> None:
        try:
            code = self._backend.move(linear_x, angular_z)
            self._safety.record_rpc_result(code, f"move:{code}")
            self._last_action = "move" if code == 0 else "move_failed"
        except Exception as exc:
            self._safety.record_rpc_exception(f"move_exception:{exc}")
            self._last_action = "move_failed"
            self._log(f"A2 Move failed closed: {exc}")

    def _call_stop(
        self,
        context: str,
        now: float,
        suppress: bool = False,
    ) -> bool:
        try:
            code = self._backend.stop()
            self._safety.record_rpc_result(code, f"stop_{context}:{code}")
            if code == 0:
                self._last_action = "stop"
                self._last_stop_at = now
                return True
            else:
                self._last_action = "stop_failed"
                self._last_stop_at = None
        except Exception as exc:
            self._safety.record_rpc_exception(f"stop_{context}_exception:{exc}")
            self._last_action = "stop_failed"
            self._last_stop_at = None
            if not suppress:
                self._log(f"A2 StopMove ({context}) failed: {exc}")
        return False

    def _stop_for_shutdown(self) -> None:
        while True:
            if self._call_stop("shutdown", self._clock(), suppress=True):
                return
            deadline = self._shutdown_deadline
            if deadline is None:
                return
            remaining = deadline - self._clock()
            retry_delay = self._safety.limits.control_period_s
            if remaining <= retry_delay:
                return
            self._sleep(retry_delay)
