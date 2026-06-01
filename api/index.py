"""FastAPI SEO Dashboard — HTML-inlined, no Jinja2 template engine.

Pure sqlite3 + Python stdlib + Plotly HTML. Avoids Jinja2 caching issues
on newer versions. Works on Vercel's serverless runtime.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from xml.sax.saxutils import escape as html_escape

import plotly.graph_objects as go
import plotly.express as px
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

_THIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = _THIS_DIR.parent
_DB_SOURCE = _THIS_DIR / "seo_dashboard.db"
if not _DB_SOURCE.exists():
    _DB_SOURCE = PROJECT_DIR / "data" / "seo_dashboard.db"
DB_PATH = Path("/tmp") / "seo_dashboard.db"
if not DB_PATH.exists():
    import shutil
    shutil.copy2(str(_DB_SOURCE), str(DB_PATH))
    # Read-only modes to avoid journal problems on serverless
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.close()

app = FastAPI(title="Tinka SEO Dashboard")


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.row_factory = sqlite3.Row
    return conn


def fetch(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    except Exception as e:
        print(f"DB error: {e}")
        return []
    finally:
        conn.close()


def get_one(sql, params=()):
    rows = fetch(sql, params)
    return rows[0] if rows else None


def fig_to_html(fig, height=300):
    return fig.to_html(
        include_plotlyjs="cdn",
        full_html=False,
        default_height=height,
        config={"displayModeBar": False, "responsive": True},
    )


def sf(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def si(v, default=0):
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


def esc(s):
    """HTML-escape a string."""
    return html_escape(str(s)) if s is not None else ""


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE HTML (inlined — no Jinja2 dependency needed)
# ═══════════════════════════════════════════════════════════════════════════════
def render_page(**ctx):
    """Build the full HTML page with inline template variables."""
    now = ctx["now"]
    filters = ctx["filters"]
    sd = ctx["selected_domain"]
    sc = ctx["selected_category"]
    si_ = ctx["selected_intent"]
    sp = ctx.get("selected_keyword", "")
    sv_ = ctx.get("selected_sev", "All")
    se_ = ctx.get("selected_effort", "All")

    # Filter HTML helpers
    def option(val, selected, label=None):
        sel = ' selected' if val == selected else ''
        return f'<option value="{esc(val)}"{sel}>{esc(label or val)}</option>'

    domain_opts = "\n".join(option(d, sd) for d in filters["domains"])
    cat_opts = "\n".join(option(c, sc) for c in filters["categories"])
    intent_opts = "\n".join(option(i, si_) for i in filters["intents"])

    # ── Keyword Rankings section ──
    kw_sec = render_keywords(ctx)
    # ── Issues section ──
    issues_sec = render_issues(ctx)
    # ── Content section ──
    content_sec = render_content(ctx)
    # ── Settings section ──
    settings_sec = render_settings(ctx)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tinka SEO Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1117;color:#ccc;min-height:100vh}}
.app-header{{background:linear-gradient(135deg,#1a1c2e,#16182a);border-bottom:1px solid #2a2d4a;padding:16px 24px;display:flex;align-items:center;justify-content:space-between}}
.app-header h1{{font-size:20px;color:#00d4aa}}
.app-header .sub{{color:#666;font-size:12px}}
.app-layout{{display:flex;min-height:calc(100vh - 60px)}}
.sidebar{{width:240px;background:#12141e;border-right:1px solid #2a2d4a;padding:20px 16px;flex-shrink:0}}
.sidebar h2{{font-size:15px;color:#aaa;margin-bottom:16px}}
.sidebar .filter-group{{margin-bottom:16px}}
.sidebar .filter-group label{{display:block;font-size:12px;color:#888;margin-bottom:4px}}
.sidebar .filter-group select{{width:100%;padding:8px 10px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px}}
.sidebar .filter-group select:focus{{outline:none;border-color:#00d4aa}}
.sidebar .footer{{margin-top:20px;font-size:11px;color:#555}}
.btn-filter{{width:100%;padding:8px;background:#00d4aa;color:#000;border:none;border-radius:6px;font-weight:600;font-size:13px;cursor:pointer;margin-top:8px}}
.btn-filter:hover{{background:#00e6b5}}
.main-content{{flex:1;padding:24px;overflow-y:auto}}
.tabs{{display:flex;gap:2px;border-bottom:1px solid #2a2d4a;margin-bottom:24px}}
.tab-btn{{padding:10px 20px;background:transparent;border:none;color:#888;font-size:14px;cursor:pointer;border-bottom:2px solid transparent}}
.tab-btn:hover{{color:#ccc}}
.tab-btn.active{{color:#00d4aa;border-bottom-color:#00d4aa}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
.metric-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.metric-card{{background:#1a1c2e;border-radius:12px;padding:20px;text-align:center;border:1px solid #2a2d4a}}
.metric-card .value{{font-size:28px;font-weight:700;color:#00d4aa}}
.metric-card .label{{margin-top:4px;font-size:13px;color:#8888aa}}
.metric-card.warn .value{{color:#ff8800}}
.metric-card.danger .value{{color:#ff4444}}
.metric-card.ok .value{{color:#4ecdc4}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.chart-box{{background:#1a1c2e;border-radius:10px;padding:12px;border:1px solid #2a2d4a}}
.quick-wins-row{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:20px}}
.quick-win{{background:linear-gradient(135deg,#002b1a,#004d2e);border:1px solid #00d4aa;border-radius:10px;padding:12px}}
.quick-win .kw{{color:#00d4aa;font-weight:600;font-size:14px}}
.quick-win .meta{{color:#aaa;font-size:12px}}
.quick-win .detail{{color:#888;font-size:11px;margin-top:4px}}
h2{{font-size:18px;margin-bottom:16px}}
h3{{font-size:15px;margin-bottom:12px;color:#ddd}}
.data-table{{width:100%;border-collapse:collapse;font-size:13px;background:#1a1c2e;border-radius:8px;overflow:hidden}}
.data-table th{{background:#22243e;padding:8px 12px;text-align:left;color:#888;font-weight:600;font-size:11px;text-transform:uppercase}}
.data-table td{{padding:8px 12px;border-top:1px solid #2a2d4a}}
.data-table tr:hover td{{background:#1e2036}}
.sev-badge{{display:inline-block;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600}}
.sev-critical{{background:#ff4444;color:#fff}}
.sev-high{{background:#ff8800;color:#fff}}
.sev-moderate{{background:#ffcc00;color:#222}}
.issue-detail{{background:#16182a;padding:12px 16px;border-radius:8px;margin-bottom:8px;border-left:3px solid #444}}
.issue-detail.critical{{border-left-color:#ff4444}}
.issue-detail.high{{border-left-color:#ff8800}}
.issue-detail.moderate{{border-left-color:#ffcc00}}
.issue-detail .desc{{color:#aaa;font-size:13px;margin:4px 0}}
.issue-detail .suggestion{{color:#4ecdc4;font-size:12px}}
.issue-detail .meta{{color:#666;font-size:11px}}
.issue-detail.fixed{{opacity:0.6}}
.top-picks{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-bottom:20px}}
.top-pick{{background:#1a1c2e;border:1px solid #2a2d4a;border-radius:8px;padding:12px}}
.top-pick .title{{color:#00d4aa;font-weight:600}}
.top-pick .meta{{color:#888;font-size:12px}}
.status-box{{background:#1a1c2e;border:1px solid #2a2d4a;border-radius:10px;padding:16px;margin-bottom:16px}}
.trend-select{{margin-bottom:16px}}
.trend-select select{{padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px;min-width:300px}}
@media(max-width:768px){{.app-layout{{flex-direction:column}}.sidebar{{width:100%;border-right:none;border-bottom:1px solid #2a2d4a}}.grid-2{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="app-header">
<div><h1>🔍 SEO Dashboard</h1><div class="sub">Giant Bubbles by Tinka — {esc(now)}</div></div>
</div>
<div class="app-layout">
<form class="sidebar" method="GET" action="/">
<h2>Filters</h2>
<div class="filter-group"><label for="domain">Domain</label><select name="domain" id="domain">{domain_opts}</select></div>
<div class="filter-group"><label for="category">Category</label><select name="category" id="category">{cat_opts}</select></div>
<div class="filter-group"><label for="intent">Intent</label><select name="intent" id="intent">{intent_opts}</select></div>
<button type="submit" class="btn-filter">Apply Filters</button>
<div class="footer">Last updated: {esc(now)}</div>
</form>
<div class="main-content">
<div class="tabs">
<button class="tab-btn active" onclick="switchTab(event,'tab-kw')">🔑 Keyword Rankings</button>
<button class="tab-btn" onclick="switchTab(event,'tab-issues')">🛠️ SEO Issues</button>
<button class="tab-btn" onclick="switchTab(event,'tab-content')">📝 Content Backlog</button>
<button class="tab-btn" onclick="switchTab(event,'tab-settings')">🔄 Sync & Settings</button>
</div>
<div id="tab-kw" class="tab-content active">{kw_sec}</div>
<div id="tab-issues" class="tab-content">{issues_sec}</div>
<div id="tab-content" class="tab-content">{content_sec}</div>
<div id="tab-settings" class="tab-content">{settings_sec}</div>
</div></div>
<script>
function switchTab(e,i){{document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.getElementById(i).classList.add('active');e.currentTarget.classList.add('active');setTimeout(()=>{{document.getElementById(i).querySelectorAll('.js-plotly-plot').forEach(p=>Plotly.Plots.resize(p))}},100)}}
</script>
</body>
</html>"""


def render_keywords(ctx):
    rows = ctx.get("kw_rows", [])
    if not rows:
        return "<h2>Keyword Rankings</h2><p style='color:#888'>No keyword data found.</p>"

    metrics = ctx["kw_metrics"]
    charts = ctx["kw_charts"]
    wins = ctx["quick_wins"]
    kws = ctx["keyword_list"]
    sel_kw = ctx.get("selected_keyword", "")
    trend = ctx.get("trend_chart", "")

    parts = ['<h2>Keyword Rankings</h2>']
    parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value">{metrics["count"]}</div><div class="label">Keywords Tracked</div></div>
<div class="metric-card"><div class="value">{metrics["avg_pos"]}</div><div class="label">Avg Position</div></div>
<div class="metric-card warn"><div class="value">{metrics["total_clicks"]:,}</div><div class="label">Total Clicks (7d)</div></div>
<div class="metric-card ok"><div class="value">{metrics["total_impressions"]:,}</div><div class="label">Total Impressions (7d)</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("vol_by_cat","")}</div><div class="chart-box">{charts.get("opp_dist","")}</div></div>')

    if wins:
        parts.append('<h3>⚡ Quick Wins (High Opportunity, Low Difficulty)</h3><div class="quick-wins-row">')
        for r in wins:
            parts.append(f'<div class="quick-win"><div class="kw">{esc(r["keyword"])}</div><div class="meta">{esc(r["domain"])}</div><div class="detail">Score: {r["opportunity_score"]:.0f} | Vol: {r["volume"]:,} | Pos: {r["current_position"]:.0f}</div></div>')
        parts.append('</div>')

    parts.append('<h3>📈 Position Trend</h3><div class="trend-select"><form method="GET" action="/">')
    for k in ctx.get("qp_keep", []):
        parts.append(f'<input type="hidden" name="{esc(k)}" value="{esc(ctx["qp_vals"][k])}">')
    parts.append(f'<select name="keyword" onchange="this.form.submit()"><option value="">Select a keyword...</option>')
    for kw in kws:
        s = ' selected' if kw == sel_kw else ''
        parts.append(f'<option value="{esc(kw)}"{s}>{esc(kw)}</option>')
    parts.append('</select></form></div>')

    if trend:
        parts.append(trend)

    parts.append('<h3>📋 All Keywords</h3><div style="max-height:400px;overflow-y:auto"><table class="data-table"><thead><tr><th>Domain</th><th>Keyword</th><th>Category</th><th>Intent</th><th>Vol</th><th>Score</th><th>Diff</th><th>Pos</th><th>Clicks</th><th>Imp</th></tr></thead><tbody>')
    for r in ctx.get("kw_display", []):
        parts.append(
            f'<tr><td>{esc(r["Domain"])}</td><td style="font-weight:600">{esc(r["Keyword"])}</td>'
            f'<td>{esc(r["Category"])}</td><td>{esc(r.get("Intent",""))}</td>'
            f'<td>{r["Vol"]:,}</td><td>{r["Score"]}</td><td>{r["Diff"]}</td>'
            f'<td>{r["Pos"]}</td><td>{r["Clicks"]}</td><td>{r["Imp"]:,}</td></tr>'
        )
    parts.append('</tbody></table></div>')
    return "".join(parts)


def render_issues(ctx):
    rows = ctx.get("issue_rows", [])
    if not rows:
        return "<h2>Technical SEO Issues</h2><p style='color:#888'>No SEO issues found.</p>"

    m = ctx["issues_metrics"]
    charts = ctx["issues_charts"]
    parts = ['<h2>Technical SEO Issues</h2>']
    parts.append(f'''<div class="metric-row">
<div class="metric-card danger"><div class="value">{m["open"]}</div><div class="label">Open Issues</div></div>
<div class="metric-card danger"><div class="value">{m["critical"]}</div><div class="label">Critical</div></div>
<div class="metric-card warn"><div class="value">{m["high"]}</div><div class="label">High</div></div>
<div class="metric-card"><div class="value">{m["moderate"]}</div><div class="label">Moderate</div></div>
<div class="metric-card ok"><div class="value">{m["fixed"]}</div><div class="label">Fixed</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("sev_pie","")}</div><div class="chart-box">{charts.get("dom_bar","")}</div></div>')

    parts.append('<div style="margin-bottom:12px"><form method="GET" action="/" style="display:inline">')
    for k in ctx.get("qp_keep", []):
        parts.append(f'<input type="hidden" name="{esc(k)}" value="{esc(ctx["qp_vals"][k])}">')
    sv_ = ctx.get("selected_sev", "All")
    parts.append(f'''<select name="sev" onchange="this.form.submit()" style="padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
<option value="All"{" selected" if sv_=="All" else ""}>All Severities</option>
<option value="critical"{" selected" if sv_=="critical" else ""}>Critical</option>
<option value="high"{" selected" if sv_=="high" else ""}>High</option>
<option value="moderate"{" selected" if sv_=="moderate" else ""}>Moderate</option>
<option value="low"{" selected" if sv_=="low" else ""}>Low</option>
</select></form></div>''')

    for r in rows:
        sev = r["severity"]
        fixed = r["status"] == "fixed"
        parts.append(f'''<div class="issue-detail {sev}{" fixed" if fixed else ""}">
<div><span class="sev-badge sev-{sev}">{sev}</span><strong style="margin-left:8px">{esc(r["error_type"].replace("_"," ").title())}</strong>
<span style="float:right;color:#888;font-size:12px">{"✅ Fixed" if fixed else "🔴 Open"}</span></div>
<div class="meta">{esc(r["domain"])} | {esc(r["page_url"])}</div>
<div class="desc">{esc(r["description"])}</div>
<div class="suggestion">💡 {esc(r["suggestion"])}</div>
</div>''')

    return "".join(parts)


def render_content(ctx):
    rows = ctx.get("ideas_rows", [])
    if not rows:
        return "<h2>Content Idea Backlog</h2><p style='color:#888'>No content ideas found.</p>"

    m = ctx["ideas_metrics"]
    charts = ctx["ideas_charts"]
    picks = ctx.get("top_picks", [])
    display = ctx.get("ideas_display", [])
    parts = ['<h2>Content Idea Backlog</h2>']
    parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value">{m["count"]}</div><div class="label">Ideas</div></div>
<div class="metric-card"><div class="value">{m["avg_score"]}</div><div class="label">Avg Score</div></div>
<div class="metric-card ok"><div class="value">{m["total_searches"]:,}</div><div class="label">Total Monthly Searches</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("matrix","")}</div><div class="chart-box">{charts.get("vol_by_cat","")}</div></div>')

    se_ = ctx.get("selected_effort", "All")
    parts.append('<div style="margin-bottom:12px"><form method="GET" action="/" style="display:inline">')
    for k in ctx.get("qp_keep", []):
        parts.append(f'<input type="hidden" name="{esc(k)}" value="{esc(ctx["qp_vals"][k])}">')
    parts.append(f'''<select name="effort" onchange="this.form.submit()" style="padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
<option value="All"{" selected" if se_=="All" else ""}>All Effort Levels</option>
<option value="easy"{" selected" if se_=="easy" else ""}>Easy</option>
<option value="medium"{" selected" if se_=="medium" else ""}>Medium</option>
<option value="hard"{" selected" if se_=="hard" else ""}>Hard</option>
</select></form></div>''')

    if picks:
        parts.append('<h3>⭐ Top Picks (Score ≥ 8.0)</h3><div class="top-picks">')
        for r in picks:
            parts.append(f'''<div class="top-pick"><div class="title">{esc(r["title"])}</div>
<div class="meta">Score: {r["opportunity_score"]:.0f} | Searches: {r["estimated_searches"]:,}</div>
<div class="meta" style="margin-top:4px;color:#777">Keyword: {esc(r["target_keyword"])} | Effort: {esc(r["effort"])} | Type: {esc(r["content_type"])}</div></div>''')
        parts.append('</div>')

    parts.append('<h3>📋 All Ideas</h3><div style="max-height:400px;overflow-y:auto"><table class="data-table"><thead><tr><th>Title</th><th>Keyword</th><th>Category</th><th>Searches</th><th>Score</th><th>Effort</th><th>Type</th></tr></thead><tbody>')
    for r in display:
        parts.append(
            f'<tr><td style="font-weight:600">{esc(r["Title"])}</td><td>{esc(r["Keyword"])}</td>'
            f'<td>{esc(r["Category"])}</td><td>{r["Searches"]:,}</td>'
            f'<td>{r["Score"]}</td><td>{esc(r["Effort"])}</td><td>{esc(r["Type"])}</td></tr>'
        )
    parts.append('</tbody></table></div>')
    return "".join(parts)


def render_settings(ctx):
    last_sync = ctx.get("last_sync")
    sync_hist = ctx.get("sync_hist", [])
    parts = ["<h2>Sync & Settings</h2><div class='grid-2'><div><h3>📡 Google Search Console Sync</h3><div class='status-box'>"]
    if last_sync:
        icon = "✅" if last_sync.get("status") == "success" else "❌" if last_sync.get("status") == "failed" else "🔄"
        parts.append(f'<div style="font-size:24px">{icon}</div>')
        parts.append(f'<p><strong>Last Sync:</strong> {esc(last_sync.get("completed_at") or "In progress...")}</p>')
        parts.append(f'<p><strong>Status:</strong> {esc(last_sync.get("status",""))}</p>')
        parts.append(f'<p><strong>Rows:</strong> {last_sync.get("rows_synced") or "N/A"}</p>')
        if last_sync.get("error"):
            parts.append(f'<p style="color:#ff4444;margin-top:8px">{esc(last_sync["error"])}</p>')
    else:
        parts.append("<p>No syncs yet.</p>")
    parts.append('</div></div><div><h3>⏰ Daily Schedule</h3><div class="status-box">')
    parts.append('<p>🕐 <strong>6:00 AM daily</strong> — Hermes cron</p>')
    parts.append('<p style="color:#888;font-size:12px;margin-top:8px">Runs 3 modules: GSC rankings, on-page errors, content ideas</p>')
    parts.append('</div><h3>📁 Project Status</h3><div class="status-box">')
    parts.append('<p>📍 <strong>Location:</strong> ~/OneDrive/Desktop/tinka-seo-dashboard/</p>')
    parts.append('<p>🔗 <strong>Vercel:</strong> tinka-seo-dashboard.vercel.app</p>')
    parts.append('<p>🗄️ <strong>Database:</strong> SQLite (seo_dashboard.db)</p>')
    parts.append('</div></div></div>')

    if sync_hist:
        parts.append('<h3>Sync History</h3><table class="data-table"><thead><tr><th>Source</th><th>Status</th><th>Rows</th><th>Started</th><th>Completed</th></tr></thead><tbody>')
        for s in sync_hist:
            icon = "✅" if s.get("status") == "success" else "❌" if s.get("status") == "failed" else "🔄"
            parts.append(
                f'<tr><td>{esc(s.get("source",""))}</td><td>{icon} {esc(s.get("status",""))}</td>'
                f'<td>{s.get("rows_synced") or "-"}</td><td>{esc(s.get("started_at",""))}</td>'
                f'<td>{esc(s.get("completed_at") or "-")}</td></tr>'
            )
        parts.append('</tbody></table>')

    return "".join(parts)


# ── Route ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    domain: str = "All",
    category: str = "All",
    intent: str = "All",
    keyword: str = None,
    sev: str = "All",
    effort: str = "All",
):
    # Available filter options
    domains = fetch("SELECT name FROM domains WHERE is_active=1")
    cats = fetch("SELECT DISTINCT category FROM keywords ORDER BY category")
    filters = {
        "domains": ["All"] + [d["name"] for d in domains],
        "categories": ["All"] + [c["category"] for c in cats],
        "intents": ["All", "informational", "commercial", "transactional", "navigational"],
    }

    # Query params to pass through forms
    qp = dict(request.query_params)
    qp_keep = [k for k in ["domain", "category", "intent"] if k in qp]

    # Build WHERE clause
    w, p = [], []
    if domain != "All":
        w.append("d.name = ?"); p.append(domain)
    if category != "All":
        w.append("k.category = ?"); p.append(category)
    if intent != "All":
        w.append("k.intent = ?"); p.append(intent)
    where = f"WHERE {' AND '.join(w)}" if w else ""

    # ═══ KEYWORDS ════════════════════════════════════════════════════════
    kw_rows = fetch(
        f"""SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent, k.volume,
                   k.opportunity_score, k.difficulty, k.is_high_priority,
                   rh.position AS current_position, rh.clicks, rh.impressions
            FROM keywords k JOIN domains d ON k.domain_id = d.id
            LEFT JOIN (SELECT keyword_id, position, clicks, impressions, date
                       FROM rank_history WHERE (keyword_id, date) IN
                       (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)
                      ) rh ON k.id = rh.keyword_id
            {where} ORDER BY k.volume DESC""",
        p,
    )

    kw_metrics, kw_charts, quick_wins = {}, {}, []
    keyword_list, kw_display = [], []
    trend_chart = ""

    if kw_rows:
        poses = [sf(r["current_position"]) for r in kw_rows if r["current_position"]]
        avg_pos = round(sum(poses)/len(poses), 1) if poses else 0
        kw_metrics = {"count": len(kw_rows), "avg_pos": avg_pos,
                      "total_clicks": sum(si(r["clicks"]) for r in kw_rows),
                      "total_impressions": sum(si(r["impressions"]) for r in kw_rows)}

        # Volume by category
        vbc = defaultdict(float)
        for r in kw_rows:
            vbc[r["category"]] += sf(r["volume"])
        vi = sorted(vbc.items(), key=lambda x: x[1])
        if vi:
            fig = go.Figure(data=[go.Bar(x=[v for _, v in vi], y=[c for c, _ in vi], orientation="h",
                         marker_color="#00d4aa")])
            fig.update_layout(title="Search Volume by Category",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            kw_charts["vol_by_cat"] = fig_to_html(fig)

        scores = [sf(r["opportunity_score"]) for r in kw_rows]
        if scores:
            fig = go.Figure(data=[go.Histogram(x=scores, nbinsx=10, marker_color="#00d4aa")])
            fig.update_layout(title="Opportunity Score Distribution",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            kw_charts["opp_dist"] = fig_to_html(fig)

        qw = sorted([r for r in kw_rows if sf(r["opportunity_score"])>=7
                     and sf(r.get("difficulty",100))<=40
                     and sf(r.get("current_position",0))>5],
                    key=lambda r: sf(r["opportunity_score"]), reverse=True)[:6]
        quick_wins = [{"keyword": r["keyword"], "domain": r["domain"],
                       "opportunity_score": sf(r["opportunity_score"]),
                       "volume": si(r["volume"]),
                       "current_position": sf(r["current_position"])} for r in qw]

        keyword_list = [r["keyword"] for r in kw_rows]

        if keyword and keyword in keyword_list:
            trend = fetch("""SELECT rh.date, rh.position, rh.clicks, rh.impressions
                             FROM rank_history rh JOIN keywords k ON rh.keyword_id = k.id
                             WHERE k.keyword=? ORDER BY rh.date""", [keyword])
            if trend:
                dates = [r["date"] for r in trend]
                fig = go.Figure(data=[go.Scatter(x=dates, y=[sf(r["position"]) for r in trend],
                              mode="lines+markers", marker_color="#ff6b6b", line=dict(width=2, color="#ff6b6b"))])
                fig.update_layout(title=f"{keyword} — Position Trend",
                                  yaxis=dict(autorange="reversed"), height=300,
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
                p1 = fig_to_html(fig)
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=dates, y=[si(r["clicks"]) for r in trend],
                                          mode="lines+markers", name="Clicks", line=dict(color="#4ecdc4")))
                fig2.add_trace(go.Scatter(x=dates, y=[si(r["impressions"]) for r in trend],
                                          mode="lines+markers", name="Impressions", line=dict(color="#ffe66d")))
                fig2.update_layout(title="Clicks & Impressions", height=300,
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                   font_color="#ccc", legend=dict(orientation="h", y=1.12))
                trend_chart = f'<div class="grid-2"><div>{p1}</div><div>{fig_to_html(fig2)}</div></div>'

        kw_display = [{"Domain": r["domain"], "Keyword": r["keyword"],
                       "Category": r["category"], "Intent": r["intent"],
                       "Vol": si(r["volume"]), "Score": round(sf(r["opportunity_score"]),1),
                       "Diff": si(r["difficulty"]), "Pos": round(sf(r["current_position"]),1),
                       "Clicks": si(r["clicks"]), "Imp": si(r["impressions"])}
                      for r in kw_rows]

    # ═══ ISSUES ══════════════════════════════════════════════════════════
    w2, p2 = [], []
    if domain != "All":
        w2.append("d.name = ?"); p2.append(domain)
    if sev != "All":
        w2.append("e.severity = ?"); p2.append(sev)
    where2 = f"WHERE {' AND '.join(w2)}" if w2 else ""

    issue_rows = fetch(
        f"""SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
                   e.description, e.suggestion, e.status, e.created_at, e.fixed_at
            FROM onpage_errors e JOIN domains d ON e.domain_id = d.id
            {where2}
            ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                         WHEN 'moderate' THEN 2 ELSE 3 END, e.id""",
        p2,
    )

    issues_metrics, issues_charts = {}, {}
    if issue_rows:
        open_ = [r for r in issue_rows if r["status"] == "open"]
        issues_metrics = {"open": len(open_), "fixed": len([r for r in issue_rows if r["status"]=="fixed"]),
                          "critical": len([r for r in open_ if r["severity"]=="critical"]),
                          "high": len([r for r in open_ if r["severity"]=="high"]),
                          "moderate": len([r for r in open_ if r["severity"]=="moderate"])}

        sc = defaultdict(int)
        for r in open_:
            sc[r["severity"]] += 1
        if sc:
            si2 = sorted(sc.items())
            fig = go.Figure(data=[go.Pie(values=[v for _, v in si2], labels=[k for k, _ in si2],
                                        marker=dict(colors=["#ff4444","#ff8800","#ffcc00","#88ccff"][:len(si2)]))])
            fig.update_layout(title="Issues by Severity", paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            issues_charts["sev_pie"] = fig_to_html(fig, 300)

        dc = defaultdict(int)
        for r in open_:
            dc[r["domain"]] += 1
        if dc:
            di = sorted(dc.items(), key=lambda x: x[1], reverse=True)
            fig = px.bar(x=[d for d,_ in di], y=[c for _,c in di],
                         title="Issues by Domain", color_discrete_sequence=["#4ecdc4"],
                         labels={"x": "Domain", "y": "Count"})
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            issues_charts["dom_bar"] = fig_to_html(fig, 300)

    # ═══ CONTENT ═════════════════════════════════════════════════════════
    w3, p3 = [], []
    if category != "All":
        w3.append("ci.category = ?"); p3.append(category)
    if effort != "All":
        w3.append("ci.effort = ?"); p3.append(effort)
    where3 = f"WHERE {' AND '.join(w3)}" if w3 else ""

    ideas_rows = fetch(
        f"""SELECT ci.id, ci.title, ci.target_keyword, ci.category,
                   ci.estimated_searches, ci.opportunity_score, ci.effort,
                   ci.content_type, ci.status, vw.current_position, vw.domain
            FROM content_ideas ci
            LEFT JOIN v_backlog_with_rankings vw ON ci.id = vw.idea_id
            {where3} ORDER BY ci.opportunity_score DESC""",
        p3,
    )

    ideas_metrics, ideas_charts, top_picks, ideas_display = {}, {}, [], []
    if ideas_rows:
        sc2 = [sf(r["opportunity_score"]) for r in ideas_rows]
        ideas_metrics = {"count": len(ideas_rows),
                         "avg_score": round(sum(sc2)/len(sc2), 1) if sc2 else 0,
                         "total_searches": sum(si(r["estimated_searches"]) for r in ideas_rows)}

        fig = px.scatter(x=[sf(r["estimated_searches"]) for r in ideas_rows],
                         y=[sf(r["opportunity_score"]) for r in ideas_rows],
                         size=[sf(r["estimated_searches"]) for r in ideas_rows],
                         color=[r["category"] for r in ideas_rows],
                         hover_name=[r["title"] for r in ideas_rows],
                         title="Opportunity Matrix: Score vs Search Volume",
                         labels={"x": "Monthly Searches", "y": "Score"})
        fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
        ideas_charts["matrix"] = fig_to_html(fig, 400)

        vbc2 = defaultdict(float)
        for r in ideas_rows:
            vbc2[r["category"]] += sf(r["estimated_searches"])
        if vbc2:
            vi2 = sorted(vbc2.items(), key=lambda x: x[1])
            fig = px.bar(x=[v for _, v in vi2], y=[c for c, _ in vi2], orientation="h",
                         title="Total Search Volume by Category",
                         color_discrete_sequence=["#ff6b6b"],
                         labels={"x": "Monthly Searches", "y": ""})
            fig.update_layout(height=400, paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc",
                              margin=dict(l=0, r=0, t=30, b=0))
            ideas_charts["vol_by_cat"] = fig_to_html(fig, 400)

        top = sorted([r for r in ideas_rows if sf(r.get("opportunity_score",0))>=8],
                     key=lambda r: sf(r["opportunity_score"]), reverse=True)[:6]
        top_picks = [{"title": r["title"],
                      "opportunity_score": sf(r["opportunity_score"]),
                      "estimated_searches": si(r["estimated_searches"]),
                      "target_keyword": r["target_keyword"],
                      "effort": r["effort"], "content_type": r["content_type"]}
                     for r in top]

        ideas_display = [{"Title": r["title"], "Keyword": r["target_keyword"],
                          "Category": r["category"], "Searches": si(r["estimated_searches"]),
                          "Score": round(sf(r["opportunity_score"]),1),
                          "Effort": r["effort"], "Type": r["content_type"]}
                         for r in ideas_rows]

    # ═══ SETTINGS ════════════════════════════════════════════════════════
    last_sync = get_one(
        """SELECT source, status, rows_synced, started_at, completed_at, error
           FROM sync_log WHERE source='gsc' ORDER BY started_at DESC LIMIT 1"""
    )
    sync_hist = fetch(
        """SELECT source, status, rows_synced, started_at, completed_at
           FROM sync_log ORDER BY started_at DESC LIMIT 10"""
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = render_page(
        now=now, filters=filters,
        qp_keep=qp_keep, qp_vals=qp,
        selected_domain=domain, selected_category=category, selected_intent=intent,
        selected_sev=sev, selected_effort=effort, selected_keyword=keyword or "",
        kw_rows=kw_rows, kw_metrics=kw_metrics, kw_charts=kw_charts,
        quick_wins=quick_wins, keyword_list=keyword_list, trend_chart=trend_chart,
        kw_display=kw_display,
        issue_rows=issue_rows, issues_metrics=issues_metrics, issues_charts=issues_charts,
        ideas_rows=ideas_rows, ideas_metrics=ideas_metrics, ideas_charts=ideas_charts,
        top_picks=top_picks, ideas_display=ideas_display,
        last_sync=last_sync, sync_hist=sync_hist,
    )
    return HTMLResponse(html)
