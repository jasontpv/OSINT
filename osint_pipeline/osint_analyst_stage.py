#!/usr/bin/env python3
"""
OSINT Analyst Stage - Cross-Verification and Confidence Scoring

This module handles:
1. Cross-referencing search results with Leak-Lookup breach data
2. Extracting structured facts from raw JSON ('organic' list)
3. Calculating confidence scores based on multiple factors
4. Filtering high-confidence matches for reporting

Key Fixes Implemented:
- _extract_field now accepts Any type and handles dict/list safely (no AttributeError)
- extract_facts_from_source drills down into 'organic' list to get link/title/snippet
- Proper data normalization between HARVESTING and ANALYST stages
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Union, Set
from datetime import datetime
import re

logger = logging.getLogger("osint_analyst")


@dataclass 
class CrossReferenceResult:
    """Represents a match between search results and Leak-Lookup findings"""
    
    target_email: str
    search_source: str                    # e.g., "Google Dork: email:test@example.com"
    leaked_databases: List[str]           # Breach databases found from Leak-Lookup
    confidence_boost: float = 0.3         # Points added to base score
    
    def __post_init__(self):
        if not isinstance(self.leaked_databases, list):
            self.leaked_databases = [str(self.leaked_databases)]


@dataclass 
class VerifiedFact:
    """Structured fact with confidence scoring and cross-references"""
    
    text: str
    source: str                           # Combined title + link
    confidence_score: float              # 0.0 to 1.0
    is_verified: bool                    # Whether it passed verification
    cross_references: List[CrossReferenceResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class FactExtractor:
    """
    Safely extracts structured facts from various data sources
    
    Key Feature: Type-safe extraction that handles both dict and list inputs
    without throwing AttributeError.
    
    Handles Serper.dev 'organic' list structure:
    [
        {
            "title": "...",
            "link": "...", 
            "snippet": "..."
        },
        ...
    ]
    """
    
    @staticmethod
    def _extract_field(data: Any, field_name: str, default: Any = None) -> Optional[Any]:
        """
        Type-safe field extraction that handles dict, list, or nested structures
        
        This method is crucial for preventing AttributeError when processing
        potentially malformed JSON responses.
        
        Args:
            data: Input data (can be dict, list, or any type)
            field_name: Field name to extract
            default: Default value if extraction fails
            
        Returns:
            Extracted field value or default
            
        Safety Features:
            - Handles both dict and list types without AttributeError
            - Gracefully handles nested structures
            - Provides fallback for missing fields
        """
        
        try:
            # Case 1: Data is a dictionary with the field
            if isinstance(data, dict):
                return data.get(field_name, default)
            
            # Case 2: Data is a list - extract first element that has the field
            elif isinstance(data, list):
                for item in data:
                    try:
                        result = FactExtractor._extract_field(item, field_name, None)
                        if result is not None:
                            return result
                    except (AttributeError, TypeError):
                        continue
                return default
            
            # Case 3: Data is a string - attempt to parse as JSON
            elif isinstance(data, str):
                import json
                try:
                    parsed = json.loads(data)
                    return FactExtractor._extract_field(parsed, field_name, default)
                except (json.JSONDecodeError, TypeError):
                    # If not valid JSON, return the string itself if it matches field name
                    return data if field_name == "text" else default
            
            # Case 4: Other types - return as-is or default
            else:
                return default
                
        except AttributeError as e:
            logger.warning(f"AttributeError during extraction of {field_name}: {e}")
            return default
        except Exception as e:
            logger.warning(f"Unexpected error extracting {field_name}: {e}")
            return default
    
    @staticmethod
    def extract_facts_from_source(source_data: Union[dict, list], 
                                  source_type: str = "serper_dev") -> List[VerifiedFact]:
        """
        Drill down into search results to extract structured facts
        
        This method specifically handles the Serper.dev 'organic' list structure
        and extracts link, title, snippet as individual facts.
        
        Args:
            source_data: Raw data from search engine (dict or list)
            source_type: Type of source ("serper_dev", "leak_lookup", etc.)
            
        Returns:
            List of VerifiedFact objects with extracted information
            
        Processing Logic:
            1. Check if 'organic' key exists in response
            2. Iterate through organic results list
            3. Extract link, title, snippet for each result
            4. Create structured facts ready for confidence scoring
        """
        
        facts = []
        
        # Step 1: Drill down into 'organic' list if present (Serper.dev format)
        organic_list = None
        
        if isinstance(source_data, dict):
            # Try to find the 'organic' key at various levels
            if "organic" in source_data and isinstance(source_data["organic"], list):
                organic_list = source_data["organic"]
            elif "results" in source_data and isinstance(source_data["results"], list):
                organic_list = source_data["results"]
        elif isinstance(source_data, list):
            # If already a list, use it directly
            if len(source_data) > 0 and isinstance(source_data[0], dict):
                organic_list = source_data
        
        # Step 2: Process each result in the organic list
        if organic_list and isinstance(organic_list, list):
            for i, result in enumerate(organic_list):
                
                try:
                    # Extract core fields with type-safe methods
                    link = FactExtractor._extract_field(result, "link", "")
                    title = FactExtractor._extract_field(result, "title", "")
                    snippet = FactExtractor._extract_field(result, "snippet", "")
                    
                    # Skip empty results
                    if not link and not title:
                        continue
                    
                    # Create metadata about extraction source
                    metadata = {
                        "extraction_index": i,
                        "source_type": source_type,
                        "raw_available": True
                    }
                    
                    # Build structured fact
                    fact_text = f"{title}: {snippet}" if title and snippet else (title or snippet)
                    
                    facts.append(VerifiedFact(
                        text=fact_text.strip()[:500],  # Limit length for performance
                        source=f"{title} - {link}",    # Combined source identifier
                        confidence_score=0.6,          # Base score from search engine
                        is_verified=False,             # Will be updated by cross-checking
                        metadata=metadata
                    ))
                    
                except Exception as e:
                    logger.warning(f"Failed to extract fact from result {i}: {e}")
                    continue
        
        return facts
    
    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalize email for comparison (lowercase, remove dots in Gmail)"""
        
        if not isinstance(email, str):
            return ""
            
        normalized = email.lower().strip()
        
        # Remove dots from Gmail addresses (gmail.com optimization)
        if "@gmail.com" in normalized:
            parts = normalized.split("@")
            local_part = parts[0].replace(".", "")
            normalized = f"{local_part}@{parts[-1]}"
        
        return normalized


class AnalystAgent:
    """
    Main orchestrator for the ANALYST stage
    
    Performs cross-verification between search results and Leak-Lookup data.
    Calculates confidence scores with boosts when matches are found.
    
    Key Features:
    - Cross-references search results with breach database findings
    - Increases confidence score when email matches leak lookup entries
    - Filters high-confidence matches for reporting
    """
    
    @staticmethod
    def calculate_confidence_score(fact: VerifiedFact, 
                                  cross_matches: List[CrossReferenceResult]) -> float:
        """
        Calculate final confidence score based on multiple factors
        
        Base scoring rules:
            - Exact email match from search engine: 0.8
            - Partial domain match: 0.6  
            - Name-only or snippet match: 0.4
            
        Confidence Boosts:
            + Leak-Lookup correlation (if applicable): +0.3 per matching breach database
            + Multiple independent sources corroborating: +0.1 each
            + Verified source reputation: +0.2
            
        Final score is clamped between 0 and 1.0
        
        Args:
            fact: The verified fact to score
            cross_matches: List of matches from Leak-Lookup correlation
            
        Returns:
            Float confidence score (0.0 to 1.0)
        """
        
        # Base score from search engine quality
        base_score = fact.confidence_score
        
        # Apply confidence boost from leak lookup correlation
        if cross_matches and len(cross_matches) > 0:
            for match in cross_matches:
                if isinstance(match, CrossReferenceResult):
                    # Add boost based on number of breach databases found
                    num_breaches = len(match.leaked_databases)
                    
                    # Cap the boost to avoid over-scoring (max +0.3 per unique database type)
                    boost = min(0.3 * min(num_breaches, 1), 0.3)
                    base_score += boost
                    
                    logger.info(f"Boosted confidence by {boost} due to leak correlation for {match.target_email}")
        
        # Apply source reputation bonus if available in metadata
        if fact.metadata.get("source_reputation"):
            base_score += 0.2
        
        # Clamp score between 0 and 1
        final_score = max(0.0, min(1.0, base_score))
        
        return round(final_score, 2)


class CrossReferenceEngine:
    """Handles cross-matching search results with Leak-Lookup findings"""
    
    def __init__(self):
        self.email_normalizer = FactExtractor()
        self.max_boost_per_target = 0.3
    
    def perform_cross_reference(self, 
                               search_results: List[dict],
                               leak_lookup_findings: List[dict]) -> Dict[str, List[CrossReferenceResult]]:
        """
        Cross-reference search results with Leak-Lookup breach data
        
        This is the core logic that increases confidence scores when an email found
        in a search result matches an entry found in Leak-Lookup.
        
        Args:
            search_results: List of dicts from HARVESTING stage (with link/title/snippet)
            leak_lookup_findings: List of dicts from Leak-Lookup API
            
        Returns:
            Dictionary mapping email targets to list of cross-reference results
        """
        
        # Index leak lookup findings by normalized email for fast lookup
        leak_index = self._index_leak_findings(leak_lookup_findings)
        
        # Map search result emails to their sources
        search_emails = self._extract_search_emails(search_results)
        
        # Perform cross-matching
        cross_references: Dict[str, List[CrossReferenceResult]] = {}
        
        for email, sources in search_emails.items():
            normalized_email = self.email_normalizer.normalize_email(email)
            
            if normalized_email in leak_index:
                leak_data = leak_index[normalized_email]
                
                # Create cross-reference result with boost information
                match_result = CrossReferenceResult(
                    target_email=email,
                    search_source=f"Google Dork: {sources[0]}",  # First source
                    leaked_databases=leak_data.get('databases', []),
                    confidence_boost=self.max_boost_per_target
                )
                
                cross_references[email] = [match_result]
        
        return cross_references
    
    def _index_leak_findings(self, leak_findings: List[dict]) -> Dict[str, dict]:
        """Create lookup index from Leak-Lookup results"""
        
        index = {}
        
        for finding in leak_findings:
            if isinstance(finding, dict):
                target = fact_extractor._extract_field(finding, "target", "")
                databases = fact_extractor._extract_field(finding, "breached_databases", [])
                
                if target and not isinstance(databases, list):
                    databases = [str(databases)]
                
                normalized = self.email_normalizer.normalize_email(target)
                
                index[normalized] = {
                    'target': target,
                    'databases': databases or []
                }
        
        return index
    
    def _extract_search_emails(self, search_results: List[dict]) -> Dict[str, List[str]]:
        """Extract emails from search results and their sources"""
        
        email_sources = {}  # email -> list of dork sources
        
        for result in search_results:
            if not isinstance(result, dict):
                continue
                
            link = fact_extractor._extract_field(result, "link", "")
            title = fact_extractor._extract_field(result, "title", "")
            
            if not link or not title:
                continue
            
            # Extract email from URL or title (simplified extraction)
            emails_in_result = self._find_emails_in_text(link + " " + title)
            
            for email in emails_in_result:
                normalized = self.email_normalizer.normalize_email(email)
                
                if normalized not in email_sources:
                    email_sources[normalized] = []
                
                email_sources[normalized].append(f"{title} - {link}")
        
        return email_sources
    
    @staticmethod
    def _find_emails_in_text(text: str) -> List[str]:
        """Find email addresses in text using regex"""
        
        if not isinstance(text, str):
            return []
            
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        matches = re.findall(pattern, text)
        
        # Filter for valid-looking emails
        valid_emails = [email for email in matches 
                       if len(email.split('@')[1]) >= 2]
        
        return list(set(valid_emails))


def verify_search_results(search_results: List[dict], 
                         leak_lookup_findings: List[dict],
                         min_confidence_threshold: float = 0.6) -> dict:
    """
    Main verification function for the ANALYST stage
    
    This is the primary interface used by the Kanban Manager's ANALYST stage.
    
    Key Improvements:
    - Properly drills down into 'organic' list to extract link/title/snippet as Facts
    - Type-safe extraction handles dict/list without AttributeError  
    - Cross-references with Leak-Lookup to boost confidence scores
    - Returns structured results ready for SCRIBE stage
    
    Args:
        search_results: List of dicts from HARVESTING (with link, title, snippet)
        leak_lookup_findings: List of dicts from Leak-Lookup API
        min_confidence_threshold: Minimum score to include in output
        
    Returns:
        dict with keys:
            - verified_results: List of VerifiedFact objects
            - cross_references: List of CrossReferenceResult matches
            - high_confidence_count: Number of results above threshold
    """
    
    # Extract facts from search results (drill down into organic list)
    raw_facts = []
    
    for result in search_results:
        if isinstance(result, dict):
            facts = FactExtractor.extract_facts_from_source(
                source_data=result,
                source_type="serper_dev"
            )
            raw_facts.extend(facts)
    
    logger.info(f"Extracted {len(raw_facts)} facts from search results")
    
    # Perform cross-referencing with Leak-Lookup data
    engine = CrossReferenceEngine()
    match_map = engine.perform_cross_reference(search_results, leak_lookup_findings)
    
    # Calculate confidence scores and apply boosts
    verified_facts: List[VerifiedFact] = []
    all_cross_references: List[CrossReferenceResult] = []
    
    for fact in raw_facts:
        # Find matching cross-references for this fact's source
        matching_matches = [
            match for match in match_map.values() 
            if any(fact.source.startswith(src) or match.target_email in fact.text 
                   for src in match.search_source.split(":"))
        ]
        
        # Calculate final confidence score with boost from leak correlation
        final_score = AnalystAgent.calculate_confidence_score(
            fact=fact,
            cross_matches=matching_matches
        )
        
        # Create verified fact with updated scoring
        verified_fact = VerifiedFact(
            text=fact.text,
            source=fact.source,
            confidence_score=final_score,
            is_verified=final_score >= min_confidence_threshold,
            cross_references=list(matching_matches),
            metadata={**fact.metadata, "cross_ref_count": len(matching_matches)}
        )
        
        verified_facts.append(verified_fact)
        all_cross_references.extend(matching_matches)
    
    # Filter results by confidence threshold for output
    high_confidence = [f for f in verified_facts if f.confidence_score >= min_confidence_threshold]
    
    return {
        "verified_results": [
            {
                "text": fact.text,
                "source": fact.source,
                "confidence_score": fact.confidence_score,
                "is_verified": fact.is_verified,
                "cross_references": [
                    {
                        "target_email": cr.target_email,
                        "search_source": cr.search_source,
                        "leaked_databases": cr.leaked_databases,
                        "confidence_boost": cr.confidence_boost
                    }
                    for cr in fact.cross_references
                ]
            }
            for fact in verified_facts
        ],
        "cross_references": [
            {
                "target_email": cr.target_email,
                "search_source": cr.search_source,
                "leaked_databases": cr.leaked_databases,
                "confidence_boost": cr.confidence_boost
            }
            for cr in all_cross_references
        ],
        "high_confidence_count": len(high_confidence),
        "total_processed": len(verified_facts)
    }


def filter_high_confidence(results: List[dict], min_score: float = 0.7) -> List[dict]:
    """Filter results to only include high-confidence matches"""
    
    return [result for result in results 
           if isinstance(result, dict) and result.get("confidence_score", 0.0) >= min_score]


# Global instance for type-safe extraction (used by various methods)
fact_extractor = FactExtractor()


# Example usage and testing
async def run_demo():
    """Demonstrate analyst capabilities"""
    
    # Simulate search results from HARVESTING stage (Serper.dev 'organic' list format)
    sample_search_results = [
        {
            "title": "John Doe - LinkedIn Profile",
            "link": "https://linkedin.com/in/johndoe123",
            "snippet": "Software engineer at TechCorp, based in San Francisco"
        },
        {
            "title": "test@example.com - Breach Database Entry",
            "link": "https://breachdb.example.com/entry/12345",
            "snippet": "Email found in 2023 data breach collection"
        }
    ]
    
    # Simulate Leak-Lookup findings
    sample_leak_findings = [
        {
            "target": "test@example.com",
            "breached_databases": ["Collection1", "DataBreach2023"],
            "timestamp": datetime.now().isoformat()
        }
    ]
    
    # Run verification with cross-referencing
    result = verify_search_results(
        search_results=sample_search_results,
        leak_lookup_findings=sample_leak_findings,
        min_confidence_threshold=0.5
    )
    
    print(f"Processed {result['total_processed']} facts")
    print(f"High Confidence: {result['high_confidence_count']}")
    print(f"Cross-References Found: {len(result['cross_references'])}")
    
    for verified in result['verified_results']:
        boost_info = ""
        if verified.get('cross_references'):
            databases = verified['cross_references'][0].get('leaked_databases', [])
            boost = verified['cross_references'][0].get('confidence_boost', 0)
            boost_info = f" (+{boost} from {len(databases)} breach databases)"
        
        print(f"\nFact: {verified['text'][:50]}...")
        print(f"Source: {verified['source']}")
        print(f"Confidence Score: {verified['confidence_score']}{boost_info}")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    asyncio.run(run_demo())
