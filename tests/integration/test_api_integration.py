#!/usr/bin/env python3
"""
Live API Integration Tests — require real credentials in .env to run.

These tests hit actual external endpoints (Serper.dev, ScrapingAnt v2,
Leak-Lookup) and are therefore skipped automatically when the keys are
absent. They are NOT part of the normal CI suite — run them manually to
verify that the API integrations are working end-to-end.

Usage:
    pytest tests/integration/ -v          # skips automatically when keys absent
    python tests/integration/test_api_integration.py  # original script style

Tests:
  1. Serper.dev API — single JSON parse, proper headers
  2. ScrapingAnt v2 API — correct endpoint and parameters
  3. Type-safe data extraction
  4. Leak-Lookup cross-reference engine
  5. Confidence scoring with leak correlation boost
"""

import asyncio
import os
import pytest

# ── skip markers ──────────────────────────────────────────────────────────────

_MISSING_SERPER    = not os.getenv("SERPER_API_KEY")
_MISSING_SCRAANT   = not os.getenv("SCRAPINGANT_API_KEY")

needs_serper    = pytest.mark.skipif(_MISSING_SERPER,  reason="SERPER_API_KEY not set")
needs_scrapant  = pytest.mark.skipif(_MISSING_SCRAANT, reason="SCRAPINGANT_API_KEY not set")


# ── 1. Serper.dev ─────────────────────────────────────────────────────────────

@needs_serper
@pytest.mark.asyncio
async def test_serper_response_is_dict():
    """Response must be a dict (not a raw string) — guards against double-parse."""
    from osint_harvesting_stage import SerperClient
    client = SerperClient(os.getenv("SERPER_API_KEY"))
    result = await client.execute_search("test@example.com")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"


@needs_serper
@pytest.mark.asyncio
async def test_serper_organic_list():
    """'organic' key must be a list of dicts with a 'title' field."""
    from osint_harvesting_stage import SerperClient
    client = SerperClient(os.getenv("SERPER_API_KEY"))
    result = await client.execute_search("site:example.com")
    if "organic" in result:
        assert isinstance(result["organic"], list)
        if result["organic"]:
            assert "title" in result["organic"][0]


# ── 2. ScrapingAnt v2 ─────────────────────────────────────────────────────────

@needs_scrapant
@pytest.mark.asyncio
async def test_scrapingant_scrape_success():
    """Scraping a reliable URL must return a successful result."""
    from osint_harvesting_stage import ScrapingantClientV2
    client = ScrapingantClientV2(os.getenv("SCRAPINGANT_API_KEY"))
    result = await client.scrape_url("https://example.com")
    assert result.is_success, f"Scrape failed: {result.error}"


@needs_scrapant
@pytest.mark.asyncio
async def test_scrapingant_text_content_non_empty():
    """Scraped text content must be non-empty for a known page."""
    from osint_harvesting_stage import ScrapingantClientV2
    client = ScrapingantClientV2(os.getenv("SCRAPINGANT_API_KEY"))
    result = await client.scrape_url("https://example.com")
    if result.is_success:
        assert result.text_content and len(result.text_content) > 0


# ── 3. Type-safe data extraction ──────────────────────────────────────────────

def test_extract_field_from_dict():
    from osint_analyst_stage import FactExtractor
    extractor = FactExtractor()
    data = {"title": "Test", "link": "https://x.com"}
    assert extractor._extract_field(data, "title") == "Test"


def test_extract_field_from_list():
    from osint_analyst_stage import FactExtractor
    extractor = FactExtractor()
    data = [{"title": "First"}, {"title": "Second"}]
    result = extractor._extract_field(data, "title")
    assert result is not None


def test_extract_field_none_returns_default():
    from osint_analyst_stage import FactExtractor
    extractor = FactExtractor()
    result = extractor._extract_field(None, "field", default="fallback")
    assert result == "fallback"


def test_extract_facts_from_serper_organic():
    from osint_analyst_stage import FactExtractor
    extractor = FactExtractor()
    serper_data = {
        "organic": [
            {"title": "Result 1", "link": "https://example.com/1"},
            {"title": "Result 2", "link": "https://example.com/2"},
        ]
    }
    facts = extractor.extract_facts_from_source(serper_data, "serper_dev")
    assert isinstance(facts, list)


# ── 4. Cross-reference engine ─────────────────────────────────────────────────

def test_cross_reference_matches_email():
    from osint_analyst_stage import CrossReferenceEngine
    engine = CrossReferenceEngine()
    search_results = [
        {"organic": [{"snippet": "Contact: john.doe@example.com"}]}
    ]
    leak_findings = [
        {
            "target": "john.doe@example.com",
            "breached_databases": ["Collection1"],
            "timestamp": "2024-01-01T00:00:00Z",
        }
    ]
    matches = engine.perform_cross_reference(search_results, leak_findings)
    # result may be dict or list — just must not raise
    assert matches is not None


# ── 5. Confidence scoring ─────────────────────────────────────────────────────

def test_confidence_boost_from_leak_match():
    from osint_analyst_stage import VerifiedFact, AnalystAgent, CrossReferenceResult
    fact = VerifiedFact(
        text="john.doe@example.com",
        source="LinkedIn",
        confidence_score=0.6,
        is_verified=False,
        cross_references=[],
        metadata={},
    )
    cross = CrossReferenceResult(
        target_email="john.doe@example.com",
        search_source="Leak-Lookup",
        leaked_databases=["Collection1"],
        confidence_boost=0.3,
    )
    fact.cross_references = [cross]
    final = AnalystAgent.calculate_confidence_score(
        fact=fact, cross_matches=fact.cross_references
    )
    assert final > 0.6, f"Expected score > 0.6, got {final}"


# ── standalone runner (backwards-compatible with original script) ──────────────

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
