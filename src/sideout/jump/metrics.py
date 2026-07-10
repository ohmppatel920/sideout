"""The biomechanics metrics engine — PURE functions, no I/O.

Every function takes plain arrays/floats and returns floats. Units are stated
in every docstring; every physics formula carries its derivation.

Conventions:
- positions are normalized image units, and image **y grows DOWNWARD**
  (up = decreasing y). Depth/velocity signs below account for this explicitly.
- times are seconds from real frame timestamps.
- meter-scaled metrics need ``m_per_unit`` from :func:`calibration_m_per_unit`
  (athlete standing height). Without it, normalized-unit metrics still work.
"""

from __future__ import annotations

import numpy as np

G_M_S2 = 9.80665  # standard gravity [m/s^2]

# Anthropometric proportions (Drillis & Contini 1966, "Body Segment
# Parameters"): standing eye height ≈ 0.936·stature, ankle (lateral malleolus)
# height ≈ 0.039·stature. The eye→ankle vertical span is therefore ≈ 0.897·stature.
EYE_HEIGHT_RATIO = 0.936
ANKLE_HEIGHT_RATIO = 0.039
EYE_ANKLE_SPAN_RATIO = EYE_HEIGHT_RATIO - ANKLE_HEIGHT_RATIO  # 0.897


def jump_height_m(flight_time_s: float, g_m_s2: float = G_M_S2) -> float:
    """Jump height [m] from flight time [s] — the flight-time method.

    Derivation: projectile leaving and landing at the same level with takeoff
    speed v spends t = 2v/g in the air, so v = g·t/2. Apex height
    h = v²/(2g) = (g·t/2)²/(2g) = g·t²/8.
    Assumes takeoff and landing heights are equal (see limitations in README).
    """
    if flight_time_s < 0:
        raise ValueError(f"flight time must be non-negative, got {flight_time_s}")
    return g_m_s2 * flight_time_s**2 / 8.0


def standing_hip_y(
    hip_y: np.ndarray, t_s: np.ndarray, before_s: float, window_s: float = 0.5
) -> float:
    """Standing hip baseline [normalized units]: median hip_y over the
    ``window_s`` seconds ending at ``before_s`` (typically load_start)."""
    mask = (t_s >= before_s - window_s) & (t_s <= before_s)
    if not mask.any():
        raise ValueError("no samples in the standing-baseline window")
    return float(np.median(hip_y[mask]))


def countermovement_depth_norm(
    hip_y: np.ndarray,
    t_s: np.ndarray,
    load_start_s: float,
    takeoff_s: float,
    standing_hip_y_norm: float,
) -> float:
    """Countermovement depth [normalized units], positive = hips dropped.

    Depth = (lowest hip position during load) − (standing hip position).
    Image y grows DOWNWARD, so the *lowest physical* point is the *maximum*
    image y: depth = max(hip_y[load window]) − standing_hip_y.
    """
    mask = (t_s >= load_start_s) & (t_s <= takeoff_s)
    if not mask.any():
        raise ValueError("no samples between load_start and takeoff")
    return float(np.max(hip_y[mask]) - standing_hip_y_norm)


def countermovement_depth_m(depth_norm: float, m_per_unit: float) -> float:
    """Countermovement depth [m]: normalized depth × calibration scale [m/unit]."""
    return depth_norm * m_per_unit


def loading_time_s(load_start_s: float, takeoff_s: float) -> float:
    """Loading duration [s] = takeoff − load_start (real timestamps)."""
    dt = takeoff_s - load_start_s
    if dt < 0:
        raise ValueError("takeoff precedes load_start")
    return dt


def approach_velocity_m_s(
    hip_x: np.ndarray,
    t_s: np.ndarray,
    plant_s: float,
    m_per_unit: float,
    window_s: float = 0.5,
) -> float:
    """Approach speed [m/s]: mean horizontal hip speed over the ``window_s``
    seconds before the plant (load_start approximates the final-step plant).

    v = |Δx| / Δt, with Δx converted from normalized units to meters by
    ``m_per_unit``. Uses the actual timestamps of the window endpoints, not
    the nominal window length. |Δx| is used because approach direction
    (left/right in frame) is irrelevant to speed.
    """
    mask = (t_s >= plant_s - window_s) & (t_s <= plant_s)
    if mask.sum() < 2:
        raise ValueError("fewer than 2 samples in the approach window")
    xw, tw = hip_x[mask], t_s[mask]
    dt = float(tw[-1] - tw[0])
    if dt <= 0:
        raise ValueError("approach window has zero duration")
    return abs(float(xw[-1] - xw[0])) / dt * m_per_unit


def arm_swing_timing_s(
    wrist_y: np.ndarray,
    t_s: np.ndarray,
    takeoff_s: float,
    search_window_s: float = 1.0,
) -> float:
    """Arm-swing timing [s]: how long before takeoff the backswing bottomed out.

    The backswing bottom is the wrists' lowest *physical* point, i.e. their
    *maximum* image y (image y grows downward), within the window before
    takeoff. Returns ``takeoff_s − t_backswing`` (positive = before takeoff).
    """
    mask = (t_s >= takeoff_s - search_window_s) & (t_s <= takeoff_s)
    if not mask.any():
        raise ValueError("no samples in the arm-swing search window")
    tw = t_s[mask]
    t_backswing = float(tw[int(np.argmax(wrist_y[mask]))])
    return takeoff_s - t_backswing


def calibration_m_per_unit(
    eye_y_standing: float, ankle_y_standing: float, height_m: float
) -> float:
    """Calibration scale [meters per normalized image unit] from athlete height.

    The standing eye→ankle vertical span is ≈ 0.897 × stature (Drillis &
    Contini 1966: eye ≈ 0.936·H, ankle ≈ 0.039·H). In image units that span is
    ``ankle_y − eye_y`` (ankles below eyes ⇒ larger y). Therefore:

        m_per_unit = 0.897 · height_m / (ankle_y_standing − eye_y_standing)

    Valid only for an upright athlete roughly perpendicular to the camera.
    """
    span_units = ankle_y_standing - eye_y_standing
    if span_units <= 0:
        raise ValueError("ankle_y must exceed eye_y for an upright athlete (image y grows down)")
    if height_m <= 0:
        raise ValueError(f"height must be positive, got {height_m}")
    return EYE_ANKLE_SPAN_RATIO * height_m / span_units
