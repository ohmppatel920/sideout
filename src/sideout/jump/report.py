"""Write a run's analysis to disk: metrics.json + charts.

Reads a run directory's ``keypoints.parquet`` (produced by Phase 1) and
regenerates outputs *without re-running pose estimation* — fast to iterate on
metrics and charts. Charts use matplotlib's non-interactive Agg backend so this
runs headless (CI, servers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: no display needed
import matplotlib.pyplot as plt  # noqa: E402  (must follow use("Agg"))
import pandas as pd  # noqa: E402

from sideout.jump.analysis import SessionAnalysis, analyze_run  # noqa: E402

# Meter-scaled metrics are only present when the run was height-calibrated.
_SCATTER_METRICS = [
    ("countermovement_depth_m", "Countermovement depth (m)"),
    ("loading_time_s", "Loading time (s)"),
    ("approach_velocity_m_s", "Approach velocity (m/s)"),
    ("arm_swing_timing_s", "Arm-swing lead (s)"),
]


def _height_bar(analysis: SessionAnalysis, out_path: Path) -> None:
    """Per-jump bar chart of jump heights."""
    heights = [j.jump_height_m for j in analysis.jumps]
    positions = list(range(len(analysis.jumps)))
    labels = [f"#{j.index + 1}" for j in analysis.jumps]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(positions, heights, color="#2b7a78")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Jump height (m)")
    ax.set_xlabel("Jump")
    ax.set_title("Jump height per jump")
    for x, h in zip(positions, heights, strict=True):
        ax.text(x, h, f"{h:.2f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _metric_scatter(analysis: SessionAnalysis, out_path: Path) -> None:
    """Grid of scatter plots: each metric vs jump height across the session."""
    heights = [j.jump_height_m for j in analysis.jumps]
    fig, axes = plt.subplots(2, 2, figsize=(9, 7))
    for ax, (key, label) in zip(axes.flat, _SCATTER_METRICS, strict=True):
        ys = [getattr(j, key) for j in analysis.jumps]
        pairs = [(h, y) for h, y in zip(heights, ys, strict=True) if y is not None]
        if pairs:
            xs, yy = zip(*pairs, strict=True)
            ax.scatter(xs, yy, color="#3a86ff")
        else:
            ax.text(0.5, 0.5, "needs --height-cm", ha="center", va="center", fontsize=9)
        ax.set_xlabel("Jump height (m)")
        ax.set_ylabel(label)
    fig.suptitle("Each metric vs jump height")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def render_report(analysis: SessionAnalysis, run_dir: str | Path) -> dict[str, Any]:
    """Write metrics.json + charts for an already-computed analysis.

    Returns a dict of the written file paths (charts omitted when no jump was
    detected).
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Any] = {}
    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(analysis.to_dict(), indent=2))
    written["metrics"] = str(metrics_path)

    if analysis.jumps:
        bar = run_dir / "chart_heights.png"
        scatter = run_dir / "chart_metrics_vs_height.png"
        _height_bar(analysis, bar)
        _metric_scatter(analysis, scatter)
        written["chart_heights"] = str(bar)
        written["chart_metrics_vs_height"] = str(scatter)

    return written


def write_report(run_dir: str | Path, height_cm: float | None = None) -> dict[str, Any]:
    """Analyze ``run_dir/keypoints.parquet`` and write metrics.json + charts.

    Does NOT run pose estimation — reads the existing parquet only.
    """
    run_dir = Path(run_dir)
    parquet = run_dir / "keypoints.parquet"
    if not parquet.exists():
        raise FileNotFoundError(f"no keypoints.parquet in {run_dir}")
    analysis = analyze_run(pd.read_parquet(parquet), height_cm=height_cm)
    return render_report(analysis, run_dir)
