"""
Darwin fishing checker.

Runs once a day (via GitHub Actions), pulls the tide and weather forecast for a
few spots around Darwin, scores the day, and writes a short report.

Data: Open-Meteo (free, no account or key needed).
  - Tides come from Open-Meteo's marine model (sea_level_height_msl). It's a
    model, not the official BOM tide tables, so times can be out by ~30 min and
    heights won't match the tide chart exactly. Good enough to spot neaps vs
    springs and roughly when the tide turns.

Everything you'd want to tweak is in the SETTINGS block below.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# ----------------------------------------------------------------- SETTINGS --

SPOTS = [
    # name,                       latitude, longitude
    ("Weed Reef (Darwin Harbour)", -12.45, 130.79),   # approximate - adjust if needed
    ("Elizabeth River",            -12.54, 130.98),
    ("Adelaide River mouth",       -12.22, 131.23),
    ("Dundee Beach",               -12.73, 130.38),
]

TIMEZONE = "Australia/Darwin"

# Wind, in knots, averaged over 6am-2pm.
WIND_GREAT = 10   # at or below: glassy-ish, any spot is fishable
WIND_OK = 15      # at or below: fine in the harbour, choppy outside
WIND_MARGINAL = 20  # at or below: sheltered spots only. Above: poor.

# Tide size is judged against the biggest tide in the coming week, so it
# doesn't matter if the model's heights are a bit off.
NEAP_BELOW = 0.65    # today's range < 65% of the week's biggest = neap-ish
SPRING_ABOVE = 0.88  # today's range > 88% of the week's biggest = springs

# The tide model runs early in Darwin Harbour. Checked against published Darwin
# tide times on 9 Nov 2026: model was ~70 min early on every change.
TIDE_TIME_OFFSET_MIN = 70

# The model gives heights above/below mean sea level. Tide tables (BOM,
# WillyWeather, your sounder charts) measure from the lowest tide (chart datum).
# Mean sea level in Darwin Harbour sits about 3.7 m above that - checked against
# the BOM Darwin table on 9 Nov 2026 (6.61 / 0.97 / 7.33 m). Applied to every
# spot, so Adelaide River mouth and Dundee will be close but not exact.
TIDE_DATUM_OFFSET_M = 3.7

RAIN_WARN = 60  # % chance of rain at any point in the day that knocks a point off

# A "window" is this long either side of each tide change (hours).
WINDOW_BEFORE = 1.0
WINDOW_AFTER = 1.5

# ------------------------------------------------------------------ FETCHING --

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def get_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "fishing-checker"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_spot(lat, lon):
    marine = get_json(MARINE_URL, {
        "latitude": lat, "longitude": lon,
        "hourly": "sea_level_height_msl",
        "timezone": TIMEZONE, "forecast_days": 8,
        "cell_selection": "sea",
    })
    weather = get_json(WEATHER_URL, {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation_probability",
        "daily": "sunrise,sunset",
        "wind_speed_unit": "kn",
        "timezone": TIMEZONE, "forecast_days": 2,
    })
    return marine, weather


# ----------------------------------------------------------------- ANALYSIS --

def parse_times(strings):
    return [datetime.fromisoformat(s) for s in strings]


def tide_turns(times, heights):
    """Find highs and lows. Uses a parabola through 3 hourly points to
    estimate the actual turning time between the hours."""
    turns = []
    for i in range(1, len(heights) - 1):
        a, b, c = heights[i - 1], heights[i], heights[i + 1]
        if a is None or b is None or c is None:
            continue
        kind = None
        if b >= a and b > c:
            kind = "High"
        elif b <= a and b < c:
            kind = "Low"
        if not kind:
            continue
        denom = a - 2 * b + c
        offset = 0.5 * (a - c) / denom if denom else 0.0
        offset = max(-0.5, min(0.5, offset))
        height = b - 0.25 * (a - c) * offset
        turns.append((times[i] + timedelta(hours=offset), kind, height))
    return turns


def daily_ranges(turns):
    """Biggest high-minus-low swing for each date."""
    by_day = {}
    for t, _, h in turns:
        by_day.setdefault(t.date(), []).append(h)
    return {d: max(hs) - min(hs) for d, hs in by_day.items() if len(hs) >= 2}


def compass(deg):
    pts = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return pts[int((deg % 360) / 45 + 0.5) % 8]


def analyse(name, marine, weather, day):
    times = [t + timedelta(minutes=TIDE_TIME_OFFSET_MIN)
             for t in parse_times(marine["hourly"]["time"])]
    heights = [h + TIDE_DATUM_OFFSET_M if h is not None else None
               for h in marine["hourly"]["sea_level_height_msl"]]
    turns = tide_turns(times, heights)
    ranges = daily_ranges(turns)

    today_turns = [x for x in turns if x[0].date() == day]
    today_range = ranges.get(day)
    week_max = max(ranges.values()) if ranges else None

    if today_range is None or not week_max:
        tide_label, tide_pts = "unknown", 1
    else:
        ratio = today_range / week_max
        if ratio < NEAP_BELOW:
            tide_label, tide_pts = "neap (smaller tide, cleaner water)", 2
        elif ratio > SPRING_ABOVE:
            tide_label, tide_pts = "spring (big tide, strong run, dirtier water)", 0
        else:
            tide_label, tide_pts = "middling", 1

    # Weather for today's daylight.
    wt = parse_times(weather["hourly"]["time"])
    wh = weather["hourly"]
    idx_day = [i for i, t in enumerate(wt) if t.date() == day]
    idx_morn = [i for i in idx_day if 6 <= wt[i].hour <= 14]
    wind = [wh["wind_speed_10m"][i] for i in idx_morn if wh["wind_speed_10m"][i] is not None]
    gust = [wh["wind_gusts_10m"][i] for i in idx_morn if wh["wind_gusts_10m"][i] is not None]
    wdir = [wh["wind_direction_10m"][i] for i in idx_morn if wh["wind_direction_10m"][i] is not None]
    rain = [wh["precipitation_probability"][i] for i in idx_day
            if wh["precipitation_probability"][i] is not None]

    avg_wind = sum(wind) / len(wind) if wind else None
    max_gust = max(gust) if gust else None
    if avg_wind is None:
        wind_pts = 1
    elif avg_wind <= WIND_GREAT:
        wind_pts = 3
    elif avg_wind <= WIND_OK:
        wind_pts = 2
    elif avg_wind <= WIND_MARGINAL:
        wind_pts = 1
    else:
        wind_pts = 0

    max_rain = max(rain) if rain else 0
    rain_pts = -1 if max_rain >= RAIN_WARN else 0

    di = [i for i, d in enumerate(weather["daily"]["time"]) if d == day.isoformat()]
    sunrise = datetime.fromisoformat(weather["daily"]["sunrise"][di[0]]) if di else None
    sunset = datetime.fromisoformat(weather["daily"]["sunset"][di[0]]) if di else None

    # Fishing windows: around each tide change in or near daylight.
    windows, window_spans = [], []
    for t, kind, h in today_turns:
        start = t - timedelta(hours=WINDOW_BEFORE)
        end = t + timedelta(hours=WINDOW_AFTER)
        if sunrise and sunset and (end < sunrise - timedelta(hours=1) or start > sunset + timedelta(hours=1)):
            continue
        tag = ""
        if sunrise and abs((t - sunrise).total_seconds()) <= 2 * 3600:
            tag = " - lines up with dawn"
        elif sunset and abs((t - sunset).total_seconds()) <= 2 * 3600:
            tag = " - lines up with dusk"
        windows.append(f"{start:%H:%M}-{end:%H:%M} around the {kind.lower()} at {t:%H:%M}{tag}")
        window_spans.append((start, end))

    # Today's tide curve (plus an hour either side so the chart edges are smooth).
    series_t, series_v = [], []
    for t, h in zip(times, heights):
        if h is not None and timedelta(hours=-1) <= t - datetime.combine(day, datetime.min.time()) <= timedelta(hours=25):
            series_t.append(t)
            series_v.append(h)

    score = wind_pts + tide_pts + rain_pts
    return {
        "name": name,
        "score": score,
        "turns": today_turns,
        "range": today_range,
        "tide_label": tide_label,
        "avg_wind": avg_wind,
        "max_gust": max_gust,
        "wind_dir": compass(sum(wdir) / len(wdir)) if wdir else "?",
        "max_rain": max_rain,
        "sunrise": sunrise,
        "sunset": sunset,
        "windows": windows,
        "window_spans": window_spans,
        "series": (series_t, series_v),
    }


def verdict(score):
    if score >= 4:
        return "GOOD"
    if score >= 2:
        return "OK"
    return "POOR"


# ------------------------------------------------------------------- REPORT --

def species_tips(r):
    tips = []
    neap = r["tide_label"].startswith("neap")
    calm = r["avg_wind"] is not None and r["avg_wind"] <= WIND_OK
    tips.append("Barra: work creek mouths and drains on the run-out after the high, "
                "and the first couple of hours of the run-in off the low.")
    if neap:
        tips.append("Jewfish: neaps suit them - fish the slack either side of the change on deeper structure.")
    else:
        tips.append("Jewfish: bigger tide today - the short slack at each change is your best shot.")
    if calm and neap:
        tips.append("Squid: calm, clean water - worth a look over weed and rock on the morning high.")
    else:
        tips.append("Squid: wind or tide will stir the water up - probably not the day.")
    return tips


def build_report(results, day):
    best = max(results, key=lambda r: r["score"])
    overall = verdict(best["score"])
    lines = [
        f"# Fishing outlook - {day:%A %d %B %Y}",
        "",
        f"**Overall: {overall}**, best bet is **{best['name']}**.",
        "",
        f"![Tide chart for {best['name']}](charts/{day.isoformat()}.png)",
        "",
    ]
    for r in sorted(results, key=lambda r: -r["score"]):
        lines.append(f"## {r['name']} - {verdict(r['score'])} (score {r['score']}/5)")
        lines.append("")
        if r["avg_wind"] is not None:
            lines.append(f"- **Wind (6am-2pm):** {r['avg_wind']:.0f} kn {r['wind_dir']}, "
                         f"gusts to {r['max_gust']:.0f} kn")
        lines.append(f"- **Rain:** up to {r['max_rain']:.0f}% chance")
        rng = f"{r['range']:.1f} m swing, " if r["range"] is not None else ""
        lines.append(f"- **Tide:** {rng}{r['tide_label']}")
        if r["turns"]:
            lines.append("- **Changes:** " + ", ".join(
                f"{k} {t:%H:%M} ({h:.1f} m)" for t, k, h in r["turns"]))
        if r["sunrise"]:
            lines.append(f"- **Sun:** up {r['sunrise']:%H:%M}, down {r['sunset']:%H:%M}")
        if r["windows"]:
            lines.append("- **Best windows:**")
            lines += [f"  - {w}" for w in r["windows"]]
        lines.append("")
    lines.append("### Tips for today")
    lines.append("")
    lines += [f"- {t}" for t in species_tips(best)]
    lines += [
        "",
        "---",
        "_Tides are modelled (Open-Meteo), not the official BOM tables - times are corrected but "
        "can still be ~20-30 min out. Check the BOM tide chart before you launch. Always check current "
        "NT Fisheries rules and closures._",
    ]
    title = f"Fishing outlook {day:%a %d %b}: {overall} - best bet {best['name']}"
    return title, "\n".join(lines) + "\n", best


def main():
    # Today's date in Darwin (UTC+9:30, no daylight saving).
    from datetime import timezone
    day = (datetime.now(timezone.utc) + timedelta(hours=9, minutes=30)).date()

    results, errors = [], []
    for name, lat, lon in SPOTS:
        try:
            marine, weather = fetch_spot(lat, lon)
            results.append(analyse(name, marine, weather, day))
        except Exception as e:  # keep going if one spot fails
            errors.append(f"{name}: {e}")

    if not results:
        print("No data for any spot:\n" + "\n".join(errors), file=sys.stderr)
        sys.exit(1)

    title, body, best = build_report(results, day)
    os.makedirs("charts", exist_ok=True)
    try:
        import chart
        chart.draw(results, best, day, f"charts/{day.isoformat()}.png")
    except Exception as e:  # report still goes out without the chart
        print(f"Chart failed: {e}", file=sys.stderr)
        body = body.replace(f"![Tide chart for {best['name']}](charts/{day.isoformat()}.png)\n\n", "")
    if errors:
        body += "\n**Couldn't fetch:** " + "; ".join(errors) + "\n"

    with open("REPORT.md", "w") as f:
        f.write(body)
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{day.isoformat()}.md", "w") as f:
        f.write(body)
    with open("title.txt", "w") as f:
        f.write(title)
    print(title)
    print(body)


if __name__ == "__main__":
    main()
