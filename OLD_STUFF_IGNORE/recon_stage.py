#!/usr/bin/env python3
"""
OSINT Reconnaissance Stage - Query Generation and Dork Creation

This module handles:
1. Generate targeted search queries based on target type (email/domain)
2. Create effective Google Dorks for information discovery
3. Optimize query structure for maximum relevance
4. Support multiple search strategies per target

Key Features:
- Type-aware dork generation (email vs domain searches)
- Optimized query formats for different intelligence needs
- Query deduplication and prioritization
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime

logger = logging.getLogger("osint_recon")


@dataclass 
class ReconQuery:
    """Represents a single search query for reconnaissance"""
    
    query: str
    purpose: str                    # What intelligence this query seeks
    priority: int                   # 1=highest, higher=lower priority
    query_type: str                 # "email", "domain", "name", "company"
    metadata: dict = field(default_factory=dict)


class ReconnaissanceEngine:
    """
    Generates optimized search queries for OSINT reconnaissance
    
    Creates targeted Google Dorks based on target type and intelligence goals.
    Prioritizes high-value queries that are most likely to reveal relevant information.
    """
    
    # Pre-defined dork templates for different intelligence objectives
    EMAIL_SEARCH_TEMPLATES = [
        {
            "query": 'email:"{target}"',
            "purpose": "Direct email address match",
            "priority": 1,
            "type": "email"
        },
        {
            "query": f'{target} OR @{target.split("@")[1]} filetype:pdf OR filetype:xlsx',
            "purpose": "Find documents containing email or domain",
            "priority": 2,
            "type": "email_doc_search"
        },
        {
            "query": f'@{target.split("@")[1]} site:linkedin.com OR site:twitter.com',
            "purpose": "Social media presence for target domain",
            "priority": 3,
            "type": "social_media"
        },
        {
            "query": f'"{target}" -site:{target.split("@")[1]}',
            "purpose": "External mentions of email address",
            "priority": 4,
            "type": "external_mentions"
        },
    ]
    
    DOMAIN_SEARCH_TEMPLATES = [
        {
            "query": f'domain:{".".join(target.split(".")[:2])}' if "." in target else 'domain:{target}',
            "purpose": "All resources under domain",
            "priority": 1,
            "type": "domain"
        },
        {
            "query": f'"{target}" -site:{target}',
            "purpose": "External references to domain",
            "priority": 2,
            "type": "external_mentions"
        },
        {
            "query": f'subdomains of {".".join(target.split(".")[:2])}' if "." in target else 'subdomains of {target}',
            "purpose": "Discover subdomain structure",
            "priority": 3,
            "type": "subdomain_discovery"
        },
        {
            "query": f'{target} site:crt.sh OR site:certspotter.com',
            "purpose": "SSL certificate information",
            "priority": 4,
            "type": "ssl_info"
        },
    ]
    
    def __init__(self):
        self.max_queries_per_target = 10
        self.query_cache: Dict[str, List[ReconQuery]] = {}
        
    async def generate_recon_queries(self, target: str, search_type: str, 
                                    max_queries: int = None) -> List[dict]:
        """
        Generate optimized reconnaissance queries for a target
        
        Args:
            target: Email address or domain name to investigate
            search_type: "email" or "domain" search type
            max_queries: Maximum number of queries to generate
            
        Returns:
            List of query dictionaries with 'query', 'purpose', 'priority' fields
        """
        
        if not target:
            raise ValueError("Target cannot be empty")
            
        cache_key = f"{target}_{search_type}"
        
        # Check cache first (for repeated calls)
        if cache_key in self.query_cache:
            logger.debug(f"Using cached queries for {target} ({search_type})")
            return [self._query_to_dict(q) for q in self.query_cache[cache_key]]
        
        # Generate queries based on search type
        if search_type == "email":
            queries = await self._generate_email_queries(target, max_queries or self.max_queries_per_target)
        elif search_type == "domain":
            queries = await self._generate_domain_queries(target, max_queries or self.max_queries_per_target)
        else:
            raise ValueError(f"Unknown search type: {search_type}")
        
        # Cache the results
        self.query_cache[cache_key] = queries
        
        return [self._query_to_dict(q) for q in queries]
    
    async def _generate_email_queries(self, email: str, max_count: int) -> List[ReconQuery]:
        """Generate specialized queries for email address investigation"""
        
        if '@' not in email or '.' not in email.split('@')[1]:
            raise ValueError(f"Invalid email format: {email}")
            
        domain = email.split('@')[1]
        local_part = email.split('@')[0]
        
        queries = []
        
        # Add core templates
        for template in self.EMAIL_SEARCH_TEMPLATES[:4]:  # Limit to first 4 templates
            
            query_text = template["query"].format(target=email, domain=domain)
            
            if len(query_text.strip()) < 200:  # Google has ~150 char limit
                queries.append(ReconQuery(
                    query=query_text,
                    purpose=template["purpose"],
                    priority=template["priority"],
                    query_type=template["type"]
                ))
        
        # Add additional specialized searches
        if len(queries) < max_count:
            queries.extend([
                ReconQuery(
                    query=f'"{email}" OR "{local_part}@{domain}"',
                    purpose="Broad email variations",
                    priority=5,
                    query_type="variation_search"
                ),
                ReconQuery(
                    query=f'{local_part}@{domain} site:github.com',
                    purpose="Find code repositories with email",
                    priority=6,
                    query_type="code_repository"
                ),
            ])
        
        return self._prioritize_and_deduplicate(queries)[:max_count]
    
    async def _generate_domain_queries(self, domain: str, max_count: int) -> List[ReconQuery]:
        """Generate specialized queries for domain investigation"""
        
        if '.' not in domain:
            raise ValueError(f"Invalid domain format: {domain}")
            
        # Ensure proper domain format (add www prefix if missing common TLDs)
        if not domain.startswith("www.") and not domain.startswith("http"):
            domain = f"{domain}"
        
        queries = []
        
        # Add core templates
        for template in self.DOMAIN_SEARCH_TEMPLATES[:4]:
            
            query_text = template["query"].format(target=domain)
            
            if len(query_text.strip()) < 200:
                queries.append(ReconQuery(
                    query=query_text,
                    purpose=template["purpose"],
                    priority=template["priority"],
                    query_type=template["type"]
                ))
        
        # Add additional specialized searches
        if len(queries) < max_count:
            tld = domain.split(".")[-1] if "." in domain else "com"
            
            queries.extend([
                ReconQuery(
                    query=f'{domain} site:*.{tld}',
                    purpose="Find sibling domains with same TLD",
                    priority=5,
                    query_type="sibling_domains"
                ),
                ReconQuery(
                    query=f'subdomains of {domain} OR "subdomain:{domain}"',
                    purpose="Comprehensive subdomain discovery",
                    priority=6,
                    query_type="comprehensive_subdomains"
                ),
            ])
        
        return self._prioritize_and_deduplicate(queries)[:max_count]
    
    def _prioritize_and_deduplicate(self, queries: List[ReconQuery]) -> List[ReconQuery]:
        """Prioritize by priority field and remove duplicate queries"""
        
        # Deduplicate based on query text (case-insensitive)
        seen_queries = set()
        unique_queries = []
        
        for query in sorted(queries, key=lambda q: q.priority):
            query_lower = query.query.lower().strip()
            
            if query_lower not in seen_queries:
                seen_queries.add(query_lower)
                unique_queries.append(query)
        
        return unique_queries
    
    @staticmethod
    def _query_to_dict(query: ReconQuery) -> dict:
        """Convert ReconQuery object to dictionary format"""
        
        return {
            "query": query.query,
            "purpose": query.purpose,
            "priority": query.priority,
            "query_type": query.query_type,
            "metadata": query.metadata
        }


async def generate_recon_queries(target: str, search_type: str, 
                                max_queries: int = 10) -> List[dict]:
    """
    Convenience function for reconnaissance query generation
    
    This is the primary interface used by the Kanban Manager's RECON stage.
    
    Args:
        target: Email or domain to investigate
        search_type: "email" or "domain"
        max_queries: Maximum number of queries to generate
        
    Returns:
        List of query dictionaries ready for execution in HARVESTING stage
    """
    
    engine = ReconnaissanceEngine()
    return await engine.generate_recon_queries(target, search_type, max_queries)


# Example usage and testing
async def run_demo():
    """Demonstrate reconnaissance capabilities"""
    
    test_cases = [
        ("test@example.com", "email"),
        ("example.com", "domain")
    ]
    
    for target, search_type in test_cases:
        print(f"\n{'='*60}")
        print(f"Generating queries for {target} ({search_type})")
        print('='*60)
        
        queries = await generate_recon_queries(target, search_type, max_queries=5)
        
        for i, query_data in enumerate(queries, 1):
            print(f"\n{i}. Query: {query_data['query']}")
            print(f"   Purpose: {query_data['purpose']}")
            print(f"   Priority: {query_data['priority']}/{max(q['priority'] for q in queries)}")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    asyncio.run(run_demo())
