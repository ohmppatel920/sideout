# Demo

The public demo page: **https://ohmppatel920.github.io/sideout/**

It's a self-contained static page (annotated video + metric cards + charts) that
**replays pre-computed pipeline outputs** — no physics runs in the browser.

## Publishing the real demo (3 steps)

Once you have a **clean single-athlete clip** (side view, one dominant jumper),
drop it in `samples/` and run:

```bash
# 1. Analyze the clip (produces runs/<run-dir>/ with metrics + charts + overlay)
uv run sideout jump analyze samples/<your-clip>.mov --height-cm <your-height>

# 2. Build the demo page from that run
uv run python demo/build_demo.py runs/<run-dir>

# 3. Commit and push — GitHub Pages redeploys automatically
git add demo/ && git commit -m "Publish demo" && git push
```

The `demo/assets/overlay.mp4` is a *derived* (rendered) artifact, so it's the one
video the repo deliberately allows committing — a small, intentional exception to
the "never commit video" rule, just for the published showcase.

Hosting is already wired up: [`.github/workflows/pages.yml`](../.github/workflows/pages.yml)
deploys this folder to GitHub Pages on any change to `demo/`.
