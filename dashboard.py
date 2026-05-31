#!/usr/bin/env python3
"""
Tinka SEO Dashboard — Streamlit Multi-Page Dashboard

Integrates keyword rankings (GSC), on-page errors, and content ideas
into a single live dashboard with filters, charts, and tables.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Path setup ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.database import Database
from src.models import ERROR_TYPES

# ── Constants ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(BASE_DIR, "data", "seo_dashboard.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "data", "schema.sql")
REFRESH_INTERVAL = 3600  # seconds


# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tinka SEO Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Database Connection ──────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> Database:
    """Get or create the database connection (cached across reruns)."""
    db = Database(DB_PATH, SCHEMA_PATH)
    # Verify it has data
    try:
        summary = db.dashboard_summary()
        if summary["keywords_tracked"] == 0:
            st.warning("Database is empty. Run `python scripts/seed_data.py` to populate with sample data.")
    except Exception:
        st.error("Database not initialized. Run `python scripts/init_db.py` first.")
    return db


db = get_db()


# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("📊 Tinka SEO")
st.sidebar.caption("Giant Bubbles by Tinka")

# Domain filter
domains = db.list_domains()
domain_options = {"All Domains": None}
for d in domains:
    domain_options[d.label] = d.id

selected_domain_label = st.sidebar.selectbox(
    "Domain",
    list(domain_options.keys()),
    index=0,
)
selected_domain_id = domain_options[selected_domain_label]

# Keyword search
keyword_search = st.sidebar.text_input("🔍 Search Keywords", placeholder="e.g., giant bubble")

# Date range
st.sidebar.subheader("Date Range")
days_back = st.sidebar.slider("Days of history", 7, 90, 30)

st.sidebar.markdown("---")
st.sidebar.caption(f"Last auto-refresh: {datetime.now().strftime('%H:%M:%S')}")
if st.sidebar.button("🔄 Refresh Now"):
    st.cache_data.clear()
    st.rerun()


# ── Summary Metrics ──────────────────────────────────────────────────────────
def show_summary_metrics():
    """Display key metrics in the Overview section."""
    summary = db.dashboard_summary()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Keywords Tracked", summary["keywords_tracked"])
    with col2:
        st.metric("Rank Records", summary["rank_records"])
    with col3:
        st.metric("Open Issues", summary["open_issues"], delta_color="inverse")
    with col4:
        st.metric("Open On-Page Errors", summary["open_onpage_errors"], delta_color="inverse")
    with col5:
        st.metric("Content Backlog", summary["backlog_ideas"])

    # Domains info
    dom_text = ", ".join([f"{lbl} ({url})" for url, lbl in summary["domains"]])
    st.caption(f"Domains: {dom_text}")


# ── Keyword Rankings Tab ─────────────────────────────────────────────────│─
def show_keyword_rankings():
    """Keyword rankings tab with trend charts and filterable table."""
    st.header("📈 Keyword Rankings")
    st.caption("Historical position tracking with GSC data")

    # Get current rankings
    rankings = db.current_rankings(
        domain_id=selected_domain_id,
        keyword_filter=keyword_search if keyword_search else None,
        limit=100,
    )

    if not rankings:
        st.info("No ranking data available. Seed the database or sync GSC data.")
        return

    # Summary table
    st.subheader("Current Rankings")
    rank_data = []
    for r in rankings:
        pos = r["current_position"]
        pos_str = f"#{int(pos)}" if pos else "No data"
        rank_data.append({
            "Keyword": r["keyword"],
            "Domain": r["domain_label"],
            "Position": pos_str,
            "Position (num)": pos or 99,
            "Clicks": int(r["total_clicks"] or 0),
            "Impressions": int(r["total_impressions"] or 0),
            "CTR": f"{r['ctr']:.1%}" if r["ctr"] else "0%",
            "Volume": r["monthly_volume"],
            "Opportunity": r["opportunity_score"],
        })

    # Color-coded position indicator
    def pos_color(val):
        if val is None or val >= 99:
            return "⬜ No data"
        if val <= 5:
            return "🟢 Top 5"
        if val <= 10:
            return "🔵 Top 10"
        if val <= 20:
            return "🟡 Top 20"
        return "🔴 >20"

    for r in rank_data:
        r["Rank"] = pos_color(r["Position (num)"])

    import pandas as pd
    df = pd.DataFrame(rank_data)

    # Show the table with rank indicator
    display_cols = ["Keyword", "Domain", "Rank", "Position", "Clicks", "Impressions", "CTR", "Volume", "Opportunity"]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        column_config={
            "Opportunity": st.column_config.NumberColumn(format="%.1f"),
            "Volume": st.column_config.NumberColumn(format="%d"),
            "CTR": st.column_config.TextColumn(),
        },
        hide_index=True,
    )

    # Trend chart — show top keywords by opportunity
    st.subheader("Position Trends (Top 10 Keywords)")
    top_kw = df.nsmallest(10, "Position (num)")["Keyword"].tolist()

    if top_kw:
        # Fetch rank history for these keywords
        keywords = db.list_keywords(domain_id=selected_domain_id)
        kw_map = {k.keyword: k.id for k in keywords}

        import pandas as pd
        trend_rows = []
        for kw_text in top_kw:
            kw_id = kw_map.get(kw_text)
            if kw_id is None:
                continue
            hist = db.get_rank_history(keyword_id=kw_id, domain_id=selected_domain_id, days=days_back)
            for h in hist:
                trend_rows.append({
                    "Date": h["date"],
                    "Keyword": kw_text,
                    "Position": h["position"],
                })

        if trend_rows:
            trend_df = pd.DataFrame(trend_rows)
            trend_df["Date"] = pd.to_datetime(trend_df["Date"])
            trend_df["Position"] = pd.to_numeric(trend_df["Position"], errors="coerce")

            fig = px.line(
                trend_df,
                x="Date",
                y="Position",
                color="Keyword",
                title="Keyword Position Over Time (lower is better)",
                labels={"Position": "Search Position"},
            )
            fig.update_yaxes(autorange="reversed")  # Position 1 is best
            fig.update_layout(
                legend=dict(orientation="h", y=-0.3),
                hovermode="x unified",
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)

    # Position distribution
    st.subheader("Position Distribution")
    pos_data = [r["Position (num)"] for r in rank_data if r["Position (num)"] < 99]
    if pos_data:
        dist_fig = px.histogram(
            x=pos_data,
            nbins=20,
            title="Distribution of Keyword Positions",
            labels={"x": "Position"},
        )
        dist_fig.update_layout(height=350)
        st.plotly_chart(dist_fig, use_container_width=True)

    # Quick Wins section
    st.subheader("⚡ Quick Wins")
    quick_wins = db.get_quick_wins(domain_id=selected_domain_id, limit=10)
    if quick_wins:
        qw_data = []
        for w in quick_wins:
            qw_data.append({
                "Keyword": w["keyword"],
                "Domain": w["domain_label"],
                "Volume": w["monthly_volume"],
                "Opportunity": w["opportunity_score"],
            })
        qw_df = pd.DataFrame(qw_data)
        st.dataframe(qw_df, use_container_width=True, hide_index=True)
    else:
        st.info("No quick wins identified yet. Sync more data.")


# ── On-Page Errors Tab ───────────────────────────────────────────────────────
def show_onpage_errors():
    """On-page errors tab with severity breakdown and fix status."""
    st.header("🔧 On-Page Errors")
    st.caption("Crawl-detected page errors with severity and fix tracking")

    # Error summary
    all_errors = db.list_onpage_errors(
        domain_id=selected_domain_id,
        status="open",
        limit=500,
    )

    fixed_errors = db.list_onpage_errors(
        domain_id=selected_domain_id,
        status="fixed",
        limit=100,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Open Errors", len(all_errors))
    with col2:
        st.metric("Fixed", len(fixed_errors))
    with col3:
        total = len(all_errors) + len(fixed_errors)
        fix_rate = f"{len(fixed_errors) / max(total, 1) * 100:.0f}%" if total > 0 else "0%"
        st.metric("Fix Rate", fix_rate)

    # Severity breakdown
    import pandas as pd
    if all_errors:
        severity_counts: dict[str, int] = {}
        for e in all_errors:
            severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1

        sev_df = pd.DataFrame([
            {"Severity": k.capitalize(), "Count": v}
            for k, v in sorted(severity_counts.items(),
                                key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x[0], 3))
        ])
        col_a, col_b = st.columns([1, 2])
        with col_a:
            sev_fig = px.pie(sev_df, values="Count", names="Severity",
                            title="Error Severity Breakdown",
                            color="Severity",
                            color_discrete_map={
                                "Critical": "#FF4B4B",
                                "Warning": "#FFA500",
                                "Info": "#3498DB",
                            })
            sev_fig.update_layout(height=350)
            st.plotly_chart(sev_fig, use_container_width=True)

        with col_b:
            # Error type breakdown
            type_counts: dict[str, int] = {}
            for e in all_errors:
                type_counts[e.error_type] = type_counts.get(e.error_type, 0) + 1
            type_df = pd.DataFrame([
                {"Error Type": t.replace("_", " ").title(), "Count": c}
                for t, c in sorted(type_counts.items(), key=lambda x: -x[1])
            ])
            st.dataframe(type_df, use_container_width=True, hide_index=True)

    # Open errors table
    st.subheader("Open Errors")
    if all_errors:
        oe_data = []
        for e in all_errors:
            domain_label = ""
            for d in domains:
                if d.id == e.domain_id:
                    domain_label = d.label
                    break
            oe_data.append({
                "URL": e.url,
                "Domain": domain_label,
                "Type": e.error_type.replace("_", " ").title(),
                "Severity": e.severity.capitalize(),
                "Detail": e.detail or "",
                "Suggested Fix": e.suggested_fix or "",
                "Discovered": e.discovered_at[:10] if e.discovered_at else "",
            })

        oe_df = pd.DataFrame(oe_data)

        # Color severity
        def sev_color(s):
            colors = {"Critical": "🟥", "Warning": "🟧", "Info": "🟦"}
            return f"{colors.get(s, '⬜')} {s}"

        oe_df["Severity"] = oe_df["Severity"].apply(sev_color)

        st.dataframe(
            oe_df,
            use_container_width=True,
            column_config={
                "URL": st.column_config.TextColumn(width="medium"),
                "Detail": st.column_config.TextColumn(width="medium"),
                "Suggested Fix": st.column_config.TextColumn(width="medium"),
            },
            hide_index=True,
        )
    else:
        st.success("No open on-page errors! 🎉")

    # Error type legend
    with st.expander("📖 Error Type Legend"):
        for etype, desc in sorted(ERROR_TYPES.items()):
            st.write(f"**{etype.replace('_', ' ').title()}**: {desc}")


# ── Content Ideas Tab ────────────────────────────────────────────────────────
def show_content_ideas():
    """Content ideas tab with backlog, search, and keyword ranking context."""
    st.header("💡 Content Ideas")
    st.caption("Blog post backlog with priority scoring and keyword opportunity")

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_filter = st.selectbox(
            "Status",
            ["All", "draft", "backlog", "published", "archived"],
        )
    with col_f2:
        min_priority = st.slider("Min Priority", 1, 10, 1)
    with col_f3:
        search_text = st.text_input("Search ideas", placeholder="title or keyword...")

    # Get ideas
    if search_text:
        ideas = db.search_content_ideas(search_text)
    else:
        ideas = db.list_content_ideas(
            status=status_filter if status_filter != "All" else None,
            min_priority=min_priority,
        )

    import pandas as pd

    if ideas:
        idea_data = []
        for idea in ideas:
            idea_data.append({
                "Title": idea.title,
                "Target Keyword": idea.target_keyword,
                "Priority": f"{'⭐' * idea.priority} ({idea.priority}/10)",
                "Status": idea.status.capitalize(),
                "Effort": idea.effort.capitalize(),
                "Source": idea.source.replace("_", " ").title(),
                "Date Added": idea.date_added,
            })

        idea_df = pd.DataFrame(idea_data)
        st.dataframe(idea_df, use_container_width=True, hide_index=True)

        # Count by priority
        st.subheader("Backlog Distribution")
        priority_counts = {f"P{p}": 0 for p in range(1, 11)}
        for idea in ideas:
            priority_counts[f"P{idea.priority}"] = (
                priority_counts.get(f"P{idea.priority}", 0) + 1
            )
        p_df = pd.DataFrame([
            {"Priority": k, "Count": v}
            for k, v in sorted(priority_counts.items()) if v > 0
        ])
        if not p_df.empty:
            p_fig = px.bar(p_df, x="Priority", y="Count", title="Ideas by Priority")
            p_fig.update_layout(height=350)
            st.plotly_chart(p_fig, use_container_width=True)
    else:
        st.info("No content ideas found matching your filters.")

    # Backlog with rankings
    st.subheader("📋 Backlog with Keyword Rankings")
    backlog = db.get_backlog_with_rankings()
    if backlog:
        bl_data = []
        for b in backlog:
            bl_data.append({
                "Title": b["title"],
                "Keyword": b["target_keyword"],
                "Priority": b["priority"],
                "Volume": b["monthly_volume"],
                "Curr. Position": f"#{int(b['current_position'])}" if b["current_position"] else "No data",
                "Difficulty": f"{b['keyword_difficulty']:.0f}%" if b["keyword_difficulty"] else "N/A",
                "Opportunity": f"{b['opportunity_score']:.1f}" if b["opportunity_score"] else "N/A",
            })

        bl_df = pd.DataFrame(bl_data)
        st.dataframe(bl_df, use_container_width=True, hide_index=True)
    else:
        st.info("No backlog ideas with keyword matches.")


# ── Data Sync Tab ────────────────────────────────────────────────────────────
def show_data_sync():
    """Data sync tab with manual sync triggers and sync history."""
    st.header("🔄 Data Sync")
    st.caption("Manual sync controls and ingestion history")

    # Sync history
    st.subheader("Sync History")
    recent_syncs = db.get_recent_syncs(limit=20)
    if recent_syncs:
        import pandas as pd
        sync_data = []
        for s in recent_syncs:
            status_icon = "✅" if s["status"] == "completed" else "❌" if s["status"] == "failed" else "🔄"
            sync_data.append({
                "Status": f"{status_icon} {s['status'].capitalize()}",
                "Type": s["sync_type"].replace("_", " ").title(),
                "Rows": s["rows_processed"],
                "Started": s["started_at"][:19] if s["started_at"] else "",
                "Completed": s["completed_at"][:19] if s["completed_at"] else "",
                "Error": (s["error_detail"] or "")[:100],
            })
        sync_df = pd.DataFrame(sync_data)
        st.dataframe(sync_df, use_container_width=True, hide_index=True)
    else:
        st.info("No sync history yet.")

    # Manual sync buttons
    st.subheader("Manual Sync")
    col_s1, col_s2, col_s3 = st.columns(3)

    with col_s1:
        if st.button("🔍 Sync GSC Data", type="primary", use_container_width=True):
            with st.spinner("Syncing Google Search Console data..."):
                try:
                    from src.gsc_client import GSCClient
                    gsc = GSCClient()
                    sync_id = db.start_sync("gsc")

                    total_records = 0
                    for d in domains:
                        site_url = f"sc-domain:{d.url}"
                        results = gsc.fetch_rankings(site_url, days=7, live=False)
                        kw_results = gsc.records_for_db(results, d.id)
                        for kw_text, records in kw_results.items():
                            db.upsert_ranks_batch(records)
                            total_records += len(records)

                    db.complete_sync(sync_id, rows_processed=total_records)
                    st.success(f"Synced {total_records} rank records across {len(domains)} domains")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Sync failed: {e}")

    with col_s2:
        if st.button("📄 Import Content Ideas", use_container_width=True):
            backlog_path = os.path.join(BASE_DIR, "data", "sample_backlog.csv")
            if os.path.exists(backlog_path):
                with st.spinner("Importing content ideas..."):
                    try:
                        from src.backlog_importer import BacklogImporter
                        importer = BacklogImporter(DB_PATH, SCHEMA_PATH)
                        result = importer.import_csv(backlog_path)
                        st.success(f"Imported {result['imported']} ideas, "
                                  f"{result.get('updated', 0)} updated, "
                                  f"{result.get('skipped', 0)} skipped")
                        st.cache_data.clear()
                    except ImportError:
                        st.warning("Backlog importer not available yet.")
                    except Exception as e:
                        st.error(f"Import failed: {e}")
            else:
                st.warning("No backlog CSV found at data/sample_backlog.csv")

    with col_s3:
        if st.button("🔧 Ingest On-Page Errors", use_container_width=True):
            json_path = os.path.join(BASE_DIR, "data", "sample_onpage_errors.json")
            if os.path.exists(json_path):
                with st.spinner("Ingesting on-page errors..."):
                    try:
                        from src.onpage_ingestion import OnPageIngestion
                        ing = OnPageIngestion(DB_PATH, SCHEMA_PATH)
                        for d in domains:
                            result = ing.ingest_json(
                                json_path,
                                domain_id=d.id,
                                batch_id=f"manual-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                                close_previous=False,
                            )
                            st.success(f"Domain {d.label}: {result['imported']} errors ingested")
                        st.cache_data.clear()
                    except ImportError:
                        st.warning("On-page error ingestion module not available yet.")
                    except Exception as e:
                        st.error(f"Ingestion failed: {e}")
            else:
                st.warning("No error sample file found.")

    # Database info
    st.subheader("Database Information")
    db_path_display = DB_PATH
    if os.path.exists(DB_PATH):
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        st.caption(f"Database: `{db_path_display}` ({size_mb:.2f} MB)")
    else:
        st.caption(f"Database: `{db_path_display}` (not yet created)")


# ── Main App ─────────────────────────────────────────────────────────────────
def main():
    st.title("📊 Tinka SEO Dashboard")
    st.caption(f"Giant Bubbles | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Tabs
    tab_overview, tab_rankings, tab_errors, tab_content, tab_sync = st.tabs([
        "📋 Overview",
        "📈 Rankings",
        "🔧 On-Page Errors",
        "💡 Content Ideas",
        "🔄 Data Sync",
    ])

    with tab_overview:
        show_summary_metrics()

        # Quick overview of all sections
        st.subheader("Quick Overview")

        # Mini current rankings
        rankings = db.current_rankings(domain_id=selected_domain_id, keyword_filter=keyword_search if keyword_search else None, limit=5)
        if rankings:
            with st.expander("Top 5 Rankings by Opportunity", expanded=True):
                import pandas as pd
                mini = []
                for r in rankings[:5]:
                    mini.append({
                        "Keyword": r["keyword"],
                        "Domain": r["domain_label"],
                        "Position": f"#{int(r['current_position'])}" if r["current_position"] else "N/A",
                        "Volume": r["monthly_volume"],
                        "Score": r["opportunity_score"],
                    })
                st.dataframe(pd.DataFrame(mini), use_container_width=True, hide_index=True)

        # Mini content ideas
        ideas = db.top_content_ideas(limit=5)
        if ideas:
            with st.expander("Top 5 Content Ideas by Opportunity", expanded=True):
                import pandas as pd
                mini_i = []
                for i in ideas:
                    mini_i.append({
                        "Title": i["title"][:60] + ("..." if len(i["title"]) > 60 else ""),
                        "Keyword": i["target_keyword"],
                        "Volume": i["monthly_volume"],
                        "Score": i["opportunity_score"],
                    })
                st.dataframe(pd.DataFrame(mini_i), use_container_width=True, hide_index=True)

        # Recent syncs
        recent = db.get_recent_syncs(limit=3)
        if recent:
            with st.expander("Recent Sync Activity"):
                import pandas as pd
                sync_data = []
                for s in recent:
                    sync_data.append({
                        "Type": s["sync_type"],
                        "Status": s["status"],
                        "Rows": s["rows_processed"],
                        "When": s["started_at"][:19],
                    })
                st.dataframe(pd.DataFrame(sync_data), use_container_width=True, hide_index=True)

    with tab_rankings:
        show_keyword_rankings()

    with tab_errors:
        show_onpage_errors()

    with tab_content:
        show_content_ideas()

    with tab_sync:
        show_data_sync()

    # Footer
    st.markdown("---")
    st.caption("Tinka SEO Dashboard | Built with Streamlit | Data source: Google Search Console + Manual Research")


if __name__ == "__main__":
    main()
