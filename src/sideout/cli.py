"""sideOut command-line interface.

sideout jump analyze <video> [--out runs/] [--model full] [--height-cm 190]
sideout jump report <run-dir>          (Phase 3)
"""

from __future__ import annotations

from pathlib import Path

import typer

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
        help="Athlete standing height in cm; enables meter-scaled metrics (Phase 2+).",
    ),
) -> None:
    """Extract pose keypoints from VIDEO into a per-run parquet + summary."""
    from sideout.pose.extractor import extract_keypoints, save_run, summarize_keypoints

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
    typer.echo("  mean visibility    : ", nl=False)
    typer.echo(
        f"ankles {summary['mean_visibility_ankles']:.2f} | "
        f"hips {summary['mean_visibility_hips']:.2f} | "
        f"wrists {summary['mean_visibility_wrists']:.2f}"
    )
    if height_cm is not None:
        typer.echo(f"  height calibration : {height_cm:.0f} cm (used by metrics in Phase 2)")


@jump_app.command("report")
def report(
    run_dir: Path = typer.Argument(..., help="A run directory from `sideout jump analyze`."),
) -> None:
    """Regenerate charts + metrics JSON from a run's parquet (Phase 3)."""
    typer.echo("`sideout jump report` arrives in Phase 3.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
