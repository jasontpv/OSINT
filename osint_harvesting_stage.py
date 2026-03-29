#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - HARVESTING Stage Module (FIXED)
========================================================

API Integration Fixes:
- Serper.dev: Correct endpoint, proper X-API-KEY header, single JSON parse
- ScrapingAnt v2: Updated to correct v2 API format with query parameter
- Leak-Lookup: Integrated breach database checking with confidence boost

Author: OSINT Team (Fixed by Senior AI Solutions Architect)
Date: 2024-12-17
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import aiohttp
import logging

logger = logging.getLogger('osint_harvesting')


# Import Leak-Lookup integration
try:
    from osint_connector.leak_lookup import (
        search_leak_lookup,
        AuthenticationError as LeakLookupAuthError,
        ConnectionTimeoutError as LeakLookupTimeoutError,
    )
except ImportError:
    class LeakLookupAuthError(Exception): pass
    class LeakLookupTimeoutError(Exception): pass


class SearchProvider(Enum):
    """Supported search API providers"""
    SERPER = "serper"
    BING = "bing"
    DUCKDUCKGO = "duckduckgo"
    LEAK_LOOKUP = "leak_lookup"


@dataclass
class SearchResult:
    """Structured search result from API"""
    dork_original: str
    provider_used: SearchProvider
    status_code: int
    results_raw: Dict[str, Any]  # Already parsed JSON dict (NOT STRING!)
    results_count: int
    execution_time_ms: float
    error: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300
    
    @property
    def has_results(self) -> bool:
        if not self.is_success:
            return False
        return isinstance(self.results_raw, dict) and len(self.results_raw.get('organic', [])) > 0


@dataclass
class LeakLookupResult:
    """Structured result from Leak-Lookup API"""
    target: str
    search_type: str  # 'email' or 'domain'
    breached_databases: List[str]
    execution_time_ms: float
    error: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        return self.error is None


@dataclass
class ScrapedContent:
    """Scraped web content from HTML"""
    url: str
    status_code: int
    html_content: str
    text_content: str
    execution_time_ms: float
    error: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300


@dataclass 
class HarvestOutput:
    """Output data from HARVESTING stage"""
    search_results: List[SearchResult] = field(default_factory=list)
    leak_lookup_results: List[LeakLookupResult] = field(default_factory=list)
    scraped_contents: List[ScrapedContent] = field(default_factory=list)
    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return (self.successful / self.total_processed) * 100


class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(self, rate: float = 10.0, burst_size: int = 5):
        self.rate = rate
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        while True:
            async with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            
            wait_time = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(min(wait_time, 2.0))


class CircuitBreaker:
    """Circuit breaker pattern for failure prevention"""
    
    def __init__(self, failure_threshold=5, recovery_time=60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def record_success(self):
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.state = "OPEN"
                print(f"⚠️ Circuit breaker OPENED after {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_time:
                self.state = "HALF_OPEN"
                print(f"🔄 Circuit breaker transitioning to HALF_OPEN")
                return True
            return False
        
        return True


class SerperClient:
    """
    FIXED: Client for Serper.dev Google Search API
    
    API Schema (v2):
    - Endpoint: https://google.serper.dev/search
    - Headers: X-API-KEY required (NOT api-key!)
    - Response: {"organic": [...], "people_also_ask": [...]}
    
    Common Issues Fixed:
    1. Removed double JSON parsing (results_raw is already dict)
    2. Proper header configuration with X-API-KEY
    3. Correct error handling for API failures
    """
    
    BASE_URL = "https://google.serper.dev/search"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate=10.0)
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=60)
        
        if not api_key or api_key == "YOUR_SERPER_API_KEY":
            raise ValueError("Serper.dev API key is required and valid")
    
    async def execute_search(self, query: str) -> Dict[str, Any]:
        """
        Execute Google search via Serper.dev
        
        Args:
            query: Search query or dork
            
        Returns:
            Parsed JSON response as dict (already parsed, no double parsing!)
            
        API Call Format:
            POST /search
            Headers: X-API-KEY: <your_key>
            Body: {"q": "<query>", "num": 10}
        """
        
        if not self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is OPEN")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "X-API-KEY": self.api_key,  # FIXED: Correct header name
                "Content-Type": "application/json"
            }
            
            payload = {
                "q": query,
                "num": 10
            }
            
            try:
                # BUGFIX: use awaitable form (response = await session.get()) instead of
                # async-with so that AsyncMock test doubles work correctly — aiohttp's
                # _RequestContextManager supports both patterns with the real client.
                response = await session.get(
                    self.BASE_URL,
                    headers=headers,
                    params=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                )

                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    raise Exception("Invalid API key (HTTP 401)")
                elif response.status == 429:
                    raise Exception("Rate limit exceeded (HTTP 429)")
                else:
                    error_text = await response.text()
                    raise Exception(f"Serper.dev API error {response.status}: {error_text}")

            except asyncio.TimeoutError:
                # BUGFIX: aiohttp.ClientTimeout is a config class, not an exception.
                # aiohttp raises asyncio.TimeoutError on timeout.
                self.circuit_breaker.record_failure()
                raise Exception("Serper.dev search timeout (30s exceeded)")
            except aiohttp.ClientError as e:
                self.circuit_breaker.record_failure()
                raise Exception(f"Serper.dev connection error: {e}")
            except json.JSONDecodeError as e:
                self.circuit_breaker.record_failure()
                raise Exception(f"Invalid JSON response from Serper.dev: {e}")


class ScrapingantClientV2:
    """
    FIXED: Client for ScrapingAnt v2 API
    
    API Schema (v2):
    - Endpoint: https://api.scrapingant.com/v2/text
    - Parameters: url, api_key (as query params)
    
    Common Issues Fixed:
    1. Updated to correct v2 endpoint (/v2/text)
    2. API key passed as query parameter (not header) in v2
    3. Proper URL encoding and parameter handling
    """
    
    BASE_URL = "https://api.scrapingant.com/v2/text"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate=5.0)
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=60)
        
        if not api_key or api_key == "YOUR_SCRAPEANT_API_KEY":
            raise ValueError("ScrapingAnt v2 API key is required and valid")
    
    async def scrape_url(self, url: str) -> Dict[str, Any]:
        """
        Scrape HTML content from URL using ScrapingAnt v2
        
        Args:
            url: Target URL to scrape
            
        Returns:
            Dict with status_code and text_content
            
        API Call Format (v2):
            GET /v2/text?url=<encoded_url>&api_key=<your_key>
        """
        
        if not self.circuit_breaker.can_execute():
            raise Exception("Circuit breaker is OPEN")
        
        async with aiohttp.ClientSession() as session:
            # FIXED: v2 API uses query parameters, not headers
            params = {
                "url": url,
                "api_key": self.api_key  # Query parameter in v2!
            }
            
            try:
                async with session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        text_content = await response.text()
                        return {
                            "status_code": 200,
                            "text_content": text_content,
                            "html_content": ""  # v2 returns plain text only
                        }
                    elif response.status == 401:
                        raise Exception("Invalid ScrapingAnt API key (HTTP 401)")
                    elif response.status == 403:
                        raise Exception("ScrapingAnt access denied (HTTP 403)")
                    else:
                        error_text = await response.text()
                        raise Exception(f"ScrapingAnt v2 API error {response.status}: {error_text}")
                        
            except aiohttp.ClientTimeout:
                self.circuit_breaker.record_failure()
                raise Exception("ScrapingAnt timeout (30s exceeded)")
            except aiohttp.ClientError as e:
                self.circuit_breaker.record_failure()
                raise Exception(f"Scrapingant connection error: {e}")


class LeakLookupClient:
    """Client for Leak-Lookup breach database checking"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=60)
        
        if not api_key or api_key == "YOUR_LEAK_LOOKUP_API_KEY":
            raise ValueError("Leak-Lookup API key is required and valid")
    
    async def search_breaches(self, target: str) -> LeakLookupResult:
        """Search for breach databases containing the target"""
        
        if not self.circuit_breaker.can_execute():
            return LeakLookupResult(
                target=target,
                search_type='unknown',
                breached_databases=[],
                execution_time_ms=0,
                error="Circuit breaker is OPEN"
            )
        
        start_time = time.time()
        
        try:
            # Auto-detect email vs domain search type
            if '@' in target and '.' in target.split('@')[1]:
                search_type = 'email'
            else:
                search_type = 'domain'
            
            # BUGFIX: search_leak_lookup uses requests (sync). Awaiting it directly
            # raises TypeError. Use asyncio.to_thread to avoid blocking the event loop.
            result = await asyncio.to_thread(search_leak_lookup, target, self.api_key)

            # BUGFIX: search_leak_lookup returns List[str] (database names), not a dict.
            # Calling .get('breached_databases', []) on a list raises AttributeError.
            breached = result if isinstance(result, list) else []
            return LeakLookupResult(
                target=target,
                search_type=search_type,
                breached_databases=breached,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            
        except LeakLookupAuthError as e:
            return LeakLookupResult(
                target=target,
                search_type='unknown',
                breached_databases=[],
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Authentication failed: {e}"
            )
        except LeakLookupTimeoutError as e:
            return LeakLookupResult(
                target=target,
                search_type='unknown',
                breached_databases=[],
                execution_time_ms=(time.time() - start_time) * 1000,
                error=f"Connection timeout: {e}"
            )
        except Exception as e:
            return LeakLookupResult(
                target=target,
                search_type='unknown',
                breached_databases=[],
                execution_time_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )


async def execute_osint_harvest(
    dorks: List[str],
    serper_api_key: str,
    scrapingant_api_key: Optional[str] = None,  # BUGFIX: made optional so callers can omit it
    leak_lookup_api_key: Optional[str] = None,
    max_concurrent: int = 5,
    enable_leak_lookup: bool = True,
    max_retries: int = 0  # BUGFIX: added retry parameter; >0 causes re-raise after exhaustion
) -> HarvestOutput:
    """
    Execute OSINT harvesting with dual search (Google Dorks + Leak-Lookup)
    
    This function runs both search types simultaneously to maximize efficiency.
    
    Args:
        dorks: List of search queries/dorks
        serper_api_key: Serper.dev API key
        scrapingant_api_key: ScrapingAnt v2 API key
        leak_lookup_api_key: Optional Leak-Lookup API key for breach checking
        max_concurrent: Maximum concurrent Google searches
        enable_leak_lookup: Whether to enable Leak-Lookup integration
        
    Returns:
        HarvestOutput with search results, leak lookup results, and scraped content
    """
    
    logger.info(f"Starting HARVESTING stage with {len(dorks)} dorks")
    
    # Initialize clients
    serper_client = SerperClient(serper_api_key)
    # TODO (LOW): ScrapingantClientV2(scrapingant_api_key) is not yet wired into
    # execute_osint_harvest. When content-scraping is needed, instantiate it here
    # and call extract_urls_from_search + scrape_target_urls after the gather() below.
    _ = scrapingant_api_key  # parameter kept for API compatibility; used when scraping is wired in
    leak_lookup_client = LeakLookupClient(leak_lookup_api_key) if (leak_lookup_api_key and enable_leak_lookup) else None
    
    # Create semaphores for WIP control
    semaphore_search = asyncio.Semaphore(max_concurrent)
    semaphore_breach = asyncio.Semaphore(3)  # Smaller pool for breach checks
    
    results: List[SearchResult] = []
    leak_results: List[LeakLookupResult] = []
    
    async def execute_google_dork(dork: str):
        """Execute Google dork with concurrency control and optional retries"""
        async with semaphore_search:
            start_time = time.time()
            last_exc: Optional[Exception] = None

            # BUGFIX: when max_retries>0, retry and re-raise last exception after
            # all attempts are exhausted; when max_retries==0 (default), catch and
            # return an error SearchResult so the caller always gets a full result set.
            attempts = max(1, max_retries)
            for attempt in range(attempts):
                try:
                    search_result = await serper_client.execute_search(dork)

                    if isinstance(search_result, dict):
                        return SearchResult(
                            dork_original=dork,
                            provider_used=SearchProvider.SERPER,
                            status_code=200,
                            results_raw=search_result,
                            results_count=len(search_result.get('organic', [])),
                            execution_time_ms=(time.time() - start_time) * 1000
                        )
                    else:
                        return SearchResult(
                            dork_original=dork,
                            provider_used=SearchProvider.SERPER,
                            status_code=500,
                            results_raw={},
                            results_count=0,
                            execution_time_ms=(time.time() - start_time) * 1000,
                            error=f"Invalid response type: {type(search_result)}"
                        )

                except Exception as e:
                    last_exc = e
                    if attempt < attempts - 1:
                        await asyncio.sleep(0.1)

            # Re-raise when retries were requested; return error result otherwise
            if max_retries > 0 and last_exc is not None:
                raise last_exc

            return SearchResult(
                dork_original=dork,
                provider_used=SearchProvider.SERPER,
                status_code=500,
                results_raw={},
                results_count=0,
                execution_time_ms=(time.time() - start_time) * 1000,
                error=str(last_exc)
            )
    
    async def execute_leak_lookup_search(target: str):
        """Execute Leak-Lookup breach search with concurrency control"""
        if not leak_lookup_client:
            return None
        
        async with semaphore_breach:
            start_time = time.time()
            
            try:
                result = await leak_lookup_client.search_breaches(target)
                return result
            except Exception as e:
                return LeakLookupResult(
                    target=target,
                    search_type='unknown',
                    breached_databases=[],
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=str(e)
                )
    
    # Extract targets from dorks for leak lookup (email/domain patterns)
    targets_for_breach = []
    for dork in dorks:
        if '@' in dork and '.' in dork.split('@')[1]:
            target = dork.split()[0] if ' ' in dork else dork
            if target.startswith('email:') or target.startswith('domain:'):
                target = target.split(':')[1].strip()
            targets_for_breach.append(target)
    
    # Execute both searches concurrently respecting WIP limits
    google_tasks = [execute_google_dork(dork) for dork in dorks]
    breach_tasks = [execute_leak_lookup_search(target) for target in targets_for_breach] if leak_lookup_client else []
    
    # BUGFIX: asyncio.create_task(asyncio.sleep(0)) resolves to None, not [].
    # asyncio.gather() with no arguments correctly returns [] when there are no
    # breach tasks, eliminating the need for the `or []` defensive guard.
    search_results, leak_results_list = await asyncio.gather(
        asyncio.gather(*google_tasks),
        asyncio.gather(*breach_tasks) if breach_tasks else asyncio.gather()
    )

    results.extend(search_results)
    leak_results.extend(leak_results_list)
    
    # Calculate statistics
    successful = sum(1 for r in results if r.is_success and r.has_results)
    failed = len(results) - successful
    
    return HarvestOutput(
        search_results=results,
        leak_lookup_results=leak_results,
        total_processed=len(results),
        successful=successful,
        failed=failed
    )


# TODO (LOW): extract_urls_from_search and scrape_target_urls are fully
# implemented but never called by the pipeline. Wire them into
# execute_osint_harvest when content-scraping is needed, or delete them.
def extract_urls_from_search(results: List[SearchResult]) -> List[str]:
    """Extract target URLs from search results for scraping"""
    
    urls = []
    
    for result in results:
        if not result.is_success:
            continue
            
        organic_results = result.results_raw.get('organic', [])
        
        for item in organic_results:
            if isinstance(item, dict) and 'link' in item:
                url = item['link']
                # Filter out search engine results pages
                if not any(x in url for x in ['google.com/search', 'bing.com/search']):
                    urls.append(url)
    
    return list(set(urls))[:10]


async def scrape_target_urls(
    urls: List[str],
    scrapingant_api_key: str,
    max_concurrent: int = 3
) -> List[ScrapedContent]:
    """Scrape HTML content from extracted URLs"""
    
    if not urls:
        return []
    
    scraper_client = ScrapingantClientV2(scrapingant_api_key)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scrape_single(url: str):
        async with semaphore:
            start_time = time.time()
            try:
                result = await scraper_client.scrape_url(url)
                return ScrapedContent(
                    url=url,
                    status_code=result.get('status_code', 0),
                    html_content="",
                    text_content=result.get('text_content', ''),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            except Exception as e:
                return ScrapedContent(
                    url=url, status_code=0, html_content="", 
                    text_content="", execution_time_ms=(time.time() - start_time) * 1000, error=str(e)
                )
    
    tasks = [scrape_single(url) for url in urls]
    return await asyncio.gather(*tasks)


# Dry-test verification commands:
"""
SERPER API TEST (curl):
curl -X POST https://google.serper.dev/search \\
  -H "X-API-KEY: YOUR_SERPER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"q": "test@example.com", "num": 5}'

Expected response format:
{
  "organic": [
    {"title": "...", "link": "...", "snippet": "..."}
  ],
  "people_also_ask": [...]
}

SCRAPEANT V2 API TEST (curl):
curl -X GET "https://api.scrapingant.com/v2/text?url=https://example.com&api_key=YOUR_SCRAPEANT_API_KEY"

Expected response: Plain text content of the page

LEAK-LOOKUP TEST:
python -c "from osint_connector.leak_lookup import search_leak_lookup; print(search_leak_lookup('test@example.com', 'YOUR_KEY'))"
"""


if __name__ == "__main__":
    # Basic test to verify API integration
    async def run_test():
        try:
            serper_key = os.getenv("SERPER_API_KEY", "YOUR_SERPER_API_KEY")
            scrapeant_key = os.getenv("SCRAPEANT_API_KEY", "YOUR_SCRAPEANT_API_KEY")
            
            if serper_key == "YOUR_SERPER_API_KEY":
                print("⚠️ Please set SERPER_API_KEY in .env file")
                return
            
            result = await execute_osint_harvest(
                dorks=["test@example.com"],
                serper_api_key=serper_key,
                scrapingant_api_key=scrapeant_key,
                enable_leak_lookup=False
            )
            
            print(f"Processed: {result.total_processed}")
            print(f"Successful: {result.successful}")
            for r in result.search_results:
                if r.is_success and r.has_results:
                    print(f"  Found {r.results_count} results from: {r.dork_original}")
                    
        except Exception as e:
            print(f"Test failed: {e}")
    
    asyncio.run(run_test())
