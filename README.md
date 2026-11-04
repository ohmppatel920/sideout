# sideOut 🏐

[![CI](https://github.com/ohmppatel920/sideout/actions/workflows/ci.yml/badge.svg)](https://github.com/ohmppatel920/sideout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**sideOut** is an open-source, local-first volleyball performance-analysis toolkit. It turns an ordinary side-view phone video into biomechanical insight, with no cloud, no account and no GPU. The first module, **Jump Lab**, runs pose estimation on an attack approach and derives jump height, countermovement depth, loading time, approach velocity, and arm-swing timing, then produces an annotated video, a metrics JSON, and charts.

It grew out of scouting a D1AAA national-championship team by hand; sideOut automates that work.

**▶ Live demo: [ohmppatel920.github.io/sideout](https://ohmppatel920.github.io/sideout/)**: a real jump analyzed in the browser (skeleton overlay, event flags, live metrics, to-scale reach diagram). No install.

**Why it exists:** [MARKET.md](MARKET.md) has the segment sizing (648 college club teams at nationals vs. ~$1,250/team/yr incumbent spend) and a feature/price benchmark against Hudl, Balltime, and open-source tools.

---

## Engineering highlights

- **Correctness over coverage theatre.** 69 tests at 87% coverage, which assert that the metrics *recover ground truth* from synthetic fixtures built with known answers.
- **Green CI on every push.** GitHub Actions runs `ruff`, `mypy`, and `pytest` (badge above).
- **Typed and pure.** Fully type-annotated; the physics lives in pure, side-effect-free functions, each documenting its units and formula derivation.
- **Handles real-world input.** Variable frame rate (uses true timestamps, never assumes fps), phone rotation metadata, and dropped frames.
- **Reproducible and shippable.** A `uv` lockfile, one-command Docker, and a live auto-deployed demo (GitHub Pages).
- **Reviewed like real code.** Each phase was audited by a fresh-context reviewer that caught and fixed real bugs before merge.

---

## Quickstart

Requires **Python 3.11+**. The easiest path uses [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ohmppatel920/sideout.git
cd sideout
uv sync                      # create the environment + install deps

# One command: video → keypoints + metrics.json + charts + annotated video
uv run sideout jump analyze samples/demo.mov --height-cm 185 --reach-cm 244

# Re-generate metrics + charts from a saved run (no pose re-run)
uv run sideout jump report runs/<run-dir>
```

Outputs land in `runs/<video-stem>-<timestamp>/`:

| File | What it is |
|------|------------|
| `keypoints.parquet` | Per-frame body-point time series (the derived source of truth) |
| `metrics.json` | Every jump's metrics + a session summary |
| `chart_heights.png` | Jump height per jump |
| `chart_metrics_vs_height.png` | Each metric plotted against jump height |
| `overlay.mp4` | The video with skeleton, event flags, and live metric readout |

`--height-cm` (your standing height) unlocks the metrics that need real-world scale (depth in meters, approach velocity in m/s); `--reach-cm` (your flat-footed standing reach) unlocks **touch height**, meaning how high you reach at the apex, the number coaches care about. Everything else is computed without them.

### Docker (no local Python)

```bash
docker build -t sideout .
docker run --rm -v "$PWD/samples:/data" sideout jump analyze /data/demo.mov --out /data/runs
```

---

## How it works

```
video file
   │   MediaPipe pose estimation (per frame, real timestamps)
   ▼
keypoints.parquet          # 33 body points × every frame
   │   smoothing → event detection (load / takeoff / landing)
   ▼
biomechanics metrics       # pure functions, physics with derivations
   │
   ▼
metrics.json + charts + annotated video
```

**Design principle:** the video is treated like source code; keypoints and metrics are *derived artifacts*. Raw videos are never committed or copied; the repo holds path references to them.

### The metrics

| Metric | Unit | How |
|--------|------|-----|
| Jump height | m | Flight-time method: `h = g·t²/8` |
| Touch height | m | Standing reach + jump height (reach at apex) |
| Countermovement depth | m + normalized | Lowest hip during load minus standing hip |
| Loading time | s | Load-start → takeoff |
| Approach velocity | m/s | Horizontal hip speed over ~0.5 s before the plant |
| Arm-swing timing | s | Backswing bottom relative to takeoff |

Every physics formula carries a derivation comment; every metric function states its units.

---

## Capture protocol

For trustworthy numbers, film like this:

- **Side view.** Camera perpendicular to the approach direction (the athlete moves left↔right across the frame).
- **Tripod / steady.** A moving camera corrupts the measurements.
- **~8–10 m back**, with the **whole body in frame** for the entire approach, take-off, and landing.
- **One athlete clearly dominant** in frame (see limitations).
- Higher frame rate is better; 60 fps or more tightens the jump-height estimate.

---

## Accuracy

The jump-height physics is validated and its error is quantified. See
[`VALIDATION.md`](VALIDATION.md) for the full analysis: the flight-time method
vs force-plate references (with citations), a frame-rate sensitivity study
(why 60 fps+ matters), and the engine's tested error floor (≤ ±4 cm on clean
input). Short version: the biggest real-world risk isn't the physics, it's
monocular pose tracking the wrong athlete in a crowd, which the capture
protocol addresses.

## Honest limitations

sideOut is a monocular (single-camera) tool. Be aware:

- **No true depth.** Positions are 2-D image coordinates scaled by your height; motion toward/away from the camera is not measured.
- **Flight-time jump height assumes takeoff and landing are at the same level.** Landing in a deep lunge, or on a different surface height, biases the number.
- **Side view required.** Facing the camera breaks the horizontal-velocity and depth logic.
- **Single-athlete tracking.** On crowded footage (e.g. a full net of players) the pose model may lock onto the wrong person. Use a clip where your athlete is clearly dominant.
- **Height calibration needs a clean standing pose** at the start of the clip.

These are the honest envelope the method is valid within, and the docs state them.

---

## Module roadmap

- **Jump Lab** ✅ _(v0.1)_. Attack-approach jump analysis.
- **Film Room.** Rally and touch segmentation, with searchable match film.
- **Shot Charts.** Attack tendency and location charting.
- **Lineup Optimizer.** Rotation and lineup analysis.

---

## Development

```bash
uv sync --extra dev
uv run pytest              # test suite (synthetic-fixture, ground-truth recovery)
uv run ruff check src tests
uv run mypy src
```

The engine is validated against **synthetic jumps with known ground truth**, so the tests assert that the metrics recover the values the fixtures were built from. See [`SPEC.md`](SPEC.md) for the architecture and [`docs/DEVLOG.md`](docs/DEVLOG.md) for a plain-English build log.

## License

MIT. See [`LICENSE`](LICENSE).
