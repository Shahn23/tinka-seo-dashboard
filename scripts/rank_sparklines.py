"""
Phase: Rank History Sparklines
Generates tiny Plotly line charts (200x40px) as inline SVG for keyword rank histories.
Uses go.Scatter over the last 30 days of rank_history data.

Usage:
    python scripts/rank_sparklines.py --keyword-id 5
    (prints SVG string to stdout)

Import:
    from scripts.rank_sparklines import get_sparkline_svg
    svg = get_sparkline_svg(5)
"""

import argparse
import os
import sqlite3
import sys

import plotly.graph_objects as go
import plotly.io as pio

# ── DB Path ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")


# ── Sparkline generation ─────────────────────────────────────────────────────
def get_sparkline_svg(keyword_id: int) -> str:
    """
    Query the last 30 days of rank_history for *keyword_id* and return an
    inline SVG sparkline (200x40 px) as a string.

    Returns an empty ``<div class="sparkline-empty"></div>`` when there is
    no rank history for the keyword.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT date, position
            FROM rank_history
            WHERE keyword_id = ?
              AND date >= date('now', '-30 days')
            ORDER BY date ASC
            """,
            (keyword_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return '<div class="sparkline-empty"></div>'

    dates = [row["date"] for row in rows]
    positions = [float(row["position"]) for row in rows]

    # Build a minimal sparkline with Plotly
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=positions,
            mode="lines",
            line=dict(color="#2563eb", width=1.5),
            showlegend=False,
        )
    )

    fig.update_layout(
        width=200,
        height=40,
        margin=dict(l=0, r=0, t=0, b=0, pad=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        hovermode=False,
    )

    # Hide axes but keep the y-axis reversed so lower rank (better) is at top
    fig.update_xaxes(visible=False, showticklabels=False)
    fig.update_yaxes(
        visible=False,
        showticklabels=False,
        autorange="reversed",
    )

    svg_bytes = pio.to_image(fig, format="svg")
    svg_str = svg_bytes.decode("utf-8")

    return svg_str


# ── CLI entrypoint ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate a sparkline SVG for a keyword's rank history."
    )
    parser.add_argument(
        "--keyword-id",
        type=int,
        required=True,
        help="Keyword ID to generate sparkline for.",
    )
    args = parser.parse_args()

    svg = get_sparkline_svg(args.keyword_id)
    print(svg)


if __name__ == "__main__":
    main()
