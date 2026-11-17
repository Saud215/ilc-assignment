"""Turn pipeline results into HTML for the web UI.

Pure functions: no Gradio import and no model calls, so they are easy to test.
Every piece of model text and student text goes through html.escape before it
is put into HTML. The helpers badge() and table_html() escape their own text,
so callers pass them plain text.
"""

import html

TYPE_ORDER = ["R", "I", "A", "S", "E", "C"]
TYPE_NAMES = {
    "R": "Realistic",
    "I": "Investigative",
    "A": "Artistic",
    "S": "Social",
    "E": "Enterprising",
    "C": "Conventional",
}
MAX_SCORE = 20

STEP_ORDER = ["extract", "generate", "validate"]
STEP_LABELS = {
    "extract": "Extract",
    "generate": "Generate",
    "validate": "Validate and refine",
}
TOKEN_HEADERS = ["Step", "Model", "In", "Out", "Think", "Total", "Attempts"]

# ---------- small inline styles ----------
# Text colour is inherited from the page and every colour is a see-through tint,
# so the same styles read well on both the light and the dark theme.

SECTION_STYLE = "margin:0 0 18px 0;"
HEADING_STYLE = "margin:0 0 8px 0;font-size:1.1em;font-weight:600;"
CARD_STYLE = (
    "border:1px solid rgba(128,128,128,0.35);border-radius:10px;"
    "padding:12px 14px;margin:0 0 12px 0;background:rgba(128,128,128,0.06);"
)
BADGE_STYLE = (
    "display:inline-block;padding:2px 10px;margin:2px 6px 2px 0;"
    "border-radius:999px;font-size:0.85em;border:1px solid;"
)
TINTS = {
    "accent": "background:rgba(79,70,229,0.15);border-color:rgba(79,70,229,0.55);",
    "neutral": "background:rgba(128,128,128,0.15);border-color:rgba(128,128,128,0.5);",
    "good": "background:rgba(22,163,74,0.15);border-color:rgba(22,163,74,0.55);",
    "warn": "background:rgba(217,119,6,0.15);border-color:rgba(217,119,6,0.6);",
    "error": "background:rgba(220,38,38,0.12);border-color:rgba(220,38,38,0.6);",
}
TABLE_STYLE = "border-collapse:collapse;width:100%;"
TH_STYLE = "text-align:left;padding:6px 8px;border-bottom:1px solid rgba(128,128,128,0.5);"
TD_STYLE = "padding:6px 8px;border-bottom:1px solid rgba(128,128,128,0.2);"
NUMBER_STYLE = "text-align:right;"
BAR_TRACK_STYLE = "background:rgba(128,128,128,0.2);border-radius:4px;height:8px;min-width:80px;"
BAR_FILL_STYLE = "background:rgba(79,70,229,0.75);border-radius:4px;height:8px;"


# ---------- building blocks ----------


def badge(text, tint="neutral"):
    """A small rounded label. Escapes its text."""
    return f'<span style="{BADGE_STYLE}{TINTS[tint]}">{html.escape(str(text))}</span>'


def section(title, body_html):
    """A titled block. body_html must already be safe HTML."""
    return (
        f'<div style="{SECTION_STYLE}">'
        f'<div style="{HEADING_STYLE}">{html.escape(title)}</div>'
        f"{body_html}</div>"
    )


def callout(text, tint):
    """A tinted box with one line of text, used for notices and status."""
    return f'<div style="{CARD_STYLE}{TINTS[tint]}">{html.escape(text)}</div>'


def table_html(headers, rows, number_columns, bold_last_row=False):
    """A plain table. Every cell is escaped. number_columns are right-aligned."""
    header_cells = ""
    for index, header in enumerate(headers):
        align = NUMBER_STYLE if index in number_columns else ""
        header_cells += f'<th style="{TH_STYLE}{align}">{html.escape(header)}</th>'

    body_rows = ""
    for row_index, row in enumerate(rows):
        is_bold = bold_last_row and row_index == len(rows) - 1
        cells = ""
        for index, cell in enumerate(row):
            align = NUMBER_STYLE if index in number_columns else ""
            weight = "font-weight:600;" if is_bold else ""
            cells += f'<td style="{TD_STYLE}{align}{weight}">{html.escape(str(cell))}</td>'
        body_rows += f"<tr>{cells}</tr>"

    return (
        f'<table style="{TABLE_STYLE}"><thead><tr>{header_cells}</tr></thead>'
        f"<tbody>{body_rows}</tbody></table>"
    )


# ---------- scores ----------


def score_rows(sc, top):
    """Rows of [full type name, score, rank label]. Rank label is "" outside the top three."""
    rows = []
    for letter in TYPE_ORDER:
        rank_label = ""
        if letter in top:
            rank_label = f"Top {top.index(letter) + 1}"
        rows.append([TYPE_NAMES[letter], sc[letter], rank_label])
    return rows


def scores_html(sc, top):
    """Score table with a bar per type and badges for the top three."""
    top_badges = ""
    for letter in top:
        top_badges += badge(TYPE_NAMES[letter], "accent")
    intro = f'<div style="margin-bottom:8px;">Your top three: {top_badges}</div>'

    body_rows = ""
    for name, score, rank_label in score_rows(sc, top):
        percent = round(score * 100 / MAX_SCORE)
        bar = (
            f'<div style="{BAR_TRACK_STYLE}">'
            f'<div style="{BAR_FILL_STYLE}width:{percent}%;"></div></div>'
        )
        rank_badge = ""
        if rank_label:
            rank_badge = badge(rank_label, "accent")
        body_rows += (
            f"<tr>"
            f'<td style="{TD_STYLE}">{html.escape(name)}</td>'
            f'<td style="{TD_STYLE}{NUMBER_STYLE}white-space:nowrap;">{score} / {MAX_SCORE}</td>'
            f'<td style="{TD_STYLE}width:45%;">{bar}</td>'
            f'<td style="{TD_STYLE}">{rank_badge}</td>'
            f"</tr>"
        )

    table = (
        f'<table style="{TABLE_STYLE}"><thead><tr>'
        f'<th style="{TH_STYLE}">Interest type</th>'
        f'<th style="{TH_STYLE}{NUMBER_STYLE}">Score</th>'
        f'<th style="{TH_STYLE}"></th><th style="{TH_STYLE}"></th>'
        f"</tr></thead><tbody>{body_rows}</tbody></table>"
    )
    return section("Your interest scores", intro + table)


# ---------- report ----------


def summary_html(summary_text):
    """The two-sentence summary from the report."""
    paragraph = f'<p style="margin:0;">{html.escape(summary_text)}</p>'
    return section("What your interests point to", paragraph)


def evidence_badge(ev):
    """A type letter becomes its full name; a fact is shown as written."""
    if len(ev) == 1 and ev in TYPE_NAMES:
        return badge(TYPE_NAMES[ev], "accent")
    return badge(ev, "neutral")


def career_card_html(fit, number):
    """One card: title, why it fits, evidence badges and the next step."""
    evidence = ""
    for ev in fit["ev"]:
        evidence += evidence_badge(ev)

    return (
        f'<div class="career-card" style="{CARD_STYLE}">'
        f'<div style="font-size:1.05em;font-weight:600;margin-bottom:6px;">'
        f"{number}. {html.escape(fit['t'])}</div>"
        f'<div style="margin-bottom:6px;"><b>Why it fits:</b> {html.escape(fit["why"])}</div>'
        f'<div style="margin-bottom:6px;"><b>Based on:</b> {evidence}</div>'
        f'<div><b>Next step this month:</b> {html.escape(fit["nxt"])}</div>'
        f"</div>"
    )


def cards_html(fits):
    """All career cards, best fit first."""
    cards = ""
    for index, fit in enumerate(fits):
        cards += career_card_html(fit, index + 1)
    return section("Careers that fit your interests", cards)


def review_html(review, correction_rejected=False):
    """Badge for the Validate step, with its list of issues when it found any."""
    if review["ok"]:
        return section("Quality check", badge("Checked, no problems found", "good"))

    title = "Checked and corrected"
    if correction_rejected:
        # The correction itself failed the evidence check, so the first draft was kept.
        title = "Checked: problems found, correction not applied"

    items = ""
    for issue in review["iss"]:
        items += f"<li>Career {issue['i'] + 1}: {html.escape(issue['p'])}</li>"
    issues = f'<ul style="margin:8px 0 0 0;padding-left:20px;">{items}</ul>'

    return section("Quality check", badge(title, "warn") + issues)


def notes_html(notes):
    """Notes from the pipeline, or nothing when there are none."""
    if not notes:
        return ""
    items = ""
    for note in notes:
        items += f"<li>{html.escape(note)}</li>"
    return section("Notes", f'<ul style="margin:0;padding-left:20px;">{items}</ul>')


def cache_html(cached):
    """Says whether the result came from the cache (no AI calls, no tokens)."""
    if cached:
        return badge("From cache: no AI calls were made", "neutral")
    return badge("New result: made by the AI just now", "accent")


# ---------- tokens ----------


def thinking_tokens(step_usage):
    """Hidden thinking tokens: counted in total, but not in in or out."""
    think = step_usage["total_tokens"] - step_usage["in_tokens"] - step_usage["out_tokens"]
    # A provider that reports no total would otherwise show a negative number.
    if think < 0:
        think = 0
    return think


def token_rows(usage):
    """Rows of [step, model, in, out, think, total, attempts], plus a total row."""
    rows = []
    totals = {"in": 0, "out": 0, "think": 0, "total": 0, "attempts": 0}

    for step_name in STEP_ORDER:
        step = usage[step_name]
        model = step["model"]
        if step["skipped"]:
            model = "skipped"
        think = thinking_tokens(step)
        rows.append([
            STEP_LABELS[step_name],
            model,
            step["in_tokens"],
            step["out_tokens"],
            think,
            step["total_tokens"],
            step["attempts"],
        ])
        totals["in"] += step["in_tokens"]
        totals["out"] += step["out_tokens"]
        totals["think"] += think
        totals["total"] += step["total_tokens"]
        totals["attempts"] += step["attempts"]

    rows.append([
        "Total",
        "",
        totals["in"],
        totals["out"],
        totals["think"],
        totals["total"],
        totals["attempts"],
    ])
    return rows


def token_table_html(usage):
    """Token table per step, with the total row in bold."""
    table = table_html(TOKEN_HEADERS, token_rows(usage), [2, 3, 4, 5, 6], bold_last_row=True)
    return section("Token usage", table)


# ---------- status, errors, page text ----------


def working_html():
    """Shown while the pipeline runs."""
    return callout(
        "Working on your report... This makes up to 3 AI calls and can take up to a minute.",
        "accent",
    )


def error_html(title, reason):
    """A friendly error card with a short reason. Never a stack trace."""
    return (
        f'<div style="{CARD_STYLE}{TINTS["error"]}">'
        f'<div style="font-weight:600;margin-bottom:4px;">{html.escape(title)}</div>'
        f"<div>{html.escape(reason)}</div></div>"
    )


def notice_html():
    """The notice at the top of the page."""
    return callout(
        "These career ideas are based on the activities you said you enjoy. "
        "Use them as a starting point to explore, not as a final answer.",
        "neutral",
    )


def footer_html(source_text):
    """Footer with the questionnaire source and the USDOL/ETA disclaimer."""
    return (
        f'<div style="font-size:0.85em;opacity:0.8;margin-top:24px;">'
        f"<p>{html.escape(source_text)}</p>"
        f"<p>This tool has not been approved, endorsed or tested by USDOL/ETA.</p>"
        f"</div>"
    )
