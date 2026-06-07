# Rank & Rent Dashboard — Deep Research Report

## Competitor Landscape

### 1. RankHubPro (rankhubpro.com)
**Price:** Not listed publicly (likely $50-200/mo)
**Strengths:**
- Full pipeline: site building → SEO → lead management → renter management
- 4 templates + WordPress migration (4 modes: Tailwind rebuild, Visual Clone, Content Clone, AI Rebuild)
- Cloudflare Workers hosting (free, global)
- Multi-page generator: 6 services × 5 areas = 39 pages
- AI content via GPT-4o-mini (~$0.001/site)
- Citation builder: 25+ directories across 3 tiers
- GBP automation (create, verify, manage listings)
- NAP consistency monitoring with drift detection
- 5-layer spam filter + lead quality scoring (GPT-4o-mini, 0-100)
- Multi-tenant, white-label for agencies
- Bulk operations (50+ sites one-click)
- Renter management with revenue tracking

**Weaknesses:**
- No call tracking or recording
- No form completion tracking
- No automated content freshness pipeline
- No outreach automation to potential renters
- Cloudflare Workers only (locked into one host)

---

### 2. RankRent OS (rankrent.app)
**Price:** Not listed (likely subscription)
**Strengths:**
- AI page generator with niche+city combo
- One-click deploy to Netlify
- 5 templates/styles with custom branding
- Suburb pages for local SEO
- Google Indexing API integration
- Blog engine with seasonal awareness
- Affiliate program (15% per referral)
- GBP helper

**Weaknesses:**
- No call tracking
- No lead management/forwarding
- No renter management
- No citation building
- No spam filtering
- Pure cloud play — no local/self-hosted option

---

### 3. Rank and Rent Engine (RARE) (rankandrentengine.com)
**Price:** Free plan + paid tiers (Ignition, Turbocharged, Full Throttle)
**Strengths:**
- Competition insights + site analyzer + backlink profiler
- Keyword planner with real-time data + keyword costs
- Call tracking with recordings
- SMS lead notifications
- Spam filtering
- Automated monthly rollups
- Sales pipeline + revenue modeling
- CRM included
- Task tracker + due diligence tools
- Data exports

**Weaknesses:**
- No site builder/deployment
- No content generation
- Focused on the "business management" side, not the full pipeline
- No automation for site creation or content freshness

---

### 4. Ippei Lead Gen Dashboard (ippei.com/dashboard)
**Strengths:**
- Drag-and-drop AI website builder
- Call tracking number management
- Client management
- Supports both rank-and-rent and lead gen models

**Weaknesses:**
- Limited feature set compared to others
- Less automation

---

## Gaps & Opportunities — How to Beat Them All

### Tier 1: Must-Have Features (match competitors)

| Feature | RankHubPro | RankRent | RARE | Our Target |
|---------|-----------|----------|------|-----------|
| Site builder | ✅ | ✅ | ❌ | ✅ |
| Multi-page generator | ✅ | ✅ | ❌ | ✅ |
| One-click deploy | ✅ CF Workers | ✅ Netlify | ❌ | ✅ Both |
| AI content gen | ✅ GPT-4o-mini | ✅ | ❌ | ✅ Multi-model |
| Keyword research | ✅ KW Everywhere | ✅ | ✅ | ✅ |
| Rank tracking (GSC) | ✅ | ❌ | ❌ | ✅ |
| Citation builder | ✅ 25+ dirs | ❌ | ❌ | ✅ |
| GBP automation | ✅ | ✅ helper | ❌ | ✅ |
| Lead forwarding | ✅ Email+SMS | ❌ | ✅ SMS | ✅ Multi-channel |
| Spam filter | ✅ 5-layer | ❌ | ✅ | ✅ |
| Renter management | ✅ | ❌ | ❌ | ✅ |
| Call tracking | ❌ | ❌ | ✅ | ✅ |
| CRM | ❌ | ❌ | ✅ | ✅ |
| Revenue tracking | ✅ | ❌ | ✅ | ✅ |

### Tier 2: Differentiators (beating competitors)

**1. Full Call Tracking + Intelligence**
- Not just tracking numbers — full call recording via Twilio/VoIP
- AI transcription (Whisper/Deepgram) with sentiment scoring
- Call scoring: was this a qualified lead?
- Auto-log calls to renter dashboard

**2. Form Submission Tracking**
- Auto-detect form completions on your sites
- Track which pages/forms generate the most leads
- Form abandonment analytics
- A/B test form layouts

**3. Automated Content Freshness**
- Scheduled blog post publishing (weekly/monthly)
- Seasonal content updates (e.g., "Christmas services in [City]")
- Auto-regenerate stale pages (detect pages >90 days without update)
- Google freshness signal monitoring

**4. Renter Outreach Automation**
- Auto-generate outreach emails/call scripts when a site reaches top 5
- Renter lead scoring: who's most likely to buy based on site performance
- Automated monthly performance reports for renters
- Payment tracking + invoice generation

**5. Unified Profit Dashboard**
- Single view: site costs (domain, hosting) + revenue (rental income) = profit per site
- ROI per niche/city
- Portfolio heatmap: which niches/cities are winning
- What-if modeling: "what if I build 10 more plumber sites?"

**6. Multi-Model AI Engine**
- Cheap model (GPT-4o-mini) for bulk content generation
- Smart model for lead scoring, outreach, strategic analysis
- Local model fallback (llama.cpp) for sensitive data

**7. Self-Hosted / Local Option**
- SQLite backend (our existing stack)
- Can run entirely locally with no monthly SaaS fees
- Deploy sites to $0 hosting (Cloudflare Workers, Netlify)
- Optional cloud sync for team access
- Portable — take your whole business on a USB drive

### Tier 3: Moonshots (truly OP)

**8. Niche Research AI Agent**
- Autonomous agent that researches markets:
  - Scans Google for competition in [niche] + [city]
  - Estimates CPC, search volume, difficulty
  - Predicts monthly lead value
  - Recommends go/no-go with confidence score
- Saves weeks of manual research

**9. Done-For-You Deployment Pipeline**
- One click: research niche → build site → deploy → start ranking
- Automatically submits to Google Search Console
- Auto-generates sitemap and submits to Google
- Monitors indexing status

**10. Renter Marketplace**
- Built-in directory where local businesses can browse your ranked sites
- "This plumber site gets 50 visits/mo — rent it for $500/mo"
- Automated contract generation
- Payment collection via Stripe

**11. AI Assistant for Everything**
- "Find me a niche in Auckland with low competition and high CPC"
- "Generate 5 outreach emails for this ranked site"
- "What's my best and worst performing site this month?"
- Natural language queries over your entire portfolio

---

## Architecture Recommendation

**Stack:**
- **Backend:** Python/FastAPI (existing dashboard codebase)
- **Database:** SQLite (local) + optional PostgreSQL (hosted)
- **Frontend:** SPA with Plotly/Chart.js (existing pattern)
- **Site Hosting:** Cloudflare Workers + Netlify (dual deploy)
- **AI:** OpenAI API + local llama.cpp fallback
- **Call Tracking:** Twilio Voice API
- **SMS/Email:** Twilio + Resend
- **Payments:** Stripe (for renter marketplace)

**Data Model (from our existing rank-and-rent.db):**
```
projects → sites → keywords → rankings
                        → pages (generated content)
                        → leads (calls, forms)
                        → renters (who's renting)
                        → finances (costs, revenue)
```

**Phases:**
1. **Phase 1:** Full Dashboard (matching competitors) + site builder + deploy
2. **Phase 2:** Call tracking + lead management + renter management
3. **Phase 3:** AI agents + automation + marketplace

---

Want me to turn this into the first kanban goal task and start building Phase 1?
