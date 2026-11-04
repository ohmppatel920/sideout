# Market sizing & competitive benchmark

Why sideOut exists, and what it competes against. Prices are public list prices, checked
November 2026. Sources are at the bottom.

## The segment: collegiate club volleyball

Collegiate club teams are self-funded: dues, fundraising, and a small student-activities
budget. They play a full season and travel to a national championship, but the video and
analytics tools on the market are priced for programs with an athletic-department budget.

- **648 teams** played the 2026 NCVF Championships (348 men's, 300 women's) [1]. That's
  only the teams that travel to nationals, so the full club population is larger. Treat 648
  as a floor.
- The field keeps growing: 266 teams in 2010, 489 in 2022, 635 in 2025, 648 in 2026 [2].

## Incumbent spend per account

Hudl is the incumbent in team video. Its published club volleyball plans [3]:

| Hudl plan | List price | Notes |
|---|---:|---|
| Core | $500 / team / yr | Only sold inside multi-team or club-wide packages |
| **Plus** | **$1,250 / team / yr** | Lowest plan a single team can buy. Adds analyst breakdowns, rotational stats, heatmaps |
| Premier | $1,600 / team / yr | Adds scouting reports, setter analysis, defensive positioning |

So a single college club team that wants Hudl's analysis pays **about $1,200–$1,250 a year**.
That's the benchmark sideOut is priced against: $0.

**Segment size at incumbent pricing:** 648 teams × $1,250 ≈ **$0.81M a year** of
list-price spend. Many of these teams can't justify that out of dues, which is why the
segment is underserved, not saturated.

## Competitive benchmark: features and price

| | Hudl (club) | Balltime (Hudl) | Kinovea (open source) | **sideOut** |
|---|---|---|---|---|
| Price | $500–$1,600 / team / yr [3] | $20/mo player; $299/yr recruiting; team plans by quote [4] | Free | **Free (MIT)** |
| Unit | Team subscription | Per-athlete subscription | Desktop app | CLI / Docker / browser demo |
| Account / cloud upload | Required | Required | No | **No (runs locally)** |
| Match video + stats | Yes | Yes | No | No (not the focus) |
| Jump height | Attack height [3] | Vertical jump detection [4] | Manual, frame by frame | **Automatic (flight-time physics)** |
| Approach velocity | No | No | Manual | **Yes (m/s)** |
| Countermovement depth / loading time | No | No | Manual | **Yes** |
| Arm-swing timing | No | No | Manual | **Yes** |
| Touch height (reach at apex) | No | No | No | **Yes** |
| Published accuracy analysis | No | No | n/a | **Yes ([VALIDATION.md](VALIDATION.md))** |

## The gap sideOut targets

The incumbents sell **match analytics** (what happened in the game) per team or per athlete,
through the cloud. Nobody gives a club team **approach-jump biomechanics** for free from one
phone video: depth, loading time, approach speed, and arm-swing timing. Those are the numbers
a coach uses to fix a hitter's approach. Kinovea can measure them, but only by hand-marking
frames.

**Staged entry plan**
1. **v0.1 (shipped):** Jump Lab. One side-view clip in; jump height, touch height, depth,
   loading time, approach velocity, and arm-swing timing out. Free and local. Tested: 69 tests,
   87% coverage, CI on every push.
2. **v0.2 (spec'd):** in-browser analysis, so a player can drop in a clip with no install
   ([design](docs/superpowers/specs/2026-07-20-v0.2-in-browser-analyze-design.md)).
3. **Next:** session tracking across a season (is this hitter's approach getting faster?),
   then serve and arm-swing modules. Teams that outgrow it can export to the tools they
   already pay for.

## Sources

1. NCVF, "2026 NCVF Championships": https://ncvf.org/news/2025/12/1/2026-ncvf-championships
2. NCVF, National Tournament History: https://ncvf.org/championships-history
3. Hudl, Club Volleyball Pricing: https://www.hudl.com/pricing/club/volleyball
4. Hudl, Balltime Pricing for Individuals: https://www.hudl.com/pricing/balltime
