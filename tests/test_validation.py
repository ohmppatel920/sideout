"""Frame-rate sensitivity analysis: the math behind VALIDATION.md."""

import pytest

from sideout.jump.metrics import jump_height_m
from validation.fps_sensitivity import (
    FRAME_RATES,
    flight_time_for_height,
    height_error_cm,
)


def test_flight_time_inverts_jump_height():
    for h in (0.30, 0.50, 0.70):
        t = flight_time_for_height(h)
        assert jump_height_m(t) == pytest.approx(h, rel=1e-9)


def test_error_strictly_decreases_with_frame_rate():
    errs = [height_error_cm(0.50, fps) for fps in FRAME_RATES]
    # consecutive pairs (intentionally unequal lengths → strict=False)
    assert all(a > b for a, b in zip(errs, errs[1:], strict=False))


def test_error_magnitude_matches_published_table():
    # A 0.5 m jump at 60 fps should be ~1.3 cm (between the 45 and 60 cm rows).
    assert height_error_cm(0.50, 60) == pytest.approx(1.3, abs=0.3)
    # Worst-case (1 full frame) is roughly double the midpoint (0.5 frame).
    typical = height_error_cm(0.50, 60, frame_error=0.5)
    worst = height_error_cm(0.50, 60, frame_error=1.0)
    assert worst == pytest.approx(2 * typical, rel=0.1)
