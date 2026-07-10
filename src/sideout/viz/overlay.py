"""Annotated output video: skeleton + event flags + live metric readout.

Reads the original video (path only — never copied), draws the tracked skeleton
on each frame, flags LOAD / TAKEOFF / LANDING at the detected moments, and shows
each jump's metrics once it has landed. Writes an ``.mp4``.

Frame alignment: the overlay decodes the video in the same order Phase 1 did,
so video frame ``i`` matches keypoints row ``frame == i``. Event *times*
(seconds) are mapped back to frame indices via the per-frame ``t_ms``.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from sideout.jump.analysis import JumpMetrics
from sideout.pose.landmarks import Landmark

# Skeleton edges to draw (subset of BlazePose that reads clearly for a jump).
POSE_CONNECTIONS: list[tuple[int, int]] = [
    (Landmark.LEFT_SHOULDER, Landmark.RIGHT_SHOULDER),
    (Landmark.LEFT_SHOULDER, Landmark.LEFT_ELBOW),
    (Landmark.LEFT_ELBOW, Landmark.LEFT_WRIST),
    (Landmark.RIGHT_SHOULDER, Landmark.RIGHT_ELBOW),
    (Landmark.RIGHT_ELBOW, Landmark.RIGHT_WRIST),
    (Landmark.LEFT_SHOULDER, Landmark.LEFT_HIP),
    (Landmark.RIGHT_SHOULDER, Landmark.RIGHT_HIP),
    (Landmark.LEFT_HIP, Landmark.RIGHT_HIP),
    (Landmark.LEFT_HIP, Landmark.LEFT_KNEE),
    (Landmark.LEFT_KNEE, Landmark.LEFT_ANKLE),
    (Landmark.LEFT_ANKLE, Landmark.LEFT_FOOT_INDEX),
    (Landmark.RIGHT_HIP, Landmark.RIGHT_KNEE),
    (Landmark.RIGHT_KNEE, Landmark.RIGHT_ANKLE),
    (Landmark.RIGHT_ANKLE, Landmark.RIGHT_FOOT_INDEX),
]

_FLAG_COLORS = {  # BGR
    "LOAD": (0, 200, 255),  # amber
    "TAKEOFF": (0, 220, 0),  # green
    "LANDING": (0, 120, 255),  # orange
}
_VIS_THRESHOLD = 0.3  # don't draw joints the model was unsure about
_FLAG_HOLD_S = 0.25  # how long a flag stays on screen after its instant


def time_to_frame(t_s: float, frame_t_ms: np.ndarray) -> int:
    """Index of the frame whose timestamp is closest to ``t_s`` seconds."""
    return int(np.argmin(np.abs(frame_t_ms - t_s * 1000.0)))


def _draw_skeleton(frame: np.ndarray, xy_vis: dict[int, tuple[int, int, float]]) -> None:
    """Draw connections + joints for one frame's landmarks (skips low-visibility)."""
    for a, b in POSE_CONNECTIONS:
        pa, pb = xy_vis.get(int(a)), xy_vis.get(int(b))
        if pa and pb and pa[2] >= _VIS_THRESHOLD and pb[2] >= _VIS_THRESHOLD:
            cv2.line(frame, (pa[0], pa[1]), (pb[0], pb[1]), (255, 255, 255), 2)
    for x, y, vis in xy_vis.values():
        if vis >= _VIS_THRESHOLD:
            cv2.circle(frame, (x, y), 3, (60, 220, 255), -1)


def _frame_landmarks(frame_df: pd.DataFrame, w: int, h: int) -> dict[int, tuple[int, int, float]]:
    """Map one frame's rows to {landmark_id: (px, py, visibility)}, dropping NaNs."""
    out: dict[int, tuple[int, int, float]] = {}
    for lid, x, y, vis in zip(
        frame_df["landmark_id"], frame_df["x"], frame_df["y"], frame_df["visibility"], strict=True
    ):
        if not (np.isnan(x) or np.isnan(y)):
            out[int(lid)] = (int(x * w), int(y * h), float(vis))
    return out


def _flags_by_frame(jumps: list[JumpMetrics], frame_t_ms: np.ndarray) -> dict[int, str]:
    """{frame_index: flag_label} for each jump's LOAD/TAKEOFF/LANDING instant."""
    flags: dict[int, str] = {}
    for j in jumps:
        if j.loading_time_s is not None:
            load_s = j.takeoff_s - j.loading_time_s
            flags[time_to_frame(load_s, frame_t_ms)] = "LOAD"
        flags[time_to_frame(j.takeoff_s, frame_t_ms)] = "TAKEOFF"
        flags[time_to_frame(j.landing_s, frame_t_ms)] = "LANDING"
    return flags


def _readout_lines(j: JumpMetrics) -> list[str]:
    """Human-readable metric lines shown after a jump lands."""
    lines = [f"Jump #{j.index + 1}", f"height {j.jump_height_m:.2f} m"]
    if j.countermovement_depth_m is not None:
        lines.append(f"depth  {j.countermovement_depth_m:.2f} m")
    if j.approach_velocity_m_s is not None:
        lines.append(f"approach {j.approach_velocity_m_s:.1f} m/s")
    lines.append(f"arm lead {j.arm_swing_timing_s:.2f} s")
    return lines


def render_overlay(
    video_path: str | Path,
    df: pd.DataFrame,
    jumps: list[JumpMetrics],
    out_path: str | Path,
) -> Path:
    """Render an annotated ``.mp4`` for ``video_path`` and return its path."""
    video_path, out_path = Path(video_path), Path(out_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)  # match Phase 1 frame orientation

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0

    frame_t_ms = df.groupby("frame")["t_ms"].first().to_numpy(dtype=float)
    flags = _flags_by_frame(jumps, frame_t_ms)
    flag_hold_frames = max(1, int(round(_FLAG_HOLD_S * fps)))
    # Which jump's readout to show at each frame (its landing onward).
    landing_frame = {time_to_frame(j.landing_s, frame_t_ms): j for j in jumps}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    active_flag: tuple[str, int] | None = None  # (label, frames_remaining)
    current_readout: JumpMetrics | None = None
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            rows = df[df["frame"] == frame_idx]
            _draw_skeleton(frame, _frame_landmarks(rows, w, h))

            if frame_idx in flags:
                active_flag = (flags[frame_idx], flag_hold_frames)
            if frame_idx in landing_frame:
                current_readout = landing_frame[frame_idx]

            if active_flag:
                label, remaining = active_flag
                _draw_banner(frame, label, _FLAG_COLORS[label])
                active_flag = (label, remaining - 1) if remaining > 1 else None
            if current_readout is not None:
                _draw_readout(frame, _readout_lines(current_readout))

            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()
    return out_path


def _draw_banner(frame: np.ndarray, label: str, color: tuple[int, int, int]) -> None:
    """Big centered event flag near the top of the frame."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (w // 2 - 110, 20), (w // 2 + 110, 70), color, -1)
    cv2.putText(
        frame, label, (w // 2 - 95, 57), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 3, cv2.LINE_AA
    )


def _draw_readout(frame: np.ndarray, lines: list[str]) -> None:
    """Metric readout box in the top-left corner."""
    cv2.rectangle(frame, (10, 10), (250, 20 + 26 * len(lines)), (30, 30, 30), -1)
    for i, line in enumerate(lines):
        cv2.putText(
            frame,
            line,
            (20, 38 + 26 * i),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )
