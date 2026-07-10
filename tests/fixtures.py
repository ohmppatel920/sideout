"""Synthetic keypoint generators with known ground truth.

Builds ideal (optionally noisy/gappy) keypoint DataFrames in the extractor's
long format for a parameterized jump, so tests can assert that events and
metrics recover the ground-truth values they were generated from.

Physical consistency:
- flight is a true ballistic parabola: z(t) = g·t·(T−t)/2, apex g·T²/8
- the countermovement descends by ``depth_m`` and the extension leaves the
  ground with the correct takeoff speed v = g·T/2
- image y grows DOWNWARD: y = baseline − z / m_per_unit_m
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from sideout.jump.metrics import EYE_ANKLE_SPAN_RATIO, G_M_S2
from sideout.pose.landmarks import N_LANDMARKS, Landmark

KEYPOINT_COLUMNS = [
    "frame",
    "t_ms",
    "landmark_id",
    "x",
    "y",
    "z",
    "visibility",
    "world_x",
    "world_y",
    "world_z",
]


@dataclass
class JumpSpec:
    """Parameters for one synthetic jump, all in physical units."""

    t_load_start_s: float = 1.5  # when the countermovement begins
    flight_time_s: float = 0.5  # ballistic flight duration T
    depth_m: float = 0.30  # countermovement depth
    descent_s: float = 0.35  # duration of the hip descent
    approach_v_m_s: float = 2.0  # horizontal speed before the plant
    arm_lead_s: float = 0.25  # backswing bottom occurs this long before takeoff

    @property
    def takeoff_v_m_s(self) -> float:
        # Ballistics: flight T with equal takeoff/landing level ⇒ v = g·T/2.
        return G_M_S2 * self.flight_time_s / 2.0

    @property
    def extension_s(self) -> float:
        # Constant-acceleration extension from rest over depth d ending at
        # speed v: d = v·t/2  ⇒  t = 2d/v.
        return 2.0 * self.depth_m / self.takeoff_v_m_s

    @property
    def t_takeoff_s(self) -> float:
        return self.t_load_start_s + self.descent_s + self.extension_s

    @property
    def t_landing_s(self) -> float:
        return self.t_takeoff_s + self.flight_time_s

    @property
    def loading_time_s(self) -> float:
        return self.t_takeoff_s - self.t_load_start_s

    @property
    def height_m(self) -> float:
        # Flight-time method ground truth: h = g·T²/8.
        return G_M_S2 * self.flight_time_s**2 / 8.0


@dataclass
class SyntheticJump:
    """A generated clip plus every ground-truth quantity tests assert against."""

    df: pd.DataFrame
    jumps: list[JumpSpec]
    fps: float
    height_m_athlete: float  # standing height used for calibration
    m_per_unit: float  # meters per normalized image unit
    standing_hip_y: float  # normalized image y of hips at quiet standing
    ankle_baseline_y: float  # normalized image y of ankles on the ground
    extra: dict = field(default_factory=dict)


def _hip_z_m(t: float, spec: JumpSpec) -> float:
    """Physical hip height above standing level [m] at time t (up positive)."""
    t0, d = spec.t_load_start_s, spec.depth_m
    t_bottom = t0 + spec.descent_s
    t_off, t_land = spec.t_takeoff_s, spec.t_landing_s
    v = spec.takeoff_v_m_s
    if t < t0:
        return 0.0
    if t < t_bottom:  # smooth cosine descent to −d
        phase = (t - t0) / spec.descent_s
        return -d * (1 - np.cos(np.pi * phase)) / 2.0
    if t < t_off:  # constant-acceleration extension: rest at −d → speed v at 0
        # z(τ) = −d + ½aτ², a = v²/(2d) so that z(t_ext) = 0 and ż(t_ext) = v.
        tau = t - t_bottom
        a = v**2 / (2 * d)
        return -d + 0.5 * a * tau**2
    if t < t_land:  # ballistic flight: z(τ) = v·τ − ½g·τ²  (= g·τ(T−τ)/2)
        tau = t - t_off
        return v * tau - 0.5 * G_M_S2 * tau**2
    # landing recovery: brief dip then settle (keeps landing detectable)
    tau = t - t_land
    if tau < 0.25:
        return -0.4 * d * np.sin(np.pi * tau / 0.25)
    return 0.0


def _ankle_z_m(t: float, spec: JumpSpec) -> float:
    """Physical ankle height above ground [m]: airborne only during flight."""
    if spec.t_takeoff_s <= t < spec.t_landing_s:
        tau = t - spec.t_takeoff_s
        return spec.takeoff_v_m_s * tau - 0.5 * G_M_S2 * tau**2
    return 0.0


def _wrist_z_m(t: float, spec: JumpSpec) -> float:
    """Wrist height relative to its neutral carry [m].

    Deliberately independent of hip motion so the wrists' lowest point (max
    image y) lands *exactly* ``arm_lead_s`` before takeoff — an exact ground
    truth for the arm-swing timing metric. A smooth 0 → −0.25 m → 0 backswing
    dip (width 0.6 s) centered on that time, plus an overhead reach in flight.
    """
    t_bottom = spec.t_takeoff_s - spec.arm_lead_s
    out = 0.0
    tau = (t - t_bottom) / 0.3
    if abs(tau) < 1:
        out -= 0.25 * (1 + np.cos(np.pi * tau)) / 2.0  # bottom −0.25 m at tau=0
    if spec.t_takeoff_s <= t < spec.t_landing_s:
        out += 0.5
    return out


def synthetic_jump_df(
    jumps: list[JumpSpec] | None = None,
    fps: float = 60.0,
    duration_s: float = 4.0,
    athlete_height_m: float = 1.90,
    m_per_unit: float = 2.5,  # frame spans 2.5 m vertically at the athlete's plane
    ankle_baseline_y: float = 0.80,
    noise_std: float = 0.0,
    gap_frames: list[int] | None = None,
    start_x: float = 0.2,
    seed: int = 7,
) -> SyntheticJump:
    """Generate a long-format keypoints DataFrame for a clip with known jumps.

    ``jumps=None`` gives one default jump; ``jumps=[]`` gives a no-jump clip
    (quiet standing). ``gap_frames`` simulates the person being lost.
    """
    if jumps is None:
        jumps = [JumpSpec()]
    rng = np.random.default_rng(seed)
    n_frames = int(round(duration_s * fps))
    t_s = np.arange(n_frames) / fps

    # Standing geometry in image units (y DOWN). Hip ≈ 0.530·H above ground
    # (Drillis & Contini), eye−ankle span = 0.897·H.
    hip_height_m = 0.530 * athlete_height_m
    standing_hip_y = ankle_baseline_y - hip_height_m / m_per_unit
    eye_y_standing = ankle_baseline_y - EYE_ANKLE_SPAN_RATIO * athlete_height_m / m_per_unit

    def active_spec(t: float) -> JumpSpec | None:
        for s in jumps:
            if s.t_load_start_s - 1.0 <= t <= s.t_landing_s + 0.4:
                return s
        return None

    # Horizontal approach: for each jump, constant speed over the ~0.9 s
    # before its plant, standing still otherwise. Built as a piecewise
    # velocity profile integrated to position, so multiple jumps compose and
    # the 0.5 s window before each plant has exactly the ground-truth speed.
    vx = np.zeros(n_frames)
    vx_units = 0.0
    for spec in jumps:
        vx_units = spec.approach_v_m_s / m_per_unit
        approach = (t_s >= spec.t_load_start_s - 0.9) & (t_s <= spec.t_load_start_s)
        vx[approach] = vx_units
    x = start_x + np.concatenate(([0.0], np.cumsum(vx[:-1] + vx[1:]) / 2.0)) / fps

    rows: list[tuple] = []
    gap_set = set(gap_frames or [])
    for i, t in enumerate(t_s):
        t_ms = float(t * 1000.0)
        if i in gap_set:
            nan = float("nan")
            rows.extend(
                (i, t_ms, lid, nan, nan, nan, 0.0, nan, nan, nan) for lid in range(N_LANDMARKS)
            )
            continue

        spec = active_spec(t)
        hip_z = _hip_z_m(t, spec) if spec else 0.0
        ankle_z = _ankle_z_m(t, spec) if spec else 0.0
        wrist_z = _wrist_z_m(t, spec) if spec else 0.0

        hip_y = standing_hip_y - hip_z / m_per_unit
        ankle_y = ankle_baseline_y - ankle_z / m_per_unit
        eye_y = eye_y_standing - hip_z / m_per_unit  # head rides on the hips
        # Wrists sit just above the STANDING hip line; the backswing dip and
        # flight reach come entirely from wrist_z, which is deliberately
        # independent of hip motion so the backswing bottom stays an exact
        # ground truth for the arm-swing-timing metric.
        wrist_y = standing_hip_y - 0.05 - wrist_z / m_per_unit

        # Positions per landmark id; anything not modeled tracks the hips.
        y_by_id: dict[int, float] = dict.fromkeys(range(N_LANDMARKS), hip_y)
        for lid in (Landmark.LEFT_HIP, Landmark.RIGHT_HIP):
            y_by_id[lid] = hip_y
        for lid in (Landmark.LEFT_ANKLE, Landmark.RIGHT_ANKLE):
            y_by_id[lid] = ankle_y
        for lid in (Landmark.LEFT_WRIST, Landmark.RIGHT_WRIST):
            y_by_id[lid] = wrist_y
        for lid in (Landmark.LEFT_EYE, Landmark.RIGHT_EYE):
            y_by_id[lid] = eye_y

        for lid in range(N_LANDMARKS):
            y = y_by_id[lid] + (rng.normal(0, noise_std) if noise_std else 0.0)
            xx = x[i] + (rng.normal(0, noise_std) if noise_std else 0.0)
            rows.append((i, t_ms, lid, xx, y, 0.0, 0.95, 0.0, 0.0, 0.0))

    df = pd.DataFrame(rows, columns=KEYPOINT_COLUMNS)
    return SyntheticJump(
        df=df,
        jumps=jumps,
        fps=fps,
        height_m_athlete=athlete_height_m,
        m_per_unit=m_per_unit,
        standing_hip_y=standing_hip_y,
        ankle_baseline_y=ankle_baseline_y,
        extra={"eye_y_standing": eye_y_standing, "approach_vx_units": vx_units},
    )
