"""Video → keypoint time-series.

Runs MediaPipe PoseLandmarker (Tasks API, VIDEO mode) frame-by-frame over a
video file and produces a long-format DataFrame:

    frame, t_ms, landmark_id, x, y, z, visibility, world_x, world_y, world_z

- ``x, y, z``: normalized image coordinates (x, y in [0, 1]; image y grows
  DOWNWARD). ``z`` is MediaPipe's relative depth (hip-centered, roughly
  image-width scaled) — treat with caution, monocular.
- ``world_x/y/z``: MediaPipe world landmarks in METERS, origin at hip center.
  NOTE: world **y also grows DOWNWARD** (same as image y, verified
  empirically: nose ≈ −0.58 m, ankles ≈ +0.61 m) — not the physics
  y-up convention the word "world" might suggest.
- ``t_ms``: real frame timestamp in milliseconds from the container, never an
  assumed fps. Isolated missing timestamps are interpolated from container
  neighbors; only when the container yields no usable timeline at all does the
  whole video fall back to ``frame_index * 1000 / nominal_fps`` (all-or-nothing
  so timebases are never mixed; both cases recorded in metadata).
- Frames where no person is detected produce gap rows (NaN coords,
  visibility 0.0) so downstream code sees explicit gaps and never crashes on
  missing frames.
"""

from __future__ import annotations

import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from sideout.pose.landmarks import ANKLES, HIPS, N_LANDMARKS, WRISTS

# Official MediaPipe model bundles. "full" balances accuracy vs speed for
# full-body sports video; "lite" is faster, "heavy" more accurate.
MODEL_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}


# Model weights live in a stable per-user cache, not the process CWD — running
# `sideout` from another directory must not scatter 9 MB downloads around.
# Overridable via the SIDEOUT_MODEL_DIR environment variable or the
# ``model_dir`` parameter.
def default_model_dir() -> Path:
    env = os.environ.get("SIDEOUT_MODEL_DIR")
    return Path(env) if env else Path.home() / ".cache" / "sideout" / "models"


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
class ExtractionMeta:
    """Provenance and quality metadata for one extraction run."""

    video_path: str
    frame_width: int
    frame_height: int
    nominal_fps: float
    measured_fps: float | None
    n_frames_processed: int
    n_frames_detected: int
    timestamp_source: str  # "container" | "container_interpolated" | "nominal_fps_fallback"
    rotation_meta_deg: float
    model_variant: str
    extra: dict[str, Any] = field(default_factory=dict)


def ensure_model(variant: str = "full", model_dir: Path | None = None) -> Path:
    """Return the local path to the PoseLandmarker model, downloading it if absent.

    Downloads to a temp file and atomically renames into place, so an
    interrupted download can never leave a corrupt model that later runs
    silently reuse.
    """
    if variant not in MODEL_URLS:
        raise ValueError(f"unknown model variant {variant!r}; choose from {sorted(MODEL_URLS)}")
    model_dir = model_dir if model_dir is not None else default_model_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"pose_landmarker_{variant}.task"
    if not path.exists():
        tmp = path.with_suffix(".task.download")
        try:
            urllib.request.urlretrieve(MODEL_URLS[variant], tmp)  # noqa: S310 (fixed https URL)
            tmp.replace(path)  # atomic on the same filesystem
        finally:
            tmp.unlink(missing_ok=True)
    return path


def result_to_rows(
    frame_idx: int, t_ms: float, result: Any
) -> list[tuple[int, float, int, float, float, float, float, float, float, float]]:
    """Convert one PoseLandmarkerResult into long-format rows.

    Emits exactly ``N_LANDMARKS`` rows per frame. If no pose was detected,
    emits gap rows: NaN coordinates with visibility 0.0.
    """
    if result is not None and result.pose_landmarks:
        norm = result.pose_landmarks[0]  # single-athlete assumption (num_poses=1)
        world = result.pose_world_landmarks[0]
        return [
            (
                frame_idx,
                t_ms,
                i,
                lm.x,
                lm.y,
                lm.z,
                lm.visibility,
                world[i].x,
                world[i].y,
                world[i].z,
            )
            for i, lm in enumerate(norm)
        ]
    nan = float("nan")
    return [(frame_idx, t_ms, i, nan, nan, nan, 0.0, nan, nan, nan) for i in range(N_LANDMARKS)]


def summarize_keypoints(df: pd.DataFrame) -> dict[str, float]:
    """Summary statistics for an extraction: detection rate and mean visibility
    of the joints the jump pipeline depends on (ankles, hips, wrists)."""
    n_frames = int(df["frame"].nunique())
    detected = int(df.groupby("frame")["visibility"].max().gt(0).sum())

    def mean_vis(ids: tuple[int, ...]) -> float:
        sub = df[df["landmark_id"].isin([int(i) for i in ids])]
        return float(sub["visibility"].mean()) if len(sub) else float("nan")

    return {
        "n_frames": float(n_frames),
        "n_frames_detected": float(detected),
        "detection_rate": detected / n_frames if n_frames else float("nan"),
        "mean_visibility_ankles": mean_vis(ANKLES),
        "mean_visibility_hips": mean_vis(HIPS),
        "mean_visibility_wrists": mean_vis(WRISTS),
    }


def measured_fps_from_timestamps(t_ms: np.ndarray) -> float | None:
    """Median-based fps estimate from real frame timestamps (robust to jitter).

    Returns None if there are too few frames or degenerate timestamps.
    """
    if len(t_ms) < 2:
        return None
    diffs = np.diff(np.asarray(t_ms, dtype=float))
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return None
    return float(1000.0 / np.median(diffs))


def extract_keypoints(
    video_path: str | Path,
    model_variant: str = "full",
    model_dir: Path | None = None,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
) -> tuple[pd.DataFrame, ExtractionMeta]:
    """Run PoseLandmarker (VIDEO mode) over every frame of ``video_path``.

    Returns (keypoints DataFrame in ``KEYPOINT_COLUMNS`` schema, metadata).
    Uses real container timestamps; auto-applies phone rotation metadata.
    """
    # Import here so the rest of the module (pure helpers) is testable without
    # loading MediaPipe's native libraries.
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"video not found: {video_path}")

    model_path = ensure_model(model_variant, model_dir)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    # Phone videos carry rotation metadata; ask OpenCV to apply it so frames
    # arrive upright. (ORIENTATION_AUTO defaults on in modern builds; be explicit.)
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    rotation_meta = float(cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0.0)
    nominal_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    options = vision.PoseLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=min_detection_confidence,
        min_tracking_confidence=min_tracking_confidence,
    )

    rows: list[tuple] = []
    raw_t_ms: list[float] = []  # NaN where the container gave no usable timestamp
    prev_mp_ts = -1
    frame_idx = 0
    detected = 0

    try:
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame_bgr = cap.read()
                if not ok:
                    break
                # Real presentation timestamp of the decoded frame (ms). Never
                # assume a fixed fps — phone videos are variable-frame-rate.
                # The FFmpeg backend reports 0 for frames with a missing pts;
                # record NaN and repair after the loop (all-or-nothing — a
                # per-frame fallback would mix timebases in one column).
                pos = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                usable = pos > 0.0 or frame_idx == 0
                raw_t_ms.append(pos if usable else float("nan"))

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

                # MediaPipe VIDEO mode requires strictly increasing integer ms.
                # (This provisional value never enters the saved data.)
                mp_ts = max(int(round(pos)) if usable else 0, prev_mp_ts + 1)
                prev_mp_ts = mp_ts

                result = landmarker.detect_for_video(mp_image, mp_ts)
                if result.pose_landmarks:
                    detected += 1
                rows.extend(result_to_rows(frame_idx, 0.0, result))  # t_ms filled below
                frame_idx += 1
    finally:
        cap.release()

    t_ms, timestamp_source, n_repaired = _repair_timestamps(
        np.array(raw_t_ms), nominal_fps, video_path
    )

    df = pd.DataFrame(rows, columns=KEYPOINT_COLUMNS)
    df["t_ms"] = df["frame"].map(dict(enumerate(t_ms))).astype(float)
    meta = ExtractionMeta(
        video_path=str(video_path),
        frame_width=frame_width,
        frame_height=frame_height,
        nominal_fps=nominal_fps,
        measured_fps=measured_fps_from_timestamps(t_ms),
        n_frames_processed=frame_idx,
        n_frames_detected=detected,
        timestamp_source=timestamp_source,
        rotation_meta_deg=rotation_meta,
        model_variant=model_variant,
        extra={"n_repaired_timestamps": n_repaired},
    )
    return df, meta


def _repair_timestamps(
    raw_t_ms: np.ndarray, nominal_fps: float, video_path: Path
) -> tuple[np.ndarray, str, int]:
    """Resolve missing container timestamps without mixing timebases.

    Returns ``(t_ms, timestamp_source, n_repaired)``:
    - no gaps → container timestamps untouched
    - isolated gaps → linearly interpolated from container neighbors
      (still the container timebase; count recorded)
    - all missing → nominal-fps timebase for every frame, or ``RuntimeError``
      when the container has no fps either (no time-based physics is
      computable from a clip with no notion of time).
    """
    missing = np.isnan(raw_t_ms)
    if not missing.any():
        return raw_t_ms, "container", 0

    # Fewer than 2 real timestamps ⇒ no usable container timeline at all.
    if (~missing).sum() < 2:
        if nominal_fps <= 0:
            raise RuntimeError(
                f"{video_path}: container provides neither frame timestamps nor fps; "
                "time-based metrics would be meaningless"
            )
        idx = np.arange(len(raw_t_ms), dtype=float)
        return idx * 1000.0 / nominal_fps, "nominal_fps_fallback", int(len(raw_t_ms))

    good = ~missing
    out = raw_t_ms.copy()
    out[missing] = np.interp(np.flatnonzero(missing), np.flatnonzero(good), raw_t_ms[good])
    return out, "container_interpolated", int(missing.sum())


def save_run(
    df: pd.DataFrame,
    meta: ExtractionMeta,
    out_root: Path,
    run_name: str | None = None,
) -> Path:
    """Persist one extraction run: ``<out_root>/<video-stem>-<timestamp>/keypoints.parquet``
    plus a ``run.json`` with provenance metadata. Returns the run directory."""
    import dataclasses
    import json

    stem = Path(meta.video_path).stem
    if run_name is None:
        run_name = f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = out_root / run_name
    # Same stem + same second must not silently overwrite an earlier run.
    suffix = 2
    while run_dir.exists():
        run_dir = out_root / f"{run_name}-{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)
    df.to_parquet(run_dir / "keypoints.parquet", index=False)
    (run_dir / "run.json").write_text(json.dumps(dataclasses.asdict(meta), indent=2))
    return run_dir
