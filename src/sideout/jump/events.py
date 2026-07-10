"""Jump event detection: load_start → takeoff → flight → landing.

Operates on a :class:`~sideout.jump.series.JumpSeries` (smoothed, uniform
grid, normalized image units, y DOWN).

Detection strategy (per SPEC):
- **flight**: ankles leave the ground baseline. Ground level is estimated as a
  high quantile of ankle_y (feet planted = maximal image y). A candidate
  flight is a contiguous run of ``ankle_y < baseline - flight_threshold``
  lasting at least ``min_flight_s``, validated by requiring a strong upward
  hip-velocity peak around takeoff (rejects occlusion glitches).
  The coarse threshold gives noise immunity but sits well above the floor, so
  raw run edges would clip the first/last few centimeters of flight and bias
  flight time low (h = g·t²/8 amplifies that ~2× in height). Boundaries are
  therefore *refined* outward to actual ground contact
  (``ankle_y ≥ baseline − contact_epsilon``) before timing.
- **takeoff / landing**: event times are placed at the *midpoint* between the
  last grounded and first airborne sample (and vice versa), which halves the
  frame-quantization bias of flight time versus snapping to either frame.
- **load_start**: walking backwards from takeoff, the start of the last
  *sustained* downward hip motion (countermovement). "Downward" in physical
  terms means ``hip_up_vel < -load_vel_threshold`` (image y increasing).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sideout.jump.series import JumpSeries


@dataclass
class EventParams:
    """Tunable thresholds for jump detection (normalized image units / seconds)."""

    flight_threshold: float = 0.025  # ankle rise above baseline that counts as airborne
    contact_epsilon: float = 0.006  # ankle-baseline closeness that counts as ground contact
    baseline_quantile: float = 0.80  # ankle_y quantile treated as ground level
    min_flight_s: float = 0.20  # shortest credible jump flight (filters running steps)
    max_flight_s: float = 1.20  # longest credible flight (filters tracking dropouts)
    min_takeoff_up_vel: float = 0.25  # required peak hip up-velocity [units/s] near takeoff
    takeoff_vel_window_s: float = 0.30  # search window around takeoff for that peak
    load_vel_threshold: float = 0.05  # hip descent speed that counts as loading [units/s]
    load_sustain_s: float = 0.08  # descent must persist this long to be a countermovement
    load_lookback_s: float = 1.50  # how far before takeoff to search for load_start


@dataclass
class JumpEvent:
    """One detected jump. All times in seconds on the series' clock."""

    load_start_s: float | None  # None if no clear countermovement found
    takeoff_s: float
    landing_s: float

    @property
    def flight_time_s(self) -> float:
        """Flight duration [s] = landing − takeoff (real timestamps)."""
        return self.landing_s - self.takeoff_s


def _contiguous_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end] index pairs (inclusive) of each contiguous True run."""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return list(zip(starts.tolist(), ends.tolist(), strict=True))


def _find_load_start(series: JumpSeries, takeoff_i: int, p: EventParams) -> float | None:
    """Start of the last sustained hip descent before takeoff, or None."""
    lo = max(0, takeoff_i - int(round(p.load_lookback_s / series.dt_s)))
    descending = series.hip_up_vel[lo : takeoff_i + 1] < -p.load_vel_threshold
    sustain_n = max(1, int(round(p.load_sustain_s / series.dt_s)))
    runs = [(s, e) for s, e in _contiguous_runs(descending) if e - s + 1 >= sustain_n]
    if not runs:
        return None
    start_i = lo + runs[-1][0]  # last sustained descent = the countermovement
    return float(series.t_s[start_i])


def detect_jumps(series: JumpSeries, params: EventParams | None = None) -> list[JumpEvent]:
    """Detect all jumps in a series, in chronological order.

    Returns an empty list when no credible jump is present.
    """
    p = params or EventParams()
    if len(series) < 3:
        return []

    baseline = float(np.quantile(series.ankle_y, p.baseline_quantile))
    airborne = series.ankle_y < baseline - p.flight_threshold
    off_ground = series.ankle_y < baseline - p.contact_epsilon

    events: list[JumpEvent] = []
    for run_start, run_end in _contiguous_runs(airborne):
        # Refine boundaries outward from the coarse threshold to actual ground
        # contact, so flight time isn't clipped (see module docstring).
        # Refinement must be able to REACH the array edges (indices 0 and
        # len-1); otherwise the edge-rejection guard below can never fire for a
        # jump whose takeoff/landing sits right at the clip boundary, and the
        # flight time gets silently truncated.
        start_i = run_start
        while start_i - 1 >= 0 and off_ground[start_i - 1]:
            start_i -= 1
        end_i = run_end
        while end_i + 1 < len(series) and off_ground[end_i + 1]:
            end_i += 1

        # Reject runs clipped by the video edges — takeoff/landing not observed.
        if start_i <= 0 or end_i >= len(series) - 1:
            continue

        # Midpoint convention: halves quantization bias vs snapping to a frame.
        takeoff_s = float((series.t_s[start_i - 1] + series.t_s[start_i]) / 2)
        landing_s = float((series.t_s[end_i] + series.t_s[end_i + 1]) / 2)
        flight = landing_s - takeoff_s
        if not (p.min_flight_s <= flight <= p.max_flight_s):
            continue

        # Validate: a real takeoff shows a strong upward hip-velocity peak.
        w = int(round(p.takeoff_vel_window_s / series.dt_s))
        lo, hi = max(0, start_i - w), min(len(series), start_i + w + 1)
        if float(np.max(series.hip_up_vel[lo:hi])) < p.min_takeoff_up_vel:
            continue

        # Refinement can merge with a previously-emitted run; keep the first.
        if events and takeoff_s < events[-1].landing_s:
            continue

        events.append(
            JumpEvent(
                load_start_s=_find_load_start(series, start_i - 1, p),
                takeoff_s=takeoff_s,
                landing_s=landing_s,
            )
        )
    return events
