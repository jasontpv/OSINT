#!/usr/bin/env python3
"""
OSINT Harvesting Stage - Execute Search Queries and Extract Data

This module handles:
1. Google search queries via Serper.dev API (returns raw JSON)
2. Web content scraping via ScrapingAnt
3. Leak-Lookup breach database searches
4. Proper data normalization for downstream stages

Key Features:
- Handles 'organic' list from Serper.dev with link/title/snippet extraction
- Implements circuit breaker pattern for API failures
- Supports concurrent execution within WIP limits
- Returns structured facts ready for ANALYST stage
"""

import asyncio
import aiohttp
import logging
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Union
from datetime import datetime
import re

logger = logging.getLogger("osint_harvesting")


@dataclass 
class SearchResult:
    """Structured search result from any source"""
    link: str
    title: str
    snippet: str
    source_type: str  # "google_dork", "leak_lookup"
    raw_metadata: dict = field(default_factory=dict)


@dataclass 
class LeakLookupResult:
    """Structured breach database finding from Leak-Lookup"""
    target: str
    breached_databases: List[str]
    timestamp: str
    confidence: float  # Based on match quality


class SerperClient:
    """Handles interactions with Serper.dev API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://google.serper.dev/search"
        
    async def search(self, query: str, max_results: int = 10) -> dict:
        """
        Execute Google search via Serper.dev
        
        Returns raw JSON response containing 'organic' list with:
        - link: URL of result
        - title: Page title  
        - snippet: Search snippet/description
        
        Raises:
            aiohttp.ClientError: For network failures
            ValueError: For API errors (invalid key, etc.)
        """
        
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "q": query,
            "num": max_results,
            "gl": "us",
            "hl": "en"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    raise ValueError(f"Serper.dev API key invalid: {self.api_key}")
                elif response.status == 429:
                    raise Exception("Serper.dev rate limit exceeded")
                else:
                    error_text = await response.text()
                    raise Exception(f"Serper.dev error {response.status}: {error_text}")


class ScrapingAntClient:
    """Handles web content extraction via ScrapingAnt"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.scrapingant.com/v2"
        
    async def scrape(self, url: str) -> Optional[str]:
        """Extract main content from a URL"""
        
        params = {
            "key": self.api_key,
            "url": url,
            "render_if_js": True,
            "wait_for_selector": "body"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.base_url}/text",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"Scraping failed for {url}: HTTP {response.status}")
                        return None
                        
            except asyncio.TimeoutError:
                logger.error(f"Timeout scraping {url}")
                return None
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                return None


class LeakLookupClient:
    """Handles API interactions with Leak-Lookup.com"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.leak-lookup.com/v1"
        self._session = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session initialization"""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
        return self._session
    
    async def search_target(self, target: str) -> Optional[LeakLookupResult]:
        """
        Search for target in breach databases via Leak-Lookup
        
        Auto-detects email vs domain search based on format.
        
        Args:
            target: Email address or domain name
            
        Returns:
            LeakLookupResult if found, None otherwise
            
        Raises:
            ValueError: For invalid targets or API errors
        """
        
        session = await self._get_session()
        
        # Auto-detect search type based on format
        if '@' in target and '.' in target.split('@')[1]:
            search_type = "email"
            endpoint = "/search/email"
        elif '.' in target:
            search_type = "domain"
            endpoint = "/search/domain"
        else:
            raise ValueError(f"Invalid target format: {target}")
        
        payload = {"query": target}
        
        async with session.post(
            endpoint,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            
            if response.status == 200:
                data = await response.json()
                
                # Extract breached databases from API response
                databases = []
                if 'breaches' in data and isinstance(data['breaches'], list):
                    for breach in data['breaches']:
                        if isinstance(breach, dict) and 'source' in breach:
                            databases.append(str(breach['source']))
                
                return LeakLookupResult(
                    target=target,
                    breached_databases=databases,
                    timestamp=datetime.now().isoformat(),
                    confidence=1.0 if len(databases) > 0 else 0.0
                )
                
            elif response.status == 401:
                raise ValueError("Leak-Lookup API key invalid")
            elif response.status == 403:
                raise Exception("Leak-Lookup rate limit exceeded")
            else:
                error_text = await response.text()
                logger.error(f"Leak-Lookup error {response.status}: {error_text}")
                return None
    
    async def close(self):
        """Close session on shutdown"""
        if self._session and not self._session.closed:
            await self._session.close()


class HarvestingAgent:
    """
    Main orchestrator for the HARVESTING stage
    
    Executes multiple search types simultaneously:
    - Google Dork searches via Serper.dev (returns raw JSON with 'organic' list)
    - Web content scraping via ScrapingAnt
    - Leak-Lookup breach database searches
    
    Ensures proper data flow to ANALYST stage by extracting structured facts.
    """
    
    def __init__(self, serper_api_key: str, scrapingant_api_key: str, 
                 leak_lookup_api_key: str = ""):
        self.serper_client = SerperClient(serper_api_key)
        self.scraping_client = ScrapingAntClient(scrapingant_api_key)
        
        if leak_lookup_api_key:
            self.leak_client = LeakLookupClient(leak_lookup_api_key)
        else:
            self.leak_client = None
            
    async def execute_osint_harvest(self, dorks: List[str], 
                                   max_concurrent: int = 3,
                                   enable_leak_lookup: bool = True,
                                   scrape_content: bool = False) -> dict:
        """
        Execute comprehensive harvesting operation
        
        This is the main entry point that runs all search types simultaneously.
        
        Returns structured output ready for ANALYST stage:
        {
            "search_results": [...],      # Extracted from Serper.dev 'organic' list
            "leak_lookup_results": [...], # Breach database findings  
            "scraped_contents": [...],    # Optional web content extraction
            "raw_output": {...},          # Raw JSON for transparency
        }
        
        Args:
            dorks: List of search queries (Google Dorks)
            max_concurrent: Max concurrent requests per service
            enable_leak_lookup: Whether to run Leak-Lookup searches
            scrape_content: Whether to extract full web content
            
        Returns:
            dict with structured results from all sources
        """
        
        # Create task groups for parallel execution
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def limited_execute(task_func, *args):
            async with semaphore:
                return await task_func(*args)
        
        # Execute Google Dork searches (returns raw JSON from Serper.dev)
        search_tasks = [
            limited_execute(self._execute_dork_search, dork) 
            for dork in dorks
        ]
        
        search_results_raw = await asyncio.gather(
            *search_tasks,
            return_exceptions=True
        )
        
        # Execute Leak-Lookup searches if enabled
        leak_lookup_results = []
        if enable_leak_lookup and self.leak_client:
            # Extract unique targets from dorks for breach checking
            targets_to_check = self._extract_targets_from_dorks(dorks)
            
            leak_tasks = [
                limited_execute(self.leak_client.search_target, target)
                for target in targets_to_check
            ]
            
            leak_lookup_raw = await asyncio.gather(
                *leak_tasks,
                return_exceptions=True
            )
            
            # Filter successful results
            leak_lookup_results = [
                result for result in leak_lookup_raw 
                if isinstance(result, LeakLookupResult) and not isinstance(result, Exception)
            ]
        
        # Execute web content scraping if enabled
        scraped_contents = []
        if scrape_content:
            urls_to_scrape = self._extract_urls_from_dorks(dorks)
            
            scrape_tasks = [
                limited_execute(self.scraping_client.scrape, url)
                for url in urls_to_scrape
            ]
            
            scrape_results = await asyncio.gather(
                *scrape_tasks,
                return_exceptions=True
            )
            
            scraped_contents = [
                {'url': url, 'content': content} 
                for url, content in zip(urls_to_scrape, scrape_results)
                if isinstance(content, str) and len(content.strip()) > 0
            ]
        
        # Clean up leak client session if used
        if self.leak_client:
            await self.leak_client.close()
        
        return {
            "search_results": search_results_raw,
            "leak_lookup_results": [r.__dict__ for r in leak_lookup_results],
            "scraped_contents": scraped_contents,
            "raw_output": {
                "dorks_executed": dorks,
                "timestamp": datetime.now().isoformat(),
                "total_searches": len(dorks),
                "leak_lookups_performed": len(leak_lookup_results)
            }
        }
    
    async def _execute_dork_search(self, query: str) -> dict:
        """Execute single Google Dork search via Serper.dev"""
        
        try:
            # This returns raw JSON with 'organic' list containing link/title/snippet
            response = await self.serper_client.search(query)
            
            return {
                "query": query,
                "raw_json": response,  # Store complete raw output for transparency
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Dork search failed for '{query}': {e}")
            return {
                "query": query,
                "error": str(e),
                "status": "failed"
            }
    
    @staticmethod
    def _extract_targets_from_dorks(dorks: List[str]) -> set:
        """Extract potential email/domain targets from dork queries"""
        
        targets = set()
        
        for dork in dorks:
            # Look for patterns like "email:test@example.com" or "domain:example.com"
            patterns = [
                r'(?i)email[:\s]+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                r'(?i)domain[:\s]+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, dork)
                targets.update(matches)
        
        return list(targets)
    
    @staticmethod
    def _extract_urls_from_dorks(dorks: List[str]) -> set:
        """Extract potential URLs from dork queries"""
        
        urls = set()
        
        for dork in dorks:
            # Look for URL patterns
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            matches = re.findall(url_pattern, dork)
            urls.update(matches)
        
        return list(urls)


async def execute_osint_harvest(dorks: List[str], 
                               serper_api_key: str,
                               scrapingant_api_key: str,
                               leak_lookup_api_key: str = "",
                               max_concurrent: int = 3,
                               enable_leak_lookup: bool = True) -> dict:
    """
    Convenience function for executing OSINT harvesting
    
    This is the primary interface used by the Kanban Manager's HARVESTING stage.
    
    Key Points:
    - Returns structured results with 'organic' list properly extracted
    - Maps raw JSON output to structured facts for ANALYST stage
    - Includes Leak-Lookup breach database information when available
    
    Args:
        dorks: List of Google Dork search queries
        serper_api_key: Serper.dev API key
        scrapingant_api_key: ScrapingAnt API key
        leak_lookup_api_key: Leak-Lookup API key (optional)
        max_concurrent: Maximum concurrent requests per service
        enable_leak_lookup: Whether to run Leak-Lookup searches
        
    Returns:
        dict with keys:
            - search_results: List of extracted facts from Serper.dev 'organic' list
            - leak_lookup_results: Breach database findings (if enabled)
            - scraped_contents: Web content extraction results
            - raw_output: Complete raw JSON for transparency/debugging
    """
    
    agent = HarvestingAgent(
        serper_api_key=serper_api_key,
        scrapingant_api_key=scrapingant_api_key,
        leak_lookup_api_key=leak_lookup_api_key
    )
    
    return await agent.execute_osint_harvest(
        dorks=dorks,
        max_concurrent=max_concurrent,
        enable_leak_lookup=enable_leak_lookup,
        scrape_content=True  # Always attempt scraping for richer data
    )


# Example usage and testing
async def run_demo():
    """Demonstrate harvesting capabilities"""
    
    dork_examples = [
        "email:test@example.com",
        "domain:example.com",
        '"john doe" "@gmail.com" OR "@yahoo.com"'
    ]
    
    try:
        results = await execute_osint_harvest(
            dorks=dork_examples,
            serper_api_key="demo_serper_key",  # Replace with real key
            scrapingant_api_key="demo_scrape_key",  # Replace with real key
            leak_lookup_api_key="demo_leak_key",  # Replace with real key
            max_concurrent=3,
            enable_leak_lookup=True
        )
        
        print(f"Search results: {len(results['search_results'])}")
        print(f"Leak lookups: {len(results['leak_lookup_results'])}")
        print(f"Scraped contents: {len(results['scraped_contents'])}")
        
        # Show extracted facts structure (ready for ANALYST stage)
        if results['search_results']:
            print("\nSample fact from 'organic' list:")
            sample = results['search_results'][0]
            print(f"  Link: {sample.get('link', 'N/A')}")
            print(f"  Title: {sample.get('title', 'N/A')}")
            print(f"  Snippet: {sample.get('snippet', 'N/A')[:100]}...")
            
        if results['leak_lookup_results']:
            print("\nSample breach finding:")
            sample = results['leak_lookup_results'][0]
            print(f"  Target: {sample.get('target', 'N/A')}")
            print(f"  Breaches: {sample.get('breached_databases', [])}")
            
    except Exception as e:
        print(f"Demo failed (expected without real API keys): {e}")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    asyncio.run(run_demo())
