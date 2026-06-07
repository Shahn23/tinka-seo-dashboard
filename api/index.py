"""FastAPI SEO Dashboard v0.5 - Live Syncing for Giant Bubbles by Tinka.
All 4 sections: keyword rankings, new keyword opportunities, on-page errors, blog content ideas.
Auto-refreshes every 60s. Works on Vercel serverless.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from xml.sax.saxutils import escape as html_escape

import plotly.graph_objects as go
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# Import interactive action routes (relative import — Vercel bundles api/ as a
# package because __init__.py is present, so the sibling module is .actions_routes)
try:
    from .actions_routes import router as actions_router
except (ImportError, ValueError):
    # Fallback for local dev / non-package contexts
    from actions_routes import router as actions_router

_THIS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = _THIS_DIR.parent
_DB_SOURCE = _THIS_DIR / "seo_dashboard.db"
if not _DB_SOURCE.exists():
    _DB_SOURCE = PROJECT_DIR / "data" / "seo_dashboard.db"
DB_PATH = Path("/tmp") / "seo_dashboard.db"
_DB_INIT_ERROR = None

def _init_db():
    """Copy bundled DB to /tmp (writable on Vercel) and set pragmas.
    Logged to stderr so Vercel captures it in the function log."""
    if DB_PATH.exists():
        return
    import shutil
    print(f"[init_db] DB source: {_DB_SOURCE} (exists={_DB_SOURCE.exists()})", flush=True)
    if not _DB_SOURCE.exists():
        raise FileNotFoundError(
            f"Bundled DB not found at {_DB_SOURCE}. "
            f"Check vercel.json includeFiles pattern."
        )
    shutil.copy2(str(_DB_SOURCE), str(DB_PATH))
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.close()
    print(f"[init_db] DB copied to {DB_PATH}", flush=True)

try:
    _init_db()
except Exception as _e:
    import sys, traceback
    print(f"[tinka-dashboard] DB init failed: {_e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    _DB_INIT_ERROR = str(_e)

app = FastAPI(title="Tinka SEO Dashboard v0.9 - Interactive Actions with Live Queue")
app.include_router(actions_router)

# Surface init failures as a 503 (instead of crashing the whole request with 500).
# First-request cold starts hit this if /tmp was wiped or the bundled DB is bad.
@app.middleware("http")
async def _db_init_guard(request: Request, call_next):
    if _DB_INIT_ERROR is not None and DB_PATH.exists() is False:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"error": "db_init_failed", "detail": _DB_INIT_ERROR,
             "hint": "Check vercel.json includeFiles pattern for api/seo_dashboard.db"},
            status_code=503,
        )
    return await call_next(request)

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.row_factory = sqlite3.Row
    return conn

def fetch(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
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
        include_plotlyjs="cdn", full_html=False,
        default_height=height,
        config={"displayModeBar": False, "responsive": True, "scrollZoom": False},
    )

def sf(v, default=0.0):
    if v is None: return default
    try: return float(v)
    except: return default

def si(v, default=0):
    if v is None: return default
    try: return int(v)
    except: return default

def esc(s):
    return html_escape(str(s)) if s is not None else ""

# ── Page builder ──────────────────────────────────────────────────────────────
def render_page(**ctx):
    now = ctx["now"]
    filters = ctx["filters"]
    sd, sc, si_ = ctx["selected_domain"], ctx["selected_category"], ctx["selected_intent"]
    sp = ctx.get("selected_keyword", "")
    sv_ = ctx.get("selected_sev", "All")
    se_ = ctx.get("selected_effort", "All")

    def opt(val, selected, label=None):
        s = ' selected' if val == selected else ''
        return f'<option value="{esc(val)}"{s}>{esc(label or val)}</option>'

    domain_opts = "\n".join(opt(d, sd) for d in filters["domains"])
    cat_opts = "\n".join(opt(c, sc) for c in filters["categories"])
    intent_opts = "\n".join(opt(i, si_) for i in filters["intents"])

    kw_sec = render_keywords(ctx)
    newkw_sec = render_new_keywords(ctx)
    comp_sec = render_competitive(ctx)
    issues_sec = render_issues(ctx)
    content_sec = render_content(ctx)
    studio_sec = render_content_studio(ctx)
    audit_sec = render_deep_audit(ctx)
    geo_sec = render_geo_visibility(ctx)
    settings_sec = render_settings(ctx)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tinka SEO Dashboard - Live</title>
<meta http-equiv="refresh" content="60">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1117;color:#ccc;min-height:100vh}}
.app-header{{background:linear-gradient(135deg,#1a1c2e,#16182a);border-bottom:1px solid #2a2d4a;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
.app-header h1{{font-size:20px;color:#00d4aa}}
.app-header .sub{{color:#666;font-size:12px}}
.app-header .status-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#00d4aa;margin-right:6px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
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
.main-content{{flex:1;padding:24px;overflow-y:auto;min-width:0}}
.tabs{{display:flex;gap:2px;border-bottom:1px solid #2a2d4a;margin-bottom:24px;flex-wrap:wrap}}
.tab-btn{{padding:10px 20px;background:transparent;border:none;color:#888;font-size:14px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}}
.tab-btn:hover{{color:#ccc}}
.tab-btn.active{{color:#00d4aa;border-bottom-color:#00d4aa}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
.metric-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}}
.metric-card{{background:#1a1c2e;border-radius:12px;padding:16px;text-align:center;border:1px solid #2a2d4a}}
.metric-card .value{{font-size:26px;font-weight:700;color:#00d4aa}}
.metric-card .label{{margin-top:4px;font-size:12px;color:#8888aa}}
.metric-card .sub{{font-size:11px;color:#666}}
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
.data-table{{width:100%;border-collapse:collapse;font-size:12px;background:#1a1c2e;border-radius:8px;overflow:hidden}}
.data-table th{{background:#22243e;padding:8px 10px;text-align:left;color:#888;font-weight:600;font-size:10px;text-transform:uppercase}}
.data-table td{{padding:8px 10px;border-top:1px solid #2a2d4a}}
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
.trend-select select{{padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px;min-width:300px;max-width:100%}}
.win-card{{background:linear-gradient(135deg,#002b1a,#004d2e);border:1px solid #00d4aa;border-radius:10px;padding:10px;text-align:center}}
.win-card .kw{{color:#00d4aa;font-weight:600}}
.win-card .meta{{color:#aaa;font-size:12px}}
.loss-card{{background:linear-gradient(135deg,#2e001a,#4d002e);border:1px solid #ff4444;border-radius:10px;padding:10px;text-align:center}}
.loss-card .kw{{color:#ff6b6b;font-weight:600}}
.loss-card .meta{{color:#aaa;font-size:12px}}
.wl-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px}}
.keyword-tag{{display:inline-block;background:#1e2036;border:1px solid #2a2d4a;border-radius:12px;padding:2px 10px;font-size:11px;color:#ccc;margin:2px}}
@media(max-width:768px){{.app-layout{{flex-direction:column}}.sidebar{{width:100%;border-right:none;border-bottom:1px solid #2a2d4a}}.grid-2,.wl-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="app-header">
<div><h1>🔍 SEO Dashboard</h1><div class="sub"><span class="status-dot"></span>Giant Bubbles by Tinka - auto-refreshes every 60s - {esc(now)}</div></div>
</div>
<div class="app-layout">
<form class="sidebar" method="GET" action="/">
<h2>Filters</h2>
<div class="filter-group"><label for="domain">Domain</label><select name="domain" id="domain">{domain_opts}</select></div>
<div class="filter-group"><label for="category">Category</label><select name="category" id="category">{cat_opts}</select></div>
<div class="filter-group"><label for="intent">Intent</label><select name="intent" id="intent">{intent_opts}</select></div>
<button type="submit" class="btn-filter">Apply Filters</button>
<div class="footer">Auto-refresh: 60s<br>Updated: {esc(now)}</div>
</form>
<div class="main-content">
<div class="tabs">
<button class="tab-btn active" onclick="switchTab(event,'tab-kw')">🔑 Rankings</button>
<button class="tab-btn" onclick="switchTab(event,'tab-newkw')">🆕 New Keywords</button>
<button class="tab-btn" onclick="switchTab(event,'tab-comp')">📊 Competitive</button>
<button class="tab-btn" onclick="switchTab(event,'tab-issues')">🛠️ Issues ({ctx.get('open_issue_count','?')})</button>
<button class="tab-btn" onclick="switchTab(event,'tab-content')">📝 Content ({ctx.get('idea_count','?')})</button>
<button class="tab-btn" onclick="switchTab(event,'tab-studio')">✍️ Content Studio</button>
<button class="tab-btn" onclick="switchTab(event,'tab-audit')">🔍 Deep Audit</button>
<button class="tab-btn" onclick="switchTab(event,'tab-geo')">🌐 AI Visibility</button>
<button class="tab-btn" onclick="switchTab(event,'tab-settings')">🔄 Settings</button>
</div>
<div id="tab-kw" class="tab-content active">{kw_sec}</div>
<div id="tab-newkw" class="tab-content">{newkw_sec}</div>
<div id="tab-comp" class="tab-content">{comp_sec}</div>
<div id="tab-issues" class="tab-content">{issues_sec}</div>
<div id="tab-content" class="tab-content">{content_sec}</div>
<div id="tab-studio" class="tab-content">{studio_sec}</div>
<div id="tab-audit" class="tab-content">{audit_sec}</div>
<div id="tab-geo" class="tab-content">{geo_sec}</div>
<div id="tab-settings" class="tab-content">{settings_sec}</div>
</div></div>
<script>
function switchTab(e,i){{document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.getElementById(i).classList.add('active');e.currentTarget.classList.add('active');setTimeout(()=>{{document.getElementById(i).querySelectorAll('.js-plotly-plot').forEach(p=>Plotly.Plots.resize(p))}},100)}}

// ── Interactive Action Helpers ──────────────────────────────────────────
async function postAction(url, formData) {{
    const btn = event?.target;
    if (btn) {{ btn.disabled = true; btn.textContent = '⏳'; }}
    try {{
        const resp = await fetch(url, {{ method: 'POST', body: formData }});
        const data = await resp.json();
        showToast(data.message || data.status, data.status === 'queued' || data.status === 'ok' ? 'success' : 'error');
        if (data.status === 'queued' || data.status === 'ok') {{
            setTimeout(() => location.reload(), 1500);
        }}
    }} catch(e) {{
        showToast('Network error: ' + e.message, 'error');
    }} finally {{
        if (btn) {{ btn.disabled = false; btn.textContent = btn.dataset.originalText || btn.textContent; }}
    }}
}}

async function deleteItem(url) {{
    if (!confirm('Delete this item? This cannot be undone.')) return;
    const btn = event?.target;
    if (btn) {{ btn.disabled = true; btn.textContent = '⏳'; }}
    try {{
        const resp = await fetch(url, {{ method: 'POST' }});
        const data = await resp.json();
        showToast(data.message, data.status === 'ok' ? 'success' : 'error');
        if (data.status === 'ok') setTimeout(() => location.reload(), 1000);
    }} catch(e) {{
        showToast('Error: ' + e.message, 'error');
    }} finally {{
        if (btn) {{ btn.disabled = false; btn.textContent = '✕'; }}
    }}
}}

async function markFixed(url) {{
    const btn = event?.target;
    if (btn) {{ btn.disabled = true; btn.textContent = '⏳'; }}
    try {{
        const resp = await fetch(url, {{ method: 'POST' }});
        const data = await resp.json();
        showToast(data.message, data.status === 'ok' ? 'success' : 'error');
        if (data.status === 'ok') setTimeout(() => location.reload(), 1000);
    }} catch(e) {{
        showToast('Error: ' + e.message, 'error');
    }} finally {{
        if (btn) {{ btn.disabled = false; btn.textContent = '✅'; }}
    }}
}}

function generateKeywords() {{ document.getElementById('kw-gen-form').submit(); }}
function generateIdeas() {{ document.getElementById('idea-gen-form').submit(); }}

// ── Toast Notification ──────────────────────────────────────────────────
function showToast(msg, type) {{
    const t = document.getElementById('toast') || (() => {{
        const d = document.createElement('div');
        d.id = 'toast'; d.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;padding:14px 20px;border-radius:10px;font-weight:600;font-size:14px;max-width:400px;transition:opacity .3s;box-shadow:0 4px 20px rgba(0,0,0,.5)';
        document.body.appendChild(d);
        return d;
    }})();
    t.style.background = type === 'success' ? '#004d2e' : type === 'error' ? '#4d002e' : '#1e2036';
    t.style.color = type === 'success' ? '#00d4aa' : type === 'error' ? '#ff6b6b' : '#ccc';
    t.style.border = type === 'success' ? '1px solid #00d4aa' : type === 'error' ? '1px solid #ff6b6b' : '1px solid #2a2d4a';
    t.textContent = msg; t.style.opacity = '1';
    setTimeout(() => {{ t.style.opacity = '0'; }}, 5000);
}}
</script>
</body>
</html>"""

# ── TAB 1: Keyword Rankings ──────────────────────────────────────────────────
def render_keywords(ctx):
    rows = ctx.get("kw_rows", [])
    if not rows:
        return "<h2>Keyword Rankings</h2><p style='color:#888'>No keyword data found.</p>"

    metrics = ctx["kw_metrics"]
    charts = ctx["kw_charts"]
    wins = ctx["quick_wins"]
    losses = ctx.get("quick_losses", [])
    kws = ctx["keyword_list"]
    sel_kw = ctx.get("selected_keyword", "")
    trend = ctx.get("trend_chart", "")

    parts = ['<h2>🔑 Keyword Rankings & Position Tracking</h2>']
    dist = metrics.get("distribution", {})
    parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value">{metrics["count"]}</div><div class="label">Keywords Tracked</div></div>
<div class="metric-card"><div class="value">{metrics["avg_pos"]}</div><div class="label">Avg Position</div></div>
<div class="metric-card warn"><div class="value">{metrics.get("total_clicks",0):,}</div><div class="label">Total Clicks (7d)</div></div>
<div class="metric-card ok"><div class="value">{metrics.get("total_impressions",0):,}</div><div class="label">Total Impressions (7d)</div></div>
</div>
<div class="metric-row">
<div class="metric-card"><div class="value" style="color:#00d4aa">{dist.get("top3",0)}</div><div class="label">Top 3</div><span class="sub">{dist.get("top3_pct","")}</span></div>
<div class="metric-card"><div class="value" style="color:#4ecdc4">{dist.get("top10",0)}</div><div class="label">Top 10</div><span class="sub">{dist.get("top10_pct","")}</span></div>
<div class="metric-card warn"><div class="value">{dist.get("top20",0)}</div><div class="label">Top 20</div></div>
<div class="metric-card danger"><div class="value">{dist.get("outside",0)}</div><div class="label">Outside Top 20</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("vol_by_cat","")}</div><div class="chart-box">{charts.get("opp_dist","")}</div></div>')

    if wins or losses:
        parts.append(f'<h3>🏆 Winners & Losers</h3><div class="wl-grid">')
        # Winners
        parts.append('<div><h4 style="color:#00d4aa;margin-bottom:8px">📈 Biggest Improvements</h4>')
        if wins:
            for r in wins[:6]:
                parts.append(f'<div class="win-card" style="margin-bottom:6px"><div class="kw">{esc(r["keyword"])}</div><div class="meta">{esc(r["domain"])}</div><div class="detail">&#8593; {int(r.get("change",1))} spots &mdash; #{r.get("current_pos",0):.0f} from #{r.get("past_pos",0):.0f}</div></div>')
        else:
            parts.append('<p style="color:#666;font-size:13px">No improvements in this period.</p>')
        parts.append('</div>')
        # Losers
        parts.append('<div><h4 style="color:#ff6b6b;margin-bottom:8px">📉 Biggest Drops</h4>')
        if losses:
            for r in losses[:6]:
                parts.append(f'<div class="loss-card" style="margin-bottom:6px"><div class="kw">{esc(r["keyword"])}</div><div class="meta">{esc(r["domain"])}</div><div class="detail">&#8595; {abs(int(r.get("change",1)))} spots &mdash; #{r.get("current_pos",0):.0f} from #{r.get("past_pos",0):.0f}</div></div>')
        else:
            parts.append('<p style="color:#666;font-size:13px">No drops in this period.</p>')
        parts.append('</div></div>')

    # Quick wins
    qw = ctx.get("quick_wins_all", [])
    if qw:
        parts.append('<h3>⚡ Quick Wins (High Opp, Low Diff)</h3><div class="quick-wins-row">')
        for r in qw[:6]:
            parts.append(f'<div class="quick-win"><div class="kw">{esc(r["keyword"])}</div><div class="meta">{esc(r["domain"])}</div><div class="detail">Score: {r.get("score",0):.0f} | Vol: {r.get("vol",0):,} | Pos: {r.get("pos",0):.0f}</div></div>')
        parts.append('</div>')

    # Trend chart
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

    # Full table
    parts.append('<h3>📋 All Keywords</h3>')
    kw_display = ctx.get("kw_display", [])
    if kw_display:
        parts.append('<div style="max-height:500px;overflow-y:auto"><table class="data-table"><thead><tr><th style="width:40px">Del</th><th>Domain</th><th>Keyword</th><th>Cat</th><th>Intent</th><th>Vol</th><th>Score</th><th>Diff</th><th>Pos</th><th>Clicks</th><th>Imp</th></tr></thead><tbody>')
        for r in kw_display:
            kw_id = r.get("Id", "")
            parts.append(f'<tr><td><button onclick="deleteItem(\'/api/delete/keyword/{kw_id}\')" style="background:none;border:1px solid #ff4444;color:#ff4444;border-radius:4px;cursor:pointer;padding:2px 6px;font-size:11px" title="Delete">\u2715</button></td><td>{esc(r["Domain"])}</td><td style="font-weight:600">{esc(r["Keyword"])}</td><td>{esc(r["Category"])}</td><td>{esc(r.get("Intent",""))}</td><td>{r.get("Vol",0):,}</td><td>{r.get("Score","")}</td><td>{r.get("Diff","")}</td><td>{r.get("Pos","")}</td><td>{r.get("Clicks",0)}</td><td>{r.get("Imp",0):,}</td></tr>')
        parts.append('</tbody></table></div>')
    else:
        parts.append('<p style="color:#888">No keywords match filters.</p>')

    return "".join(parts)

# ── TAB 2: New Keyword Opportunities ────────────────────────────────────────
def render_new_keywords(ctx):
    rows = ctx.get("newkw_rows", [])
    if not rows:
        return "<h2>New Keyword Opportunities</h2><p style='color:#888'>All keywords have ranking data - no untracked keywords found.</p>"

    m = ctx["newkw_metrics"]
    picks = ctx.get("newkw_picks", [])
    parts = ['<h2>\U0001f4a1 New Keyword Opportunities</h2>']

    # === Generate Keywords form ===
    parts.append('''<div class="status-box" style="margin-bottom:16px;background:linear-gradient(135deg,#0d2137,#1a3a5c);border:1px solid #58a6ff">
    <p style="color:#58a6ff;font-weight:600;margin-bottom:8px">\u2728 Generate New Keyword Ideas</p>
    <form id="kw-gen-form" action="/api/queue-action" method="POST" onsubmit="event.preventDefault();postAction('/api/queue-action',new FormData(this))" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
        <input type="hidden" name="action_type" value="generate_keywords">
        <div style="flex:2;min-width:180px">
            <label style="display:block;color:#888;font-size:11px;margin-bottom:2px">Topic</label>
            <input type="text" name="action_params" value='{"topic":"giant bubbles","market":"NZ","count":15}' style="width:100%;padding:8px 10px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
        </div>
        <div style="flex:0 0 100px">
            <label style="display:block;color:#888;font-size:11px;margin-bottom:2px">Market</label>
            <select name="market" style="width:100%;padding:8px 10px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
                <option value="NZ">NZ</option>
                <option value="AU">AU</option>
                <option value="both">Both</option>
            </select>
        </div>
        <button type="submit" style="padding:8px 16px;background:#58a6ff;color:#000;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px">\u2699\ufe0f Generate</button>
    </form>
    <p style="color:#888;font-size:11px;margin-top:6px">Generated keywords appear within 30 min. Reload the page to see results.</p>
    </div>''')

    parts.append(f'''<div class="metric-row">\n
<div class="metric-card"><div class="value">{m["count"]}</div><div class="label">Untracked Keywords</div></div>
<div class="metric-card"><div class="value">{m.get("avg_opp",0):.1f}</div><div class="label">Avg Opportunity Score</div></div>
<div class="metric-card ok"><div class="value">{m.get("total_vol",0):,}</div><div class="label">Total Monthly Searches</div></div>
</div>''')

    parts.append('<p style="color:#888;font-size:13px;margin-bottom:16px">These keywords have been identified through research but have no ranking data yet. They need dedicated content to start ranking.</p>')

    if picks:
        parts.append('<h3>⭐ Top Opportunities (Score ≥ 8.0)</h3><div class="quick-wins-row">')
        for r in picks[:9]:
            parts.append(f'<div class="quick-win"><div class="kw">{esc(r["keyword"])}</div><div class="meta">{esc(r["domain"])} &middot; {esc(r["category"])}</div><div class="detail">Score: {r.get("score",0):.0f} | Vol: {r.get("vol",0):,} | Diff: {r.get("diff",0)}</div></div>')
        parts.append('</div>')

    parts.append('<h3>\U0001f4cb All Untracked Keywords</h3><div style="max-height:500px;overflow-y:auto"><table class="data-table"><thead><tr><th style="width:40px">Del</th><th>Domain</th><th>Keyword</th><th>Category</th><th>Intent</th><th>Vol</th><th>Score</th><th>Diff</th></tr></thead><tbody>')
    for r in rows:
        parts.append(f'<tr><td><button onclick="deleteItem(\'/api/delete/keyword/{r["id"]}\')" style="background:none;border:1px solid #ff4444;color:#ff4444;border-radius:4px;cursor:pointer;padding:2px 6px;font-size:11px" title="Delete keyword">\u2715</button></td><td>{esc(r["domain"])}</td><td style="font-weight:600">{esc(r["keyword"])}</td><td>{esc(r["category"])}</td><td>{esc(r["intent"])}</td><td>{r.get("vol",0):,}</td><td>{r.get("score",0)}</td><td>{r.get("diff",0)}</td></tr>')
    parts.append('</tbody></table></div>')

    return "".join(parts)

# ── TAB 3: SEO Issues ────────────────────────────────────────────────────────
def render_issues(ctx):
    rows = ctx.get("issue_rows", [])
    if not rows:
        return "<h2>Technical SEO Issues</h2><p style='color:#888'>No SEO issues found. Great work!</p>"

    m = ctx["issues_metrics"]
    charts = ctx.get("issues_charts", {})
    sev_filter = ctx.get("selected_sev", "All")

    parts = ['<h2>🛠️ Technical SEO Issues</h2>']
    parts.append(f'''<div class="metric-row">
<div class="metric-card danger"><div class="value">{m["open"]}</div><div class="label">Open Issues</div></div>
<div class="metric-card danger"><div class="value">{m["critical"]}</div><div class="label">Critical</div></div>
<div class="metric-card warn"><div class="value">{m["high"]}</div><div class="label">High</div></div>
<div class="metric-card"><div class="value">{m["moderate"]}</div><div class="label">Moderate</div></div>
<div class="metric-card ok"><div class="value">{m["fixed"]}</div><div class="label">Fixed</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("sev_pie","")}</div><div class="chart-box">{charts.get("dom_bar","")}</div></div>')

    # Severity filter
    parts.append('<div style="margin-bottom:12px"><form method="GET" action="/" style="display:inline">')
    for k in ctx.get("qp_keep", []):
        parts.append(f'<input type="hidden" name="{esc(k)}" value="{esc(ctx["qp_vals"][k])}">')
    parts.append(f'''<select name="sev" onchange="this.form.submit()" style="padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
<option value="All"{" selected" if sev_filter=="All" else ""}>All Severities</option>
<option value="critical"{" selected" if sev_filter=="critical" else ""}>Critical</option>
<option value="high"{" selected" if sev_filter=="high" else ""}>High</option>
<option value="moderate"{" selected" if sev_filter=="moderate" else ""}>Moderate</option>
<option value="low"{" selected" if sev_filter=="low" else ""}>Low</option>
</select></form></div>''')

    for r in rows:
        sev = r["severity"]
        fixed = r["status"] == "fixed"
        error_id = str(r['id'])
        fixed_btn = f' | <button onclick="markFixed(\'/api/mark-fixed/{error_id}\')" style="background:none;border:1px solid #4ecdc4;color:#4ecdc4;border-radius:4px;cursor:pointer;padding:2px 8px;font-size:11px;margin-left:8px" title="Mark as fixed">&#9989; Mark Fixed</button>' if not fixed else ''
        parts.append(f'''<div class="issue-detail {sev}{" fixed" if fixed else ""}">
<div><span class="sev-badge sev-{sev}">{sev}</span><strong style="margin-left:8px">{esc(r.get("error_type","").replace("_"," ").title())}</strong>
<span style="float:right;color:#888;font-size:12px">{"&#9989; Fixed" if fixed else "&#128308; Open"}{fixed_btn}</span></div>
<div class="meta">{esc(r.get("domain",""))} | {esc(r.get("page_url",""))[:80]}</div>
<div class="desc">{esc(r.get("description",""))}</div>
<div class="suggestion">&#128161; {esc(r.get("suggestion",""))}</div>
</div>''')

    return "".join(parts)

# ── TAB 4: Content Backlog ──────────────────────────────────────────────────
def render_content(ctx):
    rows = ctx.get("ideas_rows", [])
    if not rows:
        return "<h2>Content Idea Backlog</h2><p style='color:#888'>No content ideas found.</p>"

    m = ctx["ideas_metrics"]
    charts = ctx.get("ideas_charts", {})
    picks = ctx.get("top_picks", [])
    display = ctx.get("ideas_display", [])
    effort_filter = ctx.get("selected_effort", "All")

    parts = ['<h2>\U0001f4dd Blog Content Ideas</h2>']

    # === Generate Content Ideas form ===
    parts.append('''<div class="status-box" style="margin-bottom:16px;background:linear-gradient(135deg,#0d2137,#1a3a5c);border:1px solid #58a6ff">
    <p style="color:#58a6ff;font-weight:600;margin-bottom:8px">\u2728 Generate New Content Ideas</p>
    <form id="idea-gen-form" action="/api/queue-action" method="POST" onsubmit="event.preventDefault();postAction('/api/queue-action',new FormData(this))" style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
        <input type="hidden" name="action_type" value="generate_ideas">
        <div style="flex:2;min-width:180px">
            <label style="display:block;color:#888;font-size:11px;margin-bottom:2px">Topic / Keywords</label>
            <input type="text" name="action_params" value='{"topic":"giant bubbles for kids parties, outdoor bubble activities, bubble entertainer hire","count":10}' style="width:100%;padding:8px 10px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
        </div>
        <button type="submit" style="padding:8px 16px;background:#58a6ff;color:#000;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px">\u2699\ufe0f Generate</button>
    </form>
    <p style="color:#888;font-size:11px;margin-top:6px">Content ideas appear within 30 min. Reload to see new ideas.</p>
    </div>''')

    parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value">{m["count"]}</div><div class="label">Ideas</div></div>
<div class="metric-card"><div class="value">{m.get("avg_score",0):.1f}</div><div class="label">Avg Opportunity Score</div></div>
<div class="metric-card ok"><div class="value">{m.get("total_searches",0):,}</div><div class="label">Total Monthly Searches</div></div>
</div>''')

    if charts:
        parts.append(f'<div class="grid-2"><div class="chart-box">{charts.get("matrix","")}</div><div class="chart-box">{charts.get("vol_by_cat","")}</div></div>')

    parts.append('<div style="margin-bottom:12px"><form method="GET" action="/" style="display:inline">')
    for k in ctx.get("qp_keep", []):
        parts.append(f'<input type="hidden" name="{esc(k)}" value="{esc(ctx["qp_vals"][k])}">')
    parts.append(f'''<select name="effort" onchange="this.form.submit()" style="padding:8px 12px;background:#1e2036;border:1px solid #2a2d4a;border-radius:6px;color:#ccc;font-size:13px">
<option value="All"{" selected" if effort_filter=="All" else ""}>All Effort Levels</option>
<option value="easy"{" selected" if effort_filter=="easy" else ""}>Easy</option>
<option value="medium"{" selected" if effort_filter=="medium" else ""}>Medium</option>
<option value="hard"{" selected" if effort_filter=="hard" else ""}>Hard</option>
</select></form></div>''')

    if picks:
        parts.append('<h3>⭐ Top Picks (Score ≥ 8.0)</h3><div class="top-picks">')
        for r in picks[:6]:
            parts.append(f'''<div class="top-pick"><div class="title">{esc(r["title"])}</div>
<div class="meta">Score: {r.get("opportunity_score",0):.0f} | Searches: {r.get("estimated_searches",0):,}</div>
<div class="meta" style="margin-top:4px;color:#777">Keyword: {esc(r.get("target_keyword",""))} | Effort: {esc(r.get("effort",""))} | Type: {esc(r.get("content_type",""))}</div></div>''')
        parts.append('</div>')

    if display:
        parts.append('<h3>\U0001f4cb All Content Ideas</h3><div style="max-height:500px;overflow-y:auto"><table class="data-table"><thead><tr><th style="width:80px">Actions</th><th>Title</th><th>Target Keyword</th><th>Category</th><th>Searches</th><th>Score</th><th>Effort</th><th>Type</th></tr></thead><tbody>')
        for r in display:
            idea_id = r.get("Id", "")
            parts.append(f'''<tr>
<td style="white-space:nowrap">
<button onclick="deleteItem('/api/delete/idea/{idea_id}')" style="background:none;border:1px solid #ff4444;color:#ff4444;border-radius:4px;cursor:pointer;padding:2px 6px;font-size:11px" title="Delete">\u2715</button>
<button onclick="postAction('/api/queue-action',new FormData(document.getElementById('wa-{idea_id}')))" style="background:none;border:1px solid #58a6ff;color:#58a6ff;border-radius:4px;cursor:pointer;padding:2px 6px;font-size:11px;margin-left:4px" title="Write Article">\u270d\ufe0f</button>
<form id="wa-{idea_id}" style="display:none"><input type="hidden" name="action_type" value="write_article"><input type="hidden" name="action_params" value='{{"idea_id":{idea_id}}}'></form>
</td>
<td style="font-weight:600">{esc(r["Title"])}</td><td>{esc(r.get("Keyword",""))}</td><td>{esc(r.get("Category",""))}</td><td>{r.get("Searches",0):,}</td><td>{r.get("Score","")}</td><td>{esc(r.get("Effort",""))}</td><td>{esc(r.get("Type",""))}</td></tr>''')
        parts.append('</tbody></table></div>')

    return "".join(parts)

# ── TAB 5: Competitive Analysis ──────────────────────────────────────────────
def render_competitive(ctx):
    rows = ctx.get("comp_rows", [])
    gap_rows = ctx.get("gap_rows", [])
    parts = ['<h2>📊 Competitive Keyword Analysis</h2>']

    # Cross-site keyword overlap
    if rows:
        parts.append('''<h3>🌐 Keyword Coverage by Domain</h3>
<div style="overflow-x:auto"><table class="data-table">
<thead><tr><th>Keyword</th><th>giantbubbles.co.nz</th><th>giantbubblesau.com</th><th>Volume</th><th>Category</th></tr></thead><tbody>''')
        for r in rows:
            nz = "✅" if r["nz_rank"] else ("🟡" if r["nz_kw"] else "❌")
            au = "✅" if r["au_rank"] else ("🟡" if r["au_kw"] else "❌")
            parts.append(f'<tr><td style="font-weight:600">{esc(r["keyword"])}</td><td>{nz}</td><td>{au}</td><td>{r.get("volume",0):,}</td><td>{esc(r.get("category",""))}</td></tr>')
        parts.append('</tbody></table></div>')

        # Summary cards
        shared = sum(1 for r in rows if r["nz_kw"] and r["au_kw"])
        nz_only = sum(1 for r in rows if r["nz_kw"] and not r["au_kw"])
        au_only = sum(1 for r in rows if r["au_kw"] and not r["nz_kw"])
        parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value" style="color:#4ecdc4">{shared}</div><div class="label">Keywords on Both Sites</div></div>
<div class="metric-card"><div class="value" style="color:#00d4aa">{nz_only}</div><div class="label">NZ Only</div></div>
<div class="metric-card"><div class="value" style="color:#ff6b6b">{au_only}</div><div class="label">AU Only</div></div>
</div>''')
    else:
        parts.append('<p style="color:#888">No keyword data for competitive analysis.</p>')

    # Keyword gap analysis (keywords tracked in one domain but not the other)
    if gap_rows:
        parts.append('<h3>🔍 Keyword Gaps</h3><p style="color:#888;font-size:13px;margin-bottom:12px">Keywords where one site has ranking data and the other does not — a content opportunity for the missing domain.</p>')
        parts.append('<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Keyword</th><th>Has Data On</th><th>Missing On</th><th>Vol</th><th>NZ Rank</th><th>AU Rank</th></tr></thead><tbody>')
        for r in gap_rows:
            has_domain, miss_domain = ("NZ", "AU") if r.get("nz_pos") else ("AU", "NZ")
            parts.append(f'<tr><td style="font-weight:600">{esc(r["keyword"])}</td><td style="color:#00d4aa">{has_domain}</td><td style="color:#ff6b6b">{miss_domain}</td><td>{r.get("volume",0):,}</td><td>{r.get("nz_rank","-")}</td><td>{r.get("au_rank","-")}</td></tr>')
        parts.append('</tbody></table></div>')

    return "".join(parts)

# ── TAB 6: Content Studio ──────────────────────────────────────────────────
def render_content_studio(ctx):
    articles = ctx.get("articles", [])
    parts = ['<h2>✍️ Content Studio</h2>']

    if articles:
        parts.append(f'''<div class="metric-row">
<div class="metric-card"><div class="value">{len(articles)}</div><div class="label">Articles Published</div></div>
<div class="metric-card"><div class="value">{sum(si(a.get("word_count",0)) for a in articles):,}</div><div class="label">Total Words Written</div></div>
<div class="metric-card ok"><div class="value">{sum(1 for a in articles if a.get("status")=="published")}</div><div class="label">Published</div></div>
<div class="metric-card warn"><div class="value">{sum(1 for a in articles if a.get("status")=="draft")}</div><div class="label">Drafts</div></div>
</div>''')

        parts.append('<h3>\U0001f4c4 Published Articles</h3>')
        parts.append('<div style="overflow-x:auto"><table class="data-table"><thead><tr><th style="width:40px">Del</th><th>Title</th><th>Domain</th><th>Status</th><th>Words</th><th>SEO Score</th><th>Created</th></tr></thead><tbody>')
        for a in articles:
            link = esc(a.get("shopify_url","") or a.get("article_url",""))
            title = esc(a.get("title",""))
            status_icon = "\u2705" if a.get("status")=="published" else "\U0001f4dd"
            domain = esc(a.get("target_domain",""))
            words = a.get("word_count",0) or 0
            seo = a.get("seo_score","") or "-"
            created = esc(a.get("created_at","") or "")
            parts.append(f'<tr><td><button onclick="deleteItem(\'/api/delete/article/{a["id"]}\')" style="background:none;border:1px solid #ff4444;color:#ff4444;border-radius:4px;cursor:pointer;padding:2px 6px;font-size:11px" title="Delete">\u2715</button></td><td style="font-weight:600">{title}</td><td>{domain}</td><td>{status_icon} {esc(a.get("status",""))}</td><td>{words:,}</td><td>{seo}</td><td>{created[:10] if created else ""}</td></tr>')
        parts.append('</tbody></table></div>')

        if any(a.get("target_keywords") for a in articles):
            parts.append('<h3>🎯 Keywords Used in Articles</h3><div class="grid-2">')
            for a in articles:
                kws = a.get("target_keywords","")
                if kws:
                    kw_list = [k.strip() for k in kws.split(",")]
                    kw_tags = " ".join(f'<span class="keyword-tag">{esc(k)}</span>' for k in kw_list[:5])
                    parts.append(f'<div class="status-box"><div style="font-weight:600;margin-bottom:6px">{esc(a["title"])}</div>{kw_tags}</div>')
            parts.append('</div>')
    else:
        parts.append('<p style="color:#888">No articles published yet. Use the "Write Article" button in the Content tab to queue an article for AI generation.</p>')

    return "".join(parts)

# ── TAB 7: Deep Audit ──────────────────────────────────────────────────────
def render_deep_audit(ctx):
    findings = ctx.get("audit_findings", [])
    audit_metrics = ctx.get("audit_metrics", {})
    parts = ['<h2>🔍 Deep Site Audit</h2>']

    if audit_metrics:
        parts.append(f'''<div class="metric-row">
<div class="metric-card danger"><div class="value">{audit_metrics.get("critical",0)}</div><div class="label">Critical</div></div>
<div class="metric-card warn"><div class="value">{audit_metrics.get("high",0)}</div><div class="label">High</div></div>
<div class="metric-card"><div class="value">{audit_metrics.get("moderate",0)}</div><div class="label">Moderate</div></div>
<div class="metric-card ok"><div class="value">{audit_metrics.get("low",0)}</div><div class="label">Low</div></div>
<div class="metric-card ok"><div class="value">{audit_metrics.get("fixed",0)}</div><div class="label">Fixed</div></div>
</div>''')

    if findings:
        parts.append('<p style="color:#888;font-size:13px;margin-bottom:16px">On-page SEO audit findings from latest crawl. These are technical issues found on your sites.</p>')
        # Group by severity
        for sev_name, sev_color in [("critical", "#ff4444"), ("high", "#ff8800"), ("moderate", "#ffcc00"), ("low", "#888")]:
            sev_items = [f for f in findings if f.get("severity") == sev_name and f.get("status") != "fixed"]
            if sev_items:
                parts.append(f'<h3 style="color:{sev_color};margin-top:16px;margin-bottom:8px">🔴 {sev_name.title()} ({len(sev_items)})</h3>')
                for f in sev_items:
                    fid = str(f['id'])
                    parts.append(f'''<div class="issue-detail {sev_name}">
<div><span class="sev-badge sev-{sev_name}">{sev_name}</span><strong style="margin-left:8px">{esc(f.get("error_type","").replace("_"," ").title())}</strong>
<span style="float:right"><button onclick="markFixed('/api/mark-fixed/{fid}')" style="background:none;border:1px solid #4ecdc4;color:#4ecdc4;border-radius:4px;cursor:pointer;padding:2px 8px;font-size:11px" title="Mark as fixed">&#9989; Mark Fixed</button></span></div>
<div class="meta">{esc(f.get("domain",""))} | {esc(f.get("page_url",""))[:80]}</div>
<div class="desc">{esc(f.get("description",""))}</div>
<div class="suggestion">&#128161; {esc(f.get("suggestion",""))}</div>
</div>''')
    else:
        parts.append('<p style="color:#888">No audit findings available. Run a site crawl to generate findings.</p>')

    return "".join(parts)

# ── TAB 8: AI & GEO Visibility ─────────────────────────────────────────────
def render_geo_visibility(ctx):
    geo_rows = ctx.get("geo_rows", [])
    geo_metrics = ctx.get("geo_metrics", {})
    parts = ['<h2>🌐 AI & GEO Visibility</h2>']

    if geo_rows:
        # Rank trend over time
        dates = sorted(set(r["date"] for r in geo_rows if r.get("date")))
        parts.append('<h3>📊 GSC Performance Trend</h3>')
        parts.append('<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Date</th><th>Domain</th><th>Avg Position</th><th>Clicks</th><th>Impressions</th><th>CTR</th></tr></thead><tbody>')
        for r in sorted(geo_rows, key=lambda x: x.get("date","") or "", reverse=True)[:30]:
            ctr = f'{r.get("ctr",0):.1f}%' if r.get("ctr") else "-"
            parts.append(f'<tr><td>{esc(r.get("date",""))}</td><td>{esc(r.get("domain",""))}</td><td>{r.get("avg_position",0):.1f}</td><td>{r.get("clicks",0):,}</td><td>{r.get("impressions",0):,}</td><td>{ctr}</td></tr>')
        parts.append('</tbody></table></div>')
    else:
        parts.append('<p style="color:#888">No GSC performance trend data available. Data syncs daily at 6 AM.</p>')

    # GEO recommendations
    parts.append('''<h3 style="margin-top:20px">🤖 AI Search Optimization Tips</h3>
<div class="status-box">
<ol style="color:#aaa;font-size:13px;line-height:2;margin-left:20px">
<li><strong>Improve Structured Data</strong> - Add FAQ, HowTo, and Product schema markup to help AI assistants understand your content.</li>
<li><strong>Build Authoritative Content</strong> - Publish in-depth guides (1,500+ words) that answer specific questions AI users search for.</li>
<li><strong>Optimize for Featured Snippets</strong> - Structure content with clear headings, lists, and tables that AI parsers extract easily.</li>
<li><strong>Increase Internal Linking</strong> - Strengthen topical clusters so AI crawlers understand site structure and relevance.</li>
<li><strong>Monitor Brand Mentions</strong> - AI models often cite well-known brands; build authority through PR and guest posting.</li>
</ol>
<div style="margin-top:16px;padding:12px;background:linear-gradient(135deg,#0d2137,#1a3a5c);border:1px solid #58a6ff;border-radius:10px">
<p style="color:#58a6ff;font-weight:600">💡 GEO Insight</p>
<p style="color:#aaa;font-size:13px">Generative Engine Optimization (GEO) focuses on being cited by AI search engines like ChatGPT, Claude, and Perplexity. Traditional SEO still matters, but GEO adds a new layer: content that's structured for AI consumption.</p>
</div>
</div>''')

    return "".join(parts)

# ── TAB 5: Sync & Settings ──────────────────────────────────────────────────
def render_settings(ctx):
    last_sync = ctx.get("last_sync")
    sync_hist = ctx.get("sync_hist", [])
    parts = ["<h2>🔄 Sync & Settings</h2><div class='grid-2'><div><h3>📡 Google Search Console Sync</h3><div class='status-box'>"]
    if last_sync:
        icon = "&#9989;" if last_sync.get("status") == "success" else "&#10060;" if last_sync.get("status") == "failed" else "&#128260;"
        parts.append(f'<div style="font-size:24px">{icon}</div>')
        parts.append(f'<p><strong>Last Sync:</strong> {esc(last_sync.get("completed_at") or "In progress...")}</p>')
        parts.append(f'<p><strong>Status:</strong> {esc(last_sync.get("status",""))}</p>')
        parts.append(f'<p><strong>Rows:</strong> {last_sync.get("rows_synced") or "N/A"}</p>')
        if last_sync.get("error"):
            parts.append(f'<p style="color:#ff4444;margin-top:8px">{esc(last_sync["error"])}</p>')
    else:
        parts.append("<p>No syncs yet.</p>")
    parts.append('</div></div><div><h3>⏰ Auto-Sync Schedule</h3><div class="status-box">')
    parts.append('<p>🕐 <strong>6:00 AM daily</strong> - Hermes cron job</p>')
    parts.append('<p style="color:#888;font-size:12px;margin-top:8px">Syncs GSC rankings, on-page errors, content ideas</p>')
    parts.append('</div><h3>📁 Dashboard Info</h3><div class="status-box">')
    parts.append('<p>📍 <strong>App:</strong> tinka-seo-dashboard.vercel.app</p>')
    parts.append('<p>🗄️ <strong>Data:</strong> SQLite, auto-refreshes every 60s</p>')
    parts.append(f'<p>\U0001f3f7\ufe0f <strong>Version:</strong> v0.9 - Interactive Actions with Live Queue</p>')
    parts.append('</div></div></div>')

    # === Pending Actions section ===
    pending_actions = ctx.get("pending_actions", [])
    pending_count = ctx.get("pending_count", 0)
    parts.append(f'''<h3 style="margin-top:20px">\u2699\ufe0f Pending Actions</h3>
<div class="status-box" style="margin-bottom:16px">
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px">
<div class="metric-card" style="flex:1;min-width:100px"><div class="value" style="font-size:18px">{len(pending_actions)}</div><div class="label">Recent Actions</div></div>
<div class="metric-card" style="flex:1;min-width:100px"><div class="value" style="font-size:18px;color:{"#ff8800" if pending_count > 0 else "#00d4aa"}">{pending_count}</div><div class="label">Pending</div></div>
</div>
<p style="color:#888;font-size:12px">Actions queued from the dashboard are processed by a local agent within 30 minutes.</p>
''')
    if pending_actions:
        parts.append('<div style="max-height:300px;overflow-y:auto"><table class="data-table"><thead><tr><th>ID</th><th>Action</th><th>Status</th><th>Created</th><th>Result</th></tr></thead><tbody>')
        for a in pending_actions:
            status_icon = "\u23f3" if a["status"] == "pending" else "\u2705" if a["status"] == "completed" else "\u274c"
            parts.append(f'<tr><td>{a["id"]}</td><td>{esc(a.get("action_type",""))}</td><td>{status_icon} {esc(a["status"])}</td><td>{esc(a.get("created_at",""))}</td><td>{esc(str(a.get("result","") or a.get("error","") or ""))[:40]}</td></tr>')
        parts.append('</tbody></table></div>')
    else:
        parts.append('<p style="color:#666;font-size:13px;margin-top:8px">No actions queued yet. Use the Generate/Delete buttons on other tabs to create actions.</p>')
    parts.append('</div>')

    if sync_hist:
        parts.append('<h3>Sync History</h3><table class="data-table"><thead><tr><th>Source</th><th>Status</th><th>Rows</th><th>Started</th><th>Completed</th></tr></thead><tbody>')
        for s in sync_hist[:10]:
            icon = "&#9989;" if s.get("status") == "success" else "&#10060;"
            parts.append(f'<tr><td>{esc(s.get("source",""))}</td><td>{icon} {esc(s.get("status",""))}</td><td>{s.get("rows_synced") or "-"}</td><td>{esc(s.get("started_at",""))}</td><td>{esc(s.get("completed_at") or "-")}</td></tr>')
        parts.append('</tbody></table>')

    parts.append('''<h3 style="margin-top:20px">📖 How to Use This Dashboard</h3>
<div class="status-box">
<p><strong>For the Site Owner (Non-Technical):</strong></p>
<ol style="color:#aaa;font-size:13px;line-height:1.8;margin-left:20px">
<li>🔑 <strong>Rankings tab</strong> - See where your keywords rank (Top 3, Top 10, etc.). Use the filter sidebar to view NZ or AU data separately. Select any keyword to see its position trend over time.</li>
<li>🆕 <strong>New Keywords tab</strong> - Research-backed keywords you're not ranking for yet. High score = write content about these first.</li>
<li>📊 <strong>Competitive tab</strong> - See which keywords are covered on NZ vs AU, and identify gaps where one site has data the other doesn't.</li>
<li>🛠️ <strong>Issues tab</strong> - Technical problems found on your sites. Critical items hurt rankings - fix first.</li>
<li>📝 <strong>Content tab</strong> - Blog post ideas ranked by opportunity score. Easy topics are quick wins.</li>
<li>✍️ <strong>Content Studio tab</strong> - Track published articles and which keywords they target.</li>
<li>🔍 <strong>Deep Audit tab</strong> - Full on-page audit findings grouped by severity.</li>
<li>🌐 <strong>AI Visibility tab</strong> - GSC performance trends and GEO optimization tips for AI search engines.</li>
<li>🔄 <strong>Settings tab</strong> - Data sync status, configuration, and this guide.</li>
<li>The dashboard <strong>auto-refreshes every 60 seconds</strong> to show the latest data.</li>
</ol>
<p style="margin-top:12px;color:#888;font-size:12px">For technical updates, run <code>scripts/daily_sync.py --live --days 1</code> from the dashboard project directory, or rely on the daily 6 AM cron job.</p>
</div>''')

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
    domains = fetch("SELECT name FROM domains WHERE is_active=1")
    cats = fetch("SELECT DISTINCT category FROM keywords ORDER BY category")
    filters = {
        "domains": ["All"] + [d["name"] for d in domains],
        "categories": ["All"] + [c["category"] for c in cats],
        "intents": ["All", "informational", "commercial", "transactional", "navigational"],
    }

    qp = dict(request.query_params)
    qp_keep = [k for k in ["domain", "category", "intent"] if k in qp]

    # WHERE for keywords
    w, p = [], []
    if domain != "All": w.append("d.name = ?"); p.append(domain)
    if category != "All": w.append("k.category = ?"); p.append(category)
    if intent != "All": w.append("k.intent = ?"); p.append(intent)
    where = f"WHERE {' AND '.join(w)}" if w else ""

    # ═══ KEYWORD RANKINGS ══════════════════════════════════════════════════
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

    kw_metrics, kw_charts = {}, {}
    quick_wins, quick_losses, quick_wins_all = [], [], []
    keyword_list, kw_display = [], []
    trend_chart = ""

    if kw_rows:
        poses = [sf(r["current_position"]) for r in kw_rows if r["current_position"]]
        avg_pos = round(sum(poses)/len(poses), 1) if poses else 0
        tracked = [r for r in kw_rows if r["current_position"]]
        top3 = len([r for r in tracked if sf(r["current_position"]) <= 3])
        top10 = len([r for r in tracked if sf(r["current_position"]) <= 10])
        top20 = len([r for r in tracked if sf(r["current_position"]) <= 20])
        outside = len(tracked) - top20

        pct3 = f"{top3/len(tracked)*100:.0f}%" if tracked else ""
        pct10 = f"{top10/len(tracked)*100:.0f}%" if tracked else ""

        kw_metrics = {
            "count": len(kw_rows), "avg_pos": avg_pos,
            "total_clicks": sum(si(r["clicks"]) for r in kw_rows),
            "total_impressions": sum(si(r["impressions"]) for r in kw_rows),
            "distribution": {"top3": top3, "top10": top10, "top20": top20, "outside": outside,
                             "top3_pct": pct3, "top10_pct": pct10},
        }

        # Volume by category chart
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

        # Opportunity score chart
        scores = [sf(r["opportunity_score"]) for r in kw_rows]
        if scores:
            fig = go.Figure(data=[go.Histogram(x=scores, nbinsx=10, marker_color="#00d4aa")])
            fig.update_layout(title="Opportunity Score Distribution",
                              font_color="#ccc", margin=dict(l=0, r=0, t=30, b=0))
            kw_charts["opp_dist"] = fig_to_html(fig)

        # Winners & Losers (position change over 30 days)
        days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        wl = fetch(
            f"""SELECT k.id, k.keyword, d.name AS domain,
                       latest.position AS current_position,
                       past.position AS past_position
                FROM keywords k JOIN domains d ON k.domain_id = d.id
                LEFT JOIN (SELECT keyword_id, position FROM rank_history
                           WHERE (keyword_id, date) IN
                           (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)
                          ) latest ON k.id = latest.keyword_id
                LEFT JOIN rank_history past ON k.id = past.keyword_id AND past.date = ?
                {where}""",
            p + [days_ago],
        )
        for r in wl:
            cur = sf(r.get("current_position"))
            past = sf(r.get("past_position"))
            if cur and past and past > 0:
                change = past - cur
                if change > 0:
                    quick_wins.append({"keyword": r["keyword"], "domain": r["domain"],
                                       "change": change, "current_pos": cur, "past_pos": past})
                elif change < 0:
                    quick_losses.append({"keyword": r["keyword"], "domain": r["domain"],
                                         "change": change, "current_pos": cur, "past_pos": past})
        quick_wins.sort(key=lambda x: x["change"], reverse=True)
        quick_losses.sort(key=lambda x: x["change"])

        # Quick wins for high-opp, low-diff, unranked keywords
        qw_all = sorted(
            [r for r in kw_rows if sf(r["opportunity_score"]) >= 7
             and sf(r.get("difficulty", 100)) <= 40
             and (r.get("current_position") is None or sf(r.get("current_position")) > 5)],
            key=lambda r: sf(r["opportunity_score"]), reverse=True
        )[:6]
        quick_wins_all = [{"keyword": r["keyword"], "domain": r["domain"],
                           "score": sf(r["opportunity_score"]), "vol": si(r["volume"]),
                           "pos": sf(r.get("current_position", 0))} for r in qw_all]

        keyword_list = [r["keyword"] for r in kw_rows]

        if keyword and keyword in keyword_list:
            trend = fetch(
                """SELECT rh.date, rh.position, rh.clicks, rh.impressions
                   FROM rank_history rh JOIN keywords k ON rh.keyword_id = k.id
                   WHERE k.keyword=? ORDER BY rh.date""",
                [keyword]
            )
            if trend:
                dates = [r["date"] for r in trend]
                fig = go.Figure(data=[go.Scatter(x=dates, y=[sf(r["position"]) for r in trend],
                                  mode="lines+markers", marker_color="#ff6b6b",
                                  line=dict(width=2, color="#ff6b6b"))])
                fig.update_layout(title=f"{keyword} - Position Trend",
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

        kw_display = [{"Id": r["id"], "Domain": r["domain"], "Keyword": r["keyword"],
                       "Category": r["category"], "Intent": r["intent"],
                       "Vol": si(r["volume"]), "Score": round(sf(r["opportunity_score"]), 1),
                       "Diff": si(r["difficulty"]), "Pos": round(sf(r.get("current_position", 0)), 1),
                       "Clicks": si(r["clicks"]), "Imp": si(r["impressions"])}
                      for r in kw_rows]

    # ═══ NEW KEYWORD OPPORTUNITIES ════════════════════════════════════════
    newkw_rows = fetch(
        f"""SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent,
                   k.volume, k.opportunity_score, k.difficulty
            FROM keywords k JOIN domains d ON k.domain_id = d.id
            LEFT JOIN rank_history rh ON k.id = rh.keyword_id
            WHERE rh.id IS NULL
            AND (d.name = ? OR ? = 'All')
            AND (k.category = ? OR ? = 'All')
            AND (k.intent = ? OR ? = 'All')
            ORDER BY k.opportunity_score DESC, k.volume DESC""",
        [domain, domain, category, category, intent, intent]
    )
    newkw_metrics, newkw_picks = {}, []
    if newkw_rows:
        scores = [sf(r["opportunity_score"]) for r in newkw_rows]
        vols = [si(r["volume"]) for r in newkw_rows]
        newkw_metrics = {
            "count": len(newkw_rows),
            "avg_opp": round(sum(scores)/len(scores), 1) if scores else 0,
            "total_vol": sum(vols),
        }
        top_p = [r for r in newkw_rows if sf(r["opportunity_score"]) >= 8][:9]
        newkw_picks = [{"keyword": r["keyword"], "domain": r["domain"],
                        "category": r["category"], "score": sf(r["opportunity_score"]),
                        "vol": si(r["volume"]), "diff": si(r["difficulty"])}
                       for r in top_p]

    # ═══ ISSUES ══════════════════════════════════════════════════════════
    w2, p2 = [], []
    if domain != "All": w2.append("d.name = ?"); p2.append(domain)
    if sev != "All": w2.append("e.severity = ?"); p2.append(sev)
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
        issues_metrics = {
            "open": len(open_), "fixed": len([r for r in issue_rows if r["status"]=="fixed"]),
            "critical": len([r for r in open_ if r["severity"]=="critical"]),
            "high": len([r for r in open_ if r["severity"]=="high"]),
            "moderate": len([r for r in open_ if r["severity"]=="moderate"]),
        }
        sc = defaultdict(int)
        for r in open_: sc[r["severity"]] += 1
        if sc:
            si2 = sorted(sc.items())
            fig = go.Figure(data=[go.Pie(values=[v for _, v in si2], labels=[k for k, _ in si2],
                                        marker=dict(colors=["#ff4444","#ff8800","#ffcc00"][:len(si2)]))])
            fig.update_layout(title="Issues by Severity (Open)", paper_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            issues_charts["sev_pie"] = fig_to_html(fig, 300)
        dc = defaultdict(int)
        for r in open_: dc[r["domain"]] += 1
        if dc:
            di = sorted(dc.items(), key=lambda x: x[1], reverse=True)
            fig = go.Figure(data=[go.Bar(x=[d for d,_ in di], y=[c for _,c in di],
                                         marker_color="#4ecdc4")])
            fig.update_layout(title="Open Issues by Domain",
                              xaxis_title="Domain", yaxis_title="Count",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
            issues_charts["dom_bar"] = fig_to_html(fig, 300)

    # ═══ CONTENT ═════════════════════════════════════════════════════════
    w3, p3 = [], []
    if category != "All": w3.append("ci.category = ?"); p3.append(category)
    if effort != "All": w3.append("ci.effort = ?"); p3.append(effort)
    where3 = f"WHERE {' AND '.join(w3)}" if w3 else ""

    ideas_rows = fetch(
        f"""SELECT ci.id, ci.title, ci.target_keyword, ci.category,
                   ci.estimated_searches, ci.opportunity_score, ci.effort,
                   ci.content_type, ci.status
            FROM content_ideas ci
            {where3} ORDER BY ci.opportunity_score DESC""",
        p3,
    )
    ideas_metrics, ideas_charts, top_picks, ideas_display = {}, {}, [], []
    if ideas_rows:
        sc2 = [sf(r["opportunity_score"]) for r in ideas_rows]
        ideas_metrics = {
            "count": len(ideas_rows),
            "avg_score": round(sum(sc2)/len(sc2), 1) if sc2 else 0,
            "total_searches": sum(si(r["estimated_searches"]) for r in ideas_rows),
        }
        # Matrix chart — assign each category a numeric color index
        _cats = sorted({r["category"] for r in ideas_rows})
        _cat_colors = {c: i for i, c in enumerate(_cats)}
        _palette = ["#ff6b6b", "#4ecdc4", "#ffe66d", "#95e1d3", "#f38181",
                    "#aa96da", "#fcbad3", "#a8d8ea", "#ffffd2", "#ff9a8b"]
        fig = go.Figure(data=[go.Scatter(
            x=[sf(r["estimated_searches"]) for r in ideas_rows],
            y=[sf(r["opportunity_score"]) for r in ideas_rows],
            mode="markers",
            marker=dict(size=[max(8, min(40, sf(r["estimated_searches"])/50)) for r in ideas_rows],
                        color=[_cat_colors[r["category"]] for r in ideas_rows],
                        colorscale=[[i/(len(_cats)-1) if len(_cats) > 1 else 0, _palette[i % len(_palette)]]
                                    for i in range(len(_cats))],
                        showscale=False),
            text=[f"{r['title']} ({r['category']})" for r in ideas_rows],
            hovertemplate="<b>%{text}</b><br>Searches: %{x}<br>Score: %{y}<extra></extra>"
        )])
        fig.update_layout(title="Opp Score vs Search Volume",
                          xaxis_title="Monthly Searches", yaxis_title="Score",
                          height=400, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc")
        ideas_charts["matrix"] = fig_to_html(fig, 400)

        vbc2 = defaultdict(float)
        for r in ideas_rows:
            vbc2[r["category"]] += sf(r["estimated_searches"])
        if vbc2:
            vi2 = sorted(vbc2.items(), key=lambda x: x[1])
            fig = go.Figure(data=[go.Bar(x=[v for _, v in vi2], y=[c for c, _ in vi2],
                                         orientation="h", marker_color="#ff6b6b")])
            fig.update_layout(title="Search Volume by Category",
                              xaxis_title="Monthly Searches", yaxis_title="",
                              height=400, paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)", font_color="#ccc",
                              margin=dict(l=0, r=0, t=30, b=0))
            ideas_charts["vol_by_cat"] = fig_to_html(fig, 400)

        top = sorted([r for r in ideas_rows if sf(r.get("opportunity_score", 0)) >= 8],
                     key=lambda r: sf(r["opportunity_score"]), reverse=True)[:6]
        top_picks = [{"title": r["title"], "opportunity_score": sf(r["opportunity_score"]),
                      "estimated_searches": si(r["estimated_searches"]),
                      "target_keyword": r["target_keyword"], "effort": r["effort"],
                      "content_type": r["content_type"]} for r in top]

        ideas_display = [{"Id": r["id"], "Title": r["title"], "Keyword": r["target_keyword"],
                          "Category": r["category"], "Searches": si(r["estimated_searches"]),
                          "Score": round(sf(r["opportunity_score"]), 1),
                          "Effort": r["effort"], "Type": r["content_type"]} for r in ideas_rows]

    # ═══ COMPETITIVE ANALYSIS ═════════════════════════════════════════════
    comp_rows = fetch(
        """SELECT k.keyword, k.volume, k.category,
                  MAX(CASE WHEN d.name='giantbubbles.co.nz' THEN 1 ELSE 0 END) AS nz_kw,
                  MAX(CASE WHEN d.name='giantbubblesau.com' THEN 1 ELSE 0 END) AS au_kw,
                  MAX(CASE WHEN d.name='giantbubbles.co.nz' AND rh.position IS NOT NULL THEN 1 ELSE 0 END) AS nz_rank,
                  MAX(CASE WHEN d.name='giantbubblesau.com' AND rh.position IS NOT NULL THEN 1 ELSE 0 END) AS au_rank
           FROM keywords k JOIN domains d ON k.domain_id = d.id
           LEFT JOIN (SELECT keyword_id, MAX(date) as max_d FROM rank_history GROUP BY keyword_id) rh_max ON k.id = rh_max.keyword_id
           LEFT JOIN rank_history rh ON k.id = rh.keyword_id AND rh.date = rh_max.max_d
           GROUP BY k.keyword
           ORDER BY k.volume DESC"""
    )
    gap_rows = [r for r in comp_rows if (r["nz_rank"] or r["nz_kw"]) and not (r["au_rank"] or r["au_kw"]) or (r["au_rank"] or r["au_kw"]) and not (r["nz_rank"] or r["nz_kw"])]
    gap_rows = [dict(r) for r in gap_rows]

    # Enrich gap rows with rank data
    gap_enriched = []
    for r in gap_rows:
        kw = r["keyword"]
        nz_r = fetch("SELECT position FROM rank_history rh JOIN keywords k ON rh.keyword_id=k.id JOIN domains d ON k.domain_id=d.id WHERE k.keyword=? AND d.name='giantbubbles.co.nz' ORDER BY rh.date DESC LIMIT 1", [kw])
        au_r = fetch("SELECT position FROM rank_history rh JOIN keywords k ON rh.keyword_id=k.id JOIN domains d ON k.domain_id=d.id WHERE k.keyword=? AND d.name='giantbubblesau.com' ORDER BY rh.date DESC LIMIT 1", [kw])
        r["nz_pos"] = str(nz_r[0]["position"]) if nz_r else None
        r["au_pos"] = str(au_r[0]["position"]) if au_r else None
        gap_enriched.append(r)

    # ═══ CONTENT STUDIO ══════════════════════════════════════════════════
    articles = fetch("""SELECT pa.id, pa.title, pa.target_domain, pa.status, pa.target_keywords,
                               pa.word_count, pa.seo_score, pa.shopify_url, pa.created_at, pa.published_at
                        FROM published_articles pa ORDER BY pa.created_at DESC""")

    # ═══ DEEP AUDIT ═══════════════════════════════════════════════════════
    audit_findings = fetch(
        """SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
                  e.description, e.suggestion, e.status, e.created_at, e.fixed_at
           FROM onpage_errors e JOIN domains d ON e.domain_id = d.id
           ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                        WHEN 'moderate' THEN 2 ELSE 3 END, e.id"""
    )
    audit_open = [f for f in audit_findings if f["status"] == "open"]
    audit_metrics = {
        "critical": len([f for f in audit_open if f["severity"]=="critical"]),
        "high": len([f for f in audit_open if f["severity"]=="high"]),
        "moderate": len([f for f in audit_open if f["severity"]=="moderate"]),
        "low": len([f for f in audit_open if f["severity"]=="low"]),
        "fixed": len([f for f in audit_findings if f["status"]=="fixed"]),
    }

    # ═══ AI & GEO VISIBILITY ════════════════════════════════════════════
    geo_rows = fetch(
        """SELECT k.keyword, d.name AS domain, rh.date, rh.position, rh.clicks, rh.impressions, rh.ctr
           FROM rank_history rh JOIN keywords k ON rh.keyword_id = k.id
           JOIN domains d ON k.domain_id = d.id
           ORDER BY rh.date DESC LIMIT 100"""
    )

    # ═══ SYNC INFO ══════════════════════════════════════════════════════
    last_sync = get_one(
        """SELECT source, status, rows_synced, started_at, completed_at, error
           FROM sync_log WHERE source='gsc' ORDER BY started_at DESC LIMIT 1"""
    )
    sync_hist = fetch(
        """SELECT source, status, rows_synced, started_at, completed_at
           FROM sync_log ORDER BY started_at DESC LIMIT 10"""
    )

    # ═══ PENDING ACTIONS ════════════════════════════════════════════════
    pending_actions = []
    pending_count = 0
    try:
        acts = fetch(
            """SELECT id, action_type, action_params, status, created_at, processed_at, result, error
               FROM action_queue ORDER BY id DESC LIMIT 20"""
        )
        if acts:
            pending_actions = acts
            pending_count = sum(1 for a in acts if a["status"] == "pending")
    except Exception:
        pass

    # Quick counts for tab badges
    open_issue_count = issues_metrics.get("open", 0)
    idea_count = ideas_metrics.get("count", 0)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = render_page(
        now=now, filters=filters,
        qp_keep=qp_keep, qp_vals=qp,
        selected_domain=domain, selected_category=category, selected_intent=intent,
        selected_sev=sev, selected_effort=effort, selected_keyword=keyword or "",
        open_issue_count=open_issue_count, idea_count=idea_count,
        kw_rows=kw_rows, kw_metrics=kw_metrics, kw_charts=kw_charts,
        quick_wins=quick_wins, quick_losses=quick_losses, quick_wins_all=quick_wins_all,
        keyword_list=keyword_list, trend_chart=trend_chart,
        kw_display=kw_display,
        newkw_rows=newkw_rows, newkw_metrics=newkw_metrics, newkw_picks=newkw_picks,
        issue_rows=issue_rows, issues_metrics=issues_metrics, issues_charts=issues_charts,
        ideas_rows=ideas_rows, ideas_metrics=ideas_metrics, ideas_charts=ideas_charts,
        top_picks=top_picks, ideas_display=ideas_display,
        comp_rows=comp_rows, gap_rows=gap_enriched,
        articles=articles,
        audit_findings=audit_findings, audit_metrics=audit_metrics,
        geo_rows=geo_rows, geo_metrics={},
        last_sync=last_sync, sync_hist=sync_hist,
        pending_actions=pending_actions, pending_count=pending_count,
    )
    return HTMLResponse(html)
