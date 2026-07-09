# sideOut — SPEC (source of truth)

> **Revision 2 (2026-07-09).** Approved change from the original kickoff: the core architecture and Phases 1–3 are unchanged, but the project now targets "all-around impressive to technical reviewers" — Phase 4 gains production-rigor conventions (lint/type/coverage CI, Docker, lockfile), and two phases are added: **Phase 5 (validation vs published reference data)** and **Phase 6 (static in-browser demo)**. The sample clip is `samples/demo.mov` (not `.mp4`). The pose model file is auto-downloaded to `models/` (gitignored), never committed.

I'm building **sideOut**, an open-source, local-first volleyball performance-analysis toolkit. I captained Brown Men's Volleyball to a D1AAA national championship and did scouting/analysis by hand; this project automates it. First module: **Jump Lab** — a pose-estimation pipeline that analyzes volleyball attack approaches from a side-view phone video.

Work in the phases below, **in order, stopping after each phase** so I can review before you continue. Write tests as you go, not at the end. Commit at every phase boundary with a clear message.

## Architecture (fixed — don't redesign)

Pipeline: `video file → MediaPipe pose estimation → keypoint time-series (parquet) → biomechanics metrics engine → outputs (metrics JSON + annotated video + charts)`

Key principle: video is treated like source code; keypoints and metrics are derived artifacts. Raw videos are NEVER committed or copied — path references only.

## Stack (fixed)

- Python 3.11+, managed with `uv` (fall back to pip + venv if needed)
- MediaPipe (Tasks API — `PoseLandmarker`, video mode), OpenCV, ffmpeg-python only if needed
- NumPy, pandas, pyarrow (parquet), matplotlib
- Typer for CLI, pytest for tests
- Dev tooling: `ruff` (lint + format), `mypy` (typed public APIs), `pytest-cov` (coverage) — enforced in CI from Phase 4
- NO web UI *server*, NO database, NO GPU dependencies. The Phase 6 demo is a **static page** (no backend) that replays pre-computed pipeline outputs — it duplicates zero physics logic. Keep dependencies minimal.

## Repo structure

```
sideout/
  pyproject.toml
  README.md
  .gitignore            # ignores *.mp4/*.mov except samples/demo.mp4|demo.mov
  samples/              # one short sample clip (samples/demo.mov)
  models/               # gitignored; pose model auto-downloaded on first run
  src/sideout/
    cli.py              # Typer app: `sideout jump analyze <video>`, `sideout jump report <run>`
    pose/extractor.py   # video -> keypoints DataFrame
    jump/events.py      # takeoff/landing/load-start detection
    jump/metrics.py     # pure functions: the biomechanics engine
    jump/report.py      # charts + metrics JSON
    viz/overlay.py      # annotated output video
  tests/
    fixtures.py         # synthetic keypoint generators
    test_events.py
    test_metrics.py
  validation/           # Phase 5: methodology + error analysis -> VALIDATION.md
  demo/                 # Phase 6: static demo page (GitHub Pages)
  runs/                 # gitignored; per-run outputs
```

## Phase 1 — Scaffold + pose extraction

1. Init repo, pyproject, .gitignore, minimal README (one-paragraph vision + module roadmap: Jump Lab now; Film Room, Shot Charts, Lineup Optimizer later).
2. `pose/extractor.py`: given a video path, run MediaPipe PoseLandmarker (video mode) frame-by-frame → DataFrame with columns: `frame, t_ms, landmark_id, x, y, z, visibility` (normalized image coords; also store `world_x/y/z` from world landmarks). Save to `runs/<video-stem>-<timestamp>/keypoints.parquet`.
3. CLI: `sideout jump analyze <video> --out runs/` runs extraction and prints a summary (frames processed, fps, mean visibility of ankles/hips/wrists).
4. Handle: video rotation metadata (phone videos!), variable fps (use frame timestamps, never assume 30fps), person briefly lost (gap rows, don't crash).

**Done when:** I can run `sideout jump analyze samples/demo.mp4` and get a parquet + summary. STOP for my review.

## Phase 2 — Event detection + metrics engine (the core; test-heavy)

`jump/events.py` — from the keypoint time series detect, per jump:
- **load_start**: hip vertical velocity turns negative sustained (start of countermovement)
- **takeoff**: last frame ankles leave baseline — use ankle-y departure + upward hip velocity peak
- **landing**: ankle-y returns to baseline after flight
- Smooth with Savitzky–Golay before differentiating; parameterize thresholds; support multiple jumps per video.

`jump/metrics.py` — PURE functions (DataFrame slice in, floats out), no I/O:
- **jump_height_m**: flight-time method, h = g·t²/8, t = landing − takeoff (uses real timestamps)
- **countermovement_depth**: standing-baseline hip y minus min hip y during load (report normalized units AND meters via height calibration)
- **loading_time_s**: load_start → takeoff
- **approach_velocity_m_s**: horizontal hip displacement over the ~0.5 s before plant; px→m calibrated from athlete standing height (CLI flag `--height-cm`, required for scaled metrics; unscaled metrics still computed without it)
- **arm_swing_timing_s**: wrist-y minimum (backswing) relative to takeoff time

Tests: synthetic fixtures in `tests/fixtures.py` that generate ideal keypoint trajectories for a parameterized jump (known flight time, known depth) → assert metrics recover the ground-truth values within tolerance. Also edge cases: no jump in clip, two jumps, missing frames mid-flight.

**Done when:** pytest green with meaningful coverage of events + metrics. STOP for my review.

## Phase 3 — Outputs

1. `viz/overlay.py`: annotated MP4 — skeleton overlay, event markers (LOAD/TAKEOFF/LANDING flags), live metric readout after each jump.
2. `jump/report.py`: `metrics.json` (per-jump + session aggregates), and charts: per-jump bar of heights, and scatter of each metric vs jump height across the session.
3. `sideout jump report <run-dir>` regenerates charts/JSON from parquet without re-running pose.

**Done when:** one command turns my real video into overlay + JSON + charts. STOP.

## Phase 4 — Polish for public

README upgrade: demo GIF placeholder, quickstart, capture protocol (side view, tripod, 8–10 m, full body in frame), **honest limitations section** (monocular, no depth reconstruction, flight-time assumes equal takeoff/landing level, side-view required), roadmap, license (MIT).

Production-rigor additions (cheap, compounds — the "ships production code" signal):
- GitHub Actions CI on push: `pytest` + coverage, `ruff check`, `ruff format --check`, `mypy src/`
- Commit `uv.lock` and `.python-version` — fully reproducible env
- `Dockerfile` so anyone runs the pipeline in one command without touching their Python
- README badges: CI status, coverage, license, Python version

**Done when:** CI is green on GitHub and the README sells the project honestly. STOP.

## Phase 5 — Validation & error analysis (the credibility phase)

Turn "I built a thing" into "I built a thing and measured how accurate it is":
- `validation/` — a small, reproducible study comparing the pipeline's flight-time jump height against published reference values for the flight-time method vs force plates (cite sources: e.g. validated MyJump/force-plate comparison literature).
- Report bias and error bounds honestly; quantify sensitivity to fps (e.g. what does ±1 frame at 30/60/240 fps do to height error? — this is a pure math analysis, no data collection needed) and to event-detection tolerance.
- Output: `VALIDATION.md` with methodology, error tables/plots, and limitations. Linked prominently from README.

**Done when:** a skeptical reviewer can read VALIDATION.md and trust (or fairly judge) the numbers. STOP.

## Phase 6 — Static in-browser demo (the resume link)

A recruiter clicks a link and sees a real volleyball jump analyzed — zero install:
- Pre-process `samples/demo.mov` offline with the real Python pipeline → overlay video (web-encoded), `metrics.json`, chart data.
- Static page (plain HTML/JS or minimal framework; hosted free on GitHub Pages): replays the annotated video with synchronized event markers and live metric readouts, shows per-jump metrics and charts.
- **No physics logic in JS** — the page only renders artifacts the Python pipeline produced. The pipeline stays the single source of truth.
- "Analyze your own clip in-browser" is explicitly deferred to v0.2.

**Done when:** a public URL shows the demo and it's linked at the top of the README. STOP.

## Agent workflow (how to operate — follow this, not just the what)

Work like a small engineering team with separated roles/contexts:

1. **Plan before building.** Before each phase, enter plan mode and produce a short implementation plan (files, functions, test cases, risks). Wait for my approval before writing code.
2. **Implement** in the main loop, tests alongside code.
3. **Review with fresh context.** At the end of every phase, before presenting to me, launch a code-review subagent (fresh context, no memory of writing the code) to audit the phase diff against this spec. Its checklist:
   - Physics/units: every metric dimensionally correct; sign conventions for image coords (y grows DOWNWARD in image space — verify countermovement and velocity signs); real timestamps used, never assumed fps
   - Tests actually assert ground-truth recovery from synthetic fixtures, not just "runs without error"
   - No raw video committed, no path leaks, `runs/` gitignored
   - Docstrings state units; formulas have derivation comments
   Fix findings before presenting the phase to me. Include the reviewer's summary when you stop.
4. **Evidence, not assertions.** Never report "done" or "it works" — show the pytest output, the command run and what it returned. If a check can't be run, say so explicitly.
5. **First session setup:**
   - Save this entire prompt into the repo as `SPEC.md` — it is the source of truth across sessions.
   - Create `.claude/agents/physics-reviewer.md` encoding the checklist above so the reviewer persists across sessions.
   - Set up hooks (deterministic, not advisory): a PostToolUse hook that runs the fast pytest suite after any edit under `src/`, and a PreToolUse hook that blocks any `git add`/commit touching `*.mp4`/`*.mov` outside `samples/`.
   - Generate `CLAUDE.md`, then trim ruthlessly ("would removing this line cause mistakes?"): architecture rule (video → parquet → metrics; never commit video), test command, uv usage, pure-metric-functions-with-units rule. Nothing else.
6. **Fresh context per phase.** Each phase should begin in a fresh session (`/clear`): re-read `@SPEC.md` and `@CLAUDE.md`, plan, implement. Don't carry a full weekend in one context window.

(For me, the human: allowlist `uv run pytest`, `uv sync`, and `git commit` in `/permissions` so I'm not clicking approvals all weekend.)

Front-end/back-end specialist agents are deliberately NOT part of v0.1. The Phase 6 static demo is a single page rendering pre-computed artifacts — it does not warrant a specialist agent. Introduce them in v0.2 if/when an interactive upload-your-own-clip layer starts.

## Constraints & style

- Prefer boring, readable code over cleverness; docstrings with units on every metric function (meters, seconds).
- Every physics formula gets a comment with its derivation source.
- If MediaPipe's Tasks API has changed from what you expect, check the installed version's docs rather than guessing.
- If a phase reveals a blocker (e.g., pose quality on my sample), stop and present options rather than silently working around it.
