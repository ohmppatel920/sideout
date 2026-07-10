"""Assemble a self-contained static demo page from a completed run.

Takes a run directory (metrics.json + charts + overlay.mp4 produced by
`sideout jump analyze`) and writes `demo/index.html` plus `demo/assets/`. The
overlay is transcoded to a browser-universal GIF (OpenCV's mp4v won't play in a
<video> tag, and ffmpeg isn't assumed present). Metrics are inlined so the page
works from `file://` and from GitHub Pages with no server, no fetch, no build.

    uv run python demo/build_demo.py runs/<run-dir>

The page is a *replay* of pipeline outputs — it contains zero physics logic.
The Python pipeline stays the single source of truth.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).parent
ASSETS = DEMO_DIR / "assets"

MENS_NET_M = 2.43  # FIVB men's net height, drawn as the reference line


def _build_gif(overlay_mp4: Path, out_gif: Path, max_width: int = 360, stride: int = 2) -> bool:
    """Transcode the overlay video to a browser-universal looping GIF via Pillow."""
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
            small = cv2.resize(bgr, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb).convert("P", palette=Image.ADAPTIVE))
        idx += 1
    cap.release()
    if not frames:
        return False
    frames[0].save(
        out_gif, save_all=True, append_images=frames[1:], loop=0,
        duration=int(stride * 1000 / fps), optimize=True, disposal=2,
    )
    return True


def _reach_diagram(jump: dict) -> str:
    """SVG: the athlete's reach drawn to scale against the net — the signature.

    Only rendered when touch height is available (needs --reach-cm). Shows
    standing reach, the men's net line, and touch height at the apex, so the
    jump reads as 'clears the net by N cm'.
    """
    touch = jump.get("touch_height_m")
    if touch is None:
        return ""
    reach = (jump.get("touch_height_m") or 0) - jump["jump_height_m"]  # standing reach
    jump_m = jump["jump_height_m"]

    max_m = max(3.2, touch + 0.25)
    top, bottom, h = 26, 34, 340
    inner = h - top - bottom

    def y(m: float) -> float:
        return round(top + inner * (1 - m / max_m), 1)

    bar_x, bar_w = 108, 46
    ground = y(0)
    parts = [f'<svg viewBox="0 0 360 {h}" role="img" aria-label="Reach to scale versus the net">']

    # y-axis ticks (metres)
    for m in range(0, int(max_m) + 1):
        yy = y(m)
        parts.append(f'<line class="grid" x1="52" y1="{yy}" x2="330" y2="{yy}"/>')
        parts.append(f'<text class="tick" x="44" y="{yy + 4}" text-anchor="end">{m} m</text>')

    # reach column: ground→standing-reach (base), standing-reach→touch (the jump)
    parts.append(
        f'<rect class="bar-base rise" x="{bar_x}" y="{y(reach)}" width="{bar_w}" '
        f'height="{round(ground - y(reach), 1)}" rx="3"/>'
    )
    parts.append(
        f'<rect class="bar-jump rise" x="{bar_x}" y="{y(touch)}" width="{bar_w}" '
        f'height="{round(y(reach) - y(touch), 1)}" rx="3"/>'
    )

    # net reference line — label sits ABOVE the line (far right) and the
    # standing-reach marker BELOW it, so the dashed line runs cleanly between
    # them even when reach ≈ net height (as it does for tall athletes).
    parts.append(f'<line class="net" x1="52" y1="{y(MENS_NET_M)}" x2="330" y2="{y(MENS_NET_M)}"/>')
    parts.append(f'<text class="net-lbl" x="326" y="{y(MENS_NET_M) - 7}" text-anchor="end">men\'s net {MENS_NET_M:.2f} m</text>')

    # markers
    lx = bar_x + bar_w + 12
    parts.append(f'<text class="mk-touch" x="{lx}" y="{y(touch) + 4}">▸ touch {touch:.2f} m</text>')
    parts.append(f'<text class="mk-reach" x="{lx}" y="{y(reach) + 17}">▸ standing reach {reach:.2f} m</text>')

    over = touch - MENS_NET_M
    parts.append(f'<text class="mk-gain" x="{bar_x + bar_w / 2}" y="{y(touch) - 10}" text-anchor="middle">+{jump_m:.2f} m</text>')
    parts.append("</svg>")
    caption = f"Flat-footed you reach the net; at the top of your jump you clear it by {over * 100:.0f} cm."
    return f'<div class="reach">{"".join(parts)}</div><p class="reach-cap">{caption}</p>'


_READOUT = [
    ("jump_height_m", "Jump height", "m", "{:.2f}"),
    ("touch_height_m", "Touch height", "m", "{:.2f}"),
    ("countermovement_depth_m", "Countermovement depth", "m", "{:.2f}"),
    ("loading_time_s", "Loading time", "s", "{:.2f}"),
    ("approach_velocity_m_s", "Approach velocity", "m/s", "{:.1f}"),
    ("arm_swing_timing_s", "Arm-swing lead", "s", "{:.2f}"),
]


def _readout_rows(jump: dict) -> str:
    rows = []
    for key, label, unit, fmt in _READOUT:
        if jump.get(key) is not None:
            rows.append(
                f'<div class="row"><span class="rl">{label}</span>'
                f'<span class="rv">{fmt.format(jump[key])}<span class="ru">{unit}</span></span></div>'
            )
    return "\n".join(rows)


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sideOut — Jump Lab</title>
<meta name="description" content="Local-first volleyball jump analysis from a single side-view phone video.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#e9edf1; --panel:#f7f9fb; --ink:#0f1720; --muted:#5a6b78; --line:#cdd6de;
    --accent:#123a8b; --accent-soft:#3b62b8; --signal:#e0532b; --turf:#2c7d59;
  }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:"Space Grotesk",-apple-system,Segoe UI,Roboto,sans-serif; line-height:1.55; }
  .mono { font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  :focus-visible { outline:2px solid var(--accent); outline-offset:2px; }

  .wrap { max-width:1000px; margin:0 auto; padding:0 1.25rem; }
  nav { display:flex; align-items:center; justify-content:space-between; padding:1.1rem 0;
        border-bottom:1px solid var(--line); }
  .brand { font-weight:700; letter-spacing:-.02em; font-size:1.15rem; }
  .brand b { color:var(--accent); }
  .brand .lab { font-size:.62rem; letter-spacing:.16em; text-transform:uppercase;
                color:var(--muted); border:1px solid var(--line); border-radius:999px;
                padding:.12rem .5rem; margin-left:.5rem; vertical-align:middle; }
  nav .links { display:flex; gap:1.25rem; font-size:.9rem; }

  .eyebrow { font-family:"IBM Plex Mono",monospace; font-size:.72rem; letter-spacing:.18em;
             text-transform:uppercase; color:var(--turf); }
  h1 { font-size:clamp(2.1rem,5vw,3.2rem); line-height:1.04; letter-spacing:-.03em;
       margin:.5rem 0 .6rem; }
  h1 em { font-style:normal; color:var(--accent); }
  .lede { color:var(--muted); font-size:1.06rem; max-width:34ch; }

  .hero { display:grid; grid-template-columns:1.05fr .95fr; gap:2.5rem; align-items:center;
          padding:3.2rem 0 2.4rem; }
  .hero .cta { display:flex; gap:.7rem; margin-top:1.4rem; flex-wrap:wrap; }
  .btn { font-size:.9rem; font-weight:500; padding:.6rem 1rem; border-radius:8px;
         border:1px solid var(--accent); }
  .btn.solid { background:var(--accent); color:#fff; }
  .btn.solid:hover { background:var(--accent-soft); text-decoration:none; }
  .btn.ghost { color:var(--accent); }
  .clip { width:100%; max-height:74vh; display:block; margin:0 auto; border-radius:12px;
          border:1px solid var(--line); background:#0f1720; box-shadow:0 12px 30px rgba(15,23,32,.12); }
  .clip-cap { text-align:center; color:var(--muted); font-size:.82rem; margin:.6rem 0 0; }

  section { padding:2.6rem 0; border-top:1px solid var(--line); }
  .sec-head { display:flex; align-items:baseline; gap:.8rem; margin-bottom:1.4rem; }
  .sec-head h2 { font-size:1.25rem; letter-spacing:-.01em; margin:0; }
  .sec-head .n { font-family:"IBM Plex Mono",monospace; color:var(--muted); font-size:.8rem; }

  /* signature: reach-to-scale */
  .signature { display:grid; grid-template-columns:340px 1fr; gap:2rem; align-items:center; }
  .reach svg { width:100%; height:auto; }
  .reach .grid { stroke:var(--line); stroke-width:1; }
  .reach .tick { fill:var(--muted); font:500 11px "IBM Plex Mono",monospace; }
  .reach .net { stroke:var(--ink); stroke-width:1.5; stroke-dasharray:5 4; }
  .reach .net-lbl { fill:var(--ink); font:500 10px "IBM Plex Mono",monospace; }
  .reach .bar-base { fill:var(--accent); }
  .reach .bar-jump { fill:var(--signal); }
  .reach .mk-touch { fill:var(--signal); font:700 13px "Space Grotesk",sans-serif; }
  .reach .mk-reach { fill:var(--accent); font:500 12px "Space Grotesk",sans-serif; }
  .reach .mk-gain { fill:var(--signal); font:700 12px "IBM Plex Mono",monospace; }
  .reach-cap { color:var(--muted); font-size:.92rem; }
  .rise { transform-box:fill-box; transform-origin:bottom; animation:rise .9s cubic-bezier(.2,.7,.2,1) both; }
  @keyframes rise { from { transform:scaleY(0); } to { transform:scaleY(1); } }

  /* metric readout */
  .readout { background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  .readout .row { display:flex; justify-content:space-between; align-items:baseline;
                  padding:.85rem 1.2rem; border-top:1px solid var(--line); }
  .readout .row:first-child { border-top:none; }
  .rl { color:var(--muted); font-size:.92rem; }
  .rv { font-family:"IBM Plex Mono",monospace; font-size:1.5rem; font-weight:500; }
  .ru { color:var(--muted); font-size:.8rem; margin-left:.3rem; }

  /* pipeline */
  .pipe { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; }
  .step { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:1rem; }
  .step .k { font-family:"IBM Plex Mono",monospace; color:var(--turf); font-size:.72rem; }
  .step h3 { font-size:.98rem; margin:.35rem 0 .3rem; }
  .step p { color:var(--muted); font-size:.84rem; margin:0; }

  /* engineering highlights */
  .eng { display:grid; grid-template-columns:1fr 1fr; gap:.7rem 2rem; }
  .eng div { display:flex; gap:.6rem; font-size:.92rem; padding:.15rem 0; }
  .eng .c { color:var(--turf); font-family:"IBM Plex Mono",monospace; }
  .stack { display:flex; flex-wrap:wrap; gap:.45rem; margin-top:1.4rem; }
  .chip { font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--muted);
          border:1px solid var(--line); border-radius:6px; padding:.25rem .55rem; background:var(--panel); }

  footer { border-top:1px solid var(--line); padding:1.6rem 0 3rem; color:var(--muted);
           font-size:.85rem; display:flex; justify-content:space-between; flex-wrap:wrap; gap:.6rem; }

  @media (max-width:760px) {
    .hero, .signature { grid-template-columns:1fr; }
    .pipe { grid-template-columns:1fr 1fr; }
    .eng { grid-template-columns:1fr; }
    nav .links a:nth-child(1) { display:none; }
  }
  @media (prefers-reduced-motion:reduce) { .rise { animation:none; } }
</style>
</head>
<body>
<div class="wrap">
  <nav>
    <div class="brand"><b>side</b>Out<span class="lab">Jump Lab</span></div>
    <div class="links">
      <a href="#how">How it works</a>
      <a href="https://github.com/ohmppatel920/sideout/blob/main/VALIDATION.md">Validation</a>
      <a href="https://github.com/ohmppatel920/sideout">GitHub ↗</a>
    </div>
  </nav>

  <header class="hero">
    <div>
      <div class="eyebrow">open-source · local-first · no cloud</div>
      <h1>See the jump<br>in the <em>numbers.</em></h1>
      <p class="lede">sideOut turns one side-view phone video into a full biomechanical
      readout — height, reach, timing — on your own machine.</p>
      <div class="cta">
        <a class="btn solid" href="https://github.com/ohmppatel920/sideout">View source</a>
        <a class="btn ghost" href="#how">How it works</a>
      </div>
    </div>
    <figure style="margin:0">
      <img class="clip" src="__OVERLAY__" alt="Annotated jump: pose skeleton with take-off and landing flags and a live metric readout">
      <figcaption class="clip-cap">Pose skeleton · LOAD / TAKEOFF / LANDING flags · live metric readout</figcaption>
    </figure>
  </header>

  <section id="reach">
    <div class="sec-head"><span class="n mono">01</span><h2>Reach, to scale</h2></div>
    <div class="signature">
      __REACH_SVG__
    </div>
  </section>

  <section id="metrics">
    <div class="sec-head"><span class="n mono">02</span><h2>Measured metrics</h2></div>
    <div class="readout">
      __READOUT__
    </div>
  </section>

  <section id="how">
    <div class="sec-head"><span class="n mono">03</span><h2>How it works</h2></div>
    <div class="pipe">
      <div class="step"><div class="k">01 · capture</div><h3>Side-view video</h3><p>An ordinary phone clip. Treated as source — never copied or committed.</p></div>
      <div class="step"><div class="k">02 · pose</div><h3>Keypoints</h3><p>MediaPipe tracks 33 body points per frame, on real timestamps.</p></div>
      <div class="step"><div class="k">03 · physics</div><h3>Metrics engine</h3><p>Detect the jump, then pure, unit-checked physics functions.</p></div>
      <div class="step"><div class="k">04 · output</div><h3>This page</h3><p>Annotated video, metrics JSON, and charts — regenerated from data.</p></div>
    </div>
  </section>

  <section id="engineering">
    <div class="sec-head"><span class="n mono">04</span><h2>Under the hood</h2></div>
    <div class="eng">
      <div><span class="c">✓</span><span>69 tests, 87% coverage — assert ground-truth recovery, not just "it runs"</span></div>
      <div><span class="c">✓</span><span>GitHub Actions CI: lint, type-check, tests on every push</span></div>
      <div><span class="c">✓</span><span>Fully typed and mypy-clean; pure, side-effect-free metric functions</span></div>
      <div><span class="c">✓</span><span>Reproducible env (uv + lockfile), one-command Docker</span></div>
      <div><span class="c">✓</span><span>Handles phone reality: variable frame rate, rotation, dropped frames</span></div>
      <div><span class="c">✓</span><span>Validated: error analysis + force-plate method comparison</span></div>
    </div>
    <div class="stack">
      <span class="chip">Python 3.11</span><span class="chip">MediaPipe</span><span class="chip">OpenCV</span>
      <span class="chip">NumPy</span><span class="chip">pandas · parquet</span><span class="chip">SciPy</span>
      <span class="chip">Typer CLI</span><span class="chip">pytest</span><span class="chip">ruff · mypy</span>
      <span class="chip">GitHub Actions</span><span class="chip">Docker</span>
    </div>
  </section>

  <footer>
    <span>Built by Ohm Patel · MIT-licensed</span>
    <span><a href="https://github.com/ohmppatel920/sideout">github.com/ohmppatel920/sideout</a></span>
  </footer>
</div>
<script>const METRICS = __METRICS_JSON__;</script>
</body>
</html>
"""


def build(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    metrics = json.loads((run_dir / "metrics.json").read_text())
    jump = metrics["jumps"][0] if metrics["jumps"] else {}

    ASSETS.mkdir(parents=True, exist_ok=True)
    overlay_mp4 = run_dir / "overlay.mp4"
    overlay_src = (
        "assets/overlay.gif"
        if overlay_mp4.exists() and _build_gif(overlay_mp4, ASSETS / "overlay.gif")
        else ""
    )

    html = (
        HTML.replace("__OVERLAY__", overlay_src)
        .replace("__REACH_SVG__", _reach_diagram(jump) or '<p class="reach-cap">Add --reach-cm to draw this.</p>')
        .replace("__READOUT__", _readout_rows(jump) or '<p class="rl">No jump detected.</p>')
        .replace("__METRICS_JSON__", json.dumps(metrics))
    )
    out = DEMO_DIR / "index.html"
    out.write_text(html)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python demo/build_demo.py runs/<run-dir>")
        raise SystemExit(2)
    print(f"Wrote {build(sys.argv[1])}")
