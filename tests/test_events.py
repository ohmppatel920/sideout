"""Event detection must recover the ground-truth times fixtures were built from."""

import numpy as np
import pytest

from sideout.jump.events import detect_jumps
from sideout.jump.series import build_series
from tests.fixtures import JumpSpec, synthetic_jump_df

# At 60 fps the grid step is ~16.7 ms; allow a little over one step for
# boundary events, more for load_start (smoothing shifts gentle onsets).
EVENT_TOL_S = 0.030
LOAD_TOL_S = 0.100


def detect(sj):
    return detect_jumps(build_series(sj.df))


class TestSingleJump:
    def test_one_jump_detected(self):
        sj = synthetic_jump_df()
        events = detect(sj)
        assert len(events) == 1

    def test_takeoff_and_landing_times_recovered(self):
        sj = synthetic_jump_df()
        (ev,) = detect(sj)
        spec = sj.jumps[0]
        assert ev.takeoff_s == pytest.approx(spec.t_takeoff_s, abs=EVENT_TOL_S)
        assert ev.landing_s == pytest.approx(spec.t_landing_s, abs=EVENT_TOL_S)

    def test_flight_time_recovered(self):
        sj = synthetic_jump_df(jumps=[JumpSpec(flight_time_s=0.55)])
        (ev,) = detect(sj)
        assert ev.flight_time_s == pytest.approx(0.55, abs=2 * EVENT_TOL_S)

    def test_load_start_recovered(self):
        sj = synthetic_jump_df()
        (ev,) = detect(sj)
        assert ev.load_start_s is not None
        assert ev.load_start_s == pytest.approx(sj.jumps[0].t_load_start_s, abs=LOAD_TOL_S)

    def test_small_flights_parametrized(self):
        # Flight-time sweep: a 0.3 s hop to a 0.7 s bounce all recovered.
        for ft in (0.30, 0.45, 0.60, 0.70):
            sj = synthetic_jump_df(jumps=[JumpSpec(flight_time_s=ft)], duration_s=4.5)
            (ev,) = detect(sj)
            assert ev.flight_time_s == pytest.approx(ft, abs=2 * EVENT_TOL_S), f"ft={ft}"


class TestEdgeCases:
    def test_no_jump_in_clip(self):
        sj = synthetic_jump_df(jumps=[])
        assert detect(sj) == []

    def test_two_jumps_detected_in_order(self):
        jumps = [
            JumpSpec(t_load_start_s=1.5, flight_time_s=0.45),
            JumpSpec(t_load_start_s=4.5, flight_time_s=0.60),
        ]
        sj = synthetic_jump_df(jumps=jumps, duration_s=7.0)
        events = detect(sj)
        assert len(events) == 2
        assert events[0].takeoff_s < events[1].takeoff_s
        assert events[0].flight_time_s == pytest.approx(0.45, abs=2 * EVENT_TOL_S)
        assert events[1].flight_time_s == pytest.approx(0.60, abs=2 * EVENT_TOL_S)

    def test_missing_frames_mid_flight(self):
        sj = synthetic_jump_df()
        spec = sj.jumps[0]
        # Drop 4 consecutive frames around the apex of the flight.
        apex_frame = int(round((spec.t_takeoff_s + spec.flight_time_s / 2) * sj.fps))
        sj_gappy = synthetic_jump_df(gap_frames=list(range(apex_frame - 2, apex_frame + 2)))
        (ev,) = detect(sj_gappy)
        assert ev.flight_time_s == pytest.approx(spec.flight_time_s, abs=3 * EVENT_TOL_S)

    def test_noise_robustness(self):
        sj = synthetic_jump_df(noise_std=0.003)
        events = detect(sj)
        assert len(events) == 1
        assert events[0].flight_time_s == pytest.approx(
            sj.jumps[0].flight_time_s, abs=3 * EVENT_TOL_S
        )

    def test_jump_clipped_by_video_end_not_reported(self):
        # Clip ends mid-flight: landing unobserved → no event.
        spec = JumpSpec(t_load_start_s=1.5, flight_time_s=0.6)
        sj = synthetic_jump_df(jumps=[spec], duration_s=spec.t_takeoff_s + 0.3)
        assert detect(sj) == []


class TestSeries:
    def test_series_uses_real_timestamps(self):
        sj = synthetic_jump_df(fps=48.0)  # not 30, not 60
        s = build_series(sj.df)
        assert s.dt_s == pytest.approx(1 / 48.0, rel=1e-6)

    def test_hip_up_vel_sign_convention(self):
        # During flight ascent the hips move up ⇒ image y decreases ⇒ up_vel > 0.
        sj = synthetic_jump_df()
        s = build_series(sj.df)
        spec = sj.jumps[0]
        i = np.searchsorted(s.t_s, spec.t_takeoff_s + 0.05)
        assert s.hip_up_vel[i] > 0

    def test_too_few_detected_frames_raises(self):
        sj = synthetic_jump_df(duration_s=0.5, fps=10)
        gappy = synthetic_jump_df(duration_s=0.5, fps=10, gap_frames=list(range(1, 5)))
        assert len(gappy.df) == len(sj.df)  # same shape, mostly gaps
        with pytest.raises(ValueError, match="fewer than 2 frames"):
            build_series(gappy.df[gappy.df.frame < 2])
