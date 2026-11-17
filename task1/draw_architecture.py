"""
draw_architecture.py

Draws the system architecture diagram for the university exams, results
and fees platform, and saves it as architecture.png next to this script.

Run it with:
    .venv/bin/python draw_architecture.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw straight into a file, no window needed

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

print("Using matplotlib", matplotlib.__version__)

# ------------------------------------------------------------------
# Page setup
# ------------------------------------------------------------------
# The page is 11.7 x 8.3 inches (A4 landscape).
# We draw on a grid of 117 x 83 units, so 1 unit = 0.1 inch.
# x runs from 0 (left) to 117 (right), y from 0 (bottom) to 83 (top).
fig = plt.figure(figsize=(11.7, 8.3), facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])  # one drawing area that fills the page
ax.set_xlim(0, 117)
ax.set_ylim(0, 83)
ax.axis("off")  # no axes, ticks or frame

# Colours
LINE = "#37474f"     # box outlines and arrows
TEXT = "#212121"     # text inside boxes
LABEL = "#455a64"    # arrow labels
REGION = "#546e7a"   # dashed AWS region box and its label
MARKER = "#c62828"   # numbered circles
BLUE = "#e3f2fd"     # the student's browser
ORANGE = "#fff3e0"   # outside services (CDN, payment gateway)
GREEN = "#e8f5e9"    # load balancer and app servers
PURPLE = "#ede7f6"   # data stores (Redis, PostgreSQL, Queue)


# ------------------------------------------------------------------
# Small helper functions
# ------------------------------------------------------------------
def box_shape(x, y, w, h, fill, z=2):
    """Draw an empty rounded box. (x, y) is its bottom-left corner."""
    shape = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.8",
        facecolor=fill, edgecolor=LINE, linewidth=1.3, zorder=z,
    )
    ax.add_patch(shape)


def draw_box(x, y, w, h, title, lines=(), fill="white", z=2):
    """Draw a rounded box with a bold title and optional smaller lines."""
    box_shape(x, y, w, h, fill, z)

    # Stack the title and the lines under each other, centred in the box.
    all_lines = [title] + list(lines)
    gap = 2.0  # distance between two lines of text, in grid units
    top = y + h / 2 + gap * (len(all_lines) - 1) / 2
    for i, text in enumerate(all_lines):
        is_title = i == 0
        ax.text(
            x + w / 2, top - i * gap, text,
            ha="center", va="center",
            fontsize=11 if is_title else 9,
            fontweight="bold" if is_title else "normal",
            color=TEXT, zorder=z + 0.5,
        )


def draw_arrow(start, end, elbow=False):
    """Draw an arrow from start to end.
    With elbow=True it goes sideways first, then straight down."""
    if elbow:
        style = "angle,angleA=0,angleB=90,rad=0"  # one right-angle bend
    else:
        style = "arc3,rad=0"  # a straight line
    arrow = FancyArrowPatch(
        start, end,
        arrowstyle="-|>", mutation_scale=14, connectionstyle=style,
        color=LINE, linewidth=1.3, shrinkA=0, shrinkB=0, zorder=1,
    )
    ax.add_patch(arrow)


def label(x, y, text, ha="center", va="center"):
    """Write a short arrow label."""
    ax.text(x, y, text, ha=ha, va=va, fontsize=9, color=LABEL)


def draw_marker(x, y, number):
    """Draw a small filled circle with a number in it."""
    ax.add_patch(Circle((x, y), radius=1.3, facecolor=MARKER,
                        edgecolor="none", zorder=5))
    ax.text(x, y, str(number), ha="center", va="center",
            fontsize=9, fontweight="bold", color="white", zorder=6)


# ------------------------------------------------------------------
# Title
# ------------------------------------------------------------------
ax.text(58.5, 80, "University exams, results and fees platform",
        ha="center", va="center", fontsize=16, fontweight="bold", color=TEXT)

# ------------------------------------------------------------------
# Student's browser (top centre), with marker 1 on its left
# ------------------------------------------------------------------
draw_box(36.5, 68.5, 44, 6, "Student's browser (lab PC, weak WiFi)", fill=BLUE)
draw_marker(33.8, 73.2, 1)

# ------------------------------------------------------------------
# Outside services: CDN on the left, payment gateway on the right
# ------------------------------------------------------------------
draw_box(1.5, 34, 21, 8, "CDN",
         ["static exam page files", "only, no student data"], fill=ORANGE)
draw_box(94.5, 35, 21, 6, "Payment gateway",
         ["Indian, RBI-regulated"], fill=ORANGE)

# ------------------------------------------------------------------
# AWS Mumbai region: a large dashed rectangle
# ------------------------------------------------------------------
ax.add_patch(Rectangle((25.5, 19), 66, 44.5, fill=False, edgecolor=REGION,
                       linestyle="--", linewidth=1.5, zorder=0))
ax.text(26.5, 62.5, "AWS Mumbai region\n(data stays in India)",
        ha="left", va="top", fontsize=10, fontweight="bold",
        color=REGION, linespacing=1.3)

# Load balancer, near the top of the region
draw_box(48.5, 52.5, 20, 4.5, "Load balancer", fill=GREEN)

# App servers: three boxes stacked like a pile of cards.
APP_X, APP_Y = 43.5, 34   # bottom-left corner of the front box
APP_W, APP_H = 30, 9      # size of each box
SHIFT = 1.2               # how far each card sits up and to the right

# The two cards behind are drawn first, so the front box covers them.
for step in (2, 1):
    box_shape(APP_X + step * SHIFT, APP_Y + step * SHIFT, APP_W, APP_H, GREEN)
draw_box(APP_X, APP_Y, APP_W, APP_H, "App servers",
         ["one application: exams | results | fees",
          "2 normally, more on a schedule"],
         fill=GREEN, z=3)

pile_top = APP_Y + APP_H + 2 * SHIFT     # top edge of the back card
pile_right = APP_X + APP_W + 2 * SHIFT   # right edge of the back card

# Bottom row of data stores, with marker 2 next to Redis
draw_box(26.5, 20.5, 20, 8, "Redis",
         ["ready-made results", "exam deadlines"], fill=PURPLE)
draw_box(48.5, 20.5, 20, 8, "PostgreSQL",
         ["primary + standby copy", "ACID transactions"], fill=PURPLE)
draw_box(70.5, 20.5, 20, 8, "Queue", ["payment events"], fill=PURPLE)
draw_marker(28.5, 30.6, 2)

# ------------------------------------------------------------------
# Arrows and their labels
# ------------------------------------------------------------------
# Browser -> CDN (left, then down)
draw_arrow((36.5, 70), (12, 42), elbow=True)
label(24.25, 70.6, "exam page", va="bottom")

# Browser -> load balancer (straight down)
draw_arrow((58.5, 68.5), (58.5, 57))
label(59.5, 66, "answers, results, fees", ha="left")

# Browser -> payment gateway (right, then down)
draw_arrow((80.5, 70), (105, 41), elbow=True)
label(92.75, 70.6, "pays", va="bottom")

# Load balancer -> app servers
draw_arrow((58.5, 52.5), (58.5, pile_top))

# App servers -> Redis, PostgreSQL and Queue
draw_arrow((51.5, APP_Y), (36.5, 28.5))
draw_arrow((58.5, APP_Y), (58.5, 28.5))
draw_arrow((65.5, APP_Y), (80.5, 28.5))

# Payment gateway -> app servers, with marker 3 under the arrow
draw_arrow((94.5, 38), (pile_right, 38))
label(83.7, 38.6, "confirms payment\n(signed)", va="bottom")
draw_marker(83.7, 35.5, 3)

# ------------------------------------------------------------------
# Key at the bottom, explaining the numbered markers
# ------------------------------------------------------------------
ax.add_patch(FancyBboxPatch((1.5, 1.5), 114, 14.5,
                            boxstyle="round,pad=0,rounding_size=0.8",
                            facecolor="#f7f7f7", edgecolor="#bdbdbd",
                            linewidth=1, zorder=0))
ax.text(3.5, 14.3, "Key", ha="left", va="center",
        fontsize=10.5, fontweight="bold", color=TEXT)

notes = [
    "Answers are saved in the browser first, then sent to the server. "
    "The server holds the exam clock.",
    "Results are prepared once before release and read from the cache.",
    "One unique order ID per fee. "
    "Paid only when the gateway confirms it to the server.",
]
for i, note in enumerate(notes):
    y = 11.0 - i * 3.7
    draw_marker(4.5, y, i + 1)
    ax.text(7, y, note, ha="left", va="center", fontsize=10, color=TEXT)

# ------------------------------------------------------------------
# Save the picture next to this script
# ------------------------------------------------------------------
out_file = Path(__file__).resolve().parent / "architecture.png"
fig.savefig(out_file, dpi=200, facecolor="white")
print("Saved", out_file)
