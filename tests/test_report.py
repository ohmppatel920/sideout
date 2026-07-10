"""Report writer: metrics.json + charts from a run directory's parquet."""

import json

import pytest

from sideout.jump.report import write_report
from tests.fixtures import JumpSpec, synthetic_jump_df


def _write_run(tmp_path, sj, name="run"):
    run_dir = tmp_path / name
    run_dir.mkdir()
    sj.df.to_parquet(run_dir / "keypoints.parquet", index=False)
    return run_dir


class TestWriteReport:
    def test_writes_metrics_json_and_charts(self, tmp_path):
        sj = synthetic_jump_df(jumps=[JumpSpec(flight_time_s=0.5)])
        run_dir = _write_run(tmp_path, sj)
        written = write_report(run_dir, height_cm=sj.height_m_athlete * 100)

        assert (run_dir / "metrics.json").exists()
        assert (run_dir / "chart_heights.png").exists()
        assert (run_dir / "chart_metrics_vs_height.png").exists()
        # PNGs are non-trivial files
        assert (run_dir / "chart_heights.png").stat().st_size > 1000

        data = json.loads((run_dir / "metrics.json").read_text())
        assert data["n_jumps"] == 1
        assert data["calibrated"] is True
        assert data["jumps"][0]["jump_height_m"] > 0
        assert set(written) >= {"metrics", "chart_heights", "chart_metrics_vs_height"}

    def test_no_jump_writes_json_but_no_charts(self, tmp_path):
        run_dir = _write_run(tmp_path, synthetic_jump_df(jumps=[]))
        written = write_report(run_dir)
        assert (run_dir / "metrics.json").exists()
        assert not (run_dir / "chart_heights.png").exists()
        assert "chart_heights" not in written
        assert json.loads((run_dir / "metrics.json").read_text())["n_jumps"] == 0

    def test_missing_parquet_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            write_report(tmp_path / "nonexistent")
