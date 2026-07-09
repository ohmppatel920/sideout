# sideOut

**sideOut** is an open-source, local-first volleyball performance-analysis toolkit. It turns ordinary side-view phone video into biomechanical insight — no cloud, no account, no GPU. The first module, **Jump Lab**, runs pose estimation on an attack approach and derives jump height, countermovement depth, loading time, approach velocity, and arm-swing timing, then produces an annotated video, a metrics JSON, and charts. It grew out of scouting a D1AAA national-championship team by hand; sideOut automates that work.

> Video is treated like source code: keypoints and metrics are derived artifacts. Raw videos are never committed — path references only.

## Module roadmap

- **Jump Lab** *(in progress)* — pose-estimation pipeline for attack approaches: jump height, countermovement depth, loading time, approach velocity, arm-swing timing.
- **Film Room** *(planned)* — rally/touch segmentation and searchable match film.
- **Shot Charts** *(planned)* — attack tendency and location charting.
- **Lineup Optimizer** *(planned)* — rotation and lineup analysis.

## Status

Early development. See [`SPEC.md`](SPEC.md) for the full architecture, stack, and phased build plan.

## License

MIT — see [`LICENSE`](LICENSE).
