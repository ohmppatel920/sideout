"""Analysis orchestration: per-jump metrics + session aggregates from fixtures."""

import pytest

from sideout.jump.analysis import analyze_run
from tests.fixtures import JumpSpec, synthetic_jump_df


class TestCalibratedSingleJump:
    @pytest.fixture()
    def analysis(self):
        sj = synthetic_jump_df(
            jumps=[JumpSpec(flight_time_s=0.5, depth_m=0.30, approach_v_m_s=2.5)]
        )
        return sj, analyze_run(sj.df, height_cm=sj.height_m_athlete * 100)

    def test_one_jump_and_calibrated(self, analysis):
        _, a = analysis
        assert a.n_jumps == 1
        assert a.calibrated is True
        assert a.m_per_unit == pytest.approx(2.5, rel=0.05)

    def test_all_metrics_recovered(self, analysis):
        sj, a = analysis
        spec = sj.jumps[0]
        (j,) = a.jumps
        assert j.jump_height_m == pytest.approx(spec.height_m, abs=0.04)
        assert j.countermovement_depth_m == pytest.approx(spec.depth_m, abs=0.03)
        assert j.loading_time_s == pytest.approx(spec.loading_time_s, abs=0.12)
        assert j.approach_velocity_m_s == pytest.approx(spec.approach_v_m_s, rel=0.12)
        assert j.arm_swing_timing_s == pytest.approx(spec.arm_lead_s, abs=0.06)


class TestUncalibrated:
    def test_meter_metrics_none_but_others_present(self):
        sj = synthetic_jump_df()
        a = analyze_run(sj.df, height_cm=None)
        assert a.calibrated is False
        assert a.m_per_unit is None
        (j,) = a.jumps
        # Flight-time height and normalized depth need no calibration:
        assert j.jump_height_m > 0
        assert j.countermovement_depth_norm is not None and j.countermovement_depth_norm > 0
        # Meter-scaled metrics are None without a height:
        assert j.countermovement_depth_m is None
        assert j.approach_velocity_m_s is None


class TestSession:
    def test_no_jump_clip(self):
        a = analyze_run(synthetic_jump_df(jumps=[]).df)
        assert a.n_jumps == 0
        assert a.jumps == []
        assert a.aggregates == {}

    def test_two_jumps_aggregates(self):
        jumps = [
            JumpSpec(t_load_start_s=1.5, flight_time_s=0.45),
            JumpSpec(t_load_start_s=4.5, flight_time_s=0.60),
        ]
        sj = synthetic_jump_df(jumps=jumps, duration_s=7.0)
        a = analyze_run(sj.df)
        assert a.n_jumps == 2
        # Best height corresponds to the longer flight time.
        assert a.aggregates["best_jump_height_m"] == pytest.approx(
            max(j.jump_height_m for j in a.jumps)
        )
        assert a.aggregates["best_jump_height_m"] > a.aggregates["mean_jump_height_m"]

    def test_to_dict_is_json_shaped(self):
        a = analyze_run(synthetic_jump_df().df)
        d = a.to_dict()
        assert set(d) >= {"n_jumps", "calibrated", "aggregates", "jumps"}
        assert isinstance(d["jumps"], list)
        assert "jump_height_m" in d["jumps"][0]
