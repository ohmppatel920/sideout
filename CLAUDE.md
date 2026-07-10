# CLAUDE.md

`SPEC.md` is the source of truth. Re-read it at the start of each phase.

## Architecture (non-negotiable)

Pipeline: `video → MediaPipe pose → keypoints.parquet → metrics engine → outputs`.
Video is source, not artifact. **Never commit or copy raw video** — path references only. `*.mp4`/`*.mov` are gitignored except `samples/demo.mp4`; `runs/` is gitignored.

## Metrics engine

Functions in `jump/metrics.py` are **pure**: DataFrame slice in, floats out, no I/O.
Every metric function's docstring states its **units** (meters, seconds). Every physics formula gets a comment citing its derivation. Image `y` grows **downward** — mind the sign in countermovement and velocity.
Use **real frame timestamps**, never an assumed fps.

## Tooling

- Env/deps: `uv` (`uv sync`); fall back to pip + venv only if `uv` is unavailable. Python 3.11+.
- Run tests: `uv run pytest`
- Pose model auto-downloads to `~/.cache/sideout/models` (`SIDEOUT_MODEL_DIR` overrides).

## macOS/iCloud gotcha

This repo lives under an iCloud-synced Desktop. iCloud sporadically sets the
hidden flag on `.venv` files, which makes Python skip `.pth` files and breaks
`import sideout`. Fix already applied: `xattr -w 'com.apple.fileprovider.ignore#P' 1 .venv`.
If imports ever break after a fresh clone/venv, reapply that xattr, then
`chflags nohidden .venv/lib/python*/site-packages/*.pth`.
