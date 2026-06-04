"""SEO Dashboard v0.2 — Giant Bubbles by Tinka
MOZ/SemRush-level analytics: rank distribution, position changes, competitive gap,
content performance correlation, alerts, and export.

Usage: uv run streamlit run seo_dashboard.py --server.headless true --server.port 8501
"""
import sqlite3
import subprocess
import json
import os
import csv
import io
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests
import urllib.parse

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="SEO Dashboard v0.5 — Rusty + GEO", layout="wide", initial_sidebar_state="expanded")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card { background: #1a1c2e; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #2a2d4a; }
    .metric-card h3 { margin: 0; font-size: 28px; font-weight: 700; color: #00d4aa; }
    .metric-card p { margin: 4px 0 0; font-size: 13px; color: #8888aa; }
    .metric-card .sub { font-size: 11px; color: #666; }
    .severity-critical { display: inline-block; background: #ff4444; color: white; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .severity-high { display: inline-block; background: #ff8800; color: white; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .severity-moderate { display: inline-block; background: #ffcc00; color: #222; padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .quick-win { background: linear-gradient(135deg, #002b1a, #004d2e); border: 1px solid #00d4aa; border-radius: 10px; padding: 10px; }
    .winner-card { background: linear-gradient(135deg, #002b1a, #004d2e); border: 1px solid #00d4aa; border-radius: 10px; padding: 10px; text-align: center; }
    .loser-card { background: linear-gradient(135deg, #2e001a, #4d002e); border: 1px solid #ff4444; border-radius: 10px; padding: 10px; text-align: center; }
    .alert-box { background: #2a1a1a; border-left: 4px solid #ff4444; padding: 10px 15px; border-radius: 6px; margin: 8px 0; }
    .alert-good { background: #1a2a1a; border-left: 4px solid #00d4aa; padding: 10px 15px; border-radius: 6px; margin: 8px 0; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px 6px 0 0; padding: 8px 20px; }
    .geo-card { background: linear-gradient(135deg, #0d2137, #1a3a5c); border: 1px solid #58a6ff; border-radius: 10px; padding: 14px; }
    .pass-badge { display: inline-block; background: #00d4aa; color: #000; padding: 1px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; }
    .fail-badge { display: inline-block; background: #ff4444; color: #fff; padding: 1px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; }
    .warn-badge { display: inline-block; background: #ff8800; color: #fff; padding: 1px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; }
    .score-circle { width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 700; margin: 0 auto; }
</style>
""", unsafe_allow_html=True)

# ── Database helpers ─────────────────────────────────────────────────────────
def get_conn():
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
            "stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Sync timed out (120s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_date_range() -> tuple:
    """Return (start_date, end_date) from rank_history."""
    df = query_db("SELECT MIN(date) as min_d, MAX(date) as max_d FROM rank_history")
    if df.empty or df.iloc[0]["min_d"] is None:
        return (datetime.now() - timedelta(days=30), datetime.now())
    return (pd.to_datetime(df.iloc[0]["min_d"]), pd.to_datetime(df.iloc[0]["max_d"]))

def df_to_csv(dataframe) -> bytes:
    output = io.BytesIO()
    dataframe.to_csv(output, index=False)
    return output.getvalue()

def color_pos_change(val):
    """Color a position change value: green for improvement (negative), red for drop."""
    if val is None or pd.isna(val):
        return ""
    if val < 0:
        return "color: #00d4aa; font-weight: 600"
    elif val > 0:
        return "color: #ff4444; font-weight: 600"
    return "color: #888"

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("🔍 SEO Dashboard")
st.sidebar.markdown("**Giant Bubbles by Tinka**")
st.sidebar.markdown("**v0.5** — Rusty SEO + AI GEO Features")

# Domain filter
domains_df = query_db("SELECT name, display_name FROM domains WHERE is_active=1")
domain_options = ["All"] + domains_df["name"].tolist() if not domains_df.empty else ["All"]
selected_domain = st.sidebar.selectbox("Domain", domain_options)

# Category filter
cats_df = query_db("SELECT DISTINCT category FROM keywords ORDER BY category")
cat_options = ["All"] + cats_df["category"].tolist() if not cats_df.empty else ["All"]
selected_category = st.sidebar.selectbox("Category", cat_options)

# Intent filter
intent_options = ["All", "informational", "commercial", "transactional", "navigational"]
selected_intent = st.sidebar.selectbox("Intent", intent_options)

# Time period for trend comparison
period_options = {"7 days": 7, "14 days": 14, "30 days": 30, "60 days": 60, "90 days": 90}
selected_period_label = st.sidebar.selectbox("Trend Period", list(period_options.keys()), index=2)
selected_period_days = period_options[selected_period_label]

auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=False)
if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

st.sidebar.markdown("---")
last_sync = query_db("SELECT completed_at FROM sync_log WHERE source='gsc' ORDER BY completed_at DESC LIMIT 1")
sync_label = last_sync.iloc[0]["completed_at"] if not last_sync.empty else "Never"
st.sidebar.caption(f"Last sync: {str(sync_label)[:19] if sync_label != 'Never' else 'Never'}")

# Build WHERE clause for keyword queries
where_parts_kw = []
params_kw = []
if selected_domain != "All":
    where_parts_kw.append("d.name = ?")
    params_kw.append(selected_domain)
if selected_category != "All":
    where_parts_kw.append("k.category = ?")
    params_kw.append(selected_category)
if selected_intent != "All":
    where_parts_kw.append("k.intent = ?")
    params_kw.append(selected_intent)
where_clause_kw = f"WHERE {' AND '.join(where_parts_kw)}" if where_parts_kw else ""

# ── Quick Overview (for non-technical stakeholders) ──────────────────────────
ov_total_kw = query_db("SELECT COUNT(*) as c FROM keywords")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM keywords").empty else 0
ov_ranked = query_db("SELECT COUNT(DISTINCT k.id) as c FROM keywords k JOIN rank_history rh ON k.id=rh.keyword_id")["c"].iloc[0] if not query_db("SELECT COUNT(DISTINCT k.id) as c FROM keywords k JOIN rank_history rh ON k.id=rh.keyword_id").empty else 0
ov_open_issues = query_db("SELECT COUNT(*) as c FROM onpage_errors WHERE status='open'")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM onpage_errors WHERE status='open'").empty else 0
ov_ideas = query_db("SELECT COUNT(*) as c FROM content_ideas")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM content_ideas").empty else 0
ov_avg_pos = query_db("SELECT AVG(position) as c FROM rank_history WHERE (keyword_id, date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)")["c"].iloc[0] if not query_db("SELECT AVG(position) as c FROM rank_history WHERE (keyword_id, date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)").empty else 0

st.markdown(f"""
<div style="background:linear-gradient(135deg,#0d1117,#161b22);border:1px solid #30363d;border-radius:12px;padding:16px 20px;margin-bottom:16px;">
    <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div style="text-align:center;min-width:100px;"><span style="font-size:26px;font-weight:700;color:#00d4aa;">{ov_total_kw}</span><br><span style="font-size:12px;color:#8b949e;">Keywords Tracked</span></div>
        <div style="text-align:center;min-width:100px;"><span style="font-size:26px;font-weight:700;color:#58a6ff;">{ov_ranked}</span><br><span style="font-size:12px;color:#8b949e;">Keywords Ranked</span></div>
        <div style="text-align:center;min-width:100px;"><span style="font-size:26px;font-weight:700;color:{'#ff4444' if ov_open_issues > 0 else '#00d4aa'};">{ov_open_issues}</span><br><span style="font-size:12px;color:#8b949e;">Open Issues</span></div>
        <div style="text-align:center;min-width:100px;"><span style="font-size:26px;font-weight:700;color:#d2a8ff;">{ov_ideas}</span><br><span style="font-size:12px;color:#8b949e;">Content Ideas</span></div>
        <div style="text-align:center;min-width:100px;"><span style="font-size:26px;font-weight:700;color:{'#00d4aa' if ov_avg_pos and ov_avg_pos <= 10 else '#ff8800' if ov_avg_pos and ov_avg_pos <= 20 else '#ff4444'};">{f'{ov_avg_pos:.1f}' if ov_avg_pos else 'N/A'}</span><br><span style="font-size:12px;color:#8b949e;">Avg Position</span></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_labels = [
    "🔑 Rankings",
    "📊 Competitive",
    "🛠️ SEO Issues",
    "📝 Content",
    "✍️ Content Studio",
    "🔍 Deep Audit",
    "🌐 AI Visibility",
    "🔔 Alerts",
    "🔄 Settings",
]
tabs = st.tabs(tab_labels)
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = tabs

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: KEYWORD RANKINGS (ENHANCED)
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Keyword Rankings & Position Tracking")
    st.caption("Rank distribution, winners/losers, and trend analysis — like MOZ Pro's Rank Tracker")

    # ── 1a. Current keywords with latest ranks ───────────────────────────
    kw_df = query_db(f"""
        SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent, k.volume,
               k.opportunity_score, k.difficulty, k.is_high_priority,
               rh.position AS current_position, rh.clicks, rh.impressions, rh.ctr
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN (
            SELECT keyword_id, position, clicks, impressions, ctr, date
            FROM rank_history
            WHERE (keyword_id, date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        ) rh ON k.id = rh.keyword_id
        {where_clause_kw}
        ORDER BY k.volume DESC
    """, params_kw)

    if kw_df.empty:
        st.info("No keyword data found. Run `scripts/init_db.py` to seed data.")

    # ── 1b. Position change (today vs N days ago) ─────────────────────────
    days_ago_date = (datetime.now() - timedelta(days=selected_period_days)).strftime("%Y-%m-%d")
    pos_df = query_db(f"""
        SELECT k.id, k.keyword, d.name AS domain,
               latest.position AS current_position,
               past.position AS past_position
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN (
            SELECT keyword_id, position, date
            FROM rank_history
            WHERE (keyword_id, date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        ) latest ON k.id = latest.keyword_id
        LEFT JOIN rank_history past ON k.id = past.keyword_id AND past.date = '{days_ago_date}'
        {where_clause_kw}
    """, params_kw)

    if not pos_df.empty:
        pos_df["position_change"] = pos_df.apply(
            lambda r: r["past_position"] - r["current_position"] if pd.notna(r["past_position"]) and pd.notna(r["current_position"]) else None,
            axis=1
        )
        pos_df["direction"] = pos_df["position_change"].apply(
            lambda x: "up" if pd.notna(x) and x > 0 else ("down" if pd.notna(x) and x < 0 else "same" if pd.notna(x) else "new")
        )

        # Merge position change into kw_df
        kw_df = kw_df.merge(pos_df[["id", "position_change", "past_position", "direction"]], on="id", how="left")

    # ── RANK DISTRIBUTION ─────────────────────────────────────────────────
    st.subheader("📊 Rank Distribution")

    col_dist1, col_dist2, col_dist3, col_dist4 = st.columns(4)

    tracked = kw_df[kw_df["current_position"].notna()]
    top3 = len(tracked[tracked["current_position"] <= 3])
    top10 = len(tracked[tracked["current_position"] <= 10])
    top20 = len(tracked[tracked["current_position"] <= 20])
    outside = len(tracked[tracked["current_position"] > 20])

    with col_dist1:
        st.markdown(f'<div class="metric-card"><h3>{top3}</h3><p>Top 3</p><span class="sub">{top3/len(tracked)*100:.1f}%</span></div>', unsafe_allow_html=True)
    with col_dist2:
        st.markdown(f'<div class="metric-card"><h3>{top10}</h3><p>Top 10</p><span class="sub">{top10/len(tracked)*100:.1f}%</span></div>', unsafe_allow_html=True)
    with col_dist3:
        st.markdown(f'<div class="metric-card"><h3>{top20}</h3><p>Top 20</p><span class="sub">{top20/len(tracked)*100:.1f}%</span></div>', unsafe_allow_html=True)
    with col_dist4:
        st.markdown(f'<div class="metric-card"><h3>{outside}</h3><p>Outside Top 20</p><span class="sub">{outside/len(tracked)*100:.1f}%</span></div>', unsafe_allow_html=True)

    # Position distribution bar chart
    if not tracked.empty:
        tracked["bucket"] = pd.cut(tracked["current_position"],
                                    bins=[0, 3, 5, 10, 20, 100],
                                    labels=["Top 3", "4-5", "6-10", "11-20", "20+"])
        dist_counts = tracked["bucket"].value_counts().reindex(["Top 3", "4-5", "6-10", "11-20", "20+"]).reset_index()
        dist_counts.columns = ["bucket", "count"]
        colors = ["#00d4aa", "#4ecdc4", "#ffe66d", "#ff8800", "#ff4444"]

        col_a, col_b = st.columns([1, 1])
        with col_a:
            fig = px.bar(dist_counts, x="bucket", y="count", title="Rank Distribution Buckets",
                         color="bucket", color_discrete_sequence=colors,
                         labels={"bucket": "Position", "count": "Keywords"})
            fig.update_layout(showlegend=False, height=300,
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            # Distribution trend over time (weekly average)
            dist_trend = query_db("""
                SELECT date,
                       SUM(CASE WHEN position <= 3 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) * 100 AS top3_pct,
                       SUM(CASE WHEN position <= 10 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) * 100 AS top10_pct
                FROM rank_history rh
                JOIN keywords k ON rh.keyword_id = k.id
                JOIN domains d ON k.domain_id = d.id
                GROUP BY date ORDER BY date
            """)
            if not dist_trend.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=dist_trend["date"], y=dist_trend["top3_pct"],
                                         mode="lines", name="Top 3", line=dict(color="#00d4aa", width=2)))
                fig.add_trace(go.Scatter(x=dist_trend["date"], y=dist_trend["top10_pct"],
                                         mode="lines", name="Top 10", line=dict(color="#4ecdc4", width=2)))
                fig.update_layout(title="Rank Distribution Trend", height=300,
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font_color="#ccc", legend=dict(orientation="h", y=1.12))
                st.plotly_chart(fig, use_container_width=True)

        st.divider()

    # ── WINNERS & LOSERS ──────────────────────────────────────────────────
    st.subheader(f"🏆 Winners & Losers (last {selected_period_days} days)")

    col_wl1, col_wl2 = st.columns(2)

    with col_wl1:
        st.markdown("**📈 Biggest Improvements**")
        winners = pos_df[pos_df["direction"] == "up"].dropna(subset=["position_change"]).nlargest(6, "position_change")
        if not winners.empty:
            for _, row in winners.iterrows():
                st.markdown(f"""
                <div class="winner-card">
                    <strong style="color:#00d4aa">{row['keyword']}</strong><br>
                    <span style="color:#aaa;font-size:12px">{row['domain']}</span><br>
                    <span style="font-size:14px">↑ {int(row['position_change'])} spots</span><br>
                    <span style="color:#888;font-size:11px">#{row['current_position']:.0f} ← #{row['past_position']:.0f}</span>
                </div>
                """, unsafe_allow_html=True)
                st.markdown("")
        else:
            st.caption("No improvements in this period.")

    with col_wl2:
        st.markdown("**📉 Biggest Drops**")
        losers = pos_df[pos_df["direction"] == "down"].dropna(subset=["position_change"]).nsmallest(6, "position_change")
        if not losers.empty:
            for _, row in losers.iterrows():
                st.markdown(f"""
                <div class="loser-card">
                    <strong style="color:#ff6b6b">{row['keyword']}</strong><br>
                    <span style="color:#aaa;font-size:12px">{row['domain']}</span><br>
                    <span style="font-size:14px">↓ {abs(int(row['position_change']))} spots</span><br>
                    <span style="color:#888;font-size:11px">#{row['current_position']:.0f} ← #{row['past_position']:.0f}</span>
                </div>
                """, unsafe_allow_html=True)
                st.markdown("")
        else:
            st.caption("No drops in this period.")

    st.divider()

    # ── METRIC CARDS + CHARTS ─────────────────────────────────────────────
    if not kw_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><h3>{len(kw_df)}</h3><p>Keywords Tracked</p></div>', unsafe_allow_html=True)
        with col2:
            avg_pos = kw_df["current_position"].dropna().mean()
            st.markdown(f'<div class="metric-card"><h3>{avg_pos:.1f}</h3><p>Avg Position</p></div>', unsafe_allow_html=True)
        with col3:
            total_clicks = int(kw_df["clicks"].dropna().sum())
            st.markdown(f'<div class="metric-card"><h3>{total_clicks:,}</h3><p>Total Clicks (7d)</p></div>', unsafe_allow_html=True)
        with col4:
            total_imp = int(kw_df["impressions"].dropna().sum())
            st.markdown(f'<div class="metric-card"><h3>{total_imp:,}</h3><p>Total Impressions (7d)</p></div>', unsafe_allow_html=True)

        # Summary charts
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            vol_cat = kw_df.groupby("category")["volume"].sum().reset_index().sort_values("volume", ascending=True)
            fig = px.bar(vol_cat, x="volume", y="category", orientation="h",
                         title="Search Volume by Category", color_discrete_sequence=["#00d4aa"],
                         labels={"volume": "Monthly Searches", "category": ""})
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
        with col_c2:
            fig = px.histogram(kw_df, x="opportunity_score", nbins=10,
                               title="Opportunity Score Distribution", color_discrete_sequence=["#00d4aa"],
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

        # ── ENHANCED KEYWORD TABLE with position change ───────────────────
        with st.expander("📋 All Keywords with Position Changes", expanded=False):
            if "position_change" in kw_df.columns:
                display_cols = ["domain", "keyword", "category", "intent", "volume",
                               "current_position", "position_change", "past_position",
                               "clicks", "impressions", "ctr"]
                show_df = kw_df[display_cols].copy()
                show_df["current_position"] = show_df["current_position"].round(1)
                show_df["past_position"] = show_df["past_position"].round(1)
                show_df["position_change"] = show_df["position_change"].apply(
                    lambda x: f"+{int(x)}" if pd.notna(x) and x > 0 else (f"{int(x)}" if pd.notna(x) and x < 0 else "-" if pd.notna(x) else "new")
                )
                show_df = show_df.rename(columns={
                    "current_position": "Pos", "position_change": f"Δ {selected_period_days}d",
                    "past_position": f"Prev ({selected_period_days}d ago)",
                    "clicks": "Clicks", "impressions": "Imp", "volume": "Vol", "ctr": "CTR"
                })
                if show_df["CTR"].dtype.kind in 'fi':
                    show_df["CTR"] = show_df["CTR"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
                st.dataframe(show_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(kw_df, use_container_width=True, hide_index=True)

        # Trend chart (keyword selector)
        st.subheader("📈 Position Trend")
        kw_names = kw_df["keyword"].tolist()
        sel_kw = st.selectbox("Select a keyword to view trend", kw_names, key="kw_trend")
        if sel_kw:
            trend = query_db(f"""
                SELECT rh.date, rh.position, rh.clicks, rh.impressions, rh.ctr
                FROM rank_history rh
                JOIN keywords k ON rh.keyword_id = k.id
                WHERE k.keyword = ? AND rh.date >= date('now', '-{selected_period_days} days')
                ORDER BY rh.date
            """, [sel_kw])

            if not trend.empty:
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    fig = px.line(trend, x="date", y="position", title=f"{sel_kw} — Position Trend ({selected_period_label})",
                                  markers=True, color_discrete_sequence=["#ff6b6b"])
                    fig.update_traces(line=dict(width=2))
                    fig.update_layout(yaxis=dict(autorange="reversed"), height=300,
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
                    st.plotly_chart(fig, use_container_width=True)
                with col_t2:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=trend["date"], y=trend["clicks"], mode="lines+markers",
                                             name="Clicks", line=dict(color="#4ecdc4")))
                    fig.add_trace(go.Scatter(x=trend["date"], y=trend["impressions"], mode="lines+markers",
                                             name="Impressions", line=dict(color="#ffe66d")))
                    fig.update_layout(title=f"Clicks & Impressions ({selected_period_label})", height=300,
                                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_color="#ccc", legend=dict(orientation="h", y=1.12))
                    st.plotly_chart(fig, use_container_width=True)

                # Performance summary for selected keyword
                avg_ctr = trend["ctr"].mean()
                max_pos = trend["position"].min()
                min_pos = trend["position"].max()
                trend_direction = trend["position"].iloc[-1] - trend["position"].iloc[0]
                trend_arrow = "↑ improving" if trend_direction < 0 else "↓ dropping" if trend_direction > 0 else "→ stable"
                st.caption(f"**Performance:** Best: #{max_pos:.0f} | Worst: #{min_pos:.0f} | "
                          f"Avg CTR: {avg_ctr*100:.1f}% | Trend: {trend_arrow} ({abs(trend_direction):.0f} spots)")

    # ── New Keyword Opportunities ─────────────────────────────────────────
    st.divider()
    st.subheader("🆕 New Keyword Opportunities (from Research)")
    st.caption("Keywords identified — no ranking data yet. These need content to target.")

    new_kw_df = query_db(f"""
        SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent, k.volume,
               k.opportunity_score, k.difficulty
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN rank_history rh ON k.id = rh.keyword_id
        WHERE rh.id IS NULL
        AND (d.name = ? OR ? = 'All')
        AND (k.category = ? OR ? = 'All')
        AND (k.intent = ? OR ? = 'All')
        ORDER BY k.opportunity_score DESC, k.volume DESC
    """, [selected_domain, selected_domain, selected_category, selected_category, selected_intent, selected_intent])

    if not new_kw_df.empty:
        col_n1, col_n2, col_n3 = st.columns(3)
        with col_n1:
            st.markdown(f'<div class="metric-card"><h3>{len(new_kw_df)}</h3><p>Untracked Keywords</p></div>', unsafe_allow_html=True)
        with col_n2:
            avg_opp = new_kw_df["opportunity_score"].mean()
            st.markdown(f'<div class="metric-card"><h3>{avg_opp:.1f}</h3><p>Avg Opportunity</p></div>', unsafe_allow_html=True)
        with col_n3:
            total_vol = int(new_kw_df["volume"].sum())
            st.markdown(f'<div class="metric-card"><h3>{total_vol:,}</h3><p>Total Monthly Searches</p></div>', unsafe_allow_html=True)

        top_new = new_kw_df[new_kw_df["opportunity_score"] >= 8.0].head(9)
        if not top_new.empty:
            st.markdown("**⭐ Top Opportunities (Score ≥ 8.0)**")
            cols = st.columns(3)
            for i, (_, row) in enumerate(top_new.iterrows()):
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="quick-win">
                        <strong style="color:#00d4aa">{row['keyword']}</strong><br>
                        <span style="color:#aaa;font-size:12px">{row['domain']} · {row['category']}</span><br>
                        <span style="color:#888;font-size:11px">
                            Opp: {row['opportunity_score']:.0f} | Vol: {row['volume']:,} | Diff: {row['difficulty']}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

        with st.expander("📋 All New Keyword Opportunities", expanded=False):
            show_new = new_kw_df[["domain", "keyword", "category", "intent", "volume", "opportunity_score", "difficulty"]].copy()
            show_new = show_new.rename(columns={"opportunity_score": "Score", "volume": "Vol"})
            show_new["Score"] = show_new["Score"].round(1)
            st.dataframe(show_new, use_container_width=True, hide_index=True)

            # Export button
            csv_data = df_to_csv(show_new)
            st.download_button("📥 Download CSV", data=csv_data, file_name="new_keyword_opportunities.csv",
                               mime="text/csv", key="newkw_export")
    else:
        st.info("All keywords have ranking data — no untracked keywords.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: COMPETITIVE ANALYSIS (NEW — SemRush level)
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("📊 Competitive & Keyword Gap Analysis")
    st.caption("Market coverage, share of voice, and gap analysis — like SemRush's Domain vs Domain")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🔮 Available with API integration:</strong>
    Add <strong>Google Ads API</strong> (real search volume & competition) and <strong>Ahrefs/Moz API</strong>
    (backlink profiles, domain authority, competitor domains) to unlock full competitive analysis.
    Currently using GSC + keyword research data.
    </div>
    """, unsafe_allow_html=True)

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        # ── Share of Voice by Domain ──────────────────────────────────────
        st.subheader("📡 Share of Voice (Impressions)")
        sov_df = query_db("""
            SELECT d.name AS domain, k.keyword,
                   rh.impressions, rh.clicks, rh.position
            FROM rank_history rh
            JOIN keywords k ON rh.keyword_id = k.id
            JOIN domains d ON k.domain_id = d.id
            WHERE (rh.keyword_id, rh.date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        """)
        if not sov_df.empty:
            domain_sov = sov_df.groupby("domain").agg(
                total_impressions=("impressions", "sum"),
                total_clicks=("clicks", "sum"),
                keywords=("keyword", "count"),
                avg_position=("position", "mean")
            ).reset_index()

            fig = px.pie(domain_sov, values="total_impressions", names="domain",
                         title="Share of Voice (Impressions)",
                         color_discrete_sequence=["#00d4aa", "#ff6b6b"])
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(domain_sov.rename(columns={
                "total_impressions": "Impressions", "total_clicks": "Clicks",
                "keywords": "Keywords", "avg_position": "Avg Pos"
            }), use_container_width=True, hide_index=True)

    with col_g2:
        # ── Keyword Gap Analysis ──────────────────────────────────────────
        st.subheader("🔍 Keyword Gap Analysis")
        st.caption("Keywords one domain ranks for that the other doesn't")

        gap_df = query_db("""
            SELECT k.keyword, d.name AS domain, k.category, k.volume, k.opportunity_score
            FROM keywords k
            JOIN domains d ON k.domain_id = d.id
            JOIN rank_history rh ON k.id = rh.keyword_id
            WHERE (rh.keyword_id, rh.date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
            ORDER BY k.volume DESC
        """)

        if not gap_df.empty and selected_domain != "All":
            # For the selected domain, show what the OTHER domain doesn't rank for
            ranked_keywords = set(gap_df[gap_df["domain"] == selected_domain]["keyword"])
            all_keywords = set(gap_df["keyword"])
            gap_keywords = all_keywords - ranked_keywords

            other_domain = [d for d in domain_options if d != selected_domain and d != "All"]
            other_label = other_domain[0] if other_domain else "the other domain"

            st.markdown(f"**Keywords {other_label} ranks for that {selected_domain} doesn't:**")

            gap_items = gap_df[gap_df["keyword"].isin(gap_keywords)].drop_duplicates(subset=["keyword"])
            gap_items = gap_items.nlargest(10, "volume")

            if not gap_items.empty:
                for _, row in gap_items.iterrows():
                    st.markdown(f"""
                    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:8px; padding:8px; margin:4px 0;">
                        <span style="color:#00d4aa">{row['keyword']}</span>
                        <span style="color:#888;font-size:12px;float:right">
                            Vol: {row['volume']:,} | Score: {row['opportunity_score']:.0f}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No gap keywords found.")

        elif selected_domain == "All":
            st.info("Select a specific domain to see the keyword gap with the other domain.")

    st.divider()

    # ── Market Coverage by Category ───────────────────────────────────────
    st.subheader("🌐 Market Coverage by Category")
    cov_df = query_db("""
        SELECT d.name AS domain, k.category, COUNT(*) AS keyword_count,
               SUM(rh.impressions) AS total_impressions,
               AVG(rh.position) AS avg_position
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN rank_history rh ON k.id = rh.keyword_id
            AND (rh.keyword_id, rh.date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        GROUP BY d.name, k.category
        ORDER BY d.name, total_impressions DESC
    """)
    if not cov_df.empty:
        fig = px.sunburst(cov_df, path=["domain", "category"], values="keyword_count",
                          title="Keyword Coverage by Domain & Category",
                          color="keyword_count", color_continuous_scale="tealgrn",
                          hover_data={"total_impressions": True, "avg_position": ":.1f"})
        fig.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc",
                          margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Keyword Cluster Heatmap ───────────────────────────────────────────
    st.subheader("🗂️ Keyword Cluster Matrix")
    st.caption("Keywords grouped by category × intent — see coverage gaps at a glance")

    cluster_df = query_db(f"""
        SELECT k.category, k.intent, COUNT(*) AS cnt,
               AVG(rh.position) AS avg_pos, SUM(rh.impressions) AS total_imp
        FROM keywords k
        LEFT JOIN rank_history rh ON k.id = rh.keyword_id
            AND (rh.keyword_id, rh.date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        JOIN domains d ON k.domain_id = d.id
        {where_clause_kw}
        GROUP BY k.category, k.intent
    """, params_kw)

    if not cluster_df.empty:
        pivot = cluster_df.pivot_table(index="category", columns="intent", values="cnt", fill_value=0)
        fig = px.imshow(pivot, text_auto=True, aspect="auto",
                        title="Keyword Count by Category × Intent",
                        color_continuous_scale="tealgrn",
                        labels=dict(x="Intent", y="Category", color="Keywords"))
        fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc",
                          margin=dict(l=120, r=0, t=30, b=0))
        fig.update_xaxes(side="bottom")
        st.plotly_chart(fig, use_container_width=True)

    # ── Export competitor data ────────────────────────────────────────────
    st.divider()
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        if not sov_df.empty:
            csv_data = df_to_csv(sov_df)
            st.download_button("📥 Download Share of Voice Data", data=csv_data,
                               file_name="share_of_voice.csv", mime="text/csv")
    with export_col2:
        st.info("💡 **Tip:** Set up Google Ads API for real search volumes and Moz/Ahrefs for backlink analysis.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: SEO ISSUES (ENHANCED)
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Technical SEO Issues")
    st.caption("P0/P1 prioritization board, fix progress tracking — like SemRush Site Audit")

    where2 = []
    params2 = []
    if selected_domain != "All":
        where2.append("d.name = ?")
        params2.append(selected_domain)
    sev_filter = st.selectbox("Severity", ["All", "critical", "high", "moderate", "low"], key="sev_filter_t3")
    if sev_filter != "All":
        where2.append("e.severity = ?")
        params2.append(sev_filter)
    status_filter = st.selectbox("Status", ["All", "open", "fixed", "in_progress"], key="status_filter_t3")
    if status_filter != "All":
        where2.append("e.status = ?")
        params2.append(status_filter)
    where2_clause = f"WHERE {' AND '.join(where2)}" if where2 else ""

    issues_df = query_db(f"""
        SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
               e.description, e.suggestion, e.status, e.created_at, e.fixed_at
        FROM onpage_errors e
        JOIN domains d ON e.domain_id = d.id
        {where2_clause}
        ORDER BY
            CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END,
            CASE e.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
            e.id
    """, params2)

    if not issues_df.empty:
        open_issues = issues_df[issues_df["status"] == "open"]
        fixed_issues = issues_df[issues_df["status"] == "fixed"]

        # Metric cards
        col_e1, col_e2, col_e3, col_e4, col_e5 = st.columns(5)
        with col_e1:
            st.markdown(f'<div class="metric-card"><h3>{len(open_issues)}</h3><p>Open Issues</p></div>', unsafe_allow_html=True)
        with col_e2:
            cnt = len(open_issues[open_issues["severity"] == "critical"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>Critical</p></div>', unsafe_allow_html=True)
        with col_e3:
            cnt = len(open_issues[open_issues["severity"] == "high"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>High</p></div>', unsafe_allow_html=True)
        with col_e4:
            cnt = len(open_issues[open_issues["severity"] == "moderate"])
            st.markdown(f'<div class="metric-card"><h3>{cnt}</h3><p>Moderate</p></div>', unsafe_allow_html=True)
        with col_e5:
            total_issues = len(issues_df)
            fix_rate = len(fixed_issues) / total_issues * 100 if total_issues > 0 else 0
            st.markdown(f'<div class="metric-card"><h3>{fix_rate:.0f}%</h3><p>Fix Rate</p><span class="sub">{len(fixed_issues)} fixed / {total_issues} total</span></div>', unsafe_allow_html=True)

        # ── P0/P1 Action Board ──────────────────────────────────────────
        st.subheader("🚨 P0/P1 Action Board")
        p0 = open_issues[open_issues["severity"] == "critical"].head(5)
        p1 = open_issues[open_issues["severity"] == "high"].head(5)

        col_p0, col_p1 = st.columns(2)
        with col_p0:
            st.markdown("**🔴 P0 — Critical (Fix Now)**")
            if not p0.empty:
                for _, row in p0.iterrows():
                    st.markdown(f"""
                    <div class="alert-box">
                        <strong>{row['error_type'].replace('_', ' ').title()}</strong><br>
                        <span style="color:#aaa;font-size:12px">{row['domain']} | {row['page_url']}</span><br>
                        {row['description']}<br>
                        <span style="color:#4ecdc4;font-size:12px">💡 {row['suggestion']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("No critical issues open! 🎉")

        with col_p1:
            st.markdown("**🟠 P1 — High Priority (Fix Soon)**")
            if not p1.empty:
                for _, row in p1.iterrows():
                    st.markdown(f"""
                    <div style="background:#2a1a1a; border-left:4px solid #ff8800; padding:10px 15px; border-radius:6px; margin:8px 0;">
                        <strong>{row['error_type'].replace('_', ' ').title()}</strong><br>
                        <span style="color:#aaa;font-size:12px">{row['domain']} | {row['page_url']}</span><br>
                        {row['description']}<br>
                        <span style="color:#4ecdc4;font-size:12px">💡 {row['suggestion']}</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("No high-priority issues open! 🎉")

        st.divider()

        # ── Fix Progress Trend ────────────────────────────────────────────
        st.subheader("📈 Fix Progress Over Time")
        fix_history = query_db("""
            SELECT date(created_at) AS date, severity, COUNT(*) AS opened
            FROM onpage_errors
            GROUP BY date(created_at), severity
        """)
        fix_completed = query_db("""
            SELECT date(fixed_at) AS date, severity, COUNT(*) AS fixed
            FROM onpage_errors WHERE fixed_at IS NOT NULL
            GROUP BY date(fixed_at), severity
        """)

        if not fix_history.empty or not fix_completed.empty:
            col_prog1, col_prog2 = st.columns(2)
            with col_prog1:
                # Issues opened over time
                if not fix_history.empty:
                    fig = px.bar(fix_history, x="date", y="opened", color="severity",
                                 title="Issues Opened Over Time",
                                 color_discrete_map={"critical": "#ff4444", "high": "#ff8800",
                                                     "moderate": "#ffcc00", "low": "#88ccff"})
                    fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_color="#ccc", legend=dict(orientation="h", y=1.12))
                    st.plotly_chart(fig, use_container_width=True)
            with col_prog2:
                # Issues fixed over time
                if not fix_completed.empty:
                    fig = px.bar(fix_completed, x="date", y="fixed", color="severity",
                                 title="Issues Fixed Over Time",
                                 color_discrete_map={"critical": "#ff4444", "high": "#ff8800",
                                                     "moderate": "#ffcc00", "low": "#88ccff"})
                    fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_color="#ccc", legend=dict(orientation="h", y=1.12))
                    st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Summary Charts ────────────────────────────────────────────────
        col_e3a, col_e3b = st.columns(2)
        with col_e3a:
            sev_counts = open_issues["severity"].value_counts().reset_index()
            sev_counts.columns = ["severity", "count"]
            color_map = {"critical": "#ff4444", "high": "#ff8800", "moderate": "#ffcc00", "low": "#88ccff"}
            fig = px.pie(sev_counts, values="count", names="severity", title="Open Issues by Severity",
                         color="severity", color_discrete_map=color_map)
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)
        with col_e3b:
            dom_counts = open_issues["domain"].value_counts().reset_index()
            dom_counts.columns = ["domain", "count"]
            fig = px.bar(dom_counts, x="domain", y="count", title="Open Issues by Domain",
                         color_discrete_sequence=["#4ecdc4"])
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)

        # Issues table
        with st.expander("📋 All Issues", expanded=False):
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

        # CSV export
        csv_data = df_to_csv(issues_df)
        st.download_button("📥 Download Issues CSV", data=csv_data,
                           file_name="seo_issues.csv", mime="text/csv")
    else:
        st.info("No SEO issues found. Run `scripts/init_db.py` to seed data.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: CONTENT BACKLOG (ENHANCED)
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Content Idea Backlog")
    st.caption("Content performance correlation & priority matrix — like SemRush Content Marketing")

    where3 = []
    params3 = []
    if selected_category != "All":
        where3.append("ci.category = ?")
        params3.append(selected_category)
    effort_filter = st.selectbox("Effort", ["All", "easy", "medium", "hard"], key="effort_t4")
    if effort_filter != "All":
        where3.append("ci.effort = ?")
        params3.append(effort_filter)
    source_filter = st.selectbox("Source", ["All", "new-keyword-blog-topics", "keyword-research (Blog Ideas)", "seed (original)", "manual"], key="source_t4")
    src_map = {"new-keyword-blog-topics": "new-keyword-blog-topics", "keyword-research (Blog Ideas)": "keyword-research", "seed (original)": "seed", "manual": "manual"}
    if source_filter != "All":
        where3.append("ci.source = ?")
        params3.append(src_map[source_filter])
    where3_clause = f"WHERE {' AND '.join(where3)}" if where3 else ""

    ideas_df = query_db(f"""
        SELECT ci.id, ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
               ci.opportunity_score, ci.effort, ci.content_type, ci.status, ci.source,
               vw.current_position, vw.domain
        FROM content_ideas ci
        LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
        {where3_clause}
        ORDER BY ci.opportunity_score DESC
    """, params3)

    if not ideas_df.empty:
        # Metric cards
        col_i1, col_i2, col_i3 = st.columns(3)
        with col_i1:
            st.markdown(f'<div class="metric-card"><h3>{len(ideas_df)}</h3><p>Ideas</p></div>', unsafe_allow_html=True)
        with col_i2:
            avg_score = ideas_df["opportunity_score"].mean()
            st.markdown(f'<div class="metric-card"><h3>{avg_score:.1f}</h3><p>Avg Score</p></div>', unsafe_allow_html=True)
        with col_i3:
            total_vol = int(ideas_df["estimated_searches"].sum())
            st.markdown(f'<div class="metric-card"><h3>{total_vol:,}</h3><p>Total Monthly Searches</p></div>', unsafe_allow_html=True)

        # ── Priority Matrix: Effort × Opportunity ─────────────────────────
        st.subheader("🎯 Priority Matrix (Effort vs Opportunity Score)")
        col_m1, col_m2 = st.columns(2)

        with col_m1:
            fig = px.scatter(ideas_df, x="estimated_searches", y="opportunity_score",
                             size="estimated_searches", color="category", hover_name="title",
                             title="Opportunity Matrix: Score vs Search Volume",
                             labels={"estimated_searches": "Monthly Searches", "opportunity_score": "Score"})
            fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            st.plotly_chart(fig, use_container_width=True)

        with col_m2:
            # Effort distribution
            effort_counts = ideas_df.groupby(["effort", "category"]).size().reset_index(name="count")
            fig = px.treemap(effort_counts, path=["effort", "category"], values="count",
                             title="Content Ideas by Effort & Category",
                             color="count", color_continuous_scale="tealgrn")
            fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc",
                              margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # ── Content Performance Correlation ───────────────────────────────
        st.subheader("📊 Content Performance Correlation")
        st.caption("Content ideas linked to actual rankings — track if published content is ranking for its target keyword")

        correlated = ideas_df[ideas_df["current_position"].notna()].copy()
        uncorrelated = ideas_df[ideas_df["current_position"].isna()].copy()

        col_cor1, col_cor2 = st.columns(2)
        with col_cor1:
            st.markdown(f"**✅ Ranked Content ({len(correlated)} ideas)**")
            if not correlated.empty:
                correlated = correlated.sort_values("current_position")
                for _, row in correlated.head(6).iterrows():
                    pos_color = "#00d4aa" if row["current_position"] <= 10 else "#ff8800" if row["current_position"] <= 30 else "#ff4444"
                    st.markdown(f"""
                    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:8px; padding:10px; margin:6px 0;">
                        <strong style="color:{pos_color}">#{row['current_position']:.0f}</strong>
                        <strong> {row['title'][:50]}</strong><br>
                        <span style="color:#888;font-size:12px">Keyword: {row['target_keyword']} | Score: {row['opportunity_score']:.0f}</span>
                    </div>
                    """, unsafe_allow_html=True)
        with col_cor2:
            st.markdown(f"**📝 Needs Content ({len(uncorrelated)} ideas)**")
            if not uncorrelated.empty:
                uncorrelated = uncorrelated.sort_values("opportunity_score", ascending=False)
                for _, row in uncorrelated.head(6).iterrows():
                    st.markdown(f"""
                    <div class="quick-win">
                        <strong style="color:#00d4aa">{row['title'][:50]}</strong><br>
                        <span style="color:#aaa;font-size:12px">Keyword: {row['target_keyword']}</span><br>
                        <span style="color:#888;font-size:11px">Score: {row['opportunity_score']:.0f} | Vol: {row['estimated_searches']:,} | Effort: {row['effort']}</span>
                    </div>
                    """, unsafe_allow_html=True)

        st.divider()

        # Actionable pipeline
        st.subheader("📝 Content Action Pipeline")
        pipeline = ideas_df.copy()
        pipeline["action"] = pipeline.apply(
            lambda r: "📝 Write content" if pd.isna(r["current_position"]) else "✅ Published & ranking",
            axis=1
        )
        pipeline["recommended_format"] = pipeline.apply(
            lambda r: "Blog post (length >1500 words)" if r["opportunity_score"] >= 8.0 else
                      ("How-to guide" if r["estimated_searches"] > 300 else "Short-form content (TikTok/Reels)"),
            axis=1
        )
        pipeline_display = pipeline[["title", "target_keyword", "opportunity_score", "estimated_searches",
                                      "effort", "current_position", "action", "recommended_format"]].head(10)
        pipeline_display = pipeline_display.rename(columns={
            "target_keyword": "Target KW", "opportunity_score": "Score",
            "estimated_searches": "Searches", "current_position": "Rank"
        })
        pipeline_display["Score"] = pipeline_display["Score"].round(1)
        st.dataframe(pipeline_display, use_container_width=True, hide_index=True)

        # Export
        csv_data = df_to_csv(ideas_df)
        st.download_button("📥 Download Content Ideas CSV", data=csv_data,
                           file_name="content_ideas.csv", mime="text/csv")
    else:
        st.info("No content ideas found.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 5: ✍️ CONTENT STUDIO (NEW v0.4 — Article Writing Pipeline)
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("✍️ Content Studio v0.4")
    st.caption("Write SEO articles from researched keywords, post drafts to Shopify, and track your publishing pipeline")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🚀 Article Pipeline Active:</strong><br>
    1. Pick a high-opportunity keyword from the research below<br>
    2. Write a full SEO-optimized article (with the help of AI)<br>
    3. Push to Shopify as a draft blog post<br>
    4. Review and publish from the Shopify admin<br>
    <em>First article already posted as a draft — check your Shopify Blog → Drafts!</em>
    </div>
    """, unsafe_allow_html=True)

    # ── Published Articles ────────────────────────────────────────────────
    st.subheader("📚 Published Articles")

    articles_df = query_db("""
        SELECT pa.id, pa.title, pa.market, pa.target_domain, pa.status,
               pa.target_keywords, pa.word_count, pa.shopify_article_id,
               pa.created_at, pa.published_at
        FROM published_articles pa
        ORDER BY pa.created_at DESC
    """)

    if not articles_df.empty:
        for _, row in articles_df.iterrows():
            status_color = "#ffcc00" if row["status"] == "draft" else "#00d4aa" if row["status"] == "published" else "#ff4444"
            status_icon = "📄" if row["status"] == "draft" else "✅" if row["status"] == "published" else "❌"
            admin_url = f"https://admin.shopify.com/store/giant-bubbles-by-tinka/admin/articles/{int(row['shopify_article_id'])}" if pd.notna(row["shopify_article_id"]) else None

            st.markdown(f"""
            <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:14px; margin:8px 0;">
                <div style="display:flex;justify-content:space-between;align-items:start;">
                    <div>
                        <strong style="color:{status_color}">{status_icon} {row['title']}</strong>
                        <span style="font-size:11px;color:#888;margin-left:10px;">🇳🇿 {row['market']}</span>
                    </div>
                    <span style="font-size:11px;background:{status_color};color:#000;padding:2px 8px;border-radius:4px;font-weight:600;">
                        {row['status'].upper()}
                    </span>
                </div>
                <div style="font-size:12px;color:#888;margin-top:6px;">
                    {int(row['word_count'])} words | Keywords: {row['target_keywords'] or 'N/A'} | Created: {str(row['created_at'])[:19]}
                </div>
                <div style="margin-top:6px;">
                    <a href="{admin_url}" target="_blank" style="color:#58a6ff;font-size:12px;">🔗 Open in Shopify Admin →</a>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No articles published yet. Use the pipeline below to write your first one!")

    st.divider()

    # ── Content Ideas Ready for Writing ───────────────────────────────────
    st.subheader("🎯 Ready to Write — Unpublished Content Ideas")
    st.caption("These high-opportunity content ideas don't have articles yet. Pick one to author.")

    ready_to_write = query_db("""
        SELECT ci.id, ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
               ci.opportunity_score, ci.effort, ci.outline
        FROM content_ideas ci
        LEFT JOIN published_articles pa ON ci.id = pa.content_idea_id
        WHERE pa.id IS NULL AND ci.status != 'published'
        ORDER BY ci.opportunity_score DESC, ci.estimated_searches DESC
    """)

    if not ready_to_write.empty:
        st.markdown(f"**{len(ready_to_write)} content ideas ready** — sorted by opportunity score (highest first)")

        for _, row in ready_to_write.head(12).iterrows():
            target_kw = row["target_keyword"] or "N/A"
            vol = int(row["estimated_searches"]) if pd.notna(row["estimated_searches"]) else 0
            score = row["opportunity_score"] if pd.notna(row["opportunity_score"]) else 0
            effort = row["effort"] or "medium"

            st.markdown(f"""
            <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:12px; margin:6px 0;">
                <div style="display:flex;justify-content:space-between;align-items:start;">
                    <div>
                        <strong style="color:#00d4aa;">{row['title'][:60]}</strong><br>
                        <span style="color:#888;font-size:12px;">
                            🎯 {target_kw} | 📈 {vol:,}/mo | ⭐ {score:.0f} opp | 💪 {effort}
                        </span>
                    </div>
                    <span style="font-size:11px;background:#002b1a;color:#00d4aa;padding:2px 8px;border-radius:4px;">
                        {row['category'] or 'general'}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.info("""
        **💡 To write a new article:**
        ```
        # 1. Pick an idea from above, create the HTML article file in articles/
        # 2. Run the article writer:
        python scripts/article_writer.py --idea <ID> --body articles/your-article.html --market NZ
        # 3. Check your Shopify admin → Blog Posts → Drafts to review & publish
        ```
        """)

        # Show the pipeline command
        st.divider()
        st.subheader("⚡ Quick Launch — Write Next Article")
        idea_ids = ready_to_write["id"].tolist()
        idea_labels = [
            f"[#{r['id']}] {r['title'][:50]} (⭐{r['opportunity_score']:.0f})"
            for _, r in ready_to_write.iterrows()
        ]
        selected_idx = 0
        if idea_labels:
            selected_label = st.selectbox("Select a content idea to write", idea_labels, key="cs_idea")
            selected_idx = idea_labels.index(selected_label)
            selected_row = ready_to_write.iloc[selected_idx]

            col_cmd1, col_cmd2 = st.columns([1, 1])
            with col_cmd1:
                market = st.radio("Target Market", ["NZ", "AU"], index=0, key="cs_market")
            with col_cmd2:
                st.markdown("**Article template hint:**")
                if selected_row.get("outline") and pd.notna(selected_row["outline"]):
                    st.caption(f"Outline available in DB: {str(selected_row['outline'])[:200]}...")
                else:
                    st.caption("See blog_post_topics_from_new_keywords_v2.md for full outlines")

            st.code(
                f"# To write this article:\n"
                f"# 1. Create articles/{selected_row['id']}_{selected_row['target_keyword'] or 'article'}.html\n"
                f"# 2. Run:\n"
                f"python scripts/article_writer.py --idea {int(selected_row['id'])} \\\n"
                f"  --body articles/{selected_row['target_keyword'] or 'article'}.html \\\n"
                f"  --market {market}\n"
                f"# 3. Verify at: https://admin.shopify.com/store/giant-bubbles-by-tinka/admin/articles",
                language="bash"
            )

    else:
        st.success("🎉 All content ideas have been published or are being written!")

    st.divider()

    # ── Pipeline Status ───────────────────────────────────────────────────
    st.subheader("📊 Pipeline Overview")

    total_ideas = query_db("SELECT COUNT(*) as c FROM content_ideas")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM content_ideas").empty else 0
    published_count = query_db("SELECT COUNT(*) as c FROM published_articles")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM published_articles").empty else 0
    draft_count = query_db("SELECT COUNT(*) as c FROM published_articles WHERE status='draft'")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM published_articles WHERE status='draft'").empty else 0

    col_ps1, col_ps2, col_ps3, col_ps4 = st.columns(4)
    with col_ps1:
        st.markdown(f'<div class="metric-card"><h3>{total_ideas}</h3><p>Total Content Ideas</p></div>', unsafe_allow_html=True)
    with col_ps2:
        st.markdown(f'<div class="metric-card"><h3>{published_count}</h3><p>Articles Written</p></div>', unsafe_allow_html=True)
    with col_ps3:
        st.markdown(f'<div class="metric-card"><h3>{total_ideas - published_count}</h3><p>Still to Write</p></div>', unsafe_allow_html=True)
    with col_ps4:
        pct = (published_count / total_ideas * 100) if total_ideas > 0 else 0
        st.markdown(f'<div class="metric-card"><h3>{pct:.0f}%</h3><p>Pipeline Progress</p></div>', unsafe_allow_html=True)

    st.caption(f"Articles on Shopify: {published_count} ({draft_count} as draft) | Dashboard: {PROJECT_DIR}")

    # Quick link to Shopify admin
    st.divider()
    st.subheader("🔗 Quick Links")
    st.markdown("""
    [![Shopify Admin](https://img.shields.io/badge/Shopify-Admin-green)](https://admin.shopify.com/store/giant-bubbles-by-tinka/admin/articles)
    [![GitHub Repo](https://img.shields.io/badge/GitHub-Repo-blue)](https://github.com/Shahn23/tinka-seo-dashboard)
    """)

    st.markdown("""
    **Need a new article written?** Ask me (the AI agent) to:
    - Pick the highest-opportunity keyword from the Content tab
    - Write a comprehensive SEO-optimized article
    - Record it in the dashboard
    """)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 6: 🔍 DEEP SITE AUDIT (NEW v0.5 — RustySEO Inspired)
# ═════════════════════════════════════════════════════════════════════════════
with tab6:
    st.header("🔍 Deep Site Audit")
    st.caption("Live page analysis — inspired by RustySEO's free website crawling toolkit. Checks meta tags, schema, page speed, images, and more.")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🦀 RustySEO Integration:</strong> RustySEO is a free, open-source SEO/GEO desktop toolkit
    (GUI app, <a href="https://github.com/mascanho/RustySEO" target="_blank" style="color:#58a6ff;">github.com/mascanho/RustySEO</a>)
    for deep website crawling, log file analysis, AI-powered audits, and multi-format reporting.
    <br><br>
    <strong>💡 To get RustySEO:</strong> Download the installer from <strong>rustyseo.com</strong> (Windows/Mac/Linux).
    It runs as a native desktop app — no crawl limits, no API costs. Configure GSC + PageSpeed + Gemini API keys for the full feature set.
    <br><br>
    <em>This tab provides a lightweight in-dashboard audit for quick checks. For hundreds of pages and log analysis, use the RustySEO desktop app.</em>
    </div>
    """, unsafe_allow_html=True)

    col_url, col_btn = st.columns([3, 1])
    with col_url:
        audit_url = st.text_input("Enter a URL to audit",
                                   placeholder="https://www.giantbubbles.co.nz/",
                                   value="https://www.giantbubbles.co.nz/")
    with col_btn:
        run_audit = st.button("🔍 Run Deep Audit", type="primary", use_container_width=True)

    if run_audit and audit_url:
        with st.spinner(f"Auditing {audit_url}..."):
            try:
                # Normalize URL
                url = audit_url.strip()
                if not url.startswith("http"):
                    url = "https://" + url

                # HTTP request
                resp = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                html = resp.text
                status_code = resp.status_code
                content_type = resp.headers.get("Content-Type", "")
                content_len = len(html)

                import re

                # Title
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else ""
                title_len = len(title)
                title_ok = 30 <= title_len <= 60

                # Meta description
                meta_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
                meta_match2 = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']', html, re.IGNORECASE)
                meta_desc = meta_match.group(1).strip() if meta_match else (meta_match2.group(1).strip() if meta_match2 else "")
                meta_len = len(meta_desc)
                meta_ok = 120 <= meta_len <= 160

                # H1
                h1_match = re.findall(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
                h1_count = len(h1_match)
                h1_ok = h1_count == 1
                h1_text = h1_match[0].strip() if h1_match else ""

                # Viewport
                viewport_ok = bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.IGNORECASE))

                # Canonical
                canonical_match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
                canonical_ok = bool(canonical_match)
                canonical_url = canonical_match.group(1) if canonical_match else ""

                # Image alt tags
                img_tags = re.findall(r'<img[^>]+>', html, re.IGNORECASE)
                total_imgs = len(img_tags)
                imgs_with_alt = sum(1 for img in img_tags if re.search(r'alt=["\'][^"\']+["\']', img, re.IGNORECASE))
                alt_ok = imgs_with_alt / max(total_imgs, 1) > 0.8

                # Headings hierarchy
                all_h = {}
                for level in range(1, 7):
                    all_h[f"h{level}"] = len(re.findall(f'<h{level}[^>]*>', html, re.IGNORECASE))
                heading_ok = all_h["h1"] > 0 and all_h["h2"] > 0

                # Schema / JSON-LD
                schema_ok = bool(re.search(r'application/ld\+json', html, re.IGNORECASE) or
                                 re.search(r'itemscope|itemtype=["\']https?://schema\.org', html, re.IGNORECASE))

                # Open Graph
                og_title = bool(re.search(r'<meta[^>]+property=["\']og:title["\']', html, re.IGNORECASE))
                og_desc = bool(re.search(r'<meta[^>]+property=["\']og:description["\']', html, re.IGNORECASE))
                og_image = bool(re.search(r'<meta[^>]+property=["\']og:image["\']', html, re.IGNORECASE))
                og_ok = og_title and og_desc and og_image

                # Compute score
                checks = {
                    "Title Tag (30-60 chars)": title_ok,
                    "Meta Description (120-160 chars)": meta_ok,
                    "Single H1 Tag": h1_ok,
                    "Viewport Meta Tag": viewport_ok,
                    "Canonical URL": canonical_ok,
                    "Image Alt Text (80%+)": alt_ok,
                    "Heading Hierarchy": heading_ok,
                    "Structured Data (JSON-LD)": schema_ok,
                    "Open Graph Tags": og_ok,
                }
                passed = sum(1 for v in checks.values() if v)
                total = len(checks)
                score = round((passed / total) * 100)

                score_color = "#00d4aa" if score >= 80 else "#ff8800" if score >= 50 else "#ff4444"
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#0d1117,#161b22);border:1px solid #30363d;border-radius:16px;padding:20px;margin-bottom:20px;">
                    <div style="display:flex;align-items:center;gap:30px;flex-wrap:wrap;">
                        <div style="text-align:center;">
                            <div class="score-circle" style="background:conic-gradient({score_color} 0% {score}%, #1a1c2e {score}% 100%);color:{score_color};border:3px solid {score_color};">{score}</div>
                            <div style="font-size:12px;color:#888;margin-top:6px;">On-Page Score</div>
                        </div>
                        <div style="flex:1;">
                            <strong style="font-size:16px;color:#fff;">{url}</strong><br>
                            <span style="color:#888;font-size:13px;">HTTP {status_code} · {content_type.split(';')[0]} · {content_len:,} bytes</span><br>
                            <span style="color:#888;font-size:12px;">{passed}/{total} checks passed</span>
                        </div>
                        <div style="text-align:center;min-width:120px;">
                            <span style="font-size:24px;font-weight:700;color:{score_color};">{'GREAT' if score >= 80 else 'NEEDS WORK' if score >= 50 else 'POOR'}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.subheader("📋 Audit Checks")
                for check_name, result in checks.items():
                    badge = '<span class="pass-badge">PASS</span>' if result else '<span class="fail-badge">FAIL</span>'
                    st.markdown(f"<div style='padding:4px 0;'>{badge} <strong>{check_name}</strong></div>", unsafe_allow_html=True)

                st.divider()

                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.subheader("📄 Page Elements")
                    st.markdown(f"""
                    - **Title:** `{title[:80]}{'...' if len(title) > 80 else ''}` ({title_len} chars)
                    - **Meta Description:** `{meta_desc[:100]}{'...' if len(meta_desc) > 100 else ''}` ({meta_len} chars)
                    - **H1:** `{h1_text[:80]}{'...' if len(h1_text) > 80 else ''}` ({h1_count} H1)
                    - **Canonical URL:** `{canonical_url}` ({'✅' if canonical_ok else '❌ missing'})
                    - **Schema/JSON-LD:** {'✅ Found' if schema_ok else '❌ Not found'}
                    """)

                with col_d2:
                    st.subheader("🏷️ Meta & Social")
                    st.markdown(f"""
                    - **Viewport Tag:** {'✅ Set' if viewport_ok else '❌ Missing'}
                    - **Open Graph:** {'✅ Complete (title + desc + image)' if og_ok else '⚠️ Incomplete'}
                    - **Heading Structure:** H1:{all_h['h1']} H2:{all_h['h2']} H3:{all_h['h3']} ...
                    - **Images:** {imgs_with_alt}/{total_imgs} with alt text
                    - **HTTP Status:** {status_code}
                    """)

            except requests.exceptions.RequestException as e:
                st.error(f"Could not reach {url}: {e}")
            except Exception as e:
                st.error(f"Audit error: {e}")

    elif not run_audit:
        st.info("Enter a URL above and click **Run Deep Audit** to check on-page SEO elements.")

    st.divider()

    # RustySEO download card
    st.subheader("🦀 Get RustySEO Desktop App")
    st.markdown("""
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:250px;background:#1a1c2e;border:1px solid #2a2d4a;border-radius:12px;padding:16px;">
        <strong>RustySEO Features (Free, Open Source)</strong>
        <ul style="color:#aaa;font-size:13px;margin-top:8px;padding-left:20px;">
            <li>Deep website crawling (no limits)</li>
            <li>Technical SEO audits & diagnostics</li>
            <li>Nginx & Apache log file analysis</li>
            <li>GSC + PageSpeed API integration</li>
            <li>AI-powered analysis (Gemini/Ollama)</li>
            <li>Multi-format reporting (CSV/Excel/PDF)</li>
            <li>Built with Rust — blazing fast</li>
        </ul>
        <a href="https://github.com/mascanho/RustySEO/releases" target="_blank">Download RustySEO</a>
    </div>
    <div style="flex:1;min-width:250px;background:#1a1c2e;border:1px solid #2a2d4a;border-radius:12px;padding:16px;">
        <strong>⚠️ Known Issues from Recent Audits</strong>
        <ul style="color:#ff6b6b;font-size:13px;margin-top:8px;padding-left:20px;">
            <li>About Us / Blog pages return 404 on both sites</li>
            <li>Near-identical content across .co.nz and .com.au</li>
            <li>Best Sellers page has Shopify placeholder content</li>
            <li>AU contact page lists NZ phone number</li>
            <li>Meta descriptions too long (294-320 chars vs ideal 120-160)</li>
        </ul>
    </div>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 7: 🌐 AI & GEO VISIBILITY (NEW v0.5 — BabyLoveGrowth Inspired)
# ═════════════════════════════════════════════════════════════════════════════
with tab7:
    st.header("🌐 AI & GEO Visibility")
    st.caption("Generative Engine Optimization (GEO) — inspired by BabyLoveGrowth.ai's AI search visibility tracking")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🌱 About BabyLoveGrowth.ai:</strong> AI-powered SEO/GEO platform that automates content creation,
    builds backlinks through a 4,000+ site network, tracks AI visibility (Google + ChatGPT/Perplexity),
    performs technical audits, and manages Reddit visibility workflows.
    <br><br>
    <strong>💡 Four-Pillar GEO Strategy:</strong><br>
    1. <strong>Content Plan</strong> — Create articles for target audiences (→ Content Studio tab)<br>
    2. <strong>Backlinks</strong> — Build authority through niche backlinks (→ Settings for Ahrefs/Moz API)<br>
    3. <strong>Technical Audit</strong> — Fix issues blocking Google & AI search engines (→ SEO Issues tab)<br>
    4. <strong>AI & Social Visibility</strong> — Track AI search presence & Reddit conversations (→ this tab)
    </div>
    """, unsafe_allow_html=True)

    geo_subtabs = st.tabs(["🤖 AI Visibility Check", "🔍 Content Gap Analysis", "💬 Reddit & Social", "📈 Competition Radar"])

    with geo_subtabs[0]:
        st.subheader("🤖 AI Search Visibility Check")
        st.caption("Check if your content appears in AI search engines. Enter a query to see related keyword GEO readiness.")

        col_q, col_btn2 = st.columns([3, 1])
        with col_q:
            ai_query = st.text_input("Search query to test AI visibility",
                                      placeholder="e.g. giant bubble kit nz", value="giant bubbles nz")
        with col_btn2:
            check_ai = st.button("🧠 Check AI Visibility", type="primary", use_container_width=True)

        if check_ai and ai_query:
            kw_ai_search = query_db("""
                SELECT k.keyword, k.volume, k.opportunity_score, k.difficulty,
                       rh.position, rh.clicks, rh.impressions
                FROM keywords k
                LEFT JOIN rank_history rh ON k.id = rh.keyword_id
                    AND (rh.keyword_id, rh.date) IN (
                        SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
                    )
                WHERE k.keyword LIKE ? OR k.keyword LIKE ?
                ORDER BY k.volume DESC LIMIT 10
            """, [f"%{ai_query}%", f"%{ai_query.replace(' ', '%')}%"])

            if not kw_ai_search.empty:
                st.info(f"Found {len(kw_ai_search)} related keywords in your tracking database.")
                for _, row in kw_ai_search.iterrows():
                    pos = row["position"] if pd.notna(row["position"]) else None
                    geo_readiness = "High" if pos and pos <= 10 else "Medium" if pos else "Low"
                    geo_color = {"High": "#00d4aa", "Medium": "#ff8800", "Low": "#ff4444"}[geo_readiness]
                    pos_display = f"#{pos:.0f}" if pos else "Not ranked"
                    st.markdown(f"""
                    <div style="background:#1a1c2e;border:1px solid #30363d;border-radius:8px;padding:10px;margin:6px 0;">
                        <div style="display:flex;justify-content:space-between;">
                            <strong style="color:#fff;">{row['keyword']}</strong>
                            <span style="font-size:11px;background:{geo_color};color:#000;padding:2px 8px;border-radius:4px;font-weight:600;">GEO: {geo_readiness}</span>
                        </div>
                        <span style="color:#888;font-size:12px;">Vol: {int(row['volume']) if pd.notna(row['volume']) else 'N/A'} | Google: {pos_display} | Opp: {row['opportunity_score']:.0f}</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.divider()
                st.subheader("📋 GEO Readiness Checklist")
                for item, status, tip in [
                    ("FAQ Schema", "✅ Present", "Add FAQPage structured data to FAQ sections"),
                    ("Article Schema", "ℹ️ 1 article published", "Add Article schema to all blog posts"),
                    ("Direct Answers", "⚠️ Improve", "Write direct answers to questions in first 100 words"),
                    ("Authority Signals", "⏳ Needed", "Build niche-relevant backlinks"),
                    ("Structured Lists", "⚠️ Add more", "Use lists/tables to make content AI-friendly"),
                ]:
                    st.markdown(f"**{item}** — {status}  \n💡 {tip}")
            else:
                st.info(f"No keyword data found for '{ai_query}'.")
        elif not check_ai:
            st.info("Enter a query and click **Check AI Visibility**.")

    with geo_subtabs[1]:
        st.subheader("🔍 Content Gap Analysis")
        st.caption("High-demand topics not yet ranking — your best targets for new content")

        gap_content = query_db("""
            SELECT ci.id, ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
                   ci.opportunity_score, ci.effort
            FROM content_ideas ci
            LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
            WHERE (vw.current_position IS NULL OR vw.current_position > 20) AND ci.status != 'published'
            ORDER BY ci.opportunity_score DESC LIMIT 20
        """)
        gap_keywords = query_db("""
            SELECT k.keyword, k.category, k.volume, k.opportunity_score, k.difficulty, d.name AS domain
            FROM keywords k JOIN domains d ON k.domain_id = d.id
            LEFT JOIN rank_history rh ON k.id = rh.keyword_id
            WHERE rh.id IS NULL AND k.opportunity_score >= 6.0
            ORDER BY k.volume DESC LIMIT 20
        """)

        col_gap1, col_gap2 = st.columns(2)
        with col_gap1:
            st.subheader("📝 Untapped Content Ideas")
            if not gap_content.empty:
                for _, row in gap_content.head(8).iterrows():
                    st.markdown(f"**{row['title'][:55]}**  \n🎯 {row['target_keyword']} · 📈 {int(row['estimated_searches']) if pd.notna(row['estimated_searches']) else 0}/mo · ⭐ {row['opportunity_score']:.0f}")
            else:
                st.info("No content gaps found.")
        with col_gap2:
            st.subheader("🆕 Unranked High-Opportunity Keywords")
            if not gap_keywords.empty:
                for _, row in gap_keywords.head(8).iterrows():
                    st.markdown(f"**{row['keyword']}**  \n{row['domain']} · Vol: {int(row['volume']) if pd.notna(row['volume']) else 0}/mo · Opp: {row['opportunity_score']:.0f}")
            else:
                st.info("All high-opportunity keywords have rank data.")

        col_gap_m1, col_gap_m2, col_gap_m3, col_gap_m4 = st.columns(4)
        with col_gap_m1:
            st.metric("Content Gaps", len(gap_content) if not gap_content.empty else 0)
        with col_gap_m2:
            total_gap_vol = int(gap_content["estimated_searches"].sum()) if not gap_content.empty else 0
            st.metric("Gap Volume/mo", f"{total_gap_vol:,}")
        with col_gap_m3:
            st.metric("Unranked KWs", len(gap_keywords) if not gap_keywords.empty else 0)
        with col_gap_m4:
            total_kw_vol = int(gap_keywords["volume"].sum()) if not gap_keywords.empty else 0
            st.metric("Untapped Volume", f"{total_kw_vol:,}")

    with geo_subtabs[2]:
        st.subheader("💬 Reddit & Social Visibility")
        st.caption("Track brand mentions and conversation opportunities — inspired by BabyLoveGrowth's Reddit AI agent")

        st.info("Reddit posts now rank in Google's top 10 for many queries. Being visible in relevant threads builds brand awareness and signals authority to AI search engines.")

        col_rd, col_rb = st.columns([3, 1])
        with col_rd:
            reddit_query = st.text_input("Search Reddit for brand opportunities",
                                          placeholder="e.g. giant bubbles kids party auckland",
                                          value="giant bubbles nz")
        with col_rb:
            search_reddit = st.button("🔍 Search Reddit", type="primary", use_container_width=True)

        if search_reddit and reddit_query:
            with st.spinner(f"Searching Reddit for '{reddit_query}'..."):
                try:
                    search_url = f"https://www.google.com/search?q=site:reddit.com+{urllib.parse.quote(reddit_query)}+nz&num=10"
                    r = requests.get(search_url, timeout=10,
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    if r.status_code == 200:
                        urls_found = list(set(re.findall(r'https?://(?:www\.)?reddit\.com/r/[^"&\s<>]+', r.text)))[:8]
                        if urls_found:
                            st.success(f"Found {len(urls_found)} relevant Reddit threads!")
                            for reddit_url in urls_found:
                                sub = re.search(r'/r/([^/]+)', reddit_url)
                                sub_name = sub.group(1) if sub else "unknown"
                                st.markdown(f"[r/{sub_name} — Opportunity]({reddit_url})")
                        else:
                            st.info("No Reddit results found.")
                    else:
                        st.warning(f"Search returned status {r.status_code}. Try again later.")
                except Exception as e:
                    st.warning(f"Search error: {e}")

    with geo_subtabs[3]:
        st.subheader("📈 Competition Radar")
        st.caption("Track competitive landscape — which keywords you dominate and where competitors are winning")

        col_cr1, col_cr2 = st.columns(2)
        with col_cr1:
            st.subheader("🏆 Top Performing Keywords (Top 5)")
            top_perf = query_db("""
                SELECT k.keyword, d.name AS domain, rh.position, rh.clicks
                FROM rank_history rh JOIN keywords k ON rh.keyword_id = k.id
                JOIN domains d ON k.domain_id = d.id
                WHERE (rh.keyword_id, rh.date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)
                AND rh.position <= 5 ORDER BY rh.position ASC LIMIT 8
            """)
            if not top_perf.empty:
                for _, row in top_perf.iterrows():
                    st.markdown(f"**#{row['position']:.0f}** {row['keyword']} · {row['domain']} · {int(row['clicks']) if pd.notna(row['clicks']) else 0} clicks")
            else:
                st.caption("No data available.")

        with col_cr2:
            st.subheader("💪 Strengthening Positions (30d)")
            risers = query_db("""
                SELECT k.keyword, d.name AS domain, latest.position AS current_pos,
                       prev.position AS prev_pos, (prev.position - latest.position) AS improvement
                FROM keywords k JOIN domains d ON k.domain_id = d.id
                JOIN rank_history latest ON k.id = latest.keyword_id AND latest.date = (SELECT MAX(date) FROM rank_history WHERE keyword_id = k.id)
                JOIN rank_history prev ON k.id = prev.keyword_id AND prev.date = date('now', '-30 days')
                WHERE prev.position IS NOT NULL AND latest.position IS NOT NULL AND (prev.position - latest.position) > 1
                ORDER BY improvement DESC LIMIT 6
            """)
            if not risers.empty:
                for _, row in risers.iterrows():
                    st.markdown(f"↑ **{int(row['improvement'])} spots** {row['keyword']} · #{row['prev_pos']:.0f}→#{row['current_pos']:.0f}")
            else:
                st.caption("No gains detected.")

        st.divider()
        st.subheader("🎯 Identified Competitors")
        st.markdown("**Direct:** Felt.co.nz (Bubbleon) · SmartyPants/WOWmazing · Amazon AU · Kmart AU  \n"
                    "**Services:** Bubble Shows NZ · An Enchanted Party · Party Makers NZ · Kia Ora Party  \n"
                    "**Content:** Outdoor toy blogs · Party planning websites · NZ parenting blogs")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 8: ALERTS (Migrated to slot 8)
# ═════════════════════════════════════════════════════════════════════════════
with tab8:
    st.header("🔔 Alerts & Notifications")
    st.caption("Rank drop alerts, keyword opportunity alerts, and weekly digests — like MOZ Pro Alerts")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🔮 Coming with API integration:</strong> Email/Slack/webhook alerts are planned.
    Adding <strong>Google Ads API</strong> will enable real keyword volume alerts.
    Currently showing dashboard-native alerts from GSC data.
    </div>
    """, unsafe_allow_html=True)

    # ── Rank Drop Alerts ──────────────────────────────────────────────────
    st.subheader("🚨 Rank Drop Alerts (last 7 days)")

    drop_df = query_db(f"""
        SELECT k.keyword, d.name AS domain,
               latest.position AS current_pos,
               prev.position AS prev_pos,
               (prev.position - latest.position) AS drop_size
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        JOIN rank_history latest ON k.id = latest.keyword_id
            AND latest.date = (SELECT MAX(date) FROM rank_history WHERE keyword_id = k.id)
        JOIN rank_history prev ON k.id = prev.keyword_id
            AND prev.date = date('now', '-7 days')
        WHERE prev.position IS NOT NULL AND latest.position IS NOT NULL
        AND (prev.position - latest.position) < -3
        ORDER BY drop_size ASC
        LIMIT 15
    """)

    if not drop_df.empty:
        st.warning(f"**{len(drop_df)} keywords dropped more than 3 positions in the last 7 days**")
        for _, row in drop_df.iterrows():
            st.markdown(f"""
            <div class="alert-box">
                <strong style="color:#ff4444">↓ {int(abs(row['drop_size']))} spots</strong>
                <strong style="color:#fff"> {row['keyword']}</strong><br>
                <span style="color:#aaa;font-size:12px">{row['domain']} | #{row['prev_pos']:.0f} → #{row['current_pos']:.0f}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ No significant rank drops in the last 7 days!")

    st.divider()

    # ── New Opportunities Alert ──────────────────────────────────────────
    st.subheader("💡 New Opportunity Alerts")

    opp_alerts = query_db(f"""
        SELECT k.keyword, d.name AS domain, k.opportunity_score, k.volume, k.difficulty
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN rank_history rh ON k.id = rh.keyword_id
        WHERE rh.id IS NULL AND k.opportunity_score >= 8.0
        ORDER BY k.opportunity_score DESC, k.volume DESC
    """)

    if not opp_alerts.empty:
        st.info(f"**{len(opp_alerts)} high-opportunity keywords** are not yet ranked — create content to target them!")
        for _, row in opp_alerts.head(5).iterrows():
            st.markdown(f"""
            <div class="alert-good">
                <strong style="color:#00d4aa">{row['keyword']}</strong><br>
                <span style="color:#aaa;font-size:12px">{row['domain']}</span><br>
                <span style="color:#888;font-size:11px">
                    Score: {row['opportunity_score']:.0f} | Vol: {row['volume']:,} | Diff: {row['difficulty']}
                </span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("No new opportunity alerts right now.")

    st.divider()

    # ── Content Ideas Needing Action ─────────────────────────────────────
    st.subheader("📝 Content Ideas Ready to Publish")

    ready_content = query_db("""
        SELECT ci.title, ci.target_keyword, ci.opportunity_score, ci.estimated_searches, ci.effort
        FROM content_ideas ci
        LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
        WHERE vw.current_position IS NULL AND ci.opportunity_score >= 7.0
        ORDER BY ci.opportunity_score DESC
        LIMIT 8
    """)

    if not ready_content.empty:
        for _, row in ready_content.iterrows():
            st.markdown(f"""
            <div style="background:#1a2a1a; border-left:4px solid #4ecdc4; padding:10px 15px; border-radius:6px; margin:8px 0;">
                <strong>{row['title'][:60]}</strong><br>
                <span style="color:#aaa;font-size:12px">
                    Target: {row['target_keyword']} | Score: {row['opportunity_score']:.0f} | Vol: {row['estimated_searches']:,} | Effort: {row['effort']}
                </span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("No content ideas waiting for action.")

    st.divider()

    # ── Weekly Summary ────────────────────────────────────────────────────
    st.subheader("📊 Weekly Summary Stats")
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)

    with col_s1:
        total_kw = query_db("SELECT COUNT(*) as c FROM keywords")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM keywords").empty else 0
        st.markdown(f'<div class="metric-card"><h3>{total_kw}</h3><p>Total Keywords</p></div>', unsafe_allow_html=True)
    with col_s2:
        tracked = query_db("SELECT COUNT(DISTINCT keyword_id) as c FROM rank_history")["c"].iloc[0] if not query_db("SELECT COUNT(DISTINCT keyword_id) as c FROM rank_history").empty else 0
        st.markdown(f'<div class="metric-card"><h3>{tracked}</h3><p>Ranked Keywords</p></div>', unsafe_allow_html=True)
    with col_s3:
        open_errs = query_db("SELECT COUNT(*) as c FROM onpage_errors WHERE status='open'")["c"].iloc[0] if not query_db("SELECT COUNT(*) as c FROM onpage_errors WHERE status='open'").empty else 0
        st.markdown(f'<div class="metric-card"><h3>{open_errs}</h3><p>Open Issues</p></div>', unsafe_allow_html=True)
    with col_s4:
        avg_ctr = query_db("SELECT AVG(ctr) as c FROM rank_history WHERE date = (SELECT MAX(date) FROM rank_history)")["c"].iloc[0] if not query_db("SELECT AVG(ctr) as c FROM rank_history WHERE date = (SELECT MAX(date) FROM rank_history)").empty else 0
        if pd.notna(avg_ctr):
            st.markdown(f'<div class="metric-card"><h3>{avg_ctr*100:.1f}%</h3><p>Avg CTR</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="metric-card"><h3>N/A</h3><p>Avg CTR</p></div>', unsafe_allow_html=True)

    st.divider()

    # ── Export & Report ──────────────────────────────────────────────────
    st.subheader("📄 Export Reports")
    col_r1, col_r2, col_r3 = st.columns(3)

    with col_r1:
        # Export all keywords
        all_kw = query_db("""
            SELECT d.name AS domain, k.keyword, k.category, k.intent, k.volume,
                   k.opportunity_score, k.difficulty, rh.position, rh.clicks, rh.impressions, rh.ctr
            FROM keywords k
            JOIN domains d ON k.domain_id = d.id
            LEFT JOIN rank_history rh ON k.id = rh.keyword_id
                AND (rh.keyword_id, rh.date) IN (
                    SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
                )
        """)
        if not all_kw.empty:
            csv_data = df_to_csv(all_kw)
            st.download_button("📥 Full Keyword Report", data=csv_data,
                               file_name="full_keyword_report.csv", mime="text/csv")

    with col_r2:
        # Export all issues
        all_issues = query_db("""
            SELECT d.name AS domain, e.error_type, e.severity, e.page_url,
                   e.description, e.suggestion, e.status, e.created_at, e.fixed_at
            FROM onpage_errors e
            JOIN domains d ON e.domain_id = d.id
            ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END
        """)
        if not all_issues.empty:
            csv_data = df_to_csv(all_issues)
            st.download_button("📥 Full Issues Report", data=csv_data,
                               file_name="full_issues_report.csv", mime="text/csv")

    with col_r3:
        # Export content ideas
        all_content = query_db("""
            SELECT ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
                   ci.opportunity_score, ci.effort, ci.content_type, ci.status, ci.source,
                   vw.current_position, vw.domain
            FROM content_ideas ci
            LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
        """)
        if not all_content.empty:
            csv_data = df_to_csv(all_content)
            st.download_button("📥 Full Content Report", data=csv_data,
                               file_name="full_content_report.csv", mime="text/csv")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 9: SYNC & SETTINGS (Migrated to slot 9)
# ═════════════════════════════════════════════════════════════════════════════
with tab9:
    st.header("Sync, Settings & Integrations")
    st.caption("Data sync controls, API integration setup, and tool recommendations — like MOZ Pro Campaign Settings")

    st.markdown("""
    <div style="background:#1a1c2e; border:1px solid #2a2d4a; border-radius:10px; padding:15px; margin-bottom:20px;">
    <strong>🌐 Recommended Tool Stack for Full SemRush/MOZ-Level Coverage:</strong><br><br>
    1. <strong>Google Search Console</strong> ✅ (connected) — Ranking, clicks, impressions<br>
    2. <strong>Google Ads API</strong> 🔲 (needs credentials) — Real search volume, competition data<br>
    3. <strong>Google Analytics 4</strong> 🔲 (needs credentials) — Traffic source correlation with rankings<br>
    4. <strong>Ahrefs API</strong> 🔲 (paid) — Backlink profiles, competitor domains, content gap<br>
    5. <strong>Moz API</strong> 🔲 (paid) — Domain Authority, Spam Score, Page Authority<br>
    </div>
    """, unsafe_allow_html=True)

    # ── Google Search Console Sync ────────────────────────────────────────
    col_sync1, col_sync2 = st.columns(2)

    with col_sync1:
        st.subheader("📡 Google Search Console Sync")

        last_sync = query_db("""
            SELECT source, status, rows_synced, started_at, completed_at, error
            FROM sync_log WHERE source = 'gsc'
            ORDER BY started_at DESC LIMIT 1
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
            st.info("No syncs yet. Click below to run the first sync.")

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
        sync_hist = query_db("SELECT source, status, rows_synced, started_at, completed_at FROM sync_log ORDER BY started_at DESC LIMIT 10")
        if not sync_hist.empty:
            with st.expander("Sync History", expanded=False):
                st.dataframe(sync_hist, use_container_width=True, hide_index=True)

    with col_sync2:
        st.subheader("📁 Data Source Status")
        files = {
            "tinka_keyword_research.csv": os.path.join(PROJECT_DIR, "data", "tinka_keyword_research.csv"),
            "tinka_blog_post_ideas.md": os.path.join(PROJECT_DIR, "data", "tinka_blog_post_ideas.md"),
            "errors_au.json": os.path.join(PROJECT_DIR, "data", "errors_au.json"),
            "errors_nz.json": os.path.join(PROJECT_DIR, "data", "errors_nz.json"),
            "Database (seo_dashboard.db)": os.path.join(PROJECT_DIR, "data", "seo_dashboard.db"),
        }
        for label, fpath in files.items():
            exists = os.path.exists(fpath)
            icon = "✅" if exists else "❌"
            size = os.path.getsize(fpath) if exists else 0
            st.markdown(f"{icon} **{label}** — {size:,} bytes" if exists else f"{icon} **{label}** — Not found")

    st.divider()

    # ── Google Ads API Integration Frame ──────────────────────────────────
    st.subheader("🎯 Google Ads API — Setup Guide")
    st.markdown("""
    To enable **real search volume data** and **keyword competition metrics**:

    ```
    1. Go to https://console.cloud.google.com/ → Enable 'Google Ads API'
    2. Create a service account → Download JSON key
    3. Link your Google Ads account:
       - In Google Ads: Tools → Setup → Access & Security
       - Add the service account email with 'Standard' access
    4. Save credentials to: config/google_ads_credentials.json
    5. Connect in the dashboard by entering your Google Ads (MCC) Customer ID below
    ```

    **Why this matters:** GSC only shows clicks + impressions (post-ranking).
    Google Ads Keyword Planner shows real search volumes, competition, and
    suggested bid data — the same data SemRush and MOZ use for keyword research.
    """)

    gads_customer_id = st.text_input("Google Ads Customer ID (optional)", placeholder="e.g. 123-456-7890",
                                      help="Your Google Ads/MCC customer ID. This enables keyword volume data.")

    if gads_customer_id:
        st.success(f"Google Ads Customer ID saved: {gads_customer_id}")
        st.info("**Next step:** Place `config/google_ads_credentials.json` with your service account key, "
                "then run `scripts/sync_gads.py` to pull search volume data.")
        # Save to a config file for future use
        config_dir = os.path.join(PROJECT_DIR, "config")
        os.makedirs(config_dir, exist_ok=True)
        ads_config = {"customer_id": gads_customer_id}
        config_path = os.path.join(config_dir, "google_ads_config.json")
        with open(config_path, "w") as f:
            json.dump(ads_config, f)
        st.caption(f"Saved to {config_path}")

    st.divider()

    # ── Google Analytics 4 Integration Frame ──────────────────────────────
    st.subheader("📊 Google Analytics 4 — Setup Guide")
    st.markdown("""
    To correlate **keyword rankings with traffic sources**:

    ```
    1. Go to https://console.cloud.google.com/ → Enable 'Google Analytics Data API'
    2. Create a service account → Download JSON key
    3. In GA4: Admin → Property Access Management → Add service account
    4. Save credentials to: config/ga4_credentials.json
    5. Enter your GA4 Property ID below
    ```

    **Why this matters:** Connect rank changes to traffic — did a keyword jump
    from #15 to #5 result in more organic traffic? Is the blog content driving
    the sessions you expected?
    """)

    ga4_property_id = st.text_input("GA4 Property ID (optional)", placeholder="e.g. 123456789",
                                     help="Your Google Analytics 4 property ID.")

    if ga4_property_id:
        st.success(f"GA4 Property ID saved: {ga4_property_id}")
        config_path = os.path.join(PROJECT_DIR, "config", "ga4_config.json")
        with open(config_path, "w") as f:
            json.dump({"property_id": ga4_property_id}, f)
        st.caption(f"Saved to {config_path}")

    st.divider()

    # ── Tool Recommendations ──────────────────────────────────────────────
    st.subheader("💡 Tool Recommendations (Next Level)")
    st.markdown("""
    | Tool | Cost | What It Adds | Priority |
    |------|------|-------------|----------|
    | **Google Ads API** | Free | Real search volume, competition, bid data | ⭐ P0 |
    | **Google Analytics 4** | Free | Traffic source correlation with rankings | ⭐ P0 |
    | **Ahrefs API** | $99/mo | Backlink profiles, content gap, competitor analysis | ⭐ P1 |
    | **RustySEO** | Free | Deep crawling, log analysis, AI audits — desktop app | ⭐ P1 |
    | **Moz API** | $49/mo | Domain Authority, Spam Score | P2 |
    | **DataForSEO API** | Pay/use | Live SERP data, rank tracking, backlinks | P2 |
    | **BabyLoveGrowth.ai** | Paid | Full GEO automation, AI visibility, Reddit agent | P2 |
    """)

    st.caption(f"Dashboard path: {PROJECT_DIR} | Database: {DB_PATH} | Rows: ~2,250 rank history")
