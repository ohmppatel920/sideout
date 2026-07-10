"""Turn a keypoints DataFrame into per-jump metrics + session aggregates.

This is the orchestration layer that ties together :mod:`sideout.jump.series`
(smoothing), :mod:`sideout.jump.events` (detection), and
:mod:`sideout.jump.metrics` (the pure physics). It contains no I/O and no new
physics — every number comes from a metrics.py function — so it stays easy to
test and reason about.

Units: heights/depths in meters (when calibrated) and normalized units always;
times in seconds; velocities in m/s (calibrated only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from sideout.jump import metrics
from sideout.jump.events import JumpEvent, detect_jumps
from sideout.jump.series import JumpSeries, build_series


@dataclass
class JumpMetrics:
    """Every metric for one detected jump. ``None`` where not computable
    (e.g. meter-scaled metrics without a height calibration, or loading time
    when no clear countermovement was found)."""

    index: int
    takeoff_s: float
    landing_s: float
    flight_time_s: float
    jump_height_m: float
    countermovement_depth_norm: float | None
    countermovement_depth_m: float | None
    loading_time_s: float | None
    approach_velocity_m_s: float | None
    arm_swing_timing_s: float | None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class SessionAnalysis:
    """Full analysis of one clip: per-jump metrics plus session aggregates."""

    n_jumps: int
    calibrated: bool
    athlete_height_cm: float | None
    m_per_unit: float | None
    jumps: list[JumpMetrics]
    aggregates: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_jumps": self.n_jumps,
            "calibrated": self.calibrated,
            "athlete_height_cm": self.athlete_height_cm,
            "m_per_unit": self.m_per_unit,
            "aggregates": self.aggregates,
            "jumps": [j.to_dict() for j in self.jumps],
        }


def _standing_eye_ankle(series: JumpSeries, before_s: float) -> tuple[float, float]:
    """Median standing eye_y and ankle_y over the quiet start of the clip.

    Uses the earliest ~0.5 s (before the approach pitches the torso forward and
    compresses the eye→ankle span), and never looks past ``before_s`` (the
    first jump's load). Falls back to the first frame if that window is empty.
    """
    end = min(before_s, float(series.t_s[0]) + 0.5)
    mask = series.t_s <= end
    if mask.sum() < 1:
        mask = series.t_s <= series.t_s[0]
    return float(np.median(series.eye_y[mask])), float(np.median(series.ankle_y[mask]))


def _metrics_for_jump(
    series: JumpSeries, ev: JumpEvent, index: int, m_per_unit: float | None
) -> JumpMetrics:
    """Compute every metric for a single detected jump."""
    flight = ev.flight_time_s
    height_m = metrics.jump_height_m(flight)

    # Countermovement depth and loading time exist only when a load phase was
    # detected. Without one (e.g. a block jump straight out of the approach)
    # they are undefined — leave them None rather than fabricating a value.
    depth_norm: float | None = None
    depth_m: float | None = None
    loading: float | None = None
    if ev.load_start_s is not None:
        standing = metrics.standing_hip_y(series.hip_y, series.t_s, before_s=ev.load_start_s)
        depth_norm = metrics.countermovement_depth_norm(
            series.hip_y, series.t_s, ev.load_start_s, ev.takeoff_s, standing
        )
        depth_m = metrics.countermovement_depth_m(depth_norm, m_per_unit) if m_per_unit else None
        loading = metrics.loading_time_s(ev.load_start_s, ev.takeoff_s)

    # Approach velocity is measured up to the plant; use load_start, else takeoff.
    plant_s = ev.load_start_s if ev.load_start_s is not None else ev.takeoff_s
    arm = metrics.arm_swing_timing_s(series.wrist_y, series.t_s, ev.takeoff_s)
    approach_v = (
        metrics.approach_velocity_m_s(series.hip_x, series.t_s, plant_s, m_per_unit)
        if m_per_unit
        else None
    )

    return JumpMetrics(
        index=index,
        takeoff_s=round(ev.takeoff_s, 4),
        landing_s=round(ev.landing_s, 4),
        flight_time_s=round(flight, 4),
        jump_height_m=round(height_m, 4),
        countermovement_depth_norm=round(depth_norm, 5) if depth_norm is not None else None,
        countermovement_depth_m=round(depth_m, 4) if depth_m is not None else None,
        loading_time_s=round(loading, 4) if loading is not None else None,
        approach_velocity_m_s=round(approach_v, 3) if approach_v is not None else None,
        arm_swing_timing_s=round(arm, 4),
    )


def _aggregate(jumps: list[JumpMetrics]) -> dict[str, Any]:
    """Session-level summary statistics over the detected jumps."""
    if not jumps:
        return {}
    heights = [j.jump_height_m for j in jumps]
    return {
        "best_jump_height_m": round(max(heights), 4),
        "mean_jump_height_m": round(float(np.mean(heights)), 4),
        "mean_flight_time_s": round(float(np.mean([j.flight_time_s for j in jumps])), 4),
    }


def analyze_run(df: pd.DataFrame, height_cm: float | None = None) -> SessionAnalysis:
    """Analyze a keypoints DataFrame into per-jump metrics + session aggregates.

    ``height_cm`` (athlete standing height) unlocks the meter-scaled metrics
    (countermovement depth in meters, approach velocity). Everything else —
    jump height (flight-time), loading time, arm-swing timing, normalized depth
    — is computed with or without it.
    """
    series = build_series(df)
    events = detect_jumps(series)

    m_per_unit: float | None = None
    if height_cm and events:
        plant_s = events[0].load_start_s or events[0].takeoff_s
        eye_y, ankle_y = _standing_eye_ankle(series, before_s=plant_s)
        m_per_unit = metrics.calibration_m_per_unit(eye_y, ankle_y, height_cm / 100.0)

    jumps = [_metrics_for_jump(series, ev, i, m_per_unit) for i, ev in enumerate(events)]
    return SessionAnalysis(
        n_jumps=len(jumps),
        calibrated=m_per_unit is not None,
        athlete_height_cm=height_cm,
        m_per_unit=round(m_per_unit, 5) if m_per_unit else None,
        jumps=jumps,
        aggregates=_aggregate(jumps),
    )
