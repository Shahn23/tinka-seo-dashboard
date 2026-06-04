# ON-PAGE SEO AUDIT REPORT
## Giant Bubbles by Tinka
### www.giantbubbles.co.nz + www.giantbubblesau.com
### Date: June 4, 2026

---

## EXECUTIVE SUMMARY

61 pages crawled across both sites (61 NZ + 48 AU = 109 total). **53 key findings** identified across four severity tiers. The biggest issue is **near-total duplicate content between the NZ and AU sites** — 53/61 equivalent pages share identical titles, 41 share identical meta descriptions, and 50 share identical H1 headings. This creates a severe canonicalization problem and likely rank suppression for both domains.

Both stores are on Shopify. No broken links found on key pages. Server response times are excellent (<1s). The most impactful fix is differentiating content between the two country-specific stores.

---

## SEVERITY: CRITICAL (Must fix — blocks ranking)

### 1. CROSS-SITE DUPLICATE CONTENT — ALL PAGES
- **53 of 61 NZ pages** have EXACTLY the same title tag as their AU equivalent
- **41 of 61** have identical meta descriptions
- **50 of 61** have identical H1 headings
- Both sites compete against each other in Google's index for the same keywords
- **Fix:** Every page needs NZ/AU-specific differentiation — change site name in titles ("Giant Bubbles by Tinka NZ" vs "Giant Bubbles by Tinka AU"), add location-specific keywords to meta descriptions, rewrite H1s to reference the country

### 2. MISSING META DESCRIPTIONS — 24 pages (12 per site)
**Affected pages (both sites):**
- /pages/who-is-tinka (Who is Tinka?)
- /pages/giant-bubble-reviews (Giant Bubble Reviews)
- /pages/faq (FAQ)
- /pages/what-customers-say-about-our-giant-bubbles
- /pages/giant-bubble-giveaway-2023
- /blogs/blog (Blog index)
- /collections/home-page-carousel
- /collections/all (All Tinka Giant Bubbles)
- /collections/kits
- /collections/all-except-gift-wrap
- /collections/best-sellers
- /collections/buy-2-get-1-free
- **Fix:** Add unique, keyword-rich meta descriptions (120-158 chars) to all missing pages. These are often the snippet Google shows in SERPs.

### 3. META DESCRIPTION MASSIVELY OVERSTUFFED — 2 pages (1 per site)
- **/products/240ml-concentrate-giant-bubble-kit** — 1,859 character meta description
- This is likely a Shopify app or theme injecting product description into the meta field
- **Fix:** Trim to 120-158 chars. The current content is paragraph-long product descriptions, not meta descriptions.

### 4. MISSING H1 TAGS — 6 pages (3 per site)
- /pages/faq — No H1 tag found
- /pages/giant-bubble-giveaway-2023 — No H1 tag found
- /collections/best-sellers — No H1 tag found
- **Fix:** Every page MUST have exactly one H1 that includes the primary target keyword.

---

## SEVERITY: HIGH (Significant impact — should fix ASAP)

### 5. TITLE TAGS TOO LONG — 55 instances (30 NZ + 25 AU)
Google typically displays 50-60 characters. Many titles exceed this:
- **128 chars:** /pages/concentrate-vs-pour-n-play-giant-bubble-solution
- **105 chars:** /blogs/blog/discover-the-magic-of-giant-bubbles-perfect-christmas-gift-ideas-for-kids
- **94 chars:** /products/12-litres-professional-giant-bubble-juice-copy
- **93 chars:** /blogs/blog/giant-bubbles-a-magical-therapy-for-neurodiversity-and-autism
- **92 chars:** 4 blog posts
- **84 chars:** /products/tinka-giant-bubble-juice-1-litre
- **82 chars:** /products/32l-tinka-giant-bubble-concentrate
- Plus 20+ more between 62-81 chars

Everything >60 chars risks truncation in SERPs. **Fix:** Rewrite titles to 50-60 chars including the "&ndash; Giant Bubbles by Tinka" Shopify suffix.

### 6. META DESCRIPTIONS OVER 160 CHARS — 65 instances
Nearly every product page has a 319-324 character meta description. Google truncates at ~160 chars. Blog posts are also 166-323 chars. **Fix:** Every meta description should be a concise 120-158 character summary with a call to action.

### 7. MULTIPLE H1 TAGS — 2 pages (1 per site)
- /pages/amazing-giant-bubble-recipe — has 2 H1s:
  1. "Amazing Giant Bubble Recipe"
  2. "Tinka 500ml Giant Bubble Concentrate (Makes 7L)"
- This is likely the Shopify theme adding a "featured product" as a second H1
- **Fix:** Only one H1 per page. Move the second to H2.

---

## SEVERITY: MEDIUM (Should fix — good for rankings)

### 8. IMAGE ALT TEXT — ~1,002/1,855 images missing alt text (54%)
- NZ site: 548/1,045 images (52%) lack alt text
- AU site: 454/810 images (56%) lack alt text
- Most Shopify product images have alt text from the sitemap, but theme/design images (decorative banners, section backgrounds) don't
- **Fix:** Add descriptive alt text to product images that only have empty alt attributes. Decorative images can have alt="" (empty, but NOT missing alt attribute entirely)

### 9. META DESCRIPTIONS UNDER 120 CHARS — 15 instances
- /collections/no-frills — 32 chars ("No Frills")
- /collections/refills — 42 chars
- /pages/contact — 56 chars
- /products/10-tinka-store-gift-card — 60 chars
- /collections/giant-bubble-wands — 84 chars
- /collections/kits-for-under-5-y-o — 90 chars
- /collections/tinka-concentrate-giant-bubble-range — 109 chars
- /pages/wholesale — 110 chars
- **Fix:** Expand to 120-158 chars

### 10. TITLE TAG SHOPIFY SUFFIX WASTE
- Every title ends with "&ndash; Giant Bubbles by Tinka"
- This consumes 26+ characters of the title tag budget
- On blog posts and product pages, the title itself + suffix easily exceeds 60 chars
- **Fix:** In Shopify theme settings, shorten or remove the suffix (try just "Tinka" or "Tinka GB")

---

## SEVERITY: LOW (Nice to have)

### 11. PAGE LOAD TIME
- Server response times: 0.28-0.82s — excellent
- No broken links found in sample check of 22 key pages
- **Recommendation:** Run a full Google PageSpeed Insights audit once an API key is configured. The 0-byte download sizes suggest dynamic content, which may benefit from caching optimization.

### 12. STRUCTURED DATA (Schema.org)
- Not checked in this crawl. Shopify typically adds Product schema, but it's worth verifying review/rating markup on /pages/giant-bubble-reviews and FAQ schema on /pages/faq.

### 13. INTERNAL LINKING
- Blog posts on both sites appear to have minimal cross-linking to product pages
- The "FAQ" page only links to products through the Shopify "add to cart" buttons
- **Fix:** Add contextual internal links from blog posts to relevant products

---

## PRIORITY ACTION PLAN

### Top 5 quick wins (1-2 hours each):
1. Update Shopify theme title suffix to "Tinka" (save 14 chars per title)
2. Write meta descriptions for the 12 missing-pages (can batch in theme settings)
3. Add H1 tags to /pages/faq, /pages/giant-bubble-giveaway-2023, /collections/best-sellers
4. Fix the 1,859-char meta description on 240ml-concentrate-giant-bubble-kit
5. Add alt text to product images that have empty alt=""

### Top 5 strategic projects (1-2 days each):
1. **NZ vs AU content differentiation** — Full rewrite of titles, H1s, and meta descriptions per country. This is the single most impactful change.
2. **Title tag optimization** — Rewrite 55+ titles to 50-60 chars
3. **Meta description overhaul** — Rewrite 65+ descriptions to 120-158 chars
4. **Blog-to-product internal linking** — Add contextual product links in all blog posts
5. **Structured data audit** — Verify Product, FAQ, and Review schema markup

---

## SITE-BY-SITE ISSUE BREAKDOWN

### giantbubbles.co.nz (61 pages crawled)
| Issue | Count |
|-------|-------|
| Missing meta descriptions | 12 |
| Missing H1 tags | 3 |
| Multiple H1 tags | 1 |
| Titles >60 chars | 30 |
| Meta desc >160 chars | 36 |
| Meta desc <120 chars | 8 |
| Images missing alt text | 548/1,045 (52%) |

### giantbubblesau.com (48 pages crawled)
| Issue | Count |
|-------|-------|
| Missing meta descriptions | 12 |
| Missing H1 tags | 3 |
| Multiple H1 tags | 1 |
| Titles >60 chars | 25 |
| Meta desc >160 chars | 29 |
| Meta desc <120 chars | 7 |
| Images missing alt text | 454/810 (56%) |

---

*Full raw crawl data saved in workspace: seo_crawl_results.json*
*Analysis script: analyze_seo.py*
