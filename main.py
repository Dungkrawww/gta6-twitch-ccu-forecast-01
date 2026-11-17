"""Forecast Grand Theft Auto VI's launch-day Twitch viewers, hour by hour.

The entry point for make.fun's gta6-twitch-ccu-forecast-01 (program/v1, Python
3.13, standard library only). The grader runs `python3 -P -s /bot/main.py` in a
sandbox with no network; the program reads one case file per run from the input
directory and writes one forecast file per case to the output directory.

What a case holds (schema makefun/twitch-ccu-case/v1): the game's Twitch
category, the UTC release day's first instant, the end of hour 1 (the
checkpoint), hour 1's print (`known`: the mean concurrent viewers of the
release day's first hour), the 23 hours to forecast, the history recorded
before the checkpoint, and `comparables`: past big game launches' hourly
Twitch curves from 14 days before to 3 days after their own release days.

How the forecast is made
-------------------------
A launch day's shape is mostly the unlock wave: the game unlocks at local
midnight country by country, so viewers climb as each region wakes and plays,
peak in the US afternoon/evening, then fall overnight. Hour 1's print anchors
the level; the shape comes from past launches that unlocked the same way.

For every comparable launch we rebuild its release-day curve (log viewers
interpolated between its hourly points) and take, per hour h, the ratio of
that hour's viewers to its own hour-1 print. The forecast median for hour h
is hour 1's print times the median ratio across the training launches; the
spread is the per-hour spread of those log-ratios, never narrower than the
house baseline's random-walk spread. That makes the five quantiles honest
about how much launch days differ from each other.

Which launches train the shape matters more than anything else. A launch
that unlocked everywhere at one instant, or one whose early-access week had
already burned off the launch-day surge, has a release-day curve shaped
nothing like a rolling-midnight console launch, and a PC launch's curve is
driven by a different audience. So the training set is, in order of
preference:

1. console-only launches (no PC in their platforms) whose tier is
   "comparable" and whose unlock rolled at local midnight, and
2. failing that, any tier-"comparable" rolling-midnight launch, and
3. failing that, any comparable with a usable release-day curve, and
4. failing that, the house baseline's persistence forecast.

The target game's own pre-release history (its category existed months
before launch) is never a training launch: it has no release day in it.

Every step is deterministic: comparables are considered in name order, the
quantile and spread functions sort their inputs, and nothing random is used,
so two runs on the same case write the same bytes.

Limits the grader enforces: at most 8 seconds, 1 CPU and 1024 MB per case;
the output is at most 65,536 bytes of JSON with exactly the key `hours` and
exactly 23 rows, hours 2..24 each once, each row five finite numbers above 0
and at most 1e9, non-decreasing.
"""

import json
import math
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is a single file.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
# The house baseline's log-spread per square-root hour; our spread is never
# narrower than this, so a small training set cannot make us overconfident.
BASE_SIGMA = 0.15
# A training launch needs its hour-1 point and this many of the 24 release-day
# hours present (after interpolation) to be usable at all.
MIN_DAY_HOURS = 18
# A training set smaller than this falls back to a wider set.
MIN_TRAINING = 4
# The widest gap, in hours, log-viewers may be interpolated across.
MAX_GAP_HOURS = 13.0


def parse_time(text):
    """An ISO 8601 UTC timestamp into a datetime (accepts a trailing Z)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def interp_log(points, x):
    """Log-viewers at hour-offset x, linearly interpolated between the points.

    `points` is a sorted list of (hour-offset, log viewers). Returns None when
    x is outside the covered range, or when the enclosing gap is wider than
    MAX_GAP_HOURS (SullyGnome samples a quiet category only about every 12
    hours, so a long gap means the curve is not really known there). Up to two
    hours past the last point the last value is carried flat, so the final
    hour of a release day is still covered.
    """
    if not points or x < points[0][0] or x > points[-1][0] + 2.0:
        return None
    if x > points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 - x0 > MAX_GAP_HOURS:
                return None
            if x1 == x0:
                return y0
            f = (x - x0) / (x1 - x0)
            return y0 * (1.0 - f) + y1 * f
    if abs(x - points[-1][0]) < 1e-9:
        return points[-1][1]
    return None


def release_day_curve(comp):
    """A comparable's release-day curve as {hour: viewers}, hours 1..24.

    Each hour's value is the interpolated log-viewers at the hour's midpoint.
    Returns None when the curve has no hour-1 value or too few hours.
    """
    day_start = parse_time(comp["day_start"])
    points = []
    for row in comp.get("hourly") or []:
        viewers = row.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        offset = (parse_time(row["from"]) - day_start).total_seconds() / 3600.0
        if -0.5 <= offset < 24.0:
            points.append((offset, math.log(viewers)))
    points.sort()
    curve = {}
    for hour in range(1, 25):
        value = interp_log(points, hour - 0.5)
        if value is not None:
            curve[hour] = math.exp(value)
    if 1 not in curve or len(curve) < MIN_DAY_HOURS:
        return None
    return curve


def tier_of(comp):
    """The research tier carried in the unlock note, if any is named."""
    unlock = (comp.get("unlock") or "").lower()
    marker = "tier:"
    at = unlock.find(marker)
    if at < 0:
        return None
    rest = unlock[at + len(marker):].strip()
    word = []
    for ch in rest:
        if ch.isalpha() or ch == "-":
            word.append(ch)
        else:
            break
    return "".join(word) or None


def is_console_only(comp):
    """True when no PC platform is listed for the launch."""
    platforms = (comp.get("platforms") or "").lower()
    for token in platforms.split(","):
        token = token.strip()
        if token == "pc" or token.startswith("pc ") or token.startswith("pc/"):
            return False
    return True


def unlocked_everywhere_at_once(comp):
    """True when the launch unlocked at one instant worldwide, not rolling."""
    unlock = (comp.get("unlock") or "").lower()
    if "single global unlock" in unlock or "single simultaneous global" in unlock:
        return True
    return "simultaneous" in unlock and "midnight local" not in unlock


def pick_training(comps):
    """The training launches, best set first, with fallbacks.

    Returns a list of release-day curves ({hour: viewers}) in name order.
    """
    usable = []
    for comp in sorted(comps, key=lambda c: c.get("name") or ""):
        curve = release_day_curve(comp)
        if curve is not None:
            usable.append((comp, curve))
    console = [
        curve
        for comp, curve in usable
        if tier_of(comp) == "comparable"
        and is_console_only(comp)
        and not unlocked_everywhere_at_once(comp)
    ]
    if len(console) >= MIN_TRAINING:
        return console
    rolling = [
        curve
        for comp, curve in usable
        if tier_of(comp) == "comparable" and not unlocked_everywhere_at_once(comp)
    ]
    if len(rolling) >= MIN_TRAINING:
        return rolling
    if len(usable) >= MIN_TRAINING:
        return [curve for _, curve in usable]
    return []


def median(values):
    """The median of a non-empty sorted list (linear interpolation)."""
    ordered = sorted(values)
    n = len(ordered)
    mid = (n - 1) / 2.0
    lo = int(mid)
    hi = min(lo + 1, n - 1)
    frac = mid - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def round_half_up_2dp(x):
    """x rounded to 2 decimals, half up; a whole number comes back as int."""
    scaled = math.floor(x * 100.0 + 0.5) / 100.0
    return int(scaled) if float(scaled).is_integer() else scaled


def baseline_quantiles(p1, hour):
    """The house baseline's persistence quantiles for one hour."""
    spread = BASE_SIGMA * math.sqrt(hour - 1)
    return [round_half_up_2dp(p1 * math.exp(z * spread)) for z in Z]


def forecast_case(case, name):
    """The 23-row forecast for one case."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))

    training = pick_training(case.get("comparables") or [])
    rows = []
    for row in case["forecast"]:
        hour = row["hour"]
        if not training:
            quantiles = baseline_quantiles(p1, hour)
        else:
            log_ratios = sorted(
                math.log(curve[hour] / curve[1])
                for curve in training
                if hour in curve and 1 in curve
            )
            if len(log_ratios) < MIN_TRAINING:
                quantiles = baseline_quantiles(p1, hour)
            else:
                middle = median(log_ratios)
                spread = statistics.pstdev(log_ratios)
                floor = BASE_SIGMA * math.sqrt(hour - 1)
                if spread < floor:
                    spread = floor
                quantiles = []
                for z in Z:
                    value = p1 * math.exp(middle + z * spread)
                    if value < 1.0:
                        value = 1.0
                    if value > 1e9:
                        value = 1e9
                    quantiles.append(round_half_up_2dp(value))
                # Rounding can only keep the order (exp is monotone), but
                # enforce it outright so the row is valid whatever happens.
                for i in range(1, len(quantiles)):
                    if quantiles[i] < quantiles[i - 1]:
                        quantiles[i] = quantiles[i - 1]
        rows.append({"hour": hour, "q": quantiles})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
