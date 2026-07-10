"""Keypoint DataFrame → smoothed, uniformly-sampled joint time series.

Everything downstream (events, metrics) consumes a :class:`JumpSeries` —
per-frame traces of the joints the jump pipeline cares about, resampled onto a
uniform time grid and Savitzky–Golay smoothed.

Conventions (repeated everywhere on purpose):
- Coordinates are **normalized image units**: x, y in [0, 1], and image **y
  grows DOWNWARD** — an athlete moving up has *decreasing* y.
- Time is **seconds**, derived from real container timestamps (``t_ms``),
  never an assumed fps. The uniform grid step is the *median* of the observed
  frame intervals, so variable-frame-rate phone video is handled honestly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from sideout.pose.landmarks import ANKLES, HIPS, WRISTS, Landmark

# Landmarks averaged into each trace. Eyes are used for height calibration.
EYES = (Landmark.LEFT_EYE, Landmark.RIGHT_EYE)


@dataclass
class JumpSeries:
    """Uniformly-sampled, smoothed joint traces for one video.

    All positions are normalized image units (y DOWN); all times are seconds.
    ``hip_up_vel`` is the hip's *physical upward* velocity in normalized
    units/second: ``-d(hip_y)/dt`` (negated because image y grows downward).
    """

    t_s: np.ndarray  # uniform time grid [s]
    dt_s: float  # grid step [s] (median real frame interval)
    hip_y: np.ndarray  # mean of both hips, smoothed
    hip_x: np.ndarray
    ankle_y: np.ndarray  # mean of both ankles, smoothed
    wrist_y: np.ndarray  # mean of both wrists, smoothed
    eye_y: np.ndarray  # mean of both eyes, smoothed (calibration)
    hip_up_vel: np.ndarray  # physical up velocity of hips [norm units / s]
    max_gap_s: float  # longest run of missing frames that was interpolated

    def __len__(self) -> int:
        return len(self.t_s)


def _joint_trace(df: pd.DataFrame, ids: tuple[int, ...], coord: str) -> pd.Series:
    """Per-frame mean of ``coord`` over the given landmark ids (NaN where lost)."""
    sub = df[df["landmark_id"].isin([int(i) for i in ids])]
    return sub.groupby("frame")[coord].mean()


def _smooth(x: np.ndarray, window: int, poly: int, deriv: int = 0, dt: float = 1.0) -> np.ndarray:
    """Savitzky–Golay smooth/differentiate; falls back to identity for tiny series."""
    if len(x) < window:
        return x if deriv == 0 else np.asarray(np.gradient(x, dt))
    return np.asarray(savgol_filter(x, window_length=window, polyorder=poly, deriv=deriv, delta=dt))


def build_series(
    df: pd.DataFrame,
    smooth_window_s: float = 0.15,
    smooth_poly: int = 3,
) -> JumpSeries:
    """Build a :class:`JumpSeries` from a long-format keypoints DataFrame.

    Steps:
    1. average left/right joints into per-frame traces (hips, ankles, wrists, eyes)
    2. drop frames where the person was lost (gap rows), remembering the
       largest gap so callers can judge data quality
    3. resample onto a uniform grid (step = median real frame interval) by
       linear interpolation — Savitzky–Golay assumes uniform sampling
    4. smooth positions and differentiate hip y on the same SG window

    Raises ``ValueError`` if fewer than 2 frames carry a detected pose.
    """
    t_by_frame = df.groupby("frame")["t_ms"].first()
    traces = {
        "hip_y": _joint_trace(df, HIPS, "y"),
        "hip_x": _joint_trace(df, HIPS, "x"),
        "ankle_y": _joint_trace(df, ANKLES, "y"),
        "wrist_y": _joint_trace(df, WRISTS, "y"),
        "eye_y": _joint_trace(df, EYES, "y"),
    }

    # Frames with any detection: hip trace is not NaN.
    valid = traces["hip_y"].dropna().index
    if len(valid) < 2:
        raise ValueError("fewer than 2 frames with a detected pose — cannot build series")

    t_valid_s = (t_by_frame.loc[valid] / 1000.0).to_numpy(dtype=float)
    order = np.argsort(t_valid_s)
    t_valid_s = t_valid_s[order]

    # Largest interpolated gap (s) — quality signal for downstream consumers.
    diffs = np.diff(t_valid_s)
    max_gap_s = float(diffs.max()) if len(diffs) else 0.0
    dt_s = float(np.median(diffs[diffs > 0]))

    # Uniform grid over the observed span, from real timestamps.
    t_grid = np.arange(t_valid_s[0], t_valid_s[-1] + dt_s / 2, dt_s)

    def regrid(s: pd.Series) -> np.ndarray:
        vals = s.loc[valid].to_numpy(dtype=float)[order]
        return np.asarray(np.interp(t_grid, t_valid_s, vals))

    window = max(5, int(round(smooth_window_s / dt_s)) | 1)  # odd, >= 5 samples
    hip_y_g = regrid(traces["hip_y"])

    return JumpSeries(
        t_s=t_grid,
        dt_s=dt_s,
        hip_y=_smooth(hip_y_g, window, smooth_poly),
        hip_x=_smooth(regrid(traces["hip_x"]), window, smooth_poly),
        ankle_y=_smooth(regrid(traces["ankle_y"]), window, smooth_poly),
        wrist_y=_smooth(regrid(traces["wrist_y"]), window, smooth_poly),
        eye_y=_smooth(regrid(traces["eye_y"]), window, smooth_poly),
        # Physical up velocity: image y grows downward, so up = -dy/dt.
        hip_up_vel=-_smooth(hip_y_g, window, smooth_poly, deriv=1, dt=dt_s),
        max_gap_s=max_gap_s,
    )
