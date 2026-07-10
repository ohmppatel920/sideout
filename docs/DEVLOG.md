# Dev Log — sideOut, in plain English

A running, jargon-light log of **what we built, why, and how we check it's right**.
Newest entries at the bottom. If you read only one file to understand the
project, read this one. (The formal, technical version lives in
[`../SPEC.md`](../SPEC.md).)

---

## The one-sentence version

sideOut takes a **side-view phone video of a volleyball approach** and measures
the jump — how high, how deep the crouch, how fast the run-up, arm-swing timing —
then produces numbers, charts, and an annotated video. All on your own laptop,
no cloud.

---

## The big decision (start of the project)

The original plan was a solid command-line tool. We asked one question:
**what makes this most impressive to a recruiter, efficiently?** The answer
shaped everything:

- **Keep the engine as-is.** The core idea (video → data → physics) is already
  the strong, differentiated part. We did *not* redesign it.
- **Add proof and a demo around it.** Two additions do the heavy lifting:
  1. **Validation** — don't just compute a jump height, *show it's accurate*
     by comparing against known reference numbers. (Phase 5)
  2. **A clickable web demo** — recruiters click links, they don't download
     code. A web page that shows a real jump analyzed. (Phase 6)
- **Skip the flashy-but-risky stuff** (a machine-learning model bolted on for
  its own sake). It adds work and can look gimmicky.

We call this "Approach 2" in the notes. Full phase list is in the SPEC.

---

## How the system works (the mental model)

Think of it as an **assembly line**. Each station does one job and hands off a
clean result to the next:

```
video file
   │   (Station 1: "pose estimation" — find the body in each frame)
   ▼
keypoints  = the (x, y) location of 33 body points, every frame
   │   (Station 2: smooth the data, find the jump events)
   ▼
events     = the exact moments: crouch starts, feet leave ground, feet land
   │   (Station 3: the physics — turn moments + positions into real numbers)
   ▼
metrics    = jump height, crouch depth, run-up speed, arm-swing timing
   │   (Station 4, later: draw them on the video + make charts)
   ▼
outputs
```

**One rule underpins all of it:** the video is the *only* raw ingredient. Every
station after it produces *derived* data we can always recreate by re-running.
So we **never save copies of video** into the project — just the small data
files. (This keeps the project lightweight and is good engineering hygiene.)

### The two ideas worth knowing

1. **We use real timestamps, never "assume 30 frames per second."** Phone videos
   don't record at a perfectly steady rate. Every physics number depends on
   *time*, so we read the true time of each frame from the video. Guessing the
   frame rate would silently corrupt every measurement.

2. **"Down" is positive.** In an image, the y-axis grows *downward* (row 0 is the
   top). So when the athlete jumps *up*, the number goes *down*. This flips the
   sign in a bunch of formulas. We comment it everywhere because it's exactly the
   kind of thing that causes subtle, hard-to-catch bugs.

---

## How we build and check quality (the process)

Two habits, borrowed from how good engineering teams work:

- **Tests written alongside the code, using "synthetic" jumps.** We generate a
  *fake* jump where we already know the true answer (e.g. "this jump is exactly
  0.5 seconds of airtime"), run it through the engine, and check the engine
  recovers that number. If the math is wrong, a test fails immediately. This is
  far stronger than "it ran without crashing."

- **A separate "reviewer" checks the work with fresh eyes.** After each phase,
  we spin up independent reviewer agents that *didn't write the code* and whose
  only job is to attack it — wrong physics signs, bad units, weak tests, any
  video accidentally committed. Anything they flag, a second agent tries to
  *disprove* before we trust it. Only real issues get fixed. This catches
  mistakes the author is blind to.

---

## Progress so far

**Setup.** Repo on GitHub, Python environment, automatic guardrails (a rule that
literally *blocks* committing a video by accident, and one that runs the tests
after every code change).

**Phase 1 — get the body out of the video.** Runs Google's MediaPipe pose model
over every frame and saves the 33 body points to a data file, plus a summary
(how many frames, real frame rate, how confident it was about ankles/hips/wrists).
The fresh-eyes review found 14 possible issues; 9 held up under scrutiny and were
fixed — the two biggest: a timestamp bug that could corrupt data, and a
model-download that could leave a broken file behind. ✅ Committed.

**Phase 2 — find the jump and do the physics.** The core. Detects the crouch,
takeoff, and landing moments, then computes the five metrics as pure math
functions (each labeled with its units and the formula's origin). Backed by a
suite of synthetic-jump tests. **47 tests pass.**

The fresh-eyes review (its first run was cut off by a usage limit, then re-run
to completion) raised 12 possible issues; independent double-checking confirmed
**3 real ones**, all now fixed:
1. a jump cut off by the end of the video could be reported with a too-short
   airtime instead of being ignored (would understate jump height);
2. "ground level" was measured from the *average* of both ankles — wrong for a
   running approach where one foot is always lifted; now uses the planted foot;
3. a calibration test was quietly circular (would have passed even with a
   mistyped body-proportion number); rewritten to actually catch that.
The other 9 were false alarms or style nitpicks and were dismissed with reasons.

**Housekeeping — removed the "Co-Authored-By: Claude" tag.** Turned it off for
future commits (a one-line setting) and rewrote the 4 commits already on GitHub
to strip it, so the history reads as fully yours.

**A note on the real sample clip.** Your `demo.mov` is busy match footage with
many players near the net, so the pose model sometimes locks onto the wrong
person. With the higher-accuracy model setting it does find a clean jump
(~0.38 s airtime). For the polished demo we'll want a clip with one athlete
clearly in frame — more on that when we get to Phase 6.

---

## Mini-glossary

- **Pose estimation** — software that finds where a person's joints are in an image.
- **Keypoints** — the list of joint locations (shoulder, hip, ankle, …) per frame.
- **Metric** — one measured number (e.g. jump height in meters).
- **Flight time** — how long the feet are off the ground; jump height comes from
  this via basic physics (`height = gravity × time² / 8`).
- **Commit / push** — save a snapshot of the code / upload it to GitHub.
- **Test suite** — the automated checks that prove the math is right.
