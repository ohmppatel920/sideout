"""Unit tests for the pure helpers in pose/extractor.py (no MediaPipe needed)."""

import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sideout.pose.extractor import (
    KEYPOINT_COLUMNS,
    ExtractionMeta,
    _repair_timestamps,
    measured_fps_from_timestamps,
    result_to_rows,
    save_run,
    summarize_keypoints,
)
from sideout.pose.landmarks import N_LANDMARKS


def fake_result(x: float = 0.5, y: float = 0.5, visibility: float | None = None):
    """Duck-typed stand-in for a PoseLandmarkerResult with one detected pose.

    By default each landmark gets a DISTINCT visibility (id/100) so tests can
    detect wrong joint-group ID selection — uniform visibility would let a
    swapped ankle/wrist mapping pass unnoticed.
    """
    lm = [
        SimpleNamespace(
            x=x, y=y, z=0.0, visibility=visibility if visibility is not None else i / 100
        )
        for i in range(N_LANDMARKS)
    ]
    world = [SimpleNamespace(x=0.1, y=-0.2, z=0.05) for _ in range(N_LANDMARKS)]
    return SimpleNamespace(pose_landmarks=[lm], pose_world_landmarks=[world])


def empty_result():
    """Frame where no person was detected."""
    return SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[])


class TestResultToRows:
    def test_detected_frame_yields_one_row_per_landmark(self):
        rows = result_to_rows(7, 116.7, fake_result())
        assert len(rows) == N_LANDMARKS
        frame, t_ms, lid, x, y, z, vis, wx, wy, wz = rows[0]
        assert frame == 7
        assert t_ms == 116.7
        assert lid == 0
        assert (x, y) == (0.5, 0.5)
        assert vis == 0.0  # landmark 0's distinct visibility (id/100)
        assert rows[28][6] == pytest.approx(0.28)  # RIGHT_ANKLE keeps its own
        assert (wx, wy, wz) == (0.1, -0.2, 0.05)
        # landmark ids are 0..32 in order
        assert [r[2] for r in rows] == list(range(N_LANDMARKS))

    def test_missing_person_yields_gap_rows_not_crash(self):
        rows = result_to_rows(3, 50.0, empty_result())
        assert len(rows) == N_LANDMARKS
        for _, t_ms, _, x, y, z, vis, wx, wy, wz in rows:
            assert t_ms == 50.0
            assert math.isnan(x) and math.isnan(y) and math.isnan(z)
            assert vis == 0.0
            assert math.isnan(wx) and math.isnan(wy) and math.isnan(wz)

    def test_none_result_treated_as_gap(self):
        rows = result_to_rows(0, 0.0, None)
        assert len(rows) == N_LANDMARKS
        assert all(r[6] == 0.0 for r in rows)


class TestSummarize:
    def _df(self, rows):
        return pd.DataFrame(rows, columns=KEYPOINT_COLUMNS)

    def test_detection_rate_counts_gap_frames(self):
        rows = result_to_rows(0, 0.0, fake_result()) + result_to_rows(1, 33.3, empty_result())
        s = summarize_keypoints(self._df(rows))
        assert s["n_frames"] == 2
        assert s["n_frames_detected"] == 1
        assert s["detection_rate"] == 0.5

    def test_mean_visibility_of_key_joints(self):
        # Distinct per-landmark visibilities (id/100) pin the ID→group mapping:
        # ankles = (27+28)/2, hips = (23+24)/2, wrists = (15+16)/2, all /100.
        rows = result_to_rows(0, 0.0, fake_result())
        s = summarize_keypoints(self._df(rows))
        assert s["mean_visibility_ankles"] == pytest.approx(0.275)
        assert s["mean_visibility_hips"] == pytest.approx(0.235)
        assert s["mean_visibility_wrists"] == pytest.approx(0.155)


class TestMeasuredFps:
    def test_regular_timestamps(self):
        t = np.arange(0, 1000, 1000 / 60.0)  # 60 fps
        assert measured_fps_from_timestamps(t) == pytest.approx(60.0, rel=1e-6)

    def test_jittery_timestamps_use_median(self):
        # 30 fps with one dropped frame (66.7 ms gap) — median unaffected.
        t = np.array([0.0, 33.3, 66.7, 133.3, 166.7, 200.0])
        assert measured_fps_from_timestamps(t) == pytest.approx(30.0, rel=0.02)

    def test_degenerate_cases(self):
        assert measured_fps_from_timestamps(np.array([])) is None
        assert measured_fps_from_timestamps(np.array([5.0])) is None
        assert measured_fps_from_timestamps(np.array([10.0, 10.0, 10.0])) is None


class TestRepairTimestamps:
    def test_clean_container_timestamps_untouched(self):
        t = np.array([0.0, 16.7, 33.3, 50.0])
        out, source, n = _repair_timestamps(t, 60.0, Path("v.mov"))
        np.testing.assert_array_equal(out, t)
        assert source == "container"
        assert n == 0

    def test_isolated_gap_interpolated_from_container_neighbors(self):
        # One mid-stream frame with missing pts must NOT get a foreign
        # nominal-fps timebase — it is interpolated from its neighbors.
        t = np.array([0.0, 16.0, np.nan, 48.0, 64.0])
        out, source, n = _repair_timestamps(t, 30.0, Path("v.mov"))  # wrong nominal on purpose
        assert out[2] == pytest.approx(32.0)  # neighbor interpolation, not 2*1000/30
        assert np.all(np.diff(out) > 0)  # monotonic
        assert source == "container_interpolated"
        assert n == 1

    def test_all_missing_falls_back_to_nominal_fps(self):
        t = np.array([np.nan] * 5)
        out, source, n = _repair_timestamps(t, 50.0, Path("v.mov"))
        np.testing.assert_allclose(out, [0.0, 20.0, 40.0, 60.0, 80.0])
        assert source == "nominal_fps_fallback"
        assert n == 5

    def test_no_timestamps_and_no_fps_raises(self):
        # A frame index is not a time — refuse to fabricate physics.
        with pytest.raises(RuntimeError, match="neither frame timestamps nor fps"):
            _repair_timestamps(np.array([np.nan] * 4), 0.0, Path("v.mov"))


class TestSaveRun:
    def _meta(self, video="clips/demo.mov"):
        return ExtractionMeta(
            video_path=video,
            frame_width=100,
            frame_height=100,
            nominal_fps=60.0,
            measured_fps=60.0,
            n_frames_processed=2,
            n_frames_detected=2,
            timestamp_source="container",
            rotation_meta_deg=0.0,
            model_variant="full",
        )

    def _df(self):
        rows = result_to_rows(0, 0.0, fake_result()) + result_to_rows(1, 16.7, fake_result())
        return pd.DataFrame(rows, columns=KEYPOINT_COLUMNS)

    def test_spec_layout_stem_timestamp_dir_with_parquet_and_json(self, tmp_path):
        run_dir = save_run(self._df(), self._meta(), out_root=tmp_path)
        # SPEC: runs/<video-stem>-<timestamp>/keypoints.parquet
        assert re.fullmatch(r"demo-\d{8}-\d{6}", run_dir.name)
        assert (run_dir / "keypoints.parquet").exists()
        assert (run_dir / "run.json").exists()
        loaded = pd.read_parquet(run_dir / "keypoints.parquet")
        assert list(loaded.columns) == KEYPOINT_COLUMNS
        assert json.loads((run_dir / "run.json").read_text())["timestamp_source"] == "container"

    def test_same_second_collision_does_not_overwrite(self, tmp_path):
        df, meta = self._df(), self._meta()
        first = save_run(df, meta, out_root=tmp_path, run_name="demo-20260101-120000")
        second = save_run(df, meta, out_root=tmp_path, run_name="demo-20260101-120000")
        assert first != second
        assert first.exists() and second.exists()


class TestCli:
    def test_analyze_prints_summary_without_running_mediapipe(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        import sideout.cli as cli_mod

        rows = result_to_rows(0, 0.0, fake_result()) + result_to_rows(1, 16.7, fake_result())
        df = pd.DataFrame(rows, columns=KEYPOINT_COLUMNS)
        meta = TestSaveRun()._meta(video="demo.mov")

        monkeypatch.setattr("sideout.pose.extractor.extract_keypoints", lambda *a, **k: (df, meta))
        video = tmp_path / "demo.mov"
        video.write_bytes(b"\x00")
        result = CliRunner().invoke(
            cli_mod.app, ["jump", "analyze", str(video), "--out", str(tmp_path / "runs")]
        )
        assert result.exit_code == 0, result.output
        assert "frames processed   : 2" in result.output
        assert "container" in result.output
        # Summary keys must resolve — a renamed key would KeyError here.
        assert "ankles" in result.output and "wrists" in result.output
