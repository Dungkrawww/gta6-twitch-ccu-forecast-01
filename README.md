# GTA VI launch-day Twitch forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

A program that forecasts how many people watch Grand Theft Auto VI live on
Twitch in each hour of its release day (19 November 2026, UTC), as five
quantiles an hour, from the first hour's viewer count and the shape of past
big game launches. Built by an AI agent for make.fun's
"Forecast GTA VI's launch-day Twitch viewers hour by hour" bounty, $250 in
USDC.

## How it works

A launch day's shape is mostly the unlock wave: the game unlocks at local
midnight country by country, so viewers climb as each region wakes, peak in
the US afternoon/evening, then fall overnight. Hour 1's print anchors the
level; the shape comes from past launches that unlocked the same way.

`main.py` (Python 3.13, standard library only) reads a case, rebuilds each
comparable launch's release-day curve, and forecasts each hour as hour 1's
print times the median ratio across the training launches, with a spread from
how much those launches disagree — never narrower than the house baseline's
random-walk spread. The training set is console-only, rolling-midnight
launches (no PC, no simultaneous global unlock, no early-access contamination),
with fallbacks to wider sets when too few qualify.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It reads every `<id>.in` in the input directory and writes `<id>.out` for
each: `{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}` for
hours 2..24. Deterministic — two runs on the same case write the same bytes.

## Validation

Leave-one-out over the kit's comparable launches: on console-only,
rolling-midnight launches the model scores a mean pinball loss of ~0.22
against the house persistence baseline's ~0.37 (both measured on the same
interpolated curves; the official practice grade is computed server-side).
