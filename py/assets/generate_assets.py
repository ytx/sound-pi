#!/usr/bin/env python3
"""Generate image assets for Sound-Pi UI."""

import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_PATH = os.path.join(FONT_DIR, "SpaceMono-Italic.ttf")

os.makedirs(OUT, exist_ok=True)


def load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


# ============================================================
# VU Meter background (full-size: 480x320)
# ============================================================
def gen_vu_bg():
    W, H = 480, 320
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)

    cx, cy = 240, 280
    radius = 220
    arc_start_deg = 140  # left
    arc_end_deg = 40     # right (sweep goes 140 → 90 → 40)

    font_label = load_font(12)
    font_title = load_font(28)
    font_db = load_font(11)

    # Title
    d.text((240, 16), "VU", fill=(255, 255, 255), font=font_title, anchor="mt")

    # Colored arc segments
    segments = 80
    for i in range(segments):
        frac = i / segments
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        next_frac = (i + 1) / segments
        next_angle = math.radians(arc_start_deg - next_frac * (arc_start_deg - arc_end_deg))

        if frac < 0.6:
            color = (0, 200, 0, 255)
        elif frac < 0.85:
            color = (200, 200, 0, 255)
        else:
            color = (200, 0, 0, 255)

        # Outer arc (thick)
        for r_offset in range(-2, 3):
            r = radius - 12 + r_offset
            x1 = cx + int(math.cos(angle) * r)
            y1 = cy - int(math.sin(angle) * r)
            x2 = cx + int(math.cos(next_angle) * r)
            y2 = cy - int(math.sin(next_angle) * r)
            d.line([(x1, y1), (x2, y2)], fill=color, width=1)

    # Subtle inner arc (dimmer)
    for i in range(segments):
        frac = i / segments
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        next_angle = math.radians(arc_start_deg - ((i + 1) / segments) * (arc_start_deg - arc_end_deg))
        x1 = cx + int(math.cos(angle) * (radius - 30))
        y1 = cy - int(math.sin(angle) * (radius - 30))
        x2 = cx + int(math.cos(next_angle) * (radius - 30))
        y2 = cy - int(math.sin(next_angle) * (radius - 30))
        d.line([(x1, y1), (x2, y2)], fill=(60, 60, 60, 255), width=1)

    # Scale markings and labels
    marks = [
        (0.0, "-20"), (0.1, "-15"), (0.2, "-10"), (0.3, "-7"),
        (0.4, "-5"), (0.5, "-3"), (0.6, "0"),
        (0.7, "+2"), (0.75, "+3"), (0.85, "+6"), (1.0, "+10"),
    ]
    for frac, label in marks:
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        is_major = label in ("-20", "-10", "-5", "0", "+3", "+6", "+10")
        tick_inner = radius - (35 if is_major else 25)
        tick_outer = radius - 5
        tick_w = 2 if is_major else 1

        xi = cx + int(math.cos(angle) * tick_inner)
        yi = cy - int(math.sin(angle) * tick_inner)
        xo = cx + int(math.cos(angle) * tick_outer)
        yo = cy - int(math.sin(angle) * tick_outer)
        d.line([(xi, yi), (xo, yo)], fill=(255, 255, 255, 200), width=tick_w)

        if is_major:
            xt = cx + int(math.cos(angle) * (radius + 10))
            yt = cy - int(math.sin(angle) * (radius + 10))
            # Color: red for positive dB
            lcolor = (200, 60, 60, 255) if label.startswith("+") else (160, 160, 160, 255)
            d.text((xt, yt), label, fill=lcolor, font=font_db, anchor="mm")

    # Minor tick marks between major ones
    for i in range(50):
        frac = i / 50
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        xi = cx + int(math.cos(angle) * (radius - 18))
        yi = cy - int(math.sin(angle) * (radius - 18))
        xo = cx + int(math.cos(angle) * (radius - 14))
        yo = cy - int(math.sin(angle) * (radius - 14))
        d.line([(xi, yi), (xo, yo)], fill=(80, 80, 80, 255), width=1)

    # Decorative circle at bottom
    d.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=(30, 30, 30, 255),
              outline=(80, 80, 80, 255), width=2)

    img.save(os.path.join(OUT, "vu_bg.png"))
    print("vu_bg.png")


# ============================================================
# VU Meter needle (pointing up from bottom-center, transparent)
# ============================================================
def gen_vu_needle():
    # Needle image: tall narrow image, pivot at bottom center
    W, H = 20, 210
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx = W // 2

    # Needle body — tapered
    # Wide at pivot (bottom), thin at tip (top)
    points = [
        (cx - 3, H - 5),    # bottom left
        (cx - 1, 2),        # tip left
        (cx + 1, 2),        # tip right
        (cx + 3, H - 5),    # bottom right
    ]
    d.polygon(points, fill=(240, 240, 240, 230))

    # Bright center line
    d.line([(cx, 5), (cx, H - 8)], fill=(255, 255, 255, 255), width=1)

    # Red tip
    d.polygon([(cx - 1, 2), (cx, 0), (cx + 1, 2)], fill=(200, 50, 50, 255))

    img.save(os.path.join(OUT, "vu_needle.png"))
    print("vu_needle.png")


# ============================================================
# VU Meter pivot overlay
# ============================================================
def gen_vu_pivot():
    S = 30
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S // 2

    # Outer ring
    d.ellipse([2, 2, S - 2, S - 2], fill=(50, 50, 55, 255),
              outline=(120, 120, 120, 255), width=2)
    # Inner dot
    d.ellipse([c - 3, c - 3, c + 3, c + 3], fill=(80, 80, 85, 255))
    # Highlight
    d.ellipse([c - 5, c - 7, c + 1, c - 2], fill=(100, 100, 105, 80))

    img.save(os.path.join(OUT, "vu_pivot.png"))
    print("vu_pivot.png")


# ============================================================
# Dual VU meter background (smaller, for L or R)
# ============================================================
def gen_dual_vu_bg():
    W, H = 220, 200
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx, cy = 110, 175
    radius = 140
    arc_start_deg = 140
    arc_end_deg = 40

    font_db = load_font(9)

    # Arc
    segments = 60
    for i in range(segments):
        frac = i / segments
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        next_angle = math.radians(arc_start_deg - ((i + 1) / segments) * (arc_start_deg - arc_end_deg))

        if frac < 0.6:
            color = (0, 200, 0, 200)
        elif frac < 0.85:
            color = (200, 200, 0, 200)
        else:
            color = (200, 0, 0, 200)

        for r_off in range(-1, 2):
            r = radius - 10 + r_off
            x1 = cx + int(math.cos(angle) * r)
            y1 = cy - int(math.sin(angle) * r)
            x2 = cx + int(math.cos(next_angle) * r)
            y2 = cy - int(math.sin(next_angle) * r)
            d.line([(x1, y1), (x2, y2)], fill=color, width=1)

    # Scale marks
    for frac, label in [(0.0, "-20"), (0.2, "-10"), (0.4, "-5"),
                         (0.6, "0"), (0.75, "+3"), (0.85, "+6"), (1.0, "+10")]:
        angle = math.radians(arc_start_deg - frac * (arc_start_deg - arc_end_deg))
        xi = cx + int(math.cos(angle) * (radius - 22))
        yi = cy - int(math.sin(angle) * (radius - 22))
        xo = cx + int(math.cos(angle) * (radius - 5))
        yo = cy - int(math.sin(angle) * (radius - 5))
        d.line([(xi, yi), (xo, yo)], fill=(255, 255, 255, 180), width=1)

        xt = cx + int(math.cos(angle) * (radius + 6))
        yt = cy - int(math.sin(angle) * (radius + 6))
        lcolor = (200, 60, 60, 200) if label.startswith("+") else (140, 140, 140, 200)
        d.text((xt, yt), label, fill=lcolor, font=font_db, anchor="mm")

    # Pivot
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(40, 40, 45, 255),
              outline=(80, 80, 80, 255), width=1)

    img.save(os.path.join(OUT, "dual_vu_bg.png"))
    print("dual_vu_bg.png")


# ============================================================
# Dual VU needle (smaller)
# ============================================================
def gen_dual_vu_needle():
    W, H = 14, 145
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W // 2

    points = [
        (cx - 2, H - 4),
        (cx - 1, 2),
        (cx + 1, 2),
        (cx + 2, H - 4),
    ]
    d.polygon(points, fill=(230, 230, 230, 220))
    d.line([(cx, 4), (cx, H - 6)], fill=(255, 255, 255, 255), width=1)
    d.polygon([(cx - 1, 2), (cx, 0), (cx + 1, 2)], fill=(200, 50, 50, 240))

    img.save(os.path.join(OUT, "dual_vu_needle.png"))
    print("dual_vu_needle.png")


# ============================================================
# Menu icons (64x64 transparent PNGs)
# ============================================================
def gen_menu_icon(name, draw_func):
    S = 64
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_func(d, S)
    img.save(os.path.join(OUT, f"icon_{name}.png"))
    print(f"icon_{name}.png")


def icon_vu_meter(d, S):
    """Needle meter icon."""
    cx, cy = S // 2, S - 12
    r = 28
    # Arc
    for i in range(30):
        frac = i / 30
        angle = math.radians(140 - frac * 100)
        next_angle = math.radians(140 - (i + 1) / 30 * 100)
        color = (0, 200, 0) if frac < 0.6 else ((200, 200, 0) if frac < 0.85 else (200, 0, 0))
        x1 = cx + int(math.cos(angle) * r)
        y1 = cy - int(math.sin(angle) * r)
        x2 = cx + int(math.cos(next_angle) * r)
        y2 = cy - int(math.sin(next_angle) * r)
        d.line([(x1, y1), (x2, y2)], fill=color, width=2)
    # Needle
    angle = math.radians(110)
    nx = cx + int(math.cos(angle) * (r - 6))
    ny = cy - int(math.sin(angle) * (r - 6))
    d.line([(cx, cy), (nx, ny)], fill=(255, 255, 255), width=2)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(80, 80, 80))


def icon_dual_vu(d, S):
    """Two small meters."""
    for ox in (S // 4, 3 * S // 4):
        cy = S - 10
        r = 18
        for i in range(20):
            frac = i / 20
            angle = math.radians(140 - frac * 100)
            na = math.radians(140 - (i + 1) / 20 * 100)
            color = (0, 200, 0) if frac < 0.6 else ((200, 200, 0) if frac < 0.85 else (200, 0, 0))
            d.line([(ox + int(math.cos(angle) * r), cy - int(math.sin(angle) * r)),
                    (ox + int(math.cos(na) * r), cy - int(math.sin(na) * r))], fill=color, width=2)
        angle = math.radians(105)
        d.line([(ox, cy), (ox + int(math.cos(angle) * 14), cy - int(math.sin(angle) * 14))],
               fill=(255, 255, 255), width=1)
        d.ellipse([ox - 2, cy - 2, ox + 2, cy + 2], fill=(80, 80, 80))


def icon_spectrum(d, S):
    """Spectrum bars."""
    import random
    random.seed(42)
    bars = 8
    bw = (S - 10) // bars
    for i in range(bars):
        h = random.randint(10, S - 16)
        x = 5 + i * bw
        frac = h / (S - 16)
        color = (0, 200, 0) if frac < 0.6 else ((200, 200, 0) if frac < 0.85 else (200, 0, 0))
        d.rectangle([x, S - 6 - h, x + bw - 2, S - 6], fill=color)


def icon_mixer(d, S):
    """Mixer sliders."""
    for i, h_frac in enumerate([0.7, 0.5, 0.85, 0.4]):
        x = 8 + i * 14
        track_top, track_bot = 8, S - 8
        # Track
        d.line([(x + 3, track_top), (x + 3, track_bot)], fill=(60, 60, 60), width=2)
        # Knob position
        knob_y = int(track_bot - (track_bot - track_top) * h_frac)
        d.rectangle([x, knob_y - 3, x + 6, knob_y + 3], fill=(0, 200, 200))


def icon_bluetooth(d, S):
    """Bluetooth symbol."""
    cx, cy = S // 2, S // 2
    # B rune shape
    pts = [(cx, cy - 18), (cx + 10, cy - 8), (cx - 8, cy + 6),
           (cx, cy + 18), (cx, cy - 18), (cx - 8, cy - 6), (cx + 10, cy + 8), (cx, cy + 18)]
    d.line(pts, fill=(60, 130, 230), width=2)


def icon_wifi(d, S):
    """WiFi arcs."""
    cx, cy = S // 2, S // 2 + 8
    for i, r in enumerate([24, 17, 10]):
        bbox = [cx - r, cy - r, cx + r, cy + r]
        d.arc(bbox, 220, 320, fill=(0, 200, 200), width=2)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(0, 200, 200))


# ============================================================
# Spectrum bar gradient texture (single bar, 1x height)
# ============================================================
def gen_spectrum_bar():
    W, H = 1, 240
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for y in range(H):
        frac = 1.0 - y / H  # 0 at top, 1 at bottom
        if frac > 0.85:
            r, g, b = 200, 0, 0
        elif frac > 0.6:
            t = (frac - 0.6) / 0.25
            r = int(200 * t)
            g = 200
            b = 0
        else:
            r, g, b = 0, 200, 0
        img.putpixel((0, y), (r, g, b, 255))
    img.save(os.path.join(OUT, "spectrum_bar.png"))
    print("spectrum_bar.png")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    gen_vu_bg()
    gen_vu_needle()
    gen_vu_pivot()
    gen_dual_vu_bg()
    gen_dual_vu_needle()
    gen_spectrum_bar()

    gen_menu_icon("vu_meter", icon_vu_meter)
    gen_menu_icon("dual_vu_meter", icon_dual_vu)
    gen_menu_icon("spectrum", icon_spectrum)
    gen_menu_icon("mixer", icon_mixer)
    gen_menu_icon("bluetooth", icon_bluetooth)
    gen_menu_icon("wifi", icon_wifi)

    print(f"\nAll assets generated in {OUT}/")
