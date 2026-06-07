#!/usr/bin/env python3
"""PDF Snapshot Report — generates a PDF dashboard report with 5 sections.

Sections:
  1) Site health score + grade
  2) Top 10 keywords by volume
  3) Top 5 rank movers (winners + losers)
  4) Content pipeline summary
  5) Open issues summary

Uses weasyprint for HTML-to-PDF if available; falls back to reportlab.

Usage:
    python scripts/pdf_report.py       # writes to data/report.pdf
    python scripts/pdf_report.py -o path.pdf
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "seo_dashboard.db")
DEFAULT_OUTPUT = os.path.join(BASE, "data", "report.pdf")

# ── DB helpers ────────────────────────────────────────────────────────────────


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_dicts(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_one_dict(conn: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


# ── data sections ─────────────────────────────────────────────────────────────


def section_health(conn: sqlite3.Connection) -> dict:
    """Latest site health snapshot."""
    row = fetch_one_dict(conn, """
        SELECT health_score, grade, critical_score, high_score,
               moderate_score, freshness_score,
               total_open, total_fixed,
               domain_1_name, domain_1_status, domain_1_response_time,
               domain_2_name, domain_2_status, domain_2_response_time,
               timestamp
        FROM site_health_snapshots
        ORDER BY id DESC LIMIT 1
    """)
    if row:
        row["timestamp"] = row.get("timestamp") or "N/A"
        row["grade"] = row.get("grade") or "?"
    return row or {}


def section_top_keywords(conn: sqlite3.Connection) -> list[dict]:
    """Top 10 keywords by search volume."""
    return fetch_dicts(conn, """
        SELECT keyword, volume, difficulty, opportunity_score, intent
        FROM keywords
        WHERE volume > 0
        ORDER BY volume DESC
        LIMIT 10
    """)


def section_rank_movers(conn: sqlite3.Connection) -> dict:
    """Top 5 winners and losers comparing latest two dates in rank_history."""
    dates = fetch_dicts(conn, """
        SELECT DISTINCT date FROM rank_history ORDER BY date DESC LIMIT 2
    """)
    if len(dates) < 2:
        return {"winners": [], "losers": [], "note": "Not enough rank history data"}

    latest = dates[0]["date"]
    prev = dates[1]["date"]

    # Winners: position improved (prev_pos - cur_pos is positive)
    winners = fetch_dicts(conn, """
        SELECT k.keyword, k.volume,
               r1.position AS cur_position,
               r2.position AS prev_position,
               ROUND(r2.position - r1.position, 1) AS improvement
        FROM keywords k
        JOIN rank_history r1 ON r1.keyword_id = k.id AND r1.date = ?
        JOIN rank_history r2 ON r2.keyword_id = k.id AND r2.date = ?
        WHERE r1.position > 0 AND r2.position > 0
          AND r2.position - r1.position >= 0.5
        ORDER BY improvement DESC
        LIMIT 5
    """, (latest, prev))

    # Losers: position worsened (cur_pos - prev_pos is positive)
    losers = fetch_dicts(conn, """
        SELECT k.keyword, k.volume,
               r1.position AS cur_position,
               r2.position AS prev_position,
               ROUND(r1.position - r2.position, 1) AS decline
        FROM keywords k
        JOIN rank_history r1 ON r1.keyword_id = k.id AND r1.date = ?
        JOIN rank_history r2 ON r2.keyword_id = k.id AND r2.date = ?
        WHERE r1.position > 0 AND r2.position > 0
          AND r1.position - r2.position >= 0.5
        ORDER BY decline DESC
        LIMIT 5
    """, (latest, prev))

    return {
        "winners": winners,
        "losers": losers,
        "latest_date": latest,
        "prev_date": prev,
    }


def section_content_pipeline(conn: sqlite3.Connection) -> list[dict]:
    """Count of content ideas at each pipeline stage, ordered logically."""
    return fetch_dicts(conn, """
        SELECT
            COALESCE(stage, 'ideation') AS stage,
            COUNT(*) AS count
        FROM content_ideas
        GROUP BY stage
        ORDER BY
            CASE COALESCE(stage, 'ideation')
                WHEN 'ideation'  THEN 1
                WHEN 'research'  THEN 2
                WHEN 'writing'   THEN 3
                WHEN 'editing'   THEN 4
                WHEN 'review'    THEN 5
                WHEN 'published' THEN 6
                WHEN 'archived'  THEN 7
                ELSE 99
            END
    """)


def section_open_issues(conn: sqlite3.Connection) -> dict:
    """Open onpage errors summarized by severity and type."""
    by_severity = fetch_dicts(conn, """
        SELECT severity, COUNT(*) AS count
        FROM onpage_errors
        WHERE status = 'open'
        GROUP BY severity
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'moderate' THEN 3
                WHEN 'low'      THEN 4
                ELSE 99
            END
    """)
    by_type = fetch_dicts(conn, """
        SELECT error_type, severity, COUNT(*) AS count
        FROM onpage_errors
        WHERE status = 'open'
        GROUP BY error_type, severity
        ORDER BY count DESC
        LIMIT 10
    """)
    total = sum(s["count"] for s in by_severity)
    return {"total": total, "by_severity": by_severity, "by_type": by_type}


# ── PDF generation (reportlab) ────────────────────────────────────────────────

def build_pdf_reportlab(sections: dict, output_path: str) -> str:
    """Generate PDF using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#666666"),
        spaceAfter=20,
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=16, spaceBefore=18, spaceAfter=8,
        textColor=colors.HexColor("#16213e"),
        borderWidth=0,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, spaceBefore=12, spaceAfter=6,
        textColor=colors.HexColor("#0f3460"),
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9.5, leading=13, spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "Small", parent=styles["Normal"],
        fontSize=8, leading=11, textColor=colors.HexColor("#555555"),
    )
    metric_big = ParagraphStyle(
        "MetricBig", parent=styles["Normal"],
        fontSize=28, leading=32, textColor=colors.HexColor("#16213e"),
        alignment=TA_CENTER, spaceAfter=2,
    )
    metric_label = ParagraphStyle(
        "MetricLabel", parent=styles["Normal"],
        fontSize=9, leading=11, textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER, spaceAfter=6,
    )

    elements = []

    # ── Title ──
    now_str = datetime.now().strftime("%B %d, %Y at %H:%M")
    elements.append(Paragraph("SEO Dashboard Snapshot Report", title_style))
    elements.append(Paragraph(f"Generated: {now_str}", subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    elements.append(Spacer(1, 8))

    # ── 1) Site Health ──
    elements.append(Paragraph("1. Site Health", h1_style))
    health = sections["health"]
    if health:
        grade = health.get("grade", "?")
        score = health.get("health_score", 0)
        ts = health.get("timestamp", "N/A")

        # Score + grade big display
        score_data = [
            [Paragraph(f"{score:.1f}", metric_big),
             Paragraph(f"{grade}", ParagraphStyle("GradeBig", parent=metric_big, fontSize=32, textColor=colors.HexColor("#e94560")))],
            [Paragraph("Health Score", metric_label), Paragraph("Grade", metric_label)],
        ]
        score_table = Table(score_data, colWidths=[2.3 * inch, 1.2 * inch])
        score_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8f9fa")),
        ]))
        elements.append(score_table)
        elements.append(Spacer(1, 6))

        # Detail sub-scores
        sub_data = [
            ["Component", "Score", "Weight"],
            ["Critical", f"{health.get('critical_score', 0):.1f}",
             f"{health.get('critical_weight', 0):.0%}"],
            ["High", f"{health.get('high_score', 0):.1f}",
             f"{health.get('high_weight', 0):.0%}"],
            ["Moderate", f"{health.get('moderate_score', 0):.1f}",
             f"{health.get('moderate_weight', 0):.0%}"],
            ["Freshness", f"{health.get('freshness_score', 0):.1f}",
             f"{health.get('freshness_weight', 0):.0%}"],
        ]
        sub_t = Table(sub_data, colWidths=[1.5 * inch, 1.0 * inch, 0.8 * inch])
        sub_t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(sub_t)
        elements.append(Spacer(1, 6))

        # Issues summary
        elements.append(Paragraph(
            f"Open issues: {health.get('total_open', 0)} &nbsp;|&nbsp; "
            f"Fixed issues: {health.get('total_fixed', 0)} &nbsp;|&nbsp; "
            f"Snapshot: {ts}",
            small_style,
        ))

        # Domain status
        d1 = health.get("domain_1_name", "")
        d1s = health.get("domain_1_status", "")
        d1r = health.get("domain_1_response_time", "")
        d2 = health.get("domain_2_name", "")
        d2s = health.get("domain_2_status", "")
        d2r = health.get("domain_2_response_time", "")
        elements.append(Paragraph(
            f"<b>{d1}</b>: {d1s} ({d1r}s) &nbsp;|&nbsp; "
            f"<b>{d2}</b>: {d2s} ({d2r}s)",
            small_style,
        ))
    else:
        elements.append(Paragraph("No health snapshot data available.", body_style))

    elements.append(Spacer(1, 8))

    # ── 2) Top 10 Keywords ──
    elements.append(Paragraph("2. Top 10 Keywords by Volume", h1_style))
    kws = sections["top_keywords"]
    if kws:
        kw_data = [["#", "Keyword", "Volume", "Difficulty", "Intent"]]
        for i, kw in enumerate(kws, 1):
            kw_data.append([
                str(i),
                kw["keyword"],
                str(kw["volume"]),
                str(kw["difficulty"]) if kw.get("difficulty") is not None else "-",
                kw.get("intent") or "-",
            ])
        kw_t = Table(kw_data, colWidths=[0.3 * inch, 2.8 * inch, 0.7 * inch, 0.8 * inch, 0.9 * inch])
        kw_t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (3, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ]))
        elements.append(kw_t)
    else:
        elements.append(Paragraph("No keyword data available.", body_style))

    elements.append(Spacer(1, 8))

    # ── 3) Rank Movers ──
    elements.append(Paragraph("3. Top 5 Rank Movers", h1_style))
    movers = sections["rank_movers"]
    if "note" in movers:
        elements.append(Paragraph(movers["note"], body_style))
    else:
        elements.append(Paragraph(
            f"Comparing <b>{movers.get('latest_date', '?')}</b> vs "
            f"<b>{movers.get('prev_date', '?')}</b>",
            small_style,
        ))
        elements.append(Spacer(1, 6))

        # Winners
        elements.append(Paragraph("Winners (rising in rank)", h2_style))
        winners = movers.get("winners", [])
        if winners:
            w_data = [["Keyword", "Vol.", "Prev Pos", "Cur Pos", "Gain"]]
            for w in winners:
                w_data.append([
                    w["keyword"],
                    str(w.get("volume", "")),
                    str(w.get("prev_position", "")),
                    str(w.get("cur_position", "")),
                    f"+{w.get('improvement', '')}",
                ])
            w_t = Table(w_data, colWidths=[2.5 * inch, 0.6 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch])
            w_t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b4332")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#d8f3dc")]),
            ]))
            elements.append(w_t)
        else:
            elements.append(Paragraph("No winners found.", body_style))

        elements.append(Spacer(1, 6))

        # Losers
        elements.append(Paragraph("Losers (dropping in rank)", h2_style))
        losers = movers.get("losers", [])
        if losers:
            l_data = [["Keyword", "Vol.", "Prev Pos", "Cur Pos", "Drop"]]
            for l in losers:
                l_data.append([
                    l["keyword"],
                    str(l.get("volume", "")),
                    str(l.get("prev_position", "")),
                    str(l.get("cur_position", "")),
                    f"-{l.get('decline', '')}",
                ])
            l_t = Table(l_data, colWidths=[2.5 * inch, 0.6 * inch, 0.7 * inch, 0.7 * inch, 0.6 * inch])
            l_t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6b2020")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8d7da")]),
            ]))
            elements.append(l_t)
        else:
            elements.append(Paragraph("No losers found.", body_style))

    elements.append(Spacer(1, 8))

    # ── 4) Content Pipeline ──
    elements.append(Paragraph("4. Content Pipeline Summary", h1_style))
    pipe = sections["content_pipeline"]
    if pipe:
        total_pipe = sum(p["count"] for p in pipe)
        elements.append(Paragraph(f"Total content ideas: <b>{total_pipe}</b>", body_style))
        elements.append(Spacer(1, 4))
        p_data = [["Stage", "Count", "% of Total"]]
        for p in pipe:
            pct = round(100.0 * p["count"] / total_pipe, 1) if total_pipe > 0 else 0
            p_data.append([p["stage"].capitalize(), str(p["count"]), f"{pct}%"])
        p_t = Table(p_data, colWidths=[1.5 * inch, 0.8 * inch, 0.8 * inch])
        p_t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ]))
        elements.append(p_t)
    else:
        elements.append(Paragraph("No content ideas found.", body_style))

    elements.append(Spacer(1, 8))

    # ── 5) Open Issues ──
    elements.append(Paragraph("5. Open Issues Summary", h1_style))
    issues = sections["open_issues"]
    if issues["total"] > 0:
        elements.append(Paragraph(
            f"Total open issues: <b>{issues['total']}</b>", body_style
        ))
        elements.append(Spacer(1, 4))

        # By severity
        elements.append(Paragraph("By Severity", h2_style))
        sev_data = [["Severity", "Count"]]
        for s in issues["by_severity"]:
            sev_data.append([s["severity"].capitalize(), str(s["count"])])
        sev_t = Table(sev_data, colWidths=[1.5 * inch, 0.8 * inch])
        sev_t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ]))
        elements.append(sev_t)
        elements.append(Spacer(1, 6))

        # Top issue types
        elements.append(Paragraph("Top Issue Types", h2_style))
        if issues["by_type"]:
            type_data = [["Error Type", "Severity", "Count"]]
            for t in issues["by_type"]:
                type_data.append([
                    t["error_type"].replace("_", " ").title(),
                    t["severity"].capitalize(),
                    str(t["count"]),
                ])
            type_t = Table(type_data, colWidths=[2.0 * inch, 1.0 * inch, 0.6 * inch])
            type_t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ]))
            elements.append(type_t)
    else:
        elements.append(Paragraph("No open issues found. Great job!", body_style))

    # ── Footer ──
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    elements.append(Paragraph(
        f"Tinka SEO Dashboard — Generated {now_str}",
        ParagraphStyle("Footer", parent=small_style, textColor=colors.HexColor("#999999")),
    ))

    # Build
    doc.build(elements)
    return output_path


# ── PDF generation (weasyprint HTML) ──────────────────────────────────────────

def build_pdf_weasyprint(sections: dict, output_path: str) -> str:
    """Generate PDF via weasyprint HTML-to-PDF."""
    from weasyprint import HTML

    h = sections["health"]
    health_html = ""
    if h:
        health_html = f"""
        <div class="health-cards">
          <div class="card">
            <div class="card-value">{h.get('health_score', 0):.1f}</div>
            <div class="card-label">Health Score</div>
          </div>
          <div class="card grade">
            <div class="card-value">{h.get('grade', '?')}</div>
            <div class="card-label">Grade</div>
          </div>
        </div>
        <table class="sub-table">
          <tr><th>Component</th><th>Score</th><th>Weight</th></tr>
          <tr><td>Critical</td><td>{h.get('critical_score', 0):.1f}</td><td>{h.get('critical_weight', 0):.0%}</td></tr>
          <tr><td>High</td><td>{h.get('high_score', 0):.1f}</td><td>{h.get('high_weight', 0):.0%}</td></tr>
          <tr><td>Moderate</td><td>{h.get('moderate_score', 0):.1f}</td><td>{h.get('moderate_weight', 0):.0%}</td></tr>
          <tr><td>Freshness</td><td>{h.get('freshness_score', 0):.1f}</td><td>{h.get('freshness_weight', 0):.0%}</td></tr>
        </table>
        <p class="small">Open issues: {h.get('total_open', 0)} | Fixed issues: {h.get('total_fixed', 0)} | Snapshot: {h.get('timestamp', 'N/A')}</p>
        <p class="small"><strong>{h.get('domain_1_name', '')}</strong>: {h.get('domain_1_status', '')} ({h.get('domain_1_response_time', '')}s) | <strong>{h.get('domain_2_name', '')}</strong>: {h.get('domain_2_status', '')} ({h.get('domain_2_response_time', '')}s)</p>
        """

    # Keywords HTML
    kws_html = ""
    if sections["top_keywords"]:
        rows = "".join(
            f"<tr><td>{i}</td><td>{kw['keyword']}</td><td>{kw['volume']}</td><td>{kw.get('difficulty') or '-'}</td><td>{kw.get('intent') or '-'}</td></tr>"
            for i, kw in enumerate(sections["top_keywords"], 1)
        )
        kws_html = f"<table><tr><th>#</th><th>Keyword</th><th>Volume</th><th>Diff.</th><th>Intent</th></tr>{rows}</table>"
    else:
        kws_html = "<p>No keyword data available.</p>"

    # Rank movers HTML
    movers = sections["rank_movers"]
    movers_html = ""
    if "note" in movers:
        movers_html = f"<p>{movers['note']}</p>"
    else:
        ld = movers.get("latest_date", "?")
        pd = movers.get("prev_date", "?")
        mover_rows = ""
        for w in movers.get("winners", []):
            mover_rows += f"<tr class='winner'><td>{w['keyword']}</td><td>{w.get('volume', '')}</td><td>{w.get('prev_position', '')}</td><td>{w.get('cur_position', '')}</td><td>+{w.get('improvement', '')}</td></tr>"
        for l in movers.get("losers", []):
            mover_rows += f"<tr class='loser'><td>{l['keyword']}</td><td>{l.get('volume', '')}</td><td>{l.get('prev_position', '')}</td><td>{l.get('cur_position', '')}</td><td>-{l.get('decline', '')}</td></tr>"
        movers_html = f"""
        <p class="small">Comparing <strong>{ld}</strong> vs <strong>{pd}</strong></p>
        <table><tr><th>Keyword</th><th>Vol.</th><th>Prev</th><th>Cur</th><th>Change</th></tr>{mover_rows}</table>
        """

    # Pipeline HTML
    pipe = sections["content_pipeline"]
    total_pipe = sum(p["count"] for p in pipe) if pipe else 0
    if pipe:
        pipe_rows = "".join(
            f"<tr><td>{p['stage'].capitalize()}</td><td>{p['count']}</td><td>{round(100.0 * p['count'] / total_pipe, 1) if total_pipe > 0 else 0}%</td></tr>"
            for p in pipe
        )
        pipe_html = f"<p>Total content ideas: <strong>{total_pipe}</strong></p><table><tr><th>Stage</th><th>Count</th><th>%</th></tr>{pipe_rows}</table>"
    else:
        pipe_html = "<p>No content ideas found.</p>"

    # Issues HTML
    issues = sections["open_issues"]
    if issues["total"] > 0:
        sev_rows = "".join(f"<tr><td>{s['severity'].capitalize()}</td><td>{s['count']}</td></tr>" for s in issues["by_severity"])
        type_rows = "".join(
            f"<tr><td>{t['error_type'].replace('_', ' ').title()}</td><td>{t['severity'].capitalize()}</td><td>{t['count']}</td></tr>"
            for t in issues["by_type"]
        )
        issues_html = f"""
        <p>Total open issues: <strong>{issues['total']}</strong></p>
        <h3>By Severity</h3>
        <table><tr><th>Severity</th><th>Count</th></tr>{sev_rows}</table>
        <h3>Top Issue Types</h3>
        <table><tr><th>Error Type</th><th>Severity</th><th>Count</th></tr>{type_rows}</table>
        """
    else:
        issues_html = "<p>No open issues found. Great job!</p>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SEO Dashboard Snapshot Report</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #333; font-size: 10pt; line-height: 1.4; }}
  h1 {{ color: #16213e; font-size: 18pt; border-bottom: 2px solid #16213e; padding-bottom: 4px; margin-top: 24px; }}
  h2 {{ color: #0f3460; font-size: 13pt; margin-top: 16px; }}
  h3 {{ color: #0f3460; font-size: 11pt; margin-top: 12px; }}
  .report-title {{ font-size: 24pt; color: #1a1a2e; margin-bottom: 2px; }}
  .report-subtitle {{ font-size: 10pt; color: #888; margin-bottom: 16px; }}
  .health-cards {{ display: flex; gap: 16px; margin: 12px 0; }}
  .card {{ background: #f8f9fa; border: 1px solid #ddd; border-radius: 8px; padding: 12px 24px; text-align: center; min-width: 120px; }}
  .card.grade {{ background: #fff0f0; border-color: #e94560; }}
  .card-value {{ font-size: 28pt; font-weight: bold; color: #16213e; }}
  .card.grade .card-value {{ color: #e94560; }}
  .card-label {{ font-size: 9pt; color: #888; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
  th {{ background: #16213e; color: white; font-weight: bold; padding: 6px 8px; text-align: left; font-size: 9pt; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #ddd; font-size: 9pt; }}
  tr:nth-child(even) td {{ background: #f8f9fa; }}
  .winner td {{ background: #d8f3dc !important; }}
  .loser td {{ background: #f8d7da !important; }}
  .small {{ font-size: 8pt; color: #666; }}
  .footer {{ margin-top: 24px; border-top: 1px solid #ccc; padding-top: 8px; font-size: 8pt; color: #999; }}
</style>
</head>
<body>
  <div class="report-title">SEO Dashboard Snapshot Report</div>
  <div class="report-subtitle">Generated: {now_str}</div>

  <h1>1. Site Health</h1>
  {health_html}

  <h1>2. Top 10 Keywords by Volume</h1>
  {kws_html}

  <h1>3. Rank Movers</h1>
  {movers_html}

  <h1>4. Content Pipeline Summary</h1>
  {pipe_html}

  <h1>5. Open Issues Summary</h1>
  {issues_html}

  <div class="footer">Tinka SEO Dashboard — Generated {now_str}</div>
</body>
</html>"""

    HTML(string=html_content).write_pdf(output_path)
    return output_path


# ── main ──────────────────────────────────────────────────────────────────────


def assemble_data(conn: sqlite3.Connection) -> dict:
    return {
        "health": section_health(conn),
        "top_keywords": section_top_keywords(conn),
        "rank_movers": section_rank_movers(conn),
        "content_pipeline": section_content_pipeline(conn),
        "open_issues": section_open_issues(conn),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate a PDF snapshot report of the SEO dashboard."
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output PDF path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    conn = get_conn()
    sections = assemble_data(conn)
    conn.close()

    # Try weasyprint first, fall back to reportlab
    weasy_ok = False
    try:
        import weasyprint  # noqa: F401
        weasy_ok = True
    except ImportError:
        weasy_ok = False

    try:
        if weasy_ok:
            build_pdf_weasyprint(sections, output_path)
        else:
            build_pdf_reportlab(sections, output_path)
        print(output_path)
    except Exception as e:
        print(f"ERROR generating PDF: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
