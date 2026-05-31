"""
SEO Dashboard — YAML Configuration Loader

Loads settings from config/config.yaml (or config.example.yaml as fallback).
"""

from __future__ import annotations

import os
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


_CONFIG_CACHE: dict[str, Any] | None = None


def find_config() -> str | None:
    """Locate the config file, checking for config.yaml first."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "config", "config.yaml"),
        os.path.join(base_dir, "config", "config.example.yaml"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def load_config(force_reload: bool = False) -> dict[str, Any]:
    """Load configuration from YAML file."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config_path = find_config()
    if config_path is None:
        _CONFIG_CACHE = _default_config()
        return _CONFIG_CACHE

    try:
        if yaml is None:
            raise ImportError("PyYAML is not installed")
        with open(config_path, "r", encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f) or {}
        return _CONFIG_CACHE
    except Exception:
        _CONFIG_CACHE = _default_config()
        return _CONFIG_CACHE


def _default_config() -> dict[str, Any]:
    return {
        "database": {"path": "data/seo_dashboard.db"},
        "gsc": {
            "enabled": False,
            "service_account_file": "",
            "site_urls": ["sc-domain:giantbubbles.co.nz", "sc-domain:giantbubblesau.com"],
        },
        "dashboard": {
            "title": "Tinka SEO Dashboard",
            "refresh_interval_seconds": 3600,
            "default_days": 30,
        },
    }
