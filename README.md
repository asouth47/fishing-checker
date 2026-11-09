# Fishing checker

Every morning between about 4:45 and 6:15am Darwin time, GitHub runs `checker.py` for free. It:

1. Grabs the tide and weather forecast for Weed Reef, Elizabeth River, Adelaide River mouth and Dundee Beach.
2. Scores each spot out of 5: wind (0-3) + tide size (0-2), minus 1 if rain is likely.
3. Lists the best windows around each tide change, and flags any that line up with dawn or dusk.
4. Saves the result to `REPORT.md`, with a copy in `reports/`.
5. Opens a GitHub **issue** with the report. GitHub emails you about it, so that's your morning ping.

## Where things are

| File | What it is |
|---|---|
| `checker.py` | The brains. The **SETTINGS** block at the top holds the spots and thresholds. |
| `.github/workflows/daily.yml` | The timer: when to run and what to do afterwards. |
| `REPORT.md` | Today's outlook. |
| `reports/` | One file per day, so you build up a history. |

## Run it now

**Actions** tab → **Daily fishing outlook** → **Run workflow**.

## Tweak it

- **Add a spot:** add a line to `SPOTS` with a name, latitude and longitude.
- **Change what counts as too windy:** edit `WIND_GREAT`, `WIND_OK` and `WIND_MARGINAL` (knots).
- **Change the time:** edit the `cron` line. It's in UTC, and Darwin is UTC+9:30.

## Caveats

- Tides come from Open-Meteo's ocean model, not the official BOM tables. The model runs about 70 min early, so `checker.py` adds a correction (`TIDE_TIME_OFFSET_MIN`). Expect times within about 20-30 min. Use it to spot good days, and check the BOM chart before you launch.
- Rules and closures change, so check current NT Fisheries regulations.
