# Notes — gta6-twitch-ccu-forecast-01 (overhaul, 2026-11-17)

## Live result of the shipped version (v1)

- Practice loss **0.194**, rank **979 / 2,773**, typical miss 32.7%,
  coverage of the 90% interval **0.978** (nominal 0.90 — intervals too wide).

## Diagnosis (leave-one-out on the kit's 4 practice cases)

- The console-only tier-comparable rolling-midnight training pool is **7
  launches**. Every per-hour regression is fit from 6 points in LOO.
- The spread floor `0.15 * sqrt(hour - 1)` reaches 0.72 by hour 24 and is
  the main cause of the over-coverage.
- Shrinking each hour's slope halfway toward the pooled slope hurts.
- The median (level 0.5) loses the most; the loss is largest in late hours
  on diverse targets, fairly flat across hours on console targets.
- LOO is a *relative* tool: the server scorer and reference data are sealed,
  so absolute live loss cannot be reproduced locally. Variant differences
  under ~0.005 on console LOO are noise (only 28 console targets).

## What changed in v2 (this main.py)

- Spread floor capped at **0.30**; slope shrinkage **removed**.
- Slope is the **Theil-Sen** estimate (median pairwise slope) with a
  **median intercept** — robust to one odd launch in a 6–7 point fit.
- Fitted medians **smoothed over a 3-hour window**.
- Console LOO: **0.0729** vs 0.0846 for v1 (−13.8%), coverage 0.894,
  median miss 19.8% (v1: 23.9%).

## Ideas tested and REJECTED (all made console LOO worse)

| Idea | Console LOO |
| --- | --- |
| v1 (shipped) | 0.0846 |
| Add all comparable rolling launches incl. PC | 0.156–0.164 |
| Add all usable comparables | 0.164 |
| Kernel-weighted regression on log print | 0.127–0.150 |
| Adaptive spread (widen when target print is far from pool) | 0.133–0.171 |
| Pre-release diurnal-profile similarity weighting (bw 0.5 / 1.0) | 0.0759 / 0.0751 |
| Peak-hour landmark registration (align to hour 19) | 0.0763 |
| Saturating size effect (ratio → 1 as print grows) | 0.0805 |
| Direct pinball quantile regression (IRLS, per hour per level) | 0.0870 (coverage 0.53) |
| Conformal (CQR) correction from LOO scores | 0.0757 |
| Viewers-per-channel as second regressor | 0.0863 |
| Pooled slope shared across hours | 0.0852 |
| Slope forced to 0 (intercept only) | 0.1085 |

The fancy ideas fail for the same reason: with 6–7 training points, extra
structure adds variance faster than it adds signal. The winning changes are
all variance *reductions* (capped floor, robust slope, smoothing).
