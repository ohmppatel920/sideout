"""Overlay: pure helpers + a real render on a tiny synthetic video."""

import cv2
import numpy as np

from sideout.jump.analysis import JumpMetrics
from sideout.pose.landmarks import N_LANDMARKS
from sideout.viz.overlay import (
    POSE_CONNECTIONS,
    _flags_by_frame,
    _frame_landmarks,
    render_overlay,
    time_to_frame,
)
from tests.fixtures import synthetic_jump_df


class TestPureHelpers:
    def test_time_to_frame_picks_nearest(self):
        t_ms = np.array([0.0, 100.0, 200.0, 300.0])
        assert time_to_frame(0.0, t_ms) == 0
        assert time_to_frame(0.19, t_ms) == 2  # 190 ms closest to 200
        assert time_to_frame(0.31, t_ms) == 3

    def test_connections_reference_valid_landmarks(self):
        for a, b in POSE_CONNECTIONS:
            assert 0 <= int(a) < N_LANDMARKS
            assert 0 <= int(b) < N_LANDMARKS

    def test_frame_landmarks_skips_nan(self):
        import pandas as pd

        rows = pd.DataFrame(
            {
                "landmark_id": [0, 1, 2],
                "x": [0.5, np.nan, 0.25],
                "y": [0.5, 0.5, np.nan],
                "visibility": [0.9, 0.9, 0.9],
            }
        )
        pts = _frame_landmarks(rows, w=100, h=200)
        assert set(pts) == {0}  # only the fully-valid landmark survives
        assert pts[0] == (50, 100, 0.9)

    def test_flags_by_frame_marks_all_three_events(self):
        t_ms = np.arange(0, 1000, 100.0)  # 10 frames, 10 fps
        j = JumpMetrics(
            index=0,
            takeoff_s=0.3,
            landing_s=0.6,
            flight_time_s=0.3,
            jump_height_m=0.11,
            countermovement_depth_norm=0.1,
            countermovement_depth_m=0.25,
            loading_time_s=0.1,
            approach_velocity_m_s=2.4,
            arm_swing_timing_s=0.2,
            touch_height_m=2.4,
        )
        flags = _flags_by_frame([j], t_ms)
        assert flags[time_to_frame(0.2, t_ms)] == "LOAD"  # takeoff - loading_time
        assert flags[time_to_frame(0.3, t_ms)] == "TAKEOFF"
        assert flags[time_to_frame(0.6, t_ms)] == "LANDING"


def _write_dummy_video(path, n_frames, w, h):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (w, h))
    for _ in range(n_frames):
        writer.write(np.zeros((h, w, 3), dtype=np.uint8))
    writer.release()


class TestRender:
    def test_renders_annotated_video(self, tmp_path):
        sj = synthetic_jump_df(duration_s=1.0, fps=10)  # 10 frames, all landmarks present
        video = tmp_path / "clip.avi"
        _write_dummy_video(video, n_frames=10, w=160, h=120)

        j = JumpMetrics(
            index=0,
            takeoff_s=0.3,
            landing_s=0.6,
            flight_time_s=0.3,
            jump_height_m=0.11,
            countermovement_depth_norm=0.1,
            countermovement_depth_m=0.25,
            loading_time_s=0.1,
            approach_velocity_m_s=2.4,
            arm_swing_timing_s=0.2,
            touch_height_m=2.4,
        )
        out = render_overlay(video, sj.df, [j], tmp_path / "overlay.mp4")
        assert out.exists()
        assert out.stat().st_size > 1000  # a real, non-empty video was written

    def test_no_jumps_still_renders(self, tmp_path):
        sj = synthetic_jump_df(duration_s=1.0, fps=10, jumps=[])
        video = tmp_path / "clip.avi"
        _write_dummy_video(video, n_frames=10, w=160, h=120)
        out = render_overlay(video, sj.df, [], tmp_path / "overlay.mp4")
        assert out.exists() and out.stat().st_size > 500
