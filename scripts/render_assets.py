#!/usr/bin/env python3
"""Render README assets from data/contributions.json.

  assets/contribution-ring.gif   animated "Round the year" contribution ring
  assets/best-commit-day.svg     static flat-square badge (matches the views badge)
  assets/streak-stats.svg        current & longest streak card (replaces external service)

Requires: Pillow, and DejaVu Sans (fonts-dejavu-core on Ubuntu).
All values come from the JSON; nothing is hardcoded.
"""
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "contributions.json").read_text())
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

# ---- design constants -------------------------------------------------------
BG = (13, 17, 23)                                   # GitHub dark canvas
LEVELS = [(22, 27, 34), (14, 68, 41), (0, 109, 50), (38, 166, 65), (57, 211, 83)]
C_TOTAL, C_SUB, C_MONTH, C_MUTED = (240, 246, 252), (201, 209, 217), (173, 186, 199), (155, 165, 176)
W, H = 480, 496
CX, CY = 240, 234
HOLE, RING, GAP, GAP_DEG = 100, 12, 3, 0.9
SS = 3                                              # supersampling for smooth arcs
FRAMES, FRAME_MS, HOLD_MS = 30, 70, 9000            # ~2 s sweep, then rest before looping
PALETTE_COLORS = 192

FONTS = [
    # Linux (Ubuntu / GitHub Actions)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # Windows fallbacks
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
]
FONT_PATH = next((p for p in FONTS if Path(p).exists()), None)
if FONT_PATH is None:
    sys.exit("No usable TrueType font found. On Ubuntu install fonts-dejavu-core; on Windows ensure Arial or Segoe UI is present.")


def font(size_px):
    return ImageFont.truetype(FONT_PATH, round(size_px * SS))


weeks = DATA["weeks"]
n_weeks = len(weeks)
step = 360 / n_weeks
total = DATA["totalLastYear"]


def arc_pts(r, a0, a1):
    n = max(2, int((a1 - a0) / 1.2) + 1)
    return [(CX + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             CY + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


# ---- geometry (precomputed once) -------------------------------------------
cells = []
for w, days in enumerate(weeks):
    a0 = -90 + w * step
    a1 = a0 + step - GAP_DEG
    for day in days:
        ri = HOLE + day["weekday"] * (RING + GAP)
        poly = arc_pts(ri + RING, a0, a1) + arc_pts(ri, a0, a1)[::-1]
        t = (w / n_weeks) * 0.80 + day["weekday"] * 0.012      # when this cell starts to appear
        cells.append((t, day["level"], [(x * SS, y * SS) for x, y in poly]))
P_END = 0.80 + 6 * 0.012 + 0.18

r_label = HOLE + 7 * (RING + GAP) - GAP + 14
month = lambda iso: datetime.strptime(iso, "%Y-%m-%d").strftime("%b")
labels, prev = [], None
first_month = month(weeks[0][0]["date"])
first_labelled = n_weeks > 1 and month(weeks[1][0]["date"]) == first_month
for w, days in enumerate(weeks):
    m = month(days[0]["date"])
    if m != prev:
        skip = (w == 0 and not first_labelled) or (first_labelled and w > n_weeks / 2 and m == first_month)
        if not skip:
            ang = math.radians(-90 + w * step + step / 2)
            labels.append((m, CX + r_label * math.cos(ang), CY + r_label * math.sin(ang)))
        prev = m


def blend(c, a):
    # every cell starts as an empty grid slot (level 0) and fills towards its own level colour
    base = LEVELS[0]
    return tuple(round(base[i] + (c[i] - base[i]) * a) for i in range(3))


def ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def render_frame(p):
    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)
    for t, level, poly in cells:
        a = 1.0 if level == 0 else ease((p - t) / 0.18)
        d.polygon(poly, fill=blend(LEVELS[level], a))
    for m, x, y in labels:
        d.text((x * SS, y * SS), m, font=font(13.5), fill=C_MONTH, anchor="mm")
    shown = total if p >= P_END else round(total * ease(p / 0.95))
    d.text((CX * SS, (CY - 14) * SS), f"{shown:,}", font=font(46), fill=C_TOTAL, anchor="mm")
    d.text((CX * SS, (CY + 20) * SS), "contributions", font=font(13), fill=C_SUB, anchor="mm")
    d.text((CX * SS, (CY + 37) * SS), "in the last year", font=font(13), fill=C_SUB, anchor="mm")
    # legend
    x0, y0 = CX - 38, H - 22
    for i, c in enumerate(LEVELS):
        d.rounded_rectangle([(x0 + i * 16) * SS, y0 * SS, (x0 + i * 16 + 12) * SS, (y0 + 12) * SS], radius=2 * SS, fill=c)
    d.text(((x0 - 8) * SS, (y0 + 6) * SS), "Less", font=font(12), fill=C_MUTED, anchor="rm")
    d.text(((x0 + 84) * SS, (y0 + 6) * SS), "More", font=font(12), fill=C_MUTED, anchor="lm")
    return img.resize((W, H), Image.LANCZOS)


# ---- GIF --------------------------------------------------------------------
frames_rgb = [render_frame(P_END * i / (FRAMES - 1)) for i in range(FRAMES)]
sample = [frames_rgb[-1], frames_rgb[int(FRAMES * 0.45)], frames_rgb[int(FRAMES * 0.7)]]
stack = Image.new("RGB", (W, H * len(sample)))
for i, s in enumerate(sample):
    stack.paste(s, (0, i * H))
pal = stack.quantize(colors=PALETTE_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames_rgb]
durations = [FRAME_MS] * (FRAMES - 1) + [HOLD_MS]
gif_path = OUT / "contribution-ring.gif"
frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=False, disposal=1)

# ---- Best-commit-day badge --------------------------------------------------
best = DATA["bestCommitDay"]
def fmt(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day} {d.strftime('%b %Y')}"
if best.get("exact") and best.get("date"):
    label = "Best commit day"
    value = f"{best['commits']} {'commit' if best['commits'] == 1 else 'commits'} · {fmt(best['date'])}"
else:  # commit-only figure unavailable: say what the number really is
    alt = DATA["bestContributionDay"]
    label = "Most contributions in a day"
    value = f"{alt['count']} · {fmt(alt['date'])}" if alt.get("date") else "n/a"

bf = ImageFont.truetype(FONT_PATH, 11)
pad = 8
lw = math.ceil(bf.getlength(label)) + 2 * pad
vw = math.ceil(bf.getlength(value)) + 2 * pad
badge = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{lw + vw}" height="20" role="img" aria-label="{escape(label)}: {escape(value)}">
<title>{escape(label)}: {escape(value)}</title>
<rect width="{lw}" height="20" fill="#555"/>
<rect x="{lw}" width="{vw}" height="20" fill="#2ea043"/>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
<text x="{lw / 2:.1f}" y="14">{escape(label)}</text>
<text x="{lw + vw / 2:.1f}" y="14">{escape(value)}</text>
</g>
</svg>
"""
(OUT / "best-commit-day.svg").write_text(badge)
print(f"contribution-ring.gif: {gif_path.stat().st_size / 1024:.0f} KB, {W}x{H}, {FRAMES} frames")
print(f"best-commit-day.svg: {label} | {value}")

# ---- Streak stats SVG -------------------------------------------------------
streaks = DATA["streaks"]
longest = streaks["longest"]
current = streaks["current"]


def fmt_date_range(start, end):
    """Format '1 Aug – 31 Oct 2026' from ISO dates. Cross-platform (no %-d)."""
    if not start or not end:
        return "\u2014"
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    if s.year == e.year:
        return f"{s.day} {s.strftime('%b')} \u2013 {e.day} {e.strftime('%b %Y')}"
    return f"{s.day} {s.strftime('%b %Y')} \u2013 {e.day} {e.strftime('%b %Y')}"


cur_len   = current["length"]
cur_range = fmt_date_range(current.get("start"), current.get("end"))
lng_len   = longest["length"]
lng_range = fmt_date_range(longest.get("start"), longest.get("end"))

# Card dimensions — same width as the ring (480px), height matches demolab card
CW, CH = 480, 160

# Updated timestamp (IST = UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)
updated_str = now_ist.strftime(f"Updated {now_ist.day} %b %Y, %H:%M IST")

streak_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}"
     role="img" aria-label="Contribution streak statistics">
  <title>Contribution streak statistics</title>
  <rect width="{CW}" height="{CH}" rx="10" fill="#0d1117" stroke="#30363d" stroke-width="1"/>

  <!-- Vertical divider -->
  <line x1="{CW // 2}" y1="18" x2="{CW // 2}" y2="{CH - 18}" stroke="#30363d" stroke-width="1"/>

  <!-- LEFT: Current Streak -->
  <text x="{CW // 4}" y="36"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="12" fill="#9ba5b0">Current Streak</text>
  <text x="{CW // 4}" y="88"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="42" font-weight="600" fill="#e6edf3">{cur_len}</text>
  <text x="{CW // 4}" y="110"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="11" fill="#3fb950">days</text>
  <text x="{CW // 4}" y="132"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="10" fill="#9ba5b0">{escape(cur_range)}</text>

  <!-- RIGHT: Longest Streak -->
  <text x="{3 * CW // 4}" y="36"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="12" fill="#9ba5b0">Longest Streak</text>
  <text x="{3 * CW // 4}" y="88"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="42" font-weight="600" fill="#e6edf3">{lng_len}</text>
  <text x="{3 * CW // 4}" y="110"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="11" fill="#3fb950">days</text>
  <text x="{3 * CW // 4}" y="132"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="10" fill="#9ba5b0">{escape(lng_range)}</text>

  <!-- Updated timestamp (bottom-centre, very subtle) -->
  <text x="{CW // 2}" y="{CH - 5}"
        text-anchor="middle" font-family="Segoe UI,Helvetica Neue,Arial,sans-serif"
        font-size="9" fill="#30363d">{escape(updated_str)}</text>
</svg>
"""
streak_path = OUT / "streak-stats.svg"
streak_path.write_text(streak_svg, encoding="utf-8")
print(f"streak-stats.svg: current={cur_len} ({cur_range}), longest={lng_len} ({lng_range})")
