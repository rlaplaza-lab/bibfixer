"""Structured run logging for terminal inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class RunEvent:
    """A single pipeline event."""

    kind: str
    message: str
    phase: str | None = None
    step: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseSnapshot:
    """Aggregated metrics for one pipeline phase."""

    name: str
    started_at: float
    ended_at: float | None = None
    steps_ok: int = 0
    steps_warn: int = 0
    steps_error: int = 0
    counters: dict[str, int] = field(default_factory=dict)

    def duration_s(self) -> float:
        end = self.ended_at if self.ended_at is not None else perf_counter()
        return end - self.started_at


class RunLogger:
    """Collect structured events and render consistent terminal output."""

    def __init__(self, action: str) -> None:
        self.action = action
        self.started_at = perf_counter()
        self.events: list[RunEvent] = []
        self._phases: dict[str, PhaseSnapshot] = {}
        self._phase_stack: list[str] = []
        self._global_counters: dict[str, int] = {}

    def _current_phase(self) -> str | None:
        if not self._phase_stack:
            return None
        return self._phase_stack[-1]

    def _emit(self, kind: str, message: str, step: str | None = None, **data: Any) -> None:
        phase = self._current_phase()
        self.events.append(RunEvent(kind=kind, message=message, phase=phase, step=step, data=dict(data)))
        print(message)

    def start_phase(self, name: str, title: str) -> None:
        snap = PhaseSnapshot(name=name, started_at=perf_counter())
        self._phases[name] = snap
        self._phase_stack.append(name)
        self._emit("phase_start", f"\n== {title} ==")

    def end_phase(self, name: str) -> None:
        snap = self._phases.get(name)
        if snap is None:
            return
        snap.ended_at = perf_counter()
        if self._phase_stack and self._phase_stack[-1] == name:
            self._phase_stack.pop()
        self._emit(
            "phase_end",
            (
                f"Phase complete: {name} "
                f"(ok={snap.steps_ok}, warn={snap.steps_warn}, error={snap.steps_error}, "
                f"{snap.duration_s():.2f}s)"
            ),
        )

    def step_ok(self, step: str, message: str) -> None:
        phase = self._current_phase()
        if phase and phase in self._phases:
            self._phases[phase].steps_ok += 1
        self._emit("step_ok", f"  [OK] {step}: {message}", step=step)

    def step_warn(self, step: str, message: str) -> None:
        phase = self._current_phase()
        if phase and phase in self._phases:
            self._phases[phase].steps_warn += 1
        self._emit("step_warn", f"  [WARN] {step}: {message}", step=step)

    def step_error(self, step: str, message: str) -> None:
        phase = self._current_phase()
        if phase and phase in self._phases:
            self._phases[phase].steps_error += 1
        self._emit("step_error", f"  [ERROR] {step}: {message}", step=step)

    def info(self, message: str) -> None:
        self._emit("info", message)

    def counter(self, name: str, value: int) -> None:
        self._global_counters[name] = self._global_counters.get(name, 0) + value
        phase = self._current_phase()
        if phase and phase in self._phases:
            phase_counters = self._phases[phase].counters
            phase_counters[name] = phase_counters.get(name, 0) + value
        self._emit("counter", f"  [COUNT] {name}: {value}", counter=name, value=value)

    def render_final_summary(self) -> None:
        elapsed = perf_counter() - self.started_at
        print("\n== Run Summary ==")
        print(f"Action: {self.action}")
        print(f"Total runtime: {elapsed:.2f}s")
        if self._global_counters:
            print("Totals:")
            for key in sorted(self._global_counters):
                print(f"  - {key}: {self._global_counters[key]}")
        if self._phases:
            print("Phases:")
            for key in sorted(self._phases):
                snap = self._phases[key]
                print(
                    f"  - {snap.name}: ok={snap.steps_ok}, warn={snap.steps_warn}, "
                    f"error={snap.steps_error}, duration={snap.duration_s():.2f}s"
                )
