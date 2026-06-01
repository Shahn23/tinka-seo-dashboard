"""SEO Dashboard — Giant Bubbles by Tinka
Streamlit 4-tab dashboard connecting to SQLite DB with GSC data, SEO issues, content ideas.

Usage: uv run streamlit run seo_dashboard.py --server.headless true --server.port 8501
"""
import sqlite3
import subprocess
import json
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="SEO Dashboard", layout="wide", initial_sidebar_state="expanded")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card { background: #1a1c2e; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2d4a; }
    .metric-card h3 { margin: 0; font-size: 28px; font-weight: 700; color: #00d4aa; }
    .metric-card p { margin: 4px 0 0; font-size: 13px; color: #8888aa; }
    .severity-critical { display: inline-block; background: #ff4444; color: white; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .severity-high { display: inline-block; background: #ff8800; color: white; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .severity-moderate { display: inline-block; background: #ffcc00; color: #222; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .quick-win { background: linear-gradient(135deg, #002b1a, #004d2e); border: 1px solid #00d4aa; border-radius: 10px; padding: 10px; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px 6px 0 0; padding: 8px 20px; }
</style>
""", unsafe_allow_html=True)

# ── Database helpers ─────────────────────────────────────────────────────────
def get_conn():
    """Get a read-only connection (WAL mode from init)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(ttl=30)
def query_db(sql, params=()):
    conn = get_conn()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    except Exception as e:
        st.error(f"DB query error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def run_sync():
    """Run the GSC sync script."""
    script = os.path.join(PROJECT_DIR, "scripts", "sync_gsc.py")
    if not os.path.exists(script):
        return {"status": "error", "message": "sync_gsc.py not found"}
    try:
        result = subprocess.run(
            ["python", script, "--live", "--days", "7"],
            capture_output=True, text=True, timeout=120, cwd=PROJECT_DIR
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Sync timed out (120s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🔍 SEO Dashboard")
st.sidebar.markdown("**Giant Bubbles by Tinka**")
st.sidebar.markdown("---")

domains_df = query_db("SELECT name, display_name FROM domains WHERE is_active=1")
domain_options = ["All"] + domains_df["name"].tolist() if not domains_df.empty else ["All"]
selected_domain = st.sidebar.selectbox("Domain", domain_options)

cats_df = query_db("SELECT DISTINCT category FROM keywords ORDER BY category")
cat_options = ["All"] + cats_df["category"].tolist() if not cats_df.empty else ["All"]
selected_category = st.sidebar.selectbox("Category", cat_options)

intent_options = ["All", "informational", "commercial", "transactional", "navigational"]
selected_intent = st.sidebar.selectbox("Intent", intent_options)

auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=False)
if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Build WHERE clause
where_parts = []
params = []
if selected_domain != "All":
    where_parts.append("d.name = ?")
    params.append(selected_domain)
if selected_category != "All":
    where_parts.append("k.category = ?")
    params.append(selected_category)
if selected_intent != "All":
    where_parts.append("k.intent = ?")
    params.append(selected_intent)
where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🔑 Keyword Rankings",
    "🛠️ SEO Issues",
    "📝 Content Backlog",
    "🔄 Sync & Settings"
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: KEYWORD RANKINGS
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Keyword Rankings")

    kw_df = query_db(f"""
        SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent, k.volume,
               k.opportunity_score, k.difficulty, k.is_high_priority,
               rh.position AS current_position, rh.clicks, rh.impressions
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN (
            SELECT keyword_id, position, clicks, impressions, date
            FROM rank_history
            WHERE (keyword_id, date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        ) rh ON k.id = rh.keyword_id
        {where_clause}
        ORDER BY k.volume DESC
    """, params)

    if not kw_df.empty:
        # Metric cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"""
            <div class="metric-card"><h3>{len(kw_df)}</h3><p>Keywords Tracked</p></div>
            """, unsafe_allow_html=True)
        with col2:
            avg_pos = kw_df["current_position"].dropna().mean()
            st.markdown(f"""
            <div class="metric-card"><h3>{avg_pos:.1f}</h3><p>Avg Position</p></div>
            """, unsafe_allow_html=True)
        with col3:
            total_clicks = int(kw_df["clicks"].dropna().sum())
            st.markdown(f"""
            <div class="metric-card"><h3>{total_clicks:,}</h3><p>Total Clicks (7d)</p></div>
            """, unsafe_allow_html=True)
        with col4:
            total_imp = int(kw_df["impressions"].dropna().sum())
            st.markdown(f"""
            <div class="metric-card"><h3>{total_imp:,}</h3><p>Total Impressions (7d)</p></div>
            """, unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            # Volume by category
            vol_cat = kw_df.groupby("category")["volume"].sum().reset_index().sort_values("volume", ascending=True)
            fig = px.bar(vol_cat, x="volume", y="category", orientation="h",
                         title="Search Volume by Category",
                         color_discrete_sequence=["#00d4aa"],
                         labels={"volume": "Monthly Searches", "category": ""})
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            # Opportunity score distribution
            fig = px.histogram(kw_df, x="opportunity_score", nbins=10,
                               title="Opportunity Score Distribution",
                               color_discrete_sequence=["#00d4aa"],
                               labels={"opportunity_score": "Score"})
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Quick wins
        qw = kw_df[(kw_df["opportunity_score"] >= 7.0) & (kw_df["difficulty"] <= 40) & (kw_df["current_position"] > 5)].copy()
        if not qw.empty:
            st.subheader("⚡ Quick Wins (High Opportunity, Low Difficulty)")
            qw = qw.sort_values("opportunity_score", ascending=False).head(6)
            qw_cols = st.columns(min(3, len(qw)))
            for i, (_, row) in enumerate(qw.iterrows()):
                with qw_cols[i % 3]:
                    st.markdown(f"""
                    <div class="quick-win">
                        <strong style="color:#00d4aa">{row['keyword']}</strong><br>
                        <span style="color:#aaa;font-size:12px">{row['domain']}</span><br>
                        <span style="color:#888;font-size:11px">
                            Score: {row['opportunity_score']:.0f} | Vol: {row['volume']:,} | Pos: {row['current_position']:.0f}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

        # Full keyword table
        with st.expander("📋 All Keywords", expanded=False):
            display_cols = ["domain", "keyword", "category", "intent", "volume",
                           "opportunity_score", "difficulty", "current_position", "clicks", "impressions"]
            show_df = kw_df[display_cols].copy()
            show_df["opportunity_score"] = show_df["opportunity_score"].round(1)
            show_df["current_position"] = show_df["current_position"].round(1)
            show_df = show_df.rename(columns={
                "opportunity_score": "Score", "current_position": "Pos",
                "clicks": "Clicks", "impressions": "Imp", "volume": "Vol"
            })
            st.dataframe(show_df, use_container_width=True, hide_index=True)

        # Trend chart (keyword selector)
        st.subheader("📈 Position Trend")
        kw_names = kw_df["keyword"].tolist()
        sel_kw = st.selectbox("Select a keyword to view trend", kw_names, key="kw_trend")
        if sel_kw:
            trend = query_db("""
                SELECT rh.date, rh.position, rh.clicks, rh.impressions
                FROM rank_history rh
                JOIN keywords k ON rh.keyword_id = k.id
                WHERE k.keyword = ?
                ORDER BY rh.date
            """, [sel_kw])

            if not trend.empty:
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.line(trend, x="date", y="position", title=f"{sel_kw} — Position Trend",
                                  markers=True, color_discrete_sequence=["#ff6b6b"])
                    fig.update_traces(line=dict(width=2))
                    fig.update_layout(yaxis=dict(autorange="reversed"), height=300,
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_color="#ccc")
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=trend["date"], y=trend["clicks"], mode="lines+markers",
                                             name="Clicks", line=dict(color="#4ecdc4")))
                    fig.add_trace(go.Scatter(x=trend["date"], y=trend["impressions"], mode="lines+markers",
                                             name="Impressions", line=dict(color="#ffe66d")))
                    fig.update_layout(title="Clicks & Impressions", height=300,
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_color="#ccc", legend=dict(orientation="h", y=1.12))
                    st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No keyword data found. Run `scripts/init_db.py` to seed data.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: SEO ISSUES
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Technical SEO Issues")

    where2 = []
    params2 = []
    if selected_domain != "All":
        where2.append("d.name = ?")
        params2.append(selected_domain)
    sev_filter = st.selectbox("Severity", ["All", "critical", "high", "moderate", "low"], key="sev_filter")
    if sev_filter != "All":
        where2.append("e.severity = ?")
        params2.append(sev_filter)
    where2_clause = f"WHERE {' AND '.join(where2)}" if where2 else ""

    issues_df = query_db(f"""
        SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
               e.description, e.suggestion, e.status, e.created_at, e.fixed_at
        FROM onpage_errors e
        JOIN domains d ON e.domain_id = d.id
        {where2_clause.replace('d.', where2_clause.count('d.') > 0 and 'd.' or '')}
        ORDER BY
            CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END,
            e.id
    """, params2)

    if not issues_df.empty:
        open_issues = issues_df[issues_df["status"] == "open"]
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.markdown(f'<div class="metric-card"><h3>{len(open_issues)}</h3><p>Open Issues</p></div>', unsafe_allow_html=True)
        with col2:
            cnt = len(open_issues[open_issues["severity"] == "critical"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>Critical</p></div>', unsafe_allow_html=True)
        with col3:
            cnt = len(open_issues[open_issues["severity"] == "high"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>High</p></div>', unsafe_allow_html=True)
        with col4:
            cnt = len(open_issues[open_issues["severity"] == "moderate"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>Moderate</p></div>', unsafe_allow_html=True)
        with col5:
            fixed = len(issues_df[issues_df["status"] == "fixed"])
            st.markdown(f'<div class="metric-card"><h3>{fixed}</h3><p>Fixed</p></div>', unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            sev_counts = open_issues["severity"].value_counts().reset_index()
            sev_counts.columns = ["severity", "count"]
            color_map = {"critical": "#ff4444", "high": "#ff8800", "moderate": "#ffcc00", "low": "#88ccff"}
            fig = px.pie(sev_counts, values="count", names="severity", title="Issues by Severity",
                         color="severity", color_discrete_map=color_map)
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            dom_counts = open_issues["domain"].value_counts().reset_index()
            dom_counts.columns = ["domain", "count"]
            fig = px.bar(dom_counts, x="domain", y="count", title="Issues by Domain",
                         color_discrete_sequence=["#4ecdc4"])
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)

        # Issues table
        with st.expander("📋 All Issues", expanded=True):
            for _, row in issues_df.iterrows():
                sev_badge = f'<span class="severity-{row["severity"]}">{row["severity"]}</span>'
                status_icon = "✅" if row["status"] == "fixed" else "🔴" if row["status"] == "open" else "🟡"
                st.markdown(f"""
                **{status_icon} {row["error_type"].replace("_", " ").title()}** {sev_badge}<br>
                <span style="color:#888;font-size:12px">{row["domain"]} | {row["page_url"]}</span><br>
                {row["description"]}<br>
                <span style="color:#4ecdc4;font-size:12px">💡 {row["suggestion"]}</span>
                """, unsafe_allow_html=True)
                st.divider()
    else:
        st.info("No SEO issues found. Run `scripts/init_db.py` to seed data.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: CONTENT BACKLOG
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Content Idea Backlog")

    where3 = []
    params3 = []
    if selected_category != "All":
        where3.append("ci.category = ?")
        params3.append(selected_category)
    effort_filter = st.selectbox("Effort", ["All", "easy", "medium", "hard"], key="effort_filter")
    if effort_filter != "All":
        where3.append("ci.effort = ?")
        params3.append(effort_filter)
    where3_clause = f"WHERE {' AND '.join(where3)}" if where3 else ""

    ideas_df = query_db(f"""
        SELECT ci.id, ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
               ci.opportunity_score, ci.effort, ci.content_type, ci.status,
               vw.current_position, vw.domain
        FROM content_ideas ci
        LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
        {where3_clause}
        ORDER BY ci.opportunity_score DESC
    """, params3)

    if not ideas_df.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="metric-card"><h3>{len(ideas_df)}</h3><p>Ideas</p></div>', unsafe_allow_html=True)
        with col2:
            avg_score = ideas_df["opportunity_score"].mean()
            st.markdown(f'<div class="metric-card"><h3>{avg_score:.1f}</h3><p>Avg Score</p></div>', unsafe_allow_html=True)
        with col3:
            total_vol = int(ideas_df["estimated_searches"].sum())
            st.markdown(f'<div class="metric-card"><h3>{total_vol:,}</h3><p>Total Monthly Searches</p></div>', unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.scatter(ideas_df, x="estimated_searches", y="opportunity_score",
                             size="estimated_searches", color="category", hover_name="title",
                             title="Opportunity Matrix: Score vs Search Volume",
                             labels={"estimated_searches": "Monthly Searches", "opportunity_score": "Score"})
            fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            cat_counts = ideas_df.groupby("category")["estimated_searches"].sum().reset_index()
            fig = px.bar(cat_counts.sort_values("estimated_searches"), x="estimated_searches", y="category",
                         orientation="h", title="Total Search Volume by Category",
                         color_discrete_sequence=["#ff6b6b"],
                         labels={"estimated_searches": "Monthly Searches", "category": ""})
            fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Top picks
        top = ideas_df[ideas_df["opportunity_score"] >= 8.0].head(6)
        if not top.empty:
            st.subheader("⭐ Top Picks (Score ≥ 8.0)")
            for _, row in top.iterrows():
                st.markdown(f"""
                **{row['title']}** — Score: {row['opportunity_score']:.0f} | Searches: {row['estimated_searches']:,}
                <br><span style="color:#888;font-size:12px">Keyword: {row['target_keyword']} | Effort: {row['effort']} | Type: {row['content_type']}</span>
                """, unsafe_allow_html=True)
                st.divider()

        with st.expander("📋 All Ideas", expanded=False):
            display = ideas_df[["title", "target_keyword", "category", "estimated_searches",
                               "opportunity_score", "effort", "content_type"]].copy()
            display = display.rename(columns={
                "target_keyword": "Keyword", "estimated_searches": "Searches",
                "opportunity_score": "Score", "content_type": "Type"
            })
            st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.info("No content ideas found.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: SYNC & SETTINGS
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Sync & Settings")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📡 Google Search Console Sync")
        last_sync = query_db("""
            SELECT source, status, rows_synced, started_at, completed_at, error
            FROM sync_log
            WHERE source = 'gsc'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        if not last_sync.empty:
            row = last_sync.iloc[0]
            icon = "✅" if row["status"] == "success" else "❌" if row["status"] == "failed" else "🔄"
            st.markdown(f"""
            {icon} **Last Sync:** {row['completed_at'] or 'In progress...'}<br>
            **Status:** {row['status']}<br>
            **Rows:** {int(row['rows_synced']) if pd.notna(row['rows_synced']) else 'N/A'}
            """)
            if pd.notna(row["error"]):
                st.error(row["error"])
        else:
            st.info("No syncs yet. Click the button below to run the first sync.")

        if st.button("🔄 Run GSC Sync Now", type="primary"):
            with st.spinner("Syncing GSC data... (up to 120s)"):
                result = run_sync()
            if result["status"] == "success":
                st.success("Sync complete!")
                st.code(result["stdout"] if result.get("stdout") else "OK")
                st.cache_data.clear()
            else:
                st.error(f"Sync failed: {result.get('message', result.get('stderr', 'Unknown error'))}")

        # Sync history
        sync_hist = query_db("""
            SELECT source, status, rows_synced, started_at, completed_at
            FROM sync_log ORDER BY started_at DESC LIMIT 10
        """)
        if not sync_hist.empty:
            with st.expander("Sync History", expanded=False):
                st.dataframe(sync_hist, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("📁 File Status")
        files = {
            "keyword_research.json": os.path.join(PROJECT_DIR, "keyword_research.json"),
            "blog_content_ideas.json": os.path.join(PROJECT_DIR, "blog_content_ideas.json"),
            "giantbubbles-technical-seo-audit.json": os.path.join(PROJECT_DIR, "giantbubbles-technical-seo-audit.json"),
            "Database (seo_dashboard.db)": os.path.join(PROJECT_DIR, "data", "seo_dashboard.db"),
        }
        for label, fpath in files.items():
            exists = os.path.exists(fpath)
            icon = "✅" if exists else "❌"
            size = os.path.getsize(fpath) if exists else 0
            st.markdown(f"{icon} **{label}** — {size:,} bytes" if exists else f"{icon} **{label}** — Not found")

    st.divider()

    # Vercel Deployment
    st.subheader("🚀 Vercel Deployment")
    st.markdown("""
    To deploy this dashboard on Vercel:

    1. **Install Vercel CLI:** `npm i -g vercel`
    2. **Create requirements.txt** with: `streamlit`, `pandas`, `plotly`, `google-api-python-client`, `pyyaml`
    3. **Create vercel.json:**
    ```json
    {
        "builds": [{"src": "seo_dashboard.py", "use": "@vercel/python"}],
        "routes": [{"src": "/(.*)", "dest": "seo_dashboard.py"}]
    }
    ```
    4. **Run:** `vercel --prod`
    5. Set the `CRON_SCHEDULE=0 6 * * *` environment variable for daily sync

    **Alternative:** Deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) for free.
    """)

    # Cron setup
    st.subheader("⏰ Daily Sync (Cron)")
    st.markdown("""
    Set up daily automatic GSC data sync:

    - **Hermes cron:** `hermes cron create "Sync GSC data" --schedule "0 6 * * *" --command "cd /c/Users/heysh/AppData/Local/hermes/kanban/boards/dhiya/workspaces/t_0b644a51 && python scripts/sync_gsc.py --live --days 1"`
    - **Windows Task Scheduler:** Create a basic task that runs daily at 6 AM: `python C:\\Users\\heysh\\AppData\\Local\\hermes\\kanban\\boards\\dhiya\\workspaces\\t_0b644a51\\scripts\\sync_gsc.py --live --days 1`
    """)

    st.caption(f"Dashboard path: {PROJECT_DIR}")
