"""Assemble a self-contained static demo page from a completed run.

Takes a run directory (metrics.json + charts + overlay.mp4 produced by
`sideout jump analyze`) and writes `demo/index.html` plus `demo/assets/`. The
overlay is transcoded to a browser-universal GIF (OpenCV's mp4v won't play in a
<video> tag, and ffmpeg isn't assumed present). Metrics are inlined so the page
works from `file://` and from GitHub Pages with no server, no fetch, no build.

    uv run python demo/build_demo.py runs/<run-dir>

The page is a *replay* of pipeline outputs — it contains zero physics logic.
The Python pipeline stays the single source of truth.

Design language ("court graphic"): FIVB court orange + white court lines +
sport-hall teal; Barlow Condensed for scoreboard/jersey display type; the
red/white net antenna as the section marker. One bold moment — the full-bleed
court panel holding the reach diagram — and quiet hairline structure elsewhere.
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
            small = cv2.resize(
                bgr, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA
            )
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


def _antenna_svg(x: float, net_y: float) -> str:
    """A small red/white striped net antenna rising from the net line.

    Real antennas mark the vertical boundary of legal play in ~10 cm red/white
    bands; here one sits on the drawn net line as a quiet, true-to-sport detail.
    """
    stripes = []
    for i in range(5):  # bottom stripe red, alternating upward
        fill = "#C8102E" if i % 2 == 0 else "#FFFFFF"
        stripes.append(
            f'<rect x="{x}" y="{round(net_y - 5 * (i + 1), 1)}" width="6" height="5" fill="{fill}"/>'
        )
    stripes.append(
        f'<rect x="{x}" y="{round(net_y - 25, 1)}" width="6" height="25" fill="none" '
        f'stroke="rgba(20,20,20,.3)" stroke-width="1"/>'
    )
    return "".join(stripes)


def _reach_diagram(jump: dict) -> str:
    """SVG: the athlete's reach drawn to scale against the net — the signature.

    Only rendered when touch height is available (needs --reach-cm). Drawn for
    the court panel: white court lines and type on court orange, the jump
    segment in ink on the white reach column, an antenna on the net line.
    """
    touch = jump.get("touch_height_m")
    if touch is None:
        return ""
    reach = (jump.get("touch_height_m") or 0) - jump["jump_height_m"]  # standing reach
    jump_m = jump["jump_height_m"]

    max_m = max(3.2, touch + 0.25)
    top, bottom, h = 30, 34, 340
    inner = h - top - bottom

    def y(m: float) -> float:
        return round(top + inner * (1 - m / max_m), 1)

    bar_x, bar_w = 108, 46
    ground = y(0)
    net_y = y(MENS_NET_M)
    parts = [f'<svg viewBox="0 0 360 {h}" role="img" aria-label="Reach to scale versus the net">']

    # metre lines — the court's own line language (ground line solid, rest faint)
    for m in range(0, int(max_m) + 1):
        yy = y(m)
        cls = "ground" if m == 0 else "grid"
        parts.append(f'<line class="{cls}" x1="52" y1="{yy}" x2="330" y2="{yy}"/>')
        parts.append(f'<text class="tick" x="44" y="{yy + 4}" text-anchor="end">{m} m</text>')

    # reach column: ground→standing-reach (white), standing-reach→touch (ink = the jump)
    parts.append(
        f'<rect class="bar-base rise" x="{bar_x}" y="{y(reach)}" width="{bar_w}" '
        f'height="{round(ground - y(reach), 1)}" rx="2"/>'
    )
    parts.append(
        f'<rect class="bar-jump rise" x="{bar_x}" y="{y(touch)}" width="{bar_w}" '
        f'height="{round(y(reach) - y(touch), 1)}" rx="2"/>'
    )

    # net reference line, antenna at its left end; label ABOVE the line (far
    # right) and the standing-reach marker BELOW it, so the line runs cleanly
    # between them even when reach ≈ net height (as it does for tall athletes).
    parts.append(f'<line class="net" x1="52" y1="{net_y}" x2="330" y2="{net_y}"/>')
    parts.append(_antenna_svg(56, net_y))
    parts.append(
        f'<text class="net-lbl" x="326" y="{net_y - 7}" text-anchor="end">men\'s net {MENS_NET_M:.2f} m</text>'
    )

    # markers
    lx = bar_x + bar_w + 12
    parts.append(f'<text class="mk-touch" x="{lx}" y="{y(touch) + 4}">touch {touch:.2f} m</text>')
    parts.append(
        f'<text class="mk-reach" x="{lx}" y="{y(reach) + 17}">standing reach {reach:.2f} m</text>'
    )

    over = touch - MENS_NET_M
    parts.append(
        f'<text class="mk-gain" x="{bar_x + bar_w / 2}" y="{y(touch) - 10}" text-anchor="middle">+{jump_m:.2f} m</text>'
    )
    parts.append("</svg>")
    caption = f"Flat-footed you reach the net; at the top of your jump you clear it by {over * 100:.0f} cm."
    side = (
        f'<div class="reach-side"><div class="big-stat"><span class="bs-n">{touch:.2f}</span>'
        f'<span class="bs-u">m</span></div><div class="bs-l">touch height</div>'
        f'<p class="reach-cap">{caption}</p></div>'
    )
    return f'<div class="reach">{"".join(parts)}</div>{side}'


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
<meta name="theme-color" content="#D14A24">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&family=Spline+Sans+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --court:#D14A24; --court-deep:#B03D1E; --teal:#0E6672; --ink:#16232B;
    --paper:#FBFBF8; --panel:#F1F2ED; --line:rgba(22,35,43,.16); --muted:#5C6A72;
  }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; background:var(--paper); color:var(--ink);
         font-family:"Barlow",-apple-system,Segoe UI,Roboto,sans-serif; line-height:1.55; }
  .disp { font-family:"Barlow Condensed","Barlow",sans-serif; }
  .mono { font-family:"Spline Sans Mono",ui-monospace,SFMono-Regular,Menlo,monospace; }
  a { color:var(--teal); text-decoration:none; }
  a:hover { text-decoration:underline; }
  :focus-visible { outline:2px solid var(--court); outline-offset:2px; }

  .wrap { max-width:1020px; margin:0 auto; padding:0 1.25rem; }
  nav { display:flex; align-items:center; justify-content:space-between; padding:1.05rem 0;
        border-bottom:1px solid var(--line); }
  .brand { font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:1.45rem;
           letter-spacing:.01em; color:var(--ink); }
  .brand b { color:var(--court); font-weight:700; }
  .brand .lab { display:inline-block; font-size:.66rem; font-weight:600; letter-spacing:.14em;
                text-transform:uppercase; color:var(--paper); background:var(--ink);
                border-radius:1px; padding:.2rem .5rem .16rem; margin-left:.6rem;
                transform:translateY(-3px); }
  nav .links { display:flex; gap:1.3rem; font-size:.93rem; font-weight:500; }
  nav .links a { color:var(--ink); }
  nav .links a:hover { color:var(--court); text-decoration:none; }

  .tape { width:46px; height:5px; background:var(--court); margin-bottom:1.1rem; }
  h1 { font-family:"Barlow Condensed",sans-serif; font-weight:700; text-transform:uppercase;
       font-size:clamp(2.9rem,6.5vw,4.4rem); line-height:.95; letter-spacing:.004em;
       margin:0 0 .9rem; }
  h1 em { font-style:normal; color:var(--court); }
  .lede { color:#46545C; font-size:1.08rem; max-width:36ch; margin:0; }

  .hero { display:grid; grid-template-columns:1.05fr .95fr; gap:3rem; align-items:center;
          padding:3.4rem 0 2.8rem; }
  .hero .cta { display:flex; gap:.7rem; margin-top:1.5rem; flex-wrap:wrap; }
  .btn { font-size:.95rem; font-weight:600; padding:.66rem 1.15rem; border-radius:3px;
         border:1.5px solid transparent; }
  .btn.solid { background:var(--court); color:#fff; }
  .btn.solid:hover { background:var(--court-deep); text-decoration:none; }
  .btn.ghost { border-color:var(--ink); color:var(--ink); }
  .btn.ghost:hover { background:var(--ink); color:var(--paper); text-decoration:none; }
  .facts { font-family:"Spline Sans Mono",monospace; font-size:.78rem; color:var(--muted);
           margin-top:1.35rem; }

  .clip { width:100%; max-height:70vh; display:block; margin:0 auto;
          border:1px solid var(--line); border-bottom:none; border-radius:4px 4px 0 0;
          background:#101820; }
  .clip-strip { display:flex; justify-content:space-between; gap:1rem; background:var(--ink);
                color:#fff; font-family:"Spline Sans Mono",monospace; font-size:.72rem;
                letter-spacing:.05em; padding:.52rem .8rem; border-radius:0 0 4px 4px; }

  section { padding:3rem 0; }
  .wrap > section { border-top:1px solid var(--line); }
  .sec-head { display:flex; align-items:center; gap:.68rem; margin-bottom:1.6rem; }
  .ant { width:6px; height:22px; flex:none; border-radius:2px 2px 0 0;
         background:repeating-linear-gradient(180deg,#C8102E 0 5px,#fff 5px 10px);
         box-shadow:inset 0 0 0 1px rgba(22,35,43,.22); }
  h2 { font-family:"Barlow Condensed",sans-serif; font-weight:700; text-transform:uppercase;
       font-size:1.18rem; letter-spacing:.07em; margin:0; }
  .sec-meta { margin-left:auto; font-family:"Spline Sans Mono",monospace; font-size:.72rem;
              letter-spacing:.05em; color:var(--muted); text-transform:uppercase; }

  /* signature: the court panel */
  .court-band { background:var(--court); color:#fff; }
  .court-band .sec-head { margin-bottom:1.2rem; }
  .court-band h2 { color:#fff; }
  .court-band .ant { box-shadow:inset 0 0 0 1px rgba(22,35,43,.35); }
  .signature { display:grid; grid-template-columns:minmax(300px,400px) 1fr; gap:3rem;
               align-items:center; }
  .reach svg { width:100%; height:auto; }
  .reach .grid { stroke:rgba(255,255,255,.42); stroke-width:1; }
  .reach .ground { stroke:#fff; stroke-width:2; }
  .reach .tick { fill:#fff; font:500 11.5px "Spline Sans Mono",monospace; }
  .reach .net { stroke:#fff; stroke-width:2.5; stroke-dasharray:7 5; }
  .reach .net-lbl { fill:#fff; font:600 12px "Barlow Condensed",sans-serif; letter-spacing:.04em; }
  .reach .bar-base { fill:#fff; }
  .reach .bar-jump { fill:var(--ink); }
  .reach .mk-touch { fill:#fff; font:700 15px "Barlow Condensed",sans-serif; letter-spacing:.02em; }
  .reach .mk-reach { fill:#fff; font:500 13px "Barlow",sans-serif; }
  .reach .mk-gain { fill:#fff; font:700 17px "Barlow Condensed",sans-serif; }
  .reach-cap { color:#fff; font-size:1.02rem; font-weight:500; max-width:30ch;
               line-height:1.5; margin:0; }
  .reach-side .big-stat { display:flex; align-items:baseline; gap:.45rem; }
  .bs-n { font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:4.8rem;
          line-height:1; color:#fff; font-variant-numeric:tabular-nums; }
  .bs-u { font-family:"Barlow Condensed",sans-serif; font-weight:600; font-size:1.6rem; color:#fff; }
  .bs-l { font-family:"Spline Sans Mono",monospace; font-size:.75rem; letter-spacing:.14em;
          text-transform:uppercase; color:#fff; margin:.25rem 0 1.1rem; }
  .rise { transform-box:fill-box; transform-origin:bottom; animation:rise .9s cubic-bezier(.2,.7,.2,1) both; }
  @keyframes rise { from { transform:scaleY(0); } to { transform:scaleY(1); } }

  /* the box score */
  .score { border-top:2.5px solid var(--ink); }
  .score .row { display:flex; justify-content:space-between; align-items:baseline;
                padding:.88rem .1rem; border-bottom:1px solid var(--line); }
  .rl { font-weight:500; font-size:.97rem; color:#3E4C55; }
  .rv { font-family:"Barlow Condensed",sans-serif; font-weight:700; font-size:1.75rem;
        font-variant-numeric:tabular-nums; }
  .ru { font-family:"Spline Sans Mono",monospace; font-size:.74rem; font-weight:400;
        color:var(--muted); margin-left:.35rem; }

  /* pipeline — a true sequence, so it keeps its numbers */
  .pipe { display:grid; grid-template-columns:repeat(4,1fr); gap:1.4rem; }
  .step { border-top:2.5px solid var(--ink); padding-top:.75rem; }
  .step .k { font-family:"Spline Sans Mono",monospace; color:var(--court); font-size:.72rem;
             letter-spacing:.07em; text-transform:uppercase; }
  .step h3 { font-size:1rem; font-weight:600; margin:.3rem 0 .25rem; }
  .step p { color:var(--muted); font-size:.86rem; margin:0; }

  /* engineering highlights */
  .eng { display:grid; grid-template-columns:1fr 1fr; gap:.7rem 2rem; }
  .eng div { display:flex; gap:.6rem; font-size:.93rem; padding:.15rem 0; }
  .eng .c { color:var(--teal); font-family:"Spline Sans Mono",monospace; }
  .stack { font-family:"Spline Sans Mono",monospace; font-size:.78rem; color:var(--muted);
           margin-top:1.5rem; line-height:1.9; }

  footer { border-top:1px solid var(--line); padding:1.8rem 0 3.2rem; color:var(--muted);
           font-size:.87rem; display:flex; justify-content:space-between; flex-wrap:wrap;
           gap:.6rem 2rem; }
  footer .who { max-width:60ch; }

  @media (max-width:760px) {
    .hero { grid-template-columns:1fr; gap:2rem; padding-top:2.4rem; }
    .signature { grid-template-columns:1fr; gap:1.8rem; }
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
      <div class="tape"></div>
      <h1>See the jump<br>in the <em>numbers.</em></h1>
      <p class="lede">sideOut turns one side-view phone video into a full biomechanical
      readout — height, reach, timing — on your own machine.</p>
      <div class="cta">
        <a class="btn solid" href="https://github.com/ohmppatel920/sideout">View source</a>
        <a class="btn ghost" href="#how">How it works</a>
      </div>
      <p class="facts">runs on your laptop · no cloud · no account · open source</p>
    </div>
    <figure style="margin:0">
      <img class="clip" src="__OVERLAY__" alt="Annotated jump: pose skeleton with take-off and landing flags and a live metric readout">
      <div class="clip-strip"><span>POSE · LOAD → TAKEOFF → LANDING</span><span>__FLIGHT__</span></div>
    </figure>
  </header>
</div>

<section class="court-band" id="reach">
  <div class="wrap">
    <div class="sec-head"><span class="ant"></span><h2>Reach, to scale</h2></div>
    <div class="signature">
      __REACH_SVG__
    </div>
  </div>
</section>

<div class="wrap">
  <section id="metrics">
    <div class="sec-head"><span class="ant"></span><h2>The box score</h2><span class="sec-meta">__SCORE_META__</span></div>
    <div class="score">
      __READOUT__
    </div>
  </section>

  <section id="how">
    <div class="sec-head"><span class="ant"></span><h2>How it works</h2></div>
    <div class="pipe">
      <div class="step"><div class="k">01 capture</div><h3>Side-view video</h3><p>An ordinary phone clip. Treated as source — never copied or committed.</p></div>
      <div class="step"><div class="k">02 pose</div><h3>Keypoints</h3><p>MediaPipe tracks 33 body points per frame, on real timestamps.</p></div>
      <div class="step"><div class="k">03 physics</div><h3>Metrics engine</h3><p>Detect the jump, then pure, unit-checked physics functions.</p></div>
      <div class="step"><div class="k">04 output</div><h3>This page</h3><p>Annotated video, metrics JSON, and charts — regenerated from data.</p></div>
    </div>
  </section>

  <section id="engineering">
    <div class="sec-head"><span class="ant"></span><h2>Under the hood</h2></div>
    <div class="eng">
      <div><span class="c">✓</span><span>69 tests, 87% coverage — assert ground-truth recovery, not just "it runs"</span></div>
      <div><span class="c">✓</span><span>GitHub Actions CI: lint, type-check, tests on every push</span></div>
      <div><span class="c">✓</span><span>Fully typed and mypy-clean; pure, side-effect-free metric functions</span></div>
      <div><span class="c">✓</span><span>Reproducible env (uv + lockfile), one-command Docker</span></div>
      <div><span class="c">✓</span><span>Handles phone reality: variable frame rate, rotation, dropped frames</span></div>
      <div><span class="c">✓</span><span>Validated: error analysis + force-plate method comparison</span></div>
    </div>
    <p class="stack">Python 3.11 · MediaPipe · OpenCV · NumPy · pandas / parquet · SciPy · Typer · pytest · ruff · mypy · GitHub Actions · Docker</p>
  </section>

  <footer>
    <span class="who">Built by Ohm Patel — captain of Brown men's volleyball's D1AAA
    national-championship team, automating the scouting he did by hand. MIT-licensed.</span>
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

    flight = (metrics.get("aggregates") or {}).get("mean_flight_time_s")
    flight_label = f"FLIGHT {flight:.2f} S" if flight is not None else "NO JUMP DETECTED"
    n = metrics.get("n_jumps", 0)
    score_meta = f"jump 1 of {n} · {'calibrated' if metrics.get('calibrated') else 'uncalibrated'}"

    html = (
        HTML.replace("__OVERLAY__", overlay_src)
        .replace("__FLIGHT__", flight_label)
        .replace("__SCORE_META__", score_meta)
        .replace(
            "__REACH_SVG__",
            _reach_diagram(jump) or '<p class="reach-cap">Add --reach-cm to draw this.</p>',
        )
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
