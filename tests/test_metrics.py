"""Metrics engine tests: pure functions must recover fixture ground truth."""

import numpy as np
import pytest

from sideout.jump import metrics
from sideout.jump.events import detect_jumps
from sideout.jump.series import build_series
from tests.fixtures import JumpSpec, synthetic_jump_df


class TestJumpHeightFormula:
    def test_known_values(self):
        # h = g·t²/8: exact hand-checked values.
        assert metrics.jump_height_m(0.0) == 0.0
        assert metrics.jump_height_m(0.4) == pytest.approx(9.80665 * 0.16 / 8)  # 0.196 m
        assert metrics.jump_height_m(0.5) == pytest.approx(0.3065, abs=1e-4)
        assert metrics.jump_height_m(0.6) == pytest.approx(0.4413, abs=1e-4)

    def test_negative_flight_time_rejected(self):
        with pytest.raises(ValueError):
            metrics.jump_height_m(-0.1)

    def test_purity_no_state(self):
        # Same input, same output — twice.
        assert metrics.jump_height_m(0.47) == metrics.jump_height_m(0.47)


class TestCalibration:
    def test_recovers_known_scale(self):
        # The fixture builds its standing geometry from an INDEPENDENT 0.897
        # literal (tests/fixtures.TRUE_EYE_ANKLE_SPAN), so this now also catches
        # the metrics constant drifting away from the true body proportion.
        sj = synthetic_jump_df()
        m_per_unit = metrics.calibration_m_per_unit(
            eye_y_standing=sj.extra["eye_y_standing"],
            ankle_y_standing=sj.ankle_baseline_y,
            height_m=sj.height_m_athlete,
        )
        assert m_per_unit == pytest.approx(sj.m_per_unit, rel=1e-6)

    def test_recovers_scale_from_series_extracted_standing_pose(self):
        # Exercises the REAL path: pull standing eye + ankle out of the built
        # series (not fixture constants) and recover the scale. Guards the
        # extraction path AND the anthropometric constant end to end.
        sj = synthetic_jump_df()
        s = build_series(sj.df)
        i = int(np.searchsorted(s.t_s, 0.5))  # quiet standing, before the load
        m_per_unit = metrics.calibration_m_per_unit(
            eye_y_standing=float(s.eye_y[i]),
            ankle_y_standing=float(s.ankle_y[i]),
            height_m=sj.height_m_athlete,
        )
        assert m_per_unit == pytest.approx(sj.m_per_unit, rel=0.03)

    def test_inverted_coordinates_rejected(self):
        # Eyes below ankles in image coords = upside-down input.
        with pytest.raises(ValueError, match="upright"):
            metrics.calibration_m_per_unit(0.9, 0.2, 1.90)

    def test_bad_height_rejected(self):
        with pytest.raises(ValueError):
            metrics.calibration_m_per_unit(0.2, 0.9, 0.0)


class TestEndToEndRecovery:
    """Full pipeline on synthetic data: fixture ground truth in, metrics out."""

    @pytest.fixture()
    def analyzed(self):
        sj = synthetic_jump_df(
            jumps=[JumpSpec(flight_time_s=0.5, depth_m=0.30, approach_v_m_s=2.5)]
        )
        series = build_series(sj.df)
        (event,) = detect_jumps(series)
        return sj, series, event

    def test_jump_height_recovered(self, analyzed):
        sj, _, ev = analyzed
        h = metrics.jump_height_m(ev.flight_time_s)
        assert h == pytest.approx(sj.jumps[0].height_m, abs=0.04)  # ±4 cm

    def test_loading_time_recovered(self, analyzed):
        sj, _, ev = analyzed
        lt = metrics.loading_time_s(ev.load_start_s, ev.takeoff_s)
        assert lt == pytest.approx(sj.jumps[0].loading_time_s, abs=0.12)

    def test_countermovement_depth_recovered(self, analyzed):
        sj, s, ev = analyzed
        standing = metrics.standing_hip_y(s.hip_y, s.t_s, before_s=ev.load_start_s)
        depth_norm = metrics.countermovement_depth_norm(
            s.hip_y, s.t_s, ev.load_start_s, ev.takeoff_s, standing
        )
        depth_m = metrics.countermovement_depth_m(depth_norm, sj.m_per_unit)
        assert depth_norm > 0  # sign: hips DROP ⇒ image y increases
        assert depth_m == pytest.approx(sj.jumps[0].depth_m, abs=0.03)  # ±3 cm

    def test_approach_velocity_recovered(self, analyzed):
        sj, s, ev = analyzed
        v = metrics.approach_velocity_m_s(
            s.hip_x, s.t_s, plant_s=ev.load_start_s, m_per_unit=sj.m_per_unit
        )
        assert v == pytest.approx(sj.jumps[0].approach_v_m_s, rel=0.10)

    def test_arm_swing_timing_recovered(self, analyzed):
        sj, s, ev = analyzed
        lead = metrics.arm_swing_timing_s(s.wrist_y, s.t_s, ev.takeoff_s)
        assert lead == pytest.approx(sj.jumps[0].arm_lead_s, abs=0.06)
        assert lead > 0  # backswing bottoms out BEFORE takeoff

    def test_metrics_do_not_mutate_inputs(self, analyzed):
        _, s, ev = analyzed
        hip_y_before = s.hip_y.copy()
        standing = metrics.standing_hip_y(s.hip_y, s.t_s, before_s=ev.load_start_s)
        metrics.countermovement_depth_norm(s.hip_y, s.t_s, ev.load_start_s, ev.takeoff_s, standing)
        metrics.approach_velocity_m_s(s.hip_x, s.t_s, ev.load_start_s, m_per_unit=2.5)
        np.testing.assert_array_equal(s.hip_y, hip_y_before)


class TestUnscaledStillWorks:
    def test_normalized_metrics_without_height_calibration(self):
        """SPEC: without --height-cm, unscaled metrics are still computed."""
        sj = synthetic_jump_df()
        series = build_series(sj.df)
        (ev,) = detect_jumps(series)
        # Flight-time height needs no calibration at all.
        assert metrics.jump_height_m(ev.flight_time_s) > 0
        # Depth in normalized units needs no calibration either.
        standing = metrics.standing_hip_y(series.hip_y, series.t_s, before_s=ev.load_start_s)
        depth = metrics.countermovement_depth_norm(
            series.hip_y, series.t_s, ev.load_start_s, ev.takeoff_s, standing
        )
        assert depth > 0


class TestErrorHandling:
    def test_empty_windows_raise(self):
        t = np.linspace(0, 1, 30)
        y = np.full(30, 0.5)
        with pytest.raises(ValueError):
            metrics.standing_hip_y(y, t, before_s=-5.0)
        with pytest.raises(ValueError):
            metrics.countermovement_depth_norm(y, t, 5.0, 6.0, 0.5)
        with pytest.raises(ValueError):
            metrics.arm_swing_timing_s(y, t, takeoff_s=-2.0)

    def test_takeoff_before_load_start_rejected(self):
        with pytest.raises(ValueError):
            metrics.loading_time_s(load_start_s=2.0, takeoff_s=1.0)
