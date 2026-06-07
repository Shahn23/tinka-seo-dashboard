"""Tests for the DataForSEO Python client (TDD: RED phase first)."""

import json
from unittest.mock import patch, MagicMock
import pytest

# The module doesn't exist yet — this test will fail on import (RED)
from scripts.dataforseo_client import (
    DataForSEOClient,
    DataForSEOError,
    DataForSEOConfigError,
    DataForSEORateLimitError,
    search_google_organic,
    get_keyword_volume,
    get_keyword_ideas,
    get_keyword_difficulty,
    get_related_keywords,
    lookup_rank_for_domain,
    get_backlink_summary,
    get_backlinks,
    get_referring_domains,
)


# ===================== FIXTURES =====================

@pytest.fixture
def mock_serp_response():
    """Standard SERP response from DataForSEO."""
    return {
        "version": "0.1.20260525",
        "status_code": 20000,
        "status_message": "Ok.",
        "time": "1720000000",
        "cost": 0.0020,
        "tasks": [
            {
                "id": "12345",
                "status_code": 20000,
                "status_message": "Ok.",
                "time": "1720000000",
                "cost": 0.0020,
                "result": [
                    {
                        "keyword": "giant bubbles",
                        "type": "organic",
                        "se_domain": "google.co.nz",
                        "location_code": 2076,
                        "language_code": "en",
                        "check_url": "https://google.co.nz/search?q=giant+bubbles",
                        "datetime": "2026-06-08 10:00:00 +12:00",
                        "se_results_count": 1420000,
                        "items": [
                            {
                                "type": "organic",
                                "rank_group": 1,
                                "rank_absolute": 1,
                                "domain": "giantbubbles.co.nz",
                                "title": "Giant Bubbles NZ",
                                "url": "https://giantbubbles.co.nz/",
                                "description": "The biggest bubbles in NZ"
                            },
                            {
                                "type": "organic",
                                "rank_group": 2,
                                "rank_absolute": 2,
                                "domain": "example.com",
                                "title": "Bubble Shop",
                                "url": "https://example.com/bubbles",
                                "description": "All kinds of bubbles"
                            },
                            {
                                "type": "organic",
                                "rank_group": 3,
                                "rank_absolute": 3,
                                "domain": "bigbubbles.co.nz",
                                "title": "Big Bubbles",
                                "url": "https://bigbubbles.co.nz/",
                                "description": "Big bubble kits"
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_search_volume_response():
    """Keyword volume response."""
    return {
        "tasks": [
            {
                "status_code": 20000,
                "cost": 0.0018,
                "result": [
                    {
                        "keywords": [
                            {
                                "keyword": "giant bubbles",
                                "search_volume": 3200,
                                "cpc": 1.25,
                                "competition": 0.45
                            },
                            {
                                "keyword": "bubble machine",
                                "search_volume": 8900,
                                "cpc": 0.95,
                                "competition": 0.62
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_keyword_difficulty_response():
    """Keyword difficulty response."""
    return {
        "tasks": [
            {
                "status_code": 20000,
                "cost": 0.0020,
                "result": [
                    {
                        "items": [
                            {
                                "keyword": "giant bubbles",
                                "keyword_difficulty": 34
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_backlink_summary_response():
    """Backlink summary response."""
    return {
        "tasks": [
            {
                "status_code": 20000,
                "cost": 0.0020,
                "result": [
                    {
                        "target": "giantbubbles.co.nz",
                        "backlinks": 142,
                        "dofollow": 98,
                        "nofollow": 44,
                        "referring_domains": 12,
                        "referring_domains_nofollow": 3,
                        "broken_backlinks": 5,
                        "broken_pages": 2,
                        "rank": 42,
                        "first_seen": "2024-03-15 10:00:00 +00:00"
                    }
                ]
            }
        ]
    }


# ===================== HELPERS =====================

def _setup_env_and_mock(response_data=None):
    """Set env vars and mock urllib.request.urlopen. Returns the mock."""
    import urllib.request
    patcher_env = patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True)
    patcher_env.start()
    patcher_urlopen = patch.object(urllib.request, 'urlopen')
    mock_urlopen = patcher_urlopen.start()

    if response_data is not None:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data)
        mock_urlopen.return_value.__enter__.return_value = mock_resp

    def _cleanup():
        patcher_urlopen.stop()
        patcher_env.stop()

    # Register for pytest cleanup
    import atexit
    atexit.register(_cleanup)
    return mock_urlopen


# ===================== CLIENT INIT TESTS =====================

class TestClientInitialization:
    """Tests for initializing the DataForSEO client."""

    def test_client_requires_env_var(self):
        """Client should raise ConfigError if env vars are missing."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(DataForSEOConfigError, match="DATAFORSEO_LOGIN"):
                DataForSEOClient()

    def test_client_requires_both_vars(self):
        """Client should require both LOGIN and PASSWORD."""
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'test@test.com'}, clear=True):
            with pytest.raises(DataForSEOConfigError, match="DATAFORSEO_PASSWORD"):
                DataForSEOClient()

    def test_client_init_with_env(self):
        """Client should initialize when both env vars are set."""
        with patch.dict('os.environ', {
            'DATAFORSEO_LOGIN': 'test@test.com',
            'DATAFORSEO_PASSWORD': 'testpass123'
        }, clear=True):
            client = DataForSEOClient()
            assert client.login == 'test@test.com'
            assert client.password == 'testpass123'

    def test_client_init_with_direct_args(self):
        """Should accept login/password as constructor args."""
        client = DataForSEOClient(login='user@test.com', password='sekret')
        assert client.login == 'user@test.com'
        assert client.password == 'sekret'


# ===================== AUTH TESTS =====================

class TestAuthentication:
    """Tests for authentication header generation."""

    def test_builds_basic_auth(self):
        """Should build proper Base64 Basic auth header."""
        client = DataForSEOClient(login='user@test.com', password='sekret')
        header = client._auth_header
        import base64
        decoded = base64.b64decode(header.replace('Basic ', '')).decode()
        assert decoded == 'user@test.com:sekret'

    def test_header_format(self):
        """Auth header should start with 'Basic '."""
        client = DataForSEOClient(login='x@y.com', password='pass')
        assert client._auth_header.startswith('Basic ')


# ===================== SERP TESTS =====================

class TestSearchGoogleOrganic:
    """Tests for search_google_organic."""

    def test_returns_organic_items(self, mock_serp_response):
        """Should return organic items from a SERP call."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_serp_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                result = search_google_organic(
                    keyword='giant bubbles',
                    location_name='New Zealand',
                    depth=10
                )

                assert len(result['items']) == 3
                assert result['items'][0]['domain'] == 'giantbubbles.co.nz'
                assert result['items'][0]['position'] == 1
                assert result['cost'] == 0.0020

    def test_filters_only_organic(self, mock_serp_response):
        """Should filter out non-organic results."""
        import urllib.request
        mock_serp_response['tasks'][0]['result'][0]['items'].append({
            "type": "ads",
            "rank_group": 1,
            "domain": "advertiser.com",
            "title": "Ad",
            "url": "https://advertiser.com/"
        })

        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_serp_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                result = search_google_organic(keyword='giant bubbles')
                for item in result['items']:
                    assert item['type'] == 'organic'

    def test_lookup_rank_for_domain(self, mock_serp_response):
        """lookup_rank_for_domain should find specific domain rank."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_serp_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                result = lookup_rank_for_domain(
                    keyword='giant bubbles',
                    domain='giantbubbles.co.nz',
                    location_name='New Zealand'
                )

                assert result['found'] is True
                assert result['position'] == 1
                assert result['url'] == 'https://giantbubbles.co.nz/'

    def test_lookup_rank_not_found(self, mock_serp_response):
        """Should return not found for absent domain."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_serp_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                result = lookup_rank_for_domain(
                    keyword='giant bubbles',
                    domain='nonexistent.co.nz',
                    location_name='New Zealand'
                )

                assert result['found'] is False
                assert result['position'] is None


# ===================== KEYWORD DATA TESTS =====================

class TestKeywordVolume:
    """Tests for get_keyword_volume."""

    def test_returns_keyword_volumes(self, mock_search_volume_response):
        """Should return volume data for each keyword."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_search_volume_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                results = get_keyword_volume(
                    keywords=['giant bubbles', 'bubble machine'],
                    location_name='Australia'
                )

                assert len(results) == 2
                assert results[0]['keyword'] == 'giant bubbles'
                assert results[0]['search_volume'] == 3200
                assert results[0]['cpc'] == 1.25
                assert results[1]['keyword'] == 'bubble machine'
                assert results[1]['search_volume'] == 8900


class TestKeywordDifficulty:
    """Tests for get_keyword_difficulty."""

    def test_returns_difficulty_scores(self, mock_keyword_difficulty_response):
        """Should return difficulty score 0-100 for each keyword."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_keyword_difficulty_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                results = get_keyword_difficulty(
                    keywords=['giant bubbles'],
                    location_name='New Zealand'
                )

                assert len(results) == 1
                assert results[0]['keyword'] == 'giant bubbles'
                assert results[0]['difficulty'] == 34


# ===================== BACKLINK TESTS =====================

class TestBacklinks:
    """Tests for backlink APIs."""

    def test_backlink_summary(self, mock_backlink_summary_response):
        """Should return backlink summary for a domain."""
        import urllib.request
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_backlink_summary_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                result = get_backlink_summary(target='giantbubbles.co.nz')

                assert result['backlinks'] == 142
                assert result['referring_domains'] == 12
                assert result['broken_backlinks'] == 5
                assert result['target'] == 'giantbubbles.co.nz'


# ===================== ERROR HANDLING TESTS =====================

class TestErrorHandling:
    """Tests for proper error handling."""

    def test_401_raises_config_error(self):
        """401 response should raise DataForSEOConfigError."""
        import urllib.request
        from urllib.error import HTTPError
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_urlopen.side_effect = HTTPError(
                    url='https://api.dataforseo.com/v3/serp/google/organic/live/regular',
                    code=401,
                    msg='Unauthorized',
                    hdrs={},
                    fp=None
                )

                with pytest.raises(DataForSEOConfigError, match="401|Unauthorized|authentication"):
                    search_google_organic(keyword='test')

    def test_429_raises_rate_limit_error(self):
        """429 response should raise DataForSEORateLimitError."""
        import urllib.request
        from urllib.error import HTTPError
        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_urlopen.side_effect = HTTPError(
                    url='https://api.dataforseo.com/v3/serp/google/organic/live/regular',
                    code=429,
                    msg='Too Many Requests',
                    hdrs={},
                    fp=None
                )

                with pytest.raises(DataForSEORateLimitError, match="429|rate limit"):
                    search_google_organic(keyword='test')

    def test_task_error_raises_generic_error(self, mock_serp_response):
        """Non-20000 task status should raise DataForSEOError."""
        import urllib.request
        mock_serp_response['tasks'][0]['status_code'] = 40000
        mock_serp_response['tasks'][0]['status_message'] = 'Some error occurred'

        with patch.dict('os.environ', {'DATAFORSEO_LOGIN': 'x', 'DATAFORSEO_PASSWORD': 'y'}, clear=True):
            with patch.object(urllib.request, 'urlopen') as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_serp_response).encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                with pytest.raises(DataForSEOError, match="40000"):
                    search_google_organic(keyword='test')
