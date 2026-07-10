"""sideOut command-line interface.

sideout jump analyze <video> [--out runs/] [--model full] [--height-cm 190]
sideout jump report <run-dir>          (Phase 3)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from sideout.jump.analysis import SessionAnalysis

app = typer.Typer(
    help="sideOut — local-first volleyball performance analysis.", no_args_is_help=True
)
jump_app = typer.Typer(
    help="Jump Lab: analyze attack approaches from side-view video.", no_args_is_help=True
)
app.add_typer(jump_app, name="jump")


@jump_app.command("analyze")
def analyze(
    video: Path = typer.Argument(..., help="Path to a side-view video (referenced, never copied)."),
    out: Path = typer.Option(Path("runs"), "--out", help="Root directory for run outputs."),
    model: str = typer.Option("full", "--model", help="Pose model variant: lite | full | heavy."),
    height_cm: float | None = typer.Option(
        None,
        "--height-cm",
        help="Athlete standing height in cm; enables meter-scaled metrics.",
    ),
    reach_cm: float | None = typer.Option(
        None,
        "--reach-cm",
        help="Athlete flat-footed standing reach in cm; enables touch height.",
    ),
) -> None:
    """Extract pose, detect jumps, and write metrics + charts + annotated video.

    The one command: VIDEO in, a full run directory out.
    """
    from sideout.jump.analysis import analyze_run
    from sideout.jump.report import render_report
    from sideout.pose.extractor import extract_keypoints, save_run, summarize_keypoints
    from sideout.viz.overlay import render_overlay

    typer.echo(f"Analyzing {video} (model={model}) ...")
    df, meta = extract_keypoints(video, model_variant=model)
    run_dir = save_run(df, meta, out_root=out)
    summary = summarize_keypoints(df)

    typer.echo(f"\nRun saved: {run_dir}")
    typer.echo(f"  frames processed   : {meta.n_frames_processed}")
    typer.echo(f"  frames w/ detection: {meta.n_frames_detected} ({summary['detection_rate']:.1%})")
    fps_str = f"{meta.measured_fps:.2f} (measured)" if meta.measured_fps else "n/a"
    typer.echo(f"  fps                : nominal {meta.nominal_fps:.2f} | {fps_str}")
    typer.echo(f"  timestamps         : {meta.timestamp_source}")
    typer.echo(f"  rotation metadata  : {meta.rotation_meta_deg:.0f}°")
    typer.echo(
        f"  mean visibility    : ankles {summary['mean_visibility_ankles']:.2f} | "
        f"hips {summary['mean_visibility_hips']:.2f} | "
        f"wrists {summary['mean_visibility_wrists']:.2f}"
    )

    analysis = analyze_run(df, height_cm=height_cm, standing_reach_cm=reach_cm)
    render_report(analysis, run_dir)
    overlay_path = render_overlay(meta.video_path, df, analysis.jumps, run_dir / "overlay.mp4")

    _print_jump_summary(analysis, overlay_path, height_cm)


@jump_app.command("report")
def report(
    run_dir: Path = typer.Argument(..., help="A run directory from `sideout jump analyze`."),
    height_cm: float | None = typer.Option(
        None, "--height-cm", help="Athlete standing height in cm for meter-scaled metrics."
    ),
    reach_cm: float | None = typer.Option(
        None, "--reach-cm", help="Athlete flat-footed standing reach in cm for touch height."
    ),
) -> None:
    """Regenerate metrics.json + charts from a run's parquet (no pose re-run)."""
    from sideout.jump.report import write_report

    written = write_report(run_dir, height_cm=height_cm, standing_reach_cm=reach_cm)
    typer.echo(f"Wrote {written['metrics']}")
    for key in ("chart_heights", "chart_metrics_vs_height"):
        if key in written:
            typer.echo(f"Wrote {written[key]}")


def _print_jump_summary(
    analysis: SessionAnalysis, overlay_path: Path, height_cm: float | None
) -> None:
    """Human-readable summary of detected jumps after an analyze run."""
    typer.echo(f"\n  jumps detected     : {analysis.n_jumps}")
    for j in analysis.jumps:
        parts = [f"#{j.index + 1}", f"height {j.jump_height_m:.2f} m"]
        if j.touch_height_m is not None:
            parts.append(f"touch {j.touch_height_m:.2f} m")
        if j.countermovement_depth_m is not None:
            parts.append(f"depth {j.countermovement_depth_m:.2f} m")
        if j.approach_velocity_m_s is not None:
            parts.append(f"approach {j.approach_velocity_m_s:.1f} m/s")
        typer.echo("    " + " | ".join(parts))
    if analysis.n_jumps and not analysis.calibrated:
        typer.echo("  (pass --height-cm for depth in meters and approach velocity)")
    typer.echo(f"  overlay video      : {overlay_path}")


if __name__ == "__main__":
    app()
