# sideOut 🏐

[![CI](https://github.com/ohmppatel920/sideout/actions/workflows/ci.yml/badge.svg)](https://github.com/ohmppatel920/sideout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**sideOut** is an open-source, local-first volleyball performance-analysis toolkit. It turns an ordinary side-view phone video into biomechanical insight — no cloud, no account, no GPU. The first module, **Jump Lab**, runs pose estimation on an attack approach and derives jump height, countermovement depth, loading time, approach velocity, and arm-swing timing, then produces an annotated video, a metrics JSON, and charts.

It grew out of scouting a D1AAA national-championship team by hand; sideOut automates that work.

**▶ Live demo: [ohmppatel920.github.io/sideout](https://ohmppatel920.github.io/sideout/)** — a real jump analyzed in the browser (skeleton overlay, event flags, live metrics, to-scale reach diagram). No install.

---

## Engineering highlights

- **Correctness over coverage theatre** — 69 tests / 87% coverage that assert the metrics *recover ground truth* from synthetic fixtures with known answers, not just "it runs."
- **Green CI on every push** — GitHub Actions runs `ruff`, `mypy`, and `pytest` (badge above).
- **Typed and pure** — fully type-annotated; the physics lives in pure, side-effect-free functions, each documenting its units and formula derivation.
- **Handles real-world input** — variable frame rate (uses true timestamps, never assumes fps), phone rotation metadata, and dropped frames.
- **Reproducible + shippable** — `uv` lockfile, one-command Docker, and a live auto-deployed demo (GitHub Pages).
- **Reviewed like real code** — each phase audited by a fresh-context reviewer that caught and fixed real bugs before merge.

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

`--height-cm` (your standing height) unlocks the metrics that need real-world scale (depth in meters, approach velocity in m/s); `--reach-cm` (your flat-footed standing reach) unlocks **touch height** — how high you reach at the apex, the number coaches care about. Everything else is computed without them.

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

**Design principle:** the video is treated like source code; keypoints and metrics are *derived artifacts*. Raw videos are never committed or copied — path references only.

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

- **Side view** — camera perpendicular to the approach direction (the athlete moves left↔right across the frame).
- **Tripod / steady** — a moving camera corrupts the measurements.
- **~8–10 m back**, with the **whole body in frame** for the entire approach, take-off, and landing.
- **One athlete clearly dominant** in frame (see limitations).
- Higher frame rate is better — 60 fps or more tightens the jump-height estimate.

---

## Accuracy

The jump-height physics is validated and its error is quantified — see
[`VALIDATION.md`](VALIDATION.md) for the full analysis: the flight-time method
vs force-plate references (with citations), a frame-rate sensitivity study
(why 60 fps+ matters), and the engine's tested error floor (≤ ±4 cm on clean
input). Short version: the biggest real-world risk isn't the physics, it's
monocular pose tracking the wrong athlete in a crowd — which the capture
protocol addresses.

## Honest limitations

sideOut is a monocular (single-camera) tool. Be aware:

- **No true depth.** Positions are 2-D image coordinates scaled by your height; motion toward/away from the camera is not measured.
- **Flight-time jump height assumes takeoff and landing are at the same level.** Landing in a deep lunge, or on a different surface height, biases the number.
- **Side view required.** Facing the camera breaks the horizontal-velocity and depth logic.
- **Single-athlete tracking.** On crowded footage (e.g. a full net of players) the pose model may lock onto the wrong person. Use a clip where your athlete is clearly dominant.
- **Height calibration needs a clean standing pose** at the start of the clip.

These aren't bugs to hide — they're the honest envelope the method is valid within.

---

## Module roadmap

- **Jump Lab** ✅ _(v0.1)_ — attack-approach jump analysis.
- **Film Room** — rally/touch segmentation and searchable match film.
- **Shot Charts** — attack tendency and location charting.
- **Lineup Optimizer** — rotation and lineup analysis.

---

## Development

```bash
uv sync --extra dev
uv run pytest              # test suite (synthetic-fixture, ground-truth recovery)
uv run ruff check src tests
uv run mypy src
```

The engine is validated against **synthetic jumps with known ground truth** — the tests assert the metrics recover the values the fixtures were built from, not merely that the code runs. See [`SPEC.md`](SPEC.md) for the architecture and [`docs/DEVLOG.md`](docs/DEVLOG.md) for a plain-English build log.

## License

MIT — see [`LICENSE`](LICENSE).
