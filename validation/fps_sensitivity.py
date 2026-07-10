"""How camera frame rate limits jump-height accuracy — a pure-math analysis.

The flight-time method computes jump height from airtime: ``h = g·t²/8``. A
camera can only locate takeoff and landing to within a frame, so the measured
airtime carries a quantization error of up to one frame period (``1/fps``).
sideOut's midpoint convention (placing each event halfway between the last
grounded and first airborne frame) halves the *typical* error to about half a
frame.

This script needs no data collection — it propagates that timing error through
the real ``jump_height_m`` function and writes a table + a plot. Run it with:

    uv run python validation/fps_sensitivity.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from sideout.jump.metrics import G_M_S2, jump_height_m  # noqa: E402

# Representative volleyball jump heights (m) and camera frame rates to compare.
HEIGHTS_M = [0.30, 0.45, 0.60, 0.75]
FRAME_RATES = [30, 60, 120, 240]


def flight_time_for_height(h_m: float) -> float:
    """Inverse of the flight-time method: t = sqrt(8h/g) [s]."""
    return math.sqrt(8.0 * h_m / G_M_S2)


def height_error_cm(true_h_m: float, fps: int, frame_error: float = 0.5) -> float:
    """Worst-case height error [cm] from ``frame_error`` frames of timing error.

    ``frame_error=0.5`` models sideOut's midpoint convention (typical);
    ``frame_error=1.0`` is the naive snap-to-frame worst case.
    """
    t = flight_time_for_height(true_h_m)
    dt = frame_error / fps
    return abs(jump_height_m(t + dt) - true_h_m) * 100.0


def error_table(frame_error: float = 0.5) -> list[tuple[float, list[float]]]:
    """Rows of (true_height_m, [error_cm at each frame rate])."""
    return [(h, [height_error_cm(h, fps, frame_error) for fps in FRAME_RATES]) for h in HEIGHTS_M]


def _write_plot(out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    for h in HEIGHTS_M:
        errs = [height_error_cm(h, fps) for fps in FRAME_RATES]
        ax.plot(FRAME_RATES, errs, marker="o", label=f"{h * 100:.0f} cm jump")
    ax.set_xlabel("Camera frame rate (fps)")
    ax.set_ylabel("Typical jump-height error (cm)")
    ax.set_title("Frame rate vs jump-height accuracy (midpoint convention)")
    ax.set_xticks(FRAME_RATES)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> None:
    here = Path(__file__).parent
    print("Typical jump-height error (cm), sideOut midpoint convention (~0.5 frame):\n")
    header = "  height |" + "".join(f"  {fps:>4} fps" for fps in FRAME_RATES)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for h, errs in error_table():
        print(f"  {h * 100:>4.0f} cm |" + "".join(f"  {e:>7.2f}" for e in errs))
    out = here / "fps_sensitivity.png"
    _write_plot(out)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
