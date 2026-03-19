"""
OSINT Kanban Pipeline - HARVESTING Stage Module
================================================
Executes search queries and scrapes web content with rate limiting.
Uses Serper.dev for Google searches, Scrapingant.com for HTML scraping,
and Leak-Lookup.com for breach database verification.

Author: Senior AI Solutions Architect
Date: 2024-12-17
"""

import asyncio
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import aiohttp
import http.client


# Import Leak-Lookup integration
try:
    from osint_connector.leak_lookup import (
        search_leak_lookup,
        AuthenticationError as LeakLookupAuthError,
        ConnectionTimeoutError as LeakLookupTimeoutError,
        RateLimitError as LeakLookupRateLimitError
    )
except ImportError:
    # Fallback if module not yet created
    class LeakLookupAuthError(Exception): pass
    class LeakLookupTimeoutError(Exception): pass
    class LeakLookupRateLimitError(Exception): pass


class SearchProvider(Enum):
    """Supported search API providers"""
    SERPER = "serper"
    BING = "bing"
    DUCKDUCKGO = "duckduckgo"
    LEAK_LOOKUP = "leak_lookup"


class ScrapingantError(Exception):
    """Base exception for Scrapingant errors"""
    pass


class RateLimitExceeded(ScrapingantError):
    """Raised when API rate limit is exceeded"""
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class ScrapingantTimeout(ScrapingantError):
    """Raised when scraping request times out"""
    pass


@dataclass
class SearchResult:
    """Structured search result from API"""
    dork_original: str
    provider_used: SearchProvider
    status_code: int
    results_raw: Dict[str, Any]
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
        return self.error is None and len(self.breached_databases) >= 0


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
        """
        Args:
            rate: Requests per second allowed
            burst_size: Maximum burst capacity
        """
        self.rate = rate
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire a token, waiting if necessary"""
        while True:
            async with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            
            # Wait for token to regenerate
            wait_time = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(min(wait_time, 2.0))


class CircuitBreaker:
    """Circuit breaker pattern for failure prevention"""
    
    def __init__(self, failure_threshold=5, recovery_time=60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_success(self):
        """Record a successful call"""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
    
    def record_failure(self):
        """Record a failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.state = "OPEN"
                print(f"⚠️ Circuit breaker OPENED after {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_time:
                self.state = "HALF_OPEN"
                print(f"🔄 Circuit breaker transitioning to HALF_OPEN")
                return True
            return False
        
        # HALF_OPEN state - allow one test execution
        return True


class ScrapingantClient:
    """Client for Scrapingant.com HTML scraping API"""
    
    BASE_URL = "api.scrapingant.com"  # Correct domain
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate=5.0)  # 5 req/s for scraping
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=120)
    
    async def scrape_url(self, url: str, max_retries: int = 3) -> ScrapedContent:
        """
        Scrape HTML content from a URL using Scrapingant API
        
        Args:
            url: Target URL to scrape
            max_retries: Maximum retry attempts
            
        Returns:
            ScrapedContent with extracted data
        """
        for attempt in range(max_retries):
            if not self.circuit_breaker.can_execute():
                return ScrapedContent(
                    url=url,
                    status_code=0,
                    html_content="",
                    text_content="",
                    execution_time_ms=0,
                    error="Circuit breaker open"
                )
            
            start_time = time.time()
            
            try:
                await self.rate_limiter.acquire()
                
                # Use http.client as per Scrapingant documentation example
                conn = http.client.HTTPSConnection(self.BASE_URL, timeout=30)
                
                encoded_url = urllib.parse.quote(url, safe='')
                request_path = f"/v2/general?url={encoded_url}&x-api-key={self.api_key}"
                
                conn.request("GET", request_path)
                res = conn.getresponse()
                status = res.status
                data = res.read().decode("utf-8")
                conn.close()
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                if status == 200:
                    self.circuit_breaker.record_success()
                    return ScrapedContent(
                        url=url,
                        status_code=status,
                        html_content=data,
                        text_content="",  # Text extraction would go here
                        execution_time_ms=execution_time_ms
                    )
                elif status == 429:
                    self.circuit_breaker.record_failure()
                    raise RateLimitExceeded(60)
                else:
                    self.circuit_breaker.record_failure()
                    return ScrapedContent(
                        url=url,
                        status_code=status,
                        html_content="",
                        text_content="",
                        execution_time_ms=execution_time_ms,
                        error=f"HTTP {status}"
                    )
                    
            except asyncio.TimeoutError:
                self.circuit_breaker.record_failure()
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** (attempt + 1))
                    # Removed continue - the loop will automatically move to the next 'attempt'
                else:
                    return ScrapedContent(
                        url=url,
                        status_code=0,
                        html_content="",
                        text_content="",
                        execution_time_ms=(time.time() - start_time) * 1000,
                        error="Timeout after retries"
                    )


class SerperClient:
    """Client for Serper.dev Google Search API"""
    
    BASE_URL = "google.serper.dev/search"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate=10.0)  # 10 req/s
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_time=60)
    
    async def execute_search(self, query: str, provider: SearchProvider = SearchProvider.SERPER) -> Dict[str, Any]:
        """
        Execute search query using Serper.dev API
        
        Args:
            query: Search query/dork to execute
            provider: Search provider (default SERPER)
            
        Returns:
            Dict with status and JSON response or error info
        """
        
        # Check circuit breaker before attempting
        if not self.circuit_breaker.can_execute():
            return {"status": False, "error": "Circuit breaker open"}
        
        start_time = time.time()
        
        try:
            await self.rate_limiter.acquire()
            
            # Using aiohttp for better async performance
            url = f"https://{self.BASE_URL}"
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            
            data = {"q": query} if provider == SearchProvider.SERPER else {}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as resp:
                    status = resp.status
                    raw_text = await resp.text()
                    
                    execution_time_ms = (time.time() - start_time) * 1000
                    
                    if status == 200:
                        self.circuit_breaker.record_success()
                        return {
                            "status": True,
                            "json_response": raw_text,
                            "execution_time_ms": execution_time_ms
                        }
                    elif status == 429:
                        raise RateLimitExceeded(60)
                    else:
                        self.circuit_breaker.record_failure()
                        raise Exception(f"HTTP {status}: {raw_text}")
                        
        except asyncio.TimeoutError:
            self.circuit_breaker.record_failure()
            raise
        except RateLimitExceeded as e:
            print(f"⏳ Serper rate limit. Waiting {e.retry_after}s...")
            await asyncio.sleep(e.retry_after)
            self.circuit_breaker.record_failure()
            raise  
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            print(f"⚠️ Search failed (attempt {attempt + 1}): {str(e)}")
            raise


class LeakLookupClient:
    """Client for Leak-Lookup.com breach database API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_time=60)
    
    async def search_breaches(self, target: str, max_retries: int = 2) -> LeakLookupResult:
        """
        Search for breached databases containing the target
        
        Args:
            target: Email address or domain to search
            max_retries: Maximum retry attempts
            
        Returns:
            LeakLookupResult with breach database information
        """
        
        # Auto-detect search type based on target format
        if '@' in target and '.' in target.split('@')[1]:
            search_type = 'email'
        else:
            search_type = 'domain'
        
        for attempt in range(max_retries + 1):
            if not self.circuit_breaker.can_execute():
                return LeakLookupResult(
                    target=target,
                    search_type=search_type,
                    breached_databases=[],
                    execution_time_ms=0,
                    error="Circuit breaker open"
                )
            
            start_time = time.time()
            
            try:
                # Use the integrated search_leak_lookup function
                result = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: search_leak_lookup(target, self.api_key)
                )
                
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Check if we got valid results
                if isinstance(result, list):
                    self.circuit_breaker.record_success()
                    return LeakLookupResult(
                        target=target,
                        search_type=search_type,
                        breached_databases=result,
                        execution_time_ms=execution_time_ms
                    )
                else:
                    # Error response from the function
                    error_msg = f"Invalid response format: {result}" if result else "Empty response"
                    return LeakLookupResult(
                        target=target,
                        search_type=search_type,
                        breached_databases=[],
                        execution_time_ms=execution_time_ms,
                        error=error_msg
                    )
                    
            except LeakLookupAuthError as e:
                self.circuit_breaker.record_failure()
                print(f"🔑 Leak-Lookup authentication failed: {str(e)}")
                return LeakLookupResult(
                    target=target,
                    search_type=search_type,
                    breached_databases=[],
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=f"Authentication error: {str(e)}"
                )
                
            except LeakLookupTimeoutError as e:
                self.circuit_breaker.record_failure()
                if attempt < max_retries:
                    wait_time = min(2 ** (attempt + 1), 8)
                    print(f"⏱️ Leak-Lookup timeout. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
    
                return LeakLookupResult(
                    target=target,
                    search_type=search_type,
                    breached_databases=[],
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=f"Timeout after retries: {str(e)}"
                )
                
            except Exception as e:
                self.circuit_breaker.record_failure()
                print(f"⚠️ Leak-Lookup search failed (attempt {attempt + 1}): {str(e)}")
                if attempt >= max_retries:
                    return LeakLookupResult(
                        target=target,
                        search_type=search_type,
                        breached_databases=[],
                        execution_time_ms=(time.time() - start_time) * 1000,
                        error=f"Search failed after retries: {str(e)}"
                    )
                await asyncio.sleep(2 ** (attempt + 1))


async def execute_osint_harvest(
    dorks: List[str],
    serper_api_key: str,
    scrapingant_api_key: str,
    leak_lookup_api_key: Optional[str] = None,
    max_concurrent: int = 5,
    enable_leak_lookup: bool = True
) -> HarvestOutput:
    """
    Main orchestration function for HARVESTING stage
    
    Executes both standard Google dork searches AND Leak-Lookup breach searches
    simultaneously within WIP limits to maximize efficiency.
    
    Args:
        dorks: List of Google Dorks to execute
        serper_api_key: Serper.dev API key
        scrapingant_api_key: Scrapingant.com API key  
        leak_lookup_api_key: Leak-Lookup.com API key (optional)
        max_concurrent: Maximum parallel searches (WIP limit)
        enable_leak_lookup: Whether to enable Leak-Lookup integration
        
    Returns:
        HarvestOutput with all search and breach results
    """
    
    if not dorks:
        return HarvestOutput()
    
    serper_client = SerperClient(serper_api_key)
    scraper_client = ScrapingantClient(scrapingant_api_key)
    leak_lookup_client = LeakLookupClient(leak_lookup_api_key) if leak_lookup_api_key and enable_leak_lookup else None
    
    # Adjust WIP limit to accommodate dual-search approach
    effective_max_concurrent = max_concurrent // 2 if enable_leak_lookup and leak_lookup_api_key else max_concurrent
    
    semaphore_search = asyncio.Semaphore(effective_max_concurrent)
    semaphore_breach = asyncio.Semaphore(3 if enable_leak_lookup and leak_lookup_api_key else 0)  # Separate limit for breach searches
    
    results: List[SearchResult] = []
    leak_results: List[LeakLookupResult] = []
    
    async def execute_google_dork(dork: str):
        """Execute a single Google dork with concurrency control"""
        async with semaphore_search:
            start_time = time.time()
            
            try:
                search_result = await serper_client.execute_search(dork)
                
                if isinstance(search_result, dict) and search_result.get("status"):
                    json_resp = search_result["json_response"]
                    import json
                    parsed_data = json.loads(json_resp)
                    
                    result = SearchResult(
                        dork_original=dork,
                        provider_used=SearchProvider.SERPER,
                        status_code=200,
                        results_raw=parsed_data,
                        results_count=len(parsed_data.get('organic', [])),
                        execution_time_ms=(time.time() - start_time) * 1000
                    )
                else:
                    result = SearchResult(
                        dork_original=dork,
                        provider_used=SearchProvider.SERPER,
                        status_code=500,
                        results_raw={},
                        results_count=0,
                        execution_time_ms=(time.time() - start_time) * 1000,
                        error="Invalid API response"
                    )
                
                return result
                
            except Exception as e:
                return SearchResult(
                    dork_original=dork,
                    provider_used=SearchProvider.SERPER,
                    status_code=500,
                    results_raw={},
                    results_count=0,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=str(e)
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
            # Likely an email search dork
            target = dork.split()[0] if ' ' in dork else dork
            if target.startswith('email:') or target.startswith('domain:'):
                target = target.split(':')[1].strip()
            targets_for_breach.append(target)
    
    # Execute both searches concurrently respecting WIP limits
    google_tasks = [execute_google_dork(dork) for dork in dorks]
    breach_tasks = [execute_leak_lookup_search(target) for target in targets_for_breach] if leak_lookup_client and enable_leak_lookup else []
    
    search_results, leak_results_list = await asyncio.gather(
        asyncio.gather(*google_tasks),
        asyncio.gather(*breach_tasks) if breach_tasks else asyncio.create_task(asyncio.sleep(0))
    )
    
    results.extend(search_results)
    leak_results.extend(leak_results_list or [])
    
    # Calculate statistics (count only Google searches for main metrics)
    successful = sum(1 for r in results if r.is_success and r.has_results)
    failed = len(results) - successful
    
    return HarvestOutput(
        search_results=results,
        leak_lookup_results=leak_results,
        total_processed=len(results),
        successful=successful,
        failed=failed
    )


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
    
    return list(set(urls))[:10]  # Limit to top 10 URLs


async def scrape_target_urls(
    urls: List[str],
    scrapingant_api_key: str,
    max_concurrent: int = 3
) -> List[ScrapedContent]:
    """
    Scrape HTML content from extracted URLs
    
    Args:
        urls: List of URLs to scrape
        scrapingant_api_key: Scrapingant.com API key
        max_concurrent: Maximum concurrent scrapes
        
    Returns:
        List of scraped contents
    """
    
    if not urls:
        return []
    
    scraper_client = ScrapingantClient(scrapingant_api_key)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scrape_single(url: str):
        async with semaphore:
            start_time = time.time()
            try:
                result = await scraper_client.scrape_url(url)
                return result
            except Exception as e:
                return ScrapedContent(
                    url=url,
                    status_code=0,
                    html_content="",
                    text_content="",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    error=str(e)
                )
    
    tasks = [scrape_single(url) for url in urls]
    return await asyncio.gather(*tasks)
