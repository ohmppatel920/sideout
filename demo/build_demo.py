"""Assemble a self-contained static demo page from a completed run.

Takes a run directory (metrics.json + charts + overlay.mp4 produced by
`sideout jump analyze`) and writes `demo/index.html` plus `demo/assets/`. The
metrics are inlined into the HTML so the page works from `file://` and from
GitHub Pages with no server, no fetch, no build step.

    uv run python demo/build_demo.py runs/<run-dir>

Note: the page is a *replay* of pipeline outputs — it contains zero physics
logic. The Python pipeline stays the single source of truth.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).parent
ASSETS = DEMO_DIR / "assets"


def _build_gif(overlay_mp4: Path, out_gif: Path, max_width: int = 360, stride: int = 2) -> bool:
    """Transcode the overlay video to a browser-universal animated GIF.

    OpenCV writes MPEG-4 Part 2, which browsers won't play in a <video> tag, and
    ffmpeg isn't assumed present — so we read frames with OpenCV and write an
    optimized looping GIF with Pillow. Downscaled and frame-strided to keep the
    file small. Returns False if the source can't be read.
    """
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(str(overlay_mp4))
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames: list[Image.Image] = []
    idx = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            h, w = bgr.shape[:2]
            scale = max_width / w
            small = cv2.resize(bgr, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb).convert("P", palette=Image.ADAPTIVE))
        idx += 1
    cap.release()
    if not frames:
        return False
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=int(stride * 1000 / fps),
        optimize=True,
        disposal=2,
    )
    return True


def _metric_cards(metrics: dict) -> str:
    if not metrics["jumps"]:
        return '<p class="muted">No jump detected in this clip.</p>'
    j = metrics["jumps"][0]
    cards = [("Jump height", f"{j['jump_height_m']:.2f} m")]
    if j.get("touch_height_m") is not None:
        cards.append(("Touch height", f"{j['touch_height_m']:.2f} m"))
    if j.get("countermovement_depth_m") is not None:
        cards.append(("Countermovement depth", f"{j['countermovement_depth_m']:.2f} m"))
    if j.get("loading_time_s") is not None:
        cards.append(("Loading time", f"{j['loading_time_s']:.2f} s"))
    if j.get("approach_velocity_m_s") is not None:
        cards.append(("Approach velocity", f"{j['approach_velocity_m_s']:.1f} m/s"))
    cards.append(("Arm-swing lead", f"{j['arm_swing_timing_s']:.2f} s"))
    return "\n".join(
        f'<div class="card"><div class="val">{v}</div><div class="lbl">{k}</div></div>'
        for k, v in cards
    )


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sideOut — Jump Lab demo</title>
<style>
  :root {{ color-scheme: light dark; --bg:#0e1116; --fg:#e6edf3; --muted:#8b949e;
           --accent:#2b7a78; --card:#161b22; --line:#30363d; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
          background:var(--bg); color:var(--fg); line-height:1.5; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:2rem 1.25rem 4rem; }}
  header h1 {{ font-size:2.2rem; margin:0 0 .25rem; }}
  header p {{ color:var(--muted); margin:.25rem 0 0; }}
  .tag {{ display:inline-block; background:var(--accent); color:#fff; font-size:.7rem;
          padding:.15rem .5rem; border-radius:999px; vertical-align:middle; }}
  section {{ margin-top:2.5rem; }}
  h2 {{ font-size:1.1rem; border-bottom:1px solid var(--line); padding-bottom:.4rem; }}
  .clip {{ max-width:100%; max-height:80vh; width:auto; display:block; margin:0 auto;
           border-radius:10px; border:1px solid var(--line); background:#000; }}
  img {{ width:100%; border-radius:10px; border:1px solid var(--line); background:#000; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:.75rem; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem; }}
  .card .val {{ font-size:1.6rem; font-weight:700; }}
  .card .lbl {{ color:var(--muted); font-size:.8rem; margin-top:.2rem; }}
  .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:1rem; }}
  @media (max-width:640px) {{ .charts {{ grid-template-columns:1fr; }} }}
  .muted {{ color:var(--muted); }}
  footer {{ margin-top:3rem; color:var(--muted); font-size:.85rem;
            border-top:1px solid var(--line); padding-top:1rem; }}
  a {{ color:#58a6ff; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>sideOut <span class="tag">Jump Lab</span></h1>
    <p>Local-first volleyball jump analysis from a single side-view phone video.</p>
  </header>

  <section>
    <h2>Annotated clip</h2>
    <img class="clip" src="{overlay}" alt="Annotated jump: skeleton overlay with event flags and metric readout">
    <p class="muted">Skeleton overlay with LOAD / TAKEOFF / LANDING flags and a live metric readout.</p>
  </section>

  <section>
    <h2>Measured metrics</h2>
    <div class="cards">
      {cards}
    </div>
  </section>

  <section>
    <h2>Session charts</h2>
    <div class="charts">
      <img src="{chart_heights}" alt="Jump height per jump">
      <img src="{chart_scatter}" alt="Each metric vs jump height">
    </div>
  </section>

  <footer>
    Generated by <code>sideout</code>. This page replays pre-computed pipeline
    outputs — no physics runs in the browser. Source &amp; method:
    <a href="https://github.com/ohmppatel920/sideout">github.com/ohmppatel920/sideout</a>.
  </footer>
</div>
<script>const METRICS = {metrics_json};</script>
</body>
</html>
"""


def build(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    metrics = json.loads((run_dir / "metrics.json").read_text())

    ASSETS.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}

    # The annotated overlay → a browser-universal looping GIF (see _build_gif).
    overlay_mp4 = run_dir / "overlay.mp4"
    if overlay_mp4.exists() and _build_gif(overlay_mp4, ASSETS / "overlay.gif"):
        assets["overlay"] = "assets/overlay.gif"
    else:
        assets["overlay"] = ""

    for src_name, key in [
        ("chart_heights.png", "chart_heights"),
        ("chart_metrics_vs_height.png", "chart_scatter"),
    ]:
        src = run_dir / src_name
        if src.exists():
            shutil.copy2(src, ASSETS / src_name)
            assets[key] = f"assets/{src_name}"
        else:
            assets[key] = ""

    html = HTML.format(
        overlay=assets["overlay"],
        chart_heights=assets["chart_heights"],
        chart_scatter=assets["chart_scatter"],
        cards=_metric_cards(metrics),
        metrics_json=json.dumps(metrics),
    )
    out = DEMO_DIR / "index.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python demo/build_demo.py runs/<run-dir>")
        raise SystemExit(2)
    print(f"Wrote {build(sys.argv[1])}")
