"""
DataForSEO Python Client — direct API access (pay-as-you-go).

Mirrors the TypeScript client in rank-rent-v2/src/lib/dataforseo.ts.

Required env vars (or constructor args):
    DATAFORSEO_LOGIN    — DataForSEO email (Basic auth username)
    DATAFORSEO_PASSWORD — DataForSEO API password

Pricing:
    SERP organic:      $0.002/call
    Keyword volume:    $0.0006/keyword
    Keyword ideas:     $0.002/call
    Keyword difficulty: $0.002/call
    Backlinks summary: $0.005/call

For Tinka doing ~400 calls/day: ~$30-60/mo
"""

import base64
import json
import os
import urllib.request
import urllib.error
from typing import Optional


BASE_URL = 'https://api.dataforseo.com'


# ===================== Custom Error Types =====================

class DataForSEOError(Exception):
    """Generic DataForSEO API error."""
    pass

class DataForSEOConfigError(DataForSEOError):
    """Configuration error — missing or invalid credentials."""
    pass

class DataForSEORateLimitError(DataForSEOError):
    """Rate limit hit — wait before retrying."""
    pass


# ===================== Client =====================

class DataForSEOClient:
    """Low-level HTTP client for DataForSEO API."""

    def __init__(self, login: Optional[str] = None, password: Optional[str] = None,
                 base_url: str = BASE_URL, timeout: int = 60):
        self.login = login or os.environ.get('DATAFORSEO_LOGIN')
        self.password = password or os.environ.get('DATAFORSEO_PASSWORD')
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

        if not self.login:
            raise DataForSEOConfigError(
                "DATAFORSEO_LOGIN is not set. Pass it as an argument or set the "
                "DATAFORSEO_LOGIN environment variable."
            )
        if not self.password:
            raise DataForSEOConfigError(
                "DATAFORSEO_PASSWORD is not set. Pass it as an argument or set the "
                "DATAFORSEO_PASSWORD environment variable."
            )

    @property
    def _auth_header(self) -> str:
        """Build Basic auth header from login:password."""
        raw = f"{self.login}:{self.password}"
        encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
        return f"Basic {encoded}"

    def _call(self, path: str, body: list) -> dict:
        """Make a POST request to a DataForSEO API endpoint."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            url,
            method='POST',
            data=data,
            headers={
                'Authorization': self._auth_header,
                'Content-Type': 'application/json',
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode('utf-8')
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode('utf-8', errors='replace')
            if e.code == 401:
                raise DataForSEOConfigError(
                    f"DataForSEO authentication failed (401). Check DATAFORSEO_LOGIN "
                    f"and DATAFORSEO_PASSWORD. Response: {body_text[:200]}"
                ) from e
            elif e.code == 429:
                raise DataForSEORateLimitError(
                    "DataForSEO rate limit hit (429). Wait before retrying."
                ) from e
            else:
                raise DataForSEOError(
                    f"DataForSEO HTTP {e.code}: {body_text[:300]}"
                ) from e

    def _extract_task(self, resp: dict, require_result: bool = True) -> dict:
        """Extract the first task from a DataForSEO response.
        
        Returns dict with:
            status_code, status_message, cost, result (list or None)
        """
        tasks = resp.get('tasks', [])
        if not tasks:
            raise DataForSEOError("No tasks in DataForSEO response")
        task = tasks[0]
        code = task.get('status_code', -1)
        if code != 20000:
            raise DataForSEOError(
                f"DataForSEO task failed: {code} {task.get('status_message', '')}"
            )
        result = task.get('result')
        if require_result and not result:
            raise DataForSEOError("No result in DataForSEO task response")
        return {
            'status_code': code,
            'status_message': task.get('status_message', ''),
            'cost': task.get('cost', 0),
            'result': result or [],
        }

    def _get_result0(self, resp: dict) -> dict:
        """Extract the first item of the first result array."""
        task = self._extract_task(resp)
        results = task['result']
        if not results:
            raise DataForSEOError("Empty result array in DataForSEO response")
        return results[0]

    def _get_items(self, resp: dict) -> list:
        """Extract items from the first result."""
        r0 = self._get_result0(resp)
        return r0.get('items', [])


# ===================== SERP (Organic Search) =====================

def search_google_organic(
    keyword: str,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    language_name: str = 'English',
    language_code: str = 'en',
    depth: int = 10,
    client: Optional[DataForSEOClient] = None,
) -> dict:
    """Run a live Google organic SERP search.

    Returns:
        {
            'items': [{'type', 'position', 'domain', 'title', 'url', 'snippet'}],
            'cost': float,
            'keyword': str,
            'total_results': int,
            'check_url': str,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'keyword': keyword,
        'language_name': language_name,
        'depth': depth,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code
    if language_code:
        task['language_code'] = language_code

    resp = c._call('/v3/serp/google/organic/live/regular', [task])
    r0 = c._get_result0(resp)
    raw_items = r0.get('items', [])

    items = []
    for raw in raw_items:
        if raw.get('type') == 'organic':
            items.append({
                'type': 'organic',
                'position': raw.get('rank_absolute'),
                'domain': raw.get('domain', ''),
                'title': raw.get('title', ''),
                'url': raw.get('url', ''),
                'snippet': raw.get('description', ''),
            })

    task_info = resp.get('tasks', [{}])[0]
    return {
        'items': items,
        'cost': task_info.get('cost', 0),
        'keyword': keyword,
        'total_results': r0.get('se_results_count', 0),
        'check_url': r0.get('check_url', ''),
    }


def search_google_organic_advanced(
    keyword: str,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    depth: int = 10,
    client: Optional[DataForSEOClient] = None,
) -> dict:
    """Run a Google organic SERP search with full SERP features.

    Returns items including featured_snippet, local_pack, knowledge_graph,
    people_also_ask, top_stories, etc.

    Returns:
        {
            'items': [{'type', 'position', ...}],
            'serp_features': [{'type', ...}],  # non-organic results
            'cost': float,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'keyword': keyword,
        'language_name': 'English',
        'depth': depth,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code

    resp = c._call('/v3/serp/google/organic/live/advanced', [task])
    r0 = c._get_result0(resp)
    raw_items = r0.get('items', [])

    organic = []
    serp_features = []
    for raw in raw_items:
        entry = {
            'type': raw.get('type'),
            'position': raw.get('rank_absolute'),
            'domain': raw.get('domain', ''),
            'title': raw.get('title', ''),
            'url': raw.get('url', ''),
            'snippet': raw.get('description', ''),
        }
        if raw.get('type') == 'organic':
            organic.append(entry)
        else:
            serp_features.append(entry)

    task_info = resp.get('tasks', [{}])[0]
    return {
        'items': organic,
        'serp_features': serp_features,
        'cost': task_info.get('cost', 0),
        'keyword': keyword,
        'total_results': r0.get('se_results_count', 0),
    }


def lookup_rank_for_domain(
    keyword: str,
    domain: str,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    client: Optional[DataForSEOClient] = None,
) -> dict:
    """Look up where a specific domain ranks for a keyword.

    Returns:
        {
            'keyword': str,
            'found': bool,
            'position': int | None,
            'url': str | None,
            'title': str | None,
            'cost': float,
        }
    """
    result = search_google_organic(
        keyword=keyword,
        location_name=location_name,
        location_code=location_code,
        depth=100,
        client=client,
    )
    target = domain.lower().replace('www.', '')
    hit = None
    for item in result['items']:
        try:
            from urllib.parse import urlparse
            hostname = urlparse(item['url']).hostname or ''
            if hostname.lower().replace('www.', '') == target:
                hit = item
                break
        except Exception:
            continue

    return {
        'keyword': keyword,
        'found': hit is not None,
        'position': hit['position'] if hit else None,
        'url': hit['url'] if hit else None,
        'title': hit['title'] if hit else None,
        'cost': result['cost'],
    }


# ===================== Keyword Research =====================

def get_keyword_volume(
    keywords: list,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    language_name: str = 'English',
    language_code: str = 'en',
    client: Optional[DataForSEOClient] = None,
) -> list:
    """Get search volume, CPC, and competition for up to 1000 keywords.

    Returns list of:
        {
            'keyword': str,
            'search_volume': int | None,
            'cpc': float | None,
            'competition': float | None,  # 0.0 — 1.0
            'monthly_searches': [...] | None,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'keywords': keywords,
        'language_name': language_name,
        'language_code': language_code,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code

    resp = c._call('/v3/keywords_data/google_ads/search_volume/live', [task])
    r0 = c._get_result0(resp)
    kw_data = r0.get('keywords', [])

    results = []
    for kw in kw_data:
        results.append({
            'keyword': kw.get('keyword', ''),
            'search_volume': kw.get('search_volume'),
            'cpc': kw.get('cpc'),
            'competition': kw.get('competition'),
            'monthly_searches': kw.get('monthly_searches'),
        })
    return results


def get_keyword_ideas(
    seed_keywords: list,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    language_name: str = 'English',
    language_code: str = 'en',
    limit: int = 20,
    client: Optional[DataForSEOClient] = None,
) -> list:
    """Get related keyword ideas from seed keywords.

    Returns list of:
        {
            'keyword': str,
            'search_volume': int | None,
            'cpc': float | None,
            'competition': float | None,
            'difficulty': int | None,  # 0-100
        }
    """
    c = client or DataForSEOClient()
    task = {
        'keywords': seed_keywords,
        'language_name': language_name,
        'language_code': language_code,
        'limit': limit,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code

    resp = c._call('/v3/dataforseo_labs/google/keyword_ideas/live', [task])
    items = c._get_items(resp)

    results = []
    for item in items:
        k_info = item.get('keyword_info', {})
        k_props = item.get('keyword_properties', {})
        results.append({
            'keyword': item.get('keyword', ''),
            'search_volume': k_info.get('search_volume'),
            'cpc': k_info.get('cpc'),
            'competition': k_info.get('competition'),
            'difficulty': k_props.get('keyword_difficulty'),
        })
    return results


def get_keyword_difficulty(
    keywords: list,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    language_name: str = 'English',
    language_code: str = 'en',
    client: Optional[DataForSEOClient] = None,
) -> list:
    """Get keyword difficulty scores (0-100) for a list of keywords.

    Higher = harder to rank for.
    0-29 = Easy, 30-59 = Medium, 60-79 = Hard, 80-100 = Very Hard.

    Returns list of:
        {'keyword': str, 'difficulty': int | None}
    """
    c = client or DataForSEOClient()
    task = {
        'keywords': keywords,
        'language_name': language_name,
        'language_code': language_code,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code

    resp = c._call('/v3/dataforseo_labs/google/bulk_keyword_difficulty/live', [task])
    items = c._get_items(resp)

    results = []
    for item in items:
        results.append({
            'keyword': item.get('keyword', ''),
            'difficulty': item.get('keyword_difficulty'),
        })
    return results


def get_related_keywords(
    keyword: str,
    location_name: Optional[str] = None,
    location_code: Optional[int] = None,
    language_name: str = 'English',
    language_code: str = 'en',
    depth: int = 2,
    limit: int = 20,
    client: Optional[DataForSEOClient] = None,
) -> list:
    """Get related keywords (\"People also search for\").

    Returns list of:
        {
            'keyword': str,
            'search_volume': int | None,
            'cpc': float | None,
            'competition': float | None,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'keyword': keyword,
        'language_name': language_name,
        'language_code': language_code,
        'depth': depth,
        'limit': limit,
    }
    if location_name:
        task['location_name'] = location_name
    if location_code:
        task['location_code'] = location_code

    resp = c._call('/v3/dataforseo_labs/google/related_keywords/live', [task])
    items = c._get_items(resp)

    results = []
    for item in items:
        kw_data = item.get('keyword_data', {}) or {}
        k_info = kw_data.get('keyword_info', {})
        results.append({
            'keyword': kw_data.get('keyword', item.get('keyword', '')),
            'search_volume': k_info.get('search_volume'),
            'cpc': k_info.get('cpc'),
            'competition': k_info.get('competition'),
        })
    return results


# ===================== Backlinks =====================

def get_backlink_summary(
    target: str,
    mode: str = 'domain',
    client: Optional[DataForSEOClient] = None,
) -> dict:
    """Get a summary stats card for a target domain.

    Returns:
        {
            'target': str,
            'backlinks': int,
            'dofollow': int,
            'nofollow': int,
            'referring_domains': int,
            'referring_domains_nofollow': int,
            'broken_backlinks': int,
            'broken_pages': int,
            'rank': int,
            'first_seen': str | None,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'target': target,
        'mode': mode,
    }
    resp = c._call('/v3/backlinks/summary/live', [task])
    r0 = c._get_result0(resp)

    return {
        'target': r0.get('target', target),
        'backlinks': r0.get('backlinks', 0),
        'dofollow': r0.get('dofollow', 0),
        'nofollow': r0.get('nofollow', 0),
        'referring_domains': r0.get('referring_domains', 0),
        'referring_domains_nofollow': r0.get('referring_domains_nofollow', 0),
        'broken_backlinks': r0.get('broken_backlinks', 0),
        'broken_pages': r0.get('broken_pages', 0),
        'rank': r0.get('rank', 0),
        'first_seen': r0.get('first_seen'),
        'lost_date': r0.get('lost_date'),
    }


def get_backlinks(
    target: str,
    mode: str = 'domain',
    limit: int = 100,
    offset: int = 0,
    client: Optional[DataForSEOClient] = None,
) -> dict:
    """Fetch individual backlinks for a target domain.

    Returns:
        {
            'items': [{'domain_from', 'url_from', 'url_to', 'anchor', ...}],
            'total_count': int,
            'cost': float,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'target': target,
        'mode': mode,
        'limit': limit,
        'offset': offset,
    }
    resp = c._call('/v3/backlinks/backlinks/live', [task])
    r0 = c._get_result0(resp)
    raw_items = r0.get('items', [])
    cost = resp.get('tasks', [{}])[0].get('cost', 0)

    items = []
    for raw in raw_items:
        items.append({
            'domain_from': raw.get('domain_from', ''),
            'url_from': raw.get('url_from', ''),
            'url_to': raw.get('url_to', ''),
            'anchor': raw.get('anchor', ''),
            'dofollow': raw.get('dofollow', False),
            'spam_score': raw.get('backlink_spam_score', 0),
            'first_seen': raw.get('first_seen'),
            'last_seen': raw.get('last_seen'),
        })

    return {
        'items': items,
        'total_count': r0.get('total_count', 0),
        'cost': cost,
    }


def get_referring_domains(
    target: str,
    mode: str = 'domain',
    limit: int = 100,
    offset: int = 0,
    client: Optional[DataForSEOClient] = None,
) -> list:
    """Fetch referring domains that link to the target.

    Returns list of:
        {
            'domain': str,
            'backlinks_count': int,
            'dofollow': int,
            'nofollow': int,
            'first_seen': str | None,
            'rank': int,
        }
    """
    c = client or DataForSEOClient()
    task = {
        'target': target,
        'mode': mode,
        'limit': limit,
        'offset': offset,
    }
    resp = c._call('/v3/backlinks/referring_domains/live', [task])
    items = c._get_items(resp)

    results = []
    for item in items:
        results.append({
            'domain': item.get('domain', ''),
            'backlinks_count': item.get('backlinks_count', 0),
            'dofollow': item.get('dofollow', 0),
            'nofollow': item.get('nofollow', 0),
            'first_seen': item.get('first_seen'),
            'rank': item.get('rank', 0),
        })
    return results
