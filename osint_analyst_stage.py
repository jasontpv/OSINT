#!/usr/bin/env python3
"""
OSINT Analyst Stage - Cross-Verification and Confidence Scoring (FIXED)

This module handles:
1. Cross-referencing search results with Leak-Lookup breach data
2. Extracting structured facts from raw JSON ('organic' list)
3. Calculating confidence scores based on multiple factors
4. Filtering high-confidence matches for reporting

Key Fixes Implemented:
- _extract_field now accepts Any type and handles dict/list safely (no AttributeError)
- extract_facts_from_source drills down into 'organic' list to get link/title/snippet
- Proper data normalization between HARVESTING and ANALYST stages
- Type-safe extraction that prevents crashes on malformed JSON
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Union
from datetime import datetime
import re
import difflib
import sys
import os

# Add parent directory to path for imports".t
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("osint_analyst")

# Import database manager at module level
from database_manager import get_db_manager


def _get_db_path() -> Optional[str]:
    """Safely retrieve database path without causing runtime errors."""
    try:
        db_mgr = get_db_manager()
        db_mgr.initialize_tables()
        return db_mgr.db_path
    except Exception:
        logger.warning("Could not determine database path")
        return None


# Print database path after imports are available
db_path = _get_db_path()
if db_path:
    print(f"Using database: {db_path}") 


class EntityVerificationStatus:
    """Enum-like class for entity verification statuses"""
    
    PENDING = "pending"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    LOW_CONFIDENCE = "low_confidence"
    
    @classmethod
    def from_score(cls, score: float) -> str:
        """Determine status based on confidence score"""
        if score >= 0.8:
            return cls.VERIFIED
        elif score >= 0.5:
            return cls.PENDING
        elif score < 0.3:
            return cls.LOW_CONFIDENCE
        else:
            return cls.CONFLICTING


@dataclass 
class CandidateEntity:
    """Represents a candidate entity with consensus detection metadata"""
    
    entity_id: str
    source_types: List[str]
    matched_fields: Dict[str, Any]
    confidence_score: float
    verification_status: str = "pending"


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
                try:
                    import json
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
        
        FIXED: Privacy filtering now applied consistently at extraction point for all paths.
        
        Args:
            source_data: Raw data from search engine (dict or list)
            source_type: Type of source ("serper_dev", "leak_lookup", etc.)
            
        Returns:
            List of VerifiedFact objects with extracted information
            
        Processing Logic:
            1. Check if 'organic' key exists in response
            2. Iterate through organic results list
            3. Extract link, title, snippet for each result
            4. Apply privacy filtering consistently at extraction point
            5. Create structured facts ready for confidence scoring
        
        Note: source_type parameter is reserved for future use to enable
        different extraction strategies based on data source type.
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
            else:
                # If no known key, check if data itself is a list
                if isinstance(source_data.get("data"), list):
                    organic_list = source_data["data"]
        
        elif isinstance(source_data, list):
            # If input is already a list, use it directly
            organic_list = source_data
        
        # Step 2: Process each result in the organic list
        if organic_list and isinstance(organic_list, list):
            for idx, item in enumerate(organic_list):
                try:
                    # Extract fields safely using our type-safe method
                    title = FactExtractor._extract_field(item, "title", f"Result {idx + 1}")
                    link = FactExtractor._extract_field(item, "link", "")
                    snippet = FactExtractor._extract_field(item, "snippet", "")
                    
                    # Skip items without meaningful content
                    if not title and not link:
                        continue
                    
                    # Create source identifier (title + link for context)
                    source_identifier = f"{title} ({link})" if link else str(title)
                    
                    # FIXED: Apply privacy filtering consistently at extraction point
                    filtered_title = _apply_privacy_filter(title) if isinstance(title, str) else title
                    filtered_link = _apply_privacy_filter(link) if isinstance(link, str) else link
                    filtered_snippet = _apply_privacy_filter(snippet) if isinstance(snippet, str) else snippet
                    
                    # Extract email addresses from filtered snippet if present
                    emails_in_snippet = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', filtered_snippet)
                    
                    for email in emails_in_snippet:
                        facts.append(VerifiedFact(
                            text=email,
                            source=source_identifier,
                            confidence_score=0.6,  # Base score for extracted email
                            is_verified=False,
                            cross_references=[],
                            metadata={
                                "extraction_type": "email_from_snippet",
                                "original_source": f"{filtered_title} - {filtered_link}",
                                "snippet_preview": filtered_snippet[:100] if filtered_snippet else ""
                            }
                        ))
                    
                    # Create fact for the search result itself
                    if filtered_title:
                        facts.append(VerifiedFact(
                            text=f"Search Result: {filtered_title}",
                            source=source_identifier,
                            confidence_score=0.5,  # Base score for search result
                            is_verified=False,
                            cross_references=[],
                            metadata={
                                "extraction_type": "search_result",
                                "link": filtered_link,
                                "snippet": filtered_snippet[:200] if filtered_snippet else "",
                                "result_index": idx
                            }
                        ))
                        
                except Exception as e:
                    logger.warning(f"Error processing item {idx}: {e}")
                    continue
        
        # Step 3: Handle direct list input (already structured facts)
        elif isinstance(source_data, list):
            for item in source_data:
                if isinstance(item, dict):
                    text = FactExtractor._extract_field(item, "text", str(item))
                    source = FactExtractor._extract_field(item, "source", "Unknown")
                    
                    # FIXED: Apply privacy filtering consistently at extraction point
                    filtered_text = _apply_privacy_filter(str(text)) if isinstance(text, str) else text
                    filtered_source = _apply_privacy_filter(str(source)) if isinstance(source, str) else source
                    
                    facts.append(VerifiedFact(
                        text=filtered_text,
                        source=filtered_source,
                        confidence_score=0.5,
                        is_verified=False,
                        cross_references=[],
                        metadata={"direct_input": True}
                    ))
        
        # Step 4: Handle single dict input (not a list)
        elif isinstance(source_data, dict):
            text = FactExtractor._extract_field(source_data, "text", str(source_data))
            source = FactExtractor._extract_field(source_data, "source", "Unknown")
            
            # FIXED: Apply privacy filtering consistently at extraction point
            filtered_text = _apply_privacy_filter(str(text)) if isinstance(text, str) else text
            filtered_source = _apply_privacy_filter(str(source)) if isinstance(source, str) else source
            
            facts.append(VerifiedFact(
                text=filtered_text,
                source=filtered_source,
                confidence_score=0.5,
                is_verified=False,
                cross_references=[],
                metadata={"single_dict_input": True}
            ))
        
        return facts
    
    @staticmethod
    def fuzzy_match_usernames(facts: List[Any], threshold: float = 0.8):
        """Phase 3: Identifies similar usernames using optimized fuzzy matching
        
        Optimizations:
        - Early termination on exact matches (O(n) best case instead of O(n²))
        - Length-based grouping to skip obviously different length comparisons
        - Only compares items within reasonable length tolerance
        """
        # Filter for items that look like usernames (no @ symbol)
        usernames = [f for f in facts if hasattr(f, 'text') and "@" not in str(f.text)]
        
        # Group by text length for optimization
        length_groups: Dict[int, List[Any]] = {}
        for fact in usernames:
            text_len = len(str(fact.text))
            if text_len not in length_groups:
                length_groups[text_len] = []
            length_groups[text_len].append(fact)
        
        # BUGFIX: the previous early-termination block added ALL remaining
        # within-tolerance pairs to processed_count on every outer iteration,
        # inflating the counter and triggering the 90 % break after just the
        # first element was examined. The length_groups dict and total_pairs
        # calculation were also unused after the loop was fixed.
        # Solution: move the counter increment inside the inner loop so it
        # only advances for pairs that were actually evaluated, and check
        # the threshold after the inner loop completes for each f1.
        total_pairs = sum(
            1 for i in range(len(usernames))
            for j in range(i + 1, len(usernames))
            if abs(len(str(usernames[i].text)) - len(str(usernames[j].text))) <= 5
        )
        processed_count = 0

        for i, f1 in enumerate(usernames):
            text1 = str(f1.text)

            for f2 in usernames[i + 1:]:
                text2 = str(f2.text)

                # Skip if lengths differ significantly (optimization)
                if abs(len(text1) - len(text2)) > 5:
                    continue

                processed_count += 1
                similarity = difflib.SequenceMatcher(None, text1, text2).ratio()
                if similarity >= threshold:
                    f1.text += f" (Likely alias: {f2.text})"

            # Only break after completing an entire f1 row, not mid-row
            if total_pairs > 0 and processed_count / total_pairs >= 0.9:
                break

    @staticmethod
    def apply_confidence_decay(fact: Any):
        """Phase 3: Reduces confidence for older data (5% per year)"""
        current_year = datetime.now().year
        
        if not hasattr(fact, 'text'): 
            return
            
        year_match = re.search(r'\b(20\d{2})\b', str(fact.text))
        
        if year_match:
            data_year = int(year_match.group(1))
            
            years_old = max(0, current_year - data_year)
            
            if years_old > 0:
                penalty = min(0.5, years_old * 0.05)
                
                current_score = getattr(fact, 'confidence_score', 0.5)
                fact.confidence_score = max(0.1, current_score - penalty)


class CrossReferenceEngine:
    """Engine for cross-referencing search results with Leak-Lookup data"""
    
    def __init__(self):
        self.match_threshold = 0.8
    
    def perform_cross_reference(self, 
                               search_results: List[Dict], 
                               leak_lookup_findings: List[Dict]) -> Dict[str, CrossReferenceResult]:
        """
        Match search results with Leak-Lookup breach data
        
        Args:
            search_results: Results from HARVESTING stage (search engine responses)
            leak_lookup_findings: Breach database information
            
        Returns:
            Dictionary mapping target emails to their cross-reference matches
        """
        
        # Extract all emails from search results
        search_emails = set()
        for result in search_results:
            if isinstance(result, dict):
                organic_list = result.get('organic', [])
                
                for item in organic_list:
                    if isinstance(item, dict):
                        snippet = str(item.get('snippet', ''))
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                        search_emails.update(emails)
        
        # Match against Leak-Lookup findings
        matches: Dict[str, CrossReferenceResult] = {}
        
        for finding in leak_lookup_findings:
            if not isinstance(finding, dict):
                continue
                
            target = str(finding.get('target', ''))
            databases = finding.get('breached_databases', [])
            
            # Check if this target matches any search result email
            for search_email in search_emails:
                if self._is_match(search_email, target):
                    match_key = search_email.lower()
                    
                    matches[match_key] = CrossReferenceResult(
                        target_email=search_email,
                        search_source=f"Leak-Lookup match for {target}",
                        leaked_databases=list(databases) if isinstance(databases, list) else [str(databases)],
                        confidence_boost=0.3  # Boost from leak correlation
                    )
        
        return matches
    
    def _is_match(self, email1: str, email2: str) -> bool:
        """Check if two emails match (considering Gmail dot normalization)"""
        e1 = email1.lower().strip()
        e2 = email2.lower().strip()
        
        # Exact match
        if e1 == e2:
            return True
        
        # Gmail dot normalization (john.doe@gmail.com == johndoe@gmail.com)
        if '@' in e1 and '@' in e2:
            domain1 = e1.split('@')[1]
            domain2 = e2.split('@')[1]
            
            if domain1 == domain2:  # Same domain
                local1 = e1.split('@')[0].replace('.', '')
                local2 = e2.split('@')[0].replace('.', '')
                
                if local1 == local2:
                    return True
        
        return False


class AnalystAgent:
    """Main analyst agent for OSINT verification"""
    
    @staticmethod
    def calculate_confidence_score(fact: VerifiedFact, cross_matches: List[CrossReferenceResult]) -> float:
        """
        Calculate final confidence score with leak correlation boost
        
        Base scores from match type:
            - Exact email match: 0.8
            - Partial domain match: 0.6  
            - Name-only match: 0.4
        
        + Confidence boost from leak lookup correlation (if applicable)
        
        Final score clamped between 0 and 1.0
        """
        
        base_score = fact.confidence_score
        
        # Apply boost from cross-references
        if cross_matches:
            max_boost = max(m.confidence_boost for m in cross_matches)
            # BUGFIX: multiplying max_boost by match count caused scores well above 1.0
            # before the clamp (e.g. 5 matches × 0.3 = +1.5). Cap total boost at
            # max_boost so one strong cross-reference is the ceiling, not a multiplier.
            base_score += min(max_boost, max_boost * len(cross_matches))

        # Clamp score between 0 and 1.0
        return min(1.0, max(0.0, base_score))


def verify_search_results(
    search_results: List[Dict], 
    leak_lookup_findings: List[Dict] = None,
    min_confidence_threshold: float = 0.6
) -> Dict[str, Any]:
    """
    Main verification function that processes search results and applies confidence scoring
    
    Args:
        search_results: Results from HARVESTING stage (raw JSON responses)
        leak_lookup_findings: Optional Leak-Lookup breach data for cross-referencing
        min_confidence_threshold: Minimum score for high-confidence classification
        
    Returns:
        Dictionary with verified results, cross-references, and statistics
    """
    
    if leak_lookup_findings is None:
        leak_lookup_findings = []
    
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
                   for src in str(match.search_source).split(":"))
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
    
    # --- PHASE 3: FORENSIC TRIGGER ---
    fact_extractor = FactExtractor()
    fact_extractor.fuzzy_match_usernames(verified_facts)
    for fact in verified_facts:
        fact_extractor.apply_confidence_decay(fact)
    # ---------------------------------
    
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


# NOTE (LOW): the module-level FactExtractor instance was never referenced by
# any code path; verify_search_results creates its own local instance at call
# time. Removed to avoid confusion about which instance is canonical.


class AnalysisReport:
    """Wrapper class that main.py and Scribe expect to see"""
    
    def __init__(self, report_dict):
        self.report = report_dict
        self.target_name = report_dict.get('target', 'Unknown Target')
        raw_facts = report_dict.get('verified_results', [])
        self.facts = []
        for f in raw_facts:
            raw = f.__dict__ if hasattr(f, '__dict__') else f
            if isinstance(raw, dict):
                text = raw.get('text', '')
                if ':' in text:
                    parts = text.split(':', 1)
                    fact_type = parts[0].strip().upper().replace(' ', '_')
                    fact_value = parts[1].strip()
                else:
                    fact_type = 'FINDING'
                    fact_value = text
                source_str = raw.get('source', '')
                self.facts.append({
                    'type': fact_type,
                    'value': fact_value,
                    'confidence': raw.get('confidence_score', raw.get('confidence', 0.5)),
                    'sources': [source_str] if isinstance(source_str, str) else list(source_str),
                    'is_verified': raw.get('is_verified', False),
                    'cross_references': raw.get('cross_references', []),
                    'metadata': raw.get('metadata', {})
                })
            else:
                self.facts.append(raw)
        # Additional attributes expected by tests
        self.verified_entities = report_dict.get('verified_entities', [])
        self.conflicts = report_dict.get('conflicts', [])

def analyze_osint_data(harvest_output, privacy_mode: str = 'public'):
    """
    Bridge function for main.py to execute the ANALYST stage.
    This ensures proper data flow from HARVESTING to ANALYST stage.
    """

    # -----------------------------------------------------------------
    # 1) Get a DatabaseManager (singleton) and make sure tables exist
    # -----------------------------------------------------------------
    db_manager = get_db_manager()
    db_manager.initialize_tables()          # guarantees that `verified_facts` exists

    # -----------------------------------------------------------------
    # 2) Gather raw harvest data
    # -----------------------------------------------------------------
    raw_data = []
    if hasattr(harvest_output, 'search_results') and harvest_output.search_results:
        for result in harvest_output.search_results:
            data = getattr(result, 'results_raw', None)
            if data:
                if privacy_mode == 'private':
                    data = _apply_privacy_filter(data)
                raw_data.append(data)

    # -----------------------------------------------------------------
    # 3) Run verification / cross‑reference
    # -----------------------------------------------------------------
    leak_lookup_results = []
    if hasattr(harvest_output, 'leak_lookup_results') and harvest_output.leak_lookup_results:
        leak_lookup_results = [r.__dict__ for r in harvest_output.leak_lookup_results]

    report_dict = verify_search_results(
        search_results=raw_data,
        leak_lookup_findings=leak_lookup_results,
        min_confidence_threshold=0.6
    )

    # -----------------------------------------------------------------
    # 4) Insert every verified fact into the database
    # -----------------------------------------------------------------
    try:
        fact_items = report_dict.get('verified_results', [])
        print(f"Found {len(fact_items)} fact items to store")
        print("report_dict keys:", list(report_dict.keys()))

        for fact in fact_items:
            # Map fields that `insert_verified_fact` expects
            fact_type       = fact.get('type', 'email')
            fact_value      = fact.get('text', '')
            fact_confidence = fact.get('confidence_score',
                                      fact.get('confidence', 0.5))
            fact_sources    = str(fact.get('sources', []))
            if not isinstance(fact_sources, str):
                fact_sources = str(list(fact_sources) if hasattr(fact_sources, '__iter__') else [])

            # Build a short description (use provided or create one)
            description = fact.get('description', '')
            if not description:
                parts = []
                if 'cross_references' in fact and fact['cross_references']:
                    parts.append(f"Cross‑referred with {len(fact['cross_references'])} sources")
                if isinstance(fact.get('metadata'), dict) and fact['metadata'].get('extraction_type'):
                    parts.append(f"Extracted via: {fact['metadata']['extraction_type']}")
                description = " | ".join(parts)

            # Insert the record
            success = db_manager.insert_verified_fact(
                ticket_id=harvest_output.ticket_id,
                fact_type=fact_type,
                value=fact_value,
                confidence=fact_confidence,
                sources=fact_sources,
                description=description
            )
            if not success:
                print(f"Insert failed for fact: {fact}")

        print(f"Successfully saved {len(fact_items)} verified facts to database")

    except Exception as e:
        # Any unexpected error is logged – the pipeline will continue with a clean failure message
        logging.exception("Failed to save facts to database")

    # -----------------------------------------------------------------
    # 5) Return the report wrapper
    # -----------------------------------------------------------------
    return AnalysisReport(report_dict)

def detect_consensus(candidates: List[CandidateEntity], 
                     threshold: float = 0.8) -> Dict[str, Any]:
    """
    Detect consensus among candidate entities based on matched fields
    
    Function analyzes multiple candidate entities to determine the following:
    - Which candidates have sufficient consensus to be considered verified
    - Conflicting data that requires manual review
    - High-confidence matches across sources
    
    Args:
        candidates: List of CandidateEntity objects to analyze
        threshold: Minimum consensus score for verification (default 0.8)
        
    Returns:
        Dictionary containing:
        - 'verified_entities': Candidates meeting consensus threshold
        - 'conflicts': Entities with conflicting data from multiple sources
        - 'low_confidence': Candidates below confidence threshold
        - 'consensus_metrics': Summary statistics about the analysis
        
    Logic:
        1. Group candidates by entity_id for comparison
        2. Calculate consensus scores based on field agreement
        3. Identify conflicts where sources disagree significantly
        4. Classify entities into verified, conflicting, and low-confidence buckets
    """
    
    result = {
        "verified_entities": [],
        "conflicts": [],
        "low_confidence": [],
        "consensus_metrics": {
            "total_candidates": len(candidates),
            "sources_analyzed": set(),
            "avg_confidence_score": 0.0
        }
    }
    
    if not candidates:
        return result
    
    # Calculate average confidence score for metrics
    total_score = sum(c.confidence_score for c in candidates)
    result["consensus_metrics"]["avg_confidence_score"] = total_score / len(candidates)
    
    # Collect all source types analyzed
    for candidate in candidates:
        result["consensus_metrics"]["sources_analyzed"].update(candidate.source_types)
    
    # Classify each candidate based on consensus and confidence
    for candidate in candidates:
        if candidate.confidence_score >= threshold:
            # High confidence - likely verified
            if len(candidate.source_types) >= 2:
                # Multiple sources agree = strong consensus
                result["verified_entities"].append({
                    "entity_id": candidate.entity_id,
                    "confidence_score": candidate.confidence_score,
                    "source_count": len(candidate.source_types),
                    "matched_fields": candidate.matched_fields
                })
            else:
                # Single source but high confidence
                result["verified_entities"].append({
                    "entity_id": candidate.entity_id,
                    "confidence_score": candidate.confidence_score,
                    "source_count": len(candidate.source_types),
                    "matched_fields": candidate.matched_fields
                })
        elif candidate.confidence_score >= 0.5:
            # Medium confidence - pending verification
            result["low_confidence"].append({
                "entity_id": candidate.entity_id,
                "confidence_score": candidate.confidence_score,
                "source_count": len(candidate.source_types),
                "matched_fields": candidate.matched_fields
            })
        else:
            # Low confidence - may be conflicting data
            result["conflicts"].append({
                "entity_id": candidate.entity_id,
                "confidence_score": candidate.confidence_score,
                "source_count": len(candidate.source_types),
                "matched_fields": candidate.matched_fields,
                "requires_manual_review": True
            })
    
    # Convert set to list for JSON serialization
    result["consensus_metrics"]["sources_analyzed"] = list(
        result["consensus_metrics"]["sources_analyzed"]
    )
    
    return result


def detect_conflicts(data: List[Dict], field_name: str) -> List[Dict]:
    """
    Detect conflicts in data based on a specific field
    
    This function identifies when multiple sources provide different values
    for the same field, indicating potential data quality issues.
    
    Args:
        data: List of data items to analyze
        field_name: Name of the field to check for conflicts
        
    Returns:
        List of conflict dictionaries containing:
        - 'field': The conflicting field name
        - 'conflicts': List of different values found
        - 'source_count': Number of sources with different values
    """
    
    # Collect all values for this field from the data
    values = [item["value"] for item in data if item.get("field") == field_name]
    
    # If we have multiple unique values, it's a conflict
    unique_values = list(set(values))
    
    if len(unique_values) > 1:
        return [{
            "field": field_name,
            "conflicts": unique_values,
            "source_count": len(unique_values),
            "severity": "high" if len(unique_values) >= 3 else "medium"
        }]
    
    return []


def _apply_privacy_filter(data: Any) -> Any:
    """
    Apply privacy filtering to anonymize sensitive PII
    
    This function strips or masks personally identifiable information
    based on privacy mode settings, while maintaining analysis capability.
    
    Args:
        data: Input data which can be dict, list, string, or other types
        
    Returns:
        Filtered data with PII anonymized/masked appropriately
    """
    
    if isinstance(data, str):
        # Mask email addresses
        masked_email = re.sub(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            '[EMAIL_REDACTED]',
            data
        )
        
        # Mask phone numbers (common US format)
        masked_phone = re.sub(
            r'\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?)[-.\s]?\d{3}[-.\s]?\d{4}\b',
            '[PHONE_REDACTED]',
            masked_email
        )
        
        # Mask IP addresses
        masked_ip = re.sub(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            '[IP_REDACTED]',
            masked_phone
        )
        
        return masked_ip
    
    elif isinstance(data, dict):
        # Recursively filter dictionary values
        filtered = {}
        for key, value in data.items():
            if isinstance(value, (str, dict, list)):
                filtered[key] = _apply_privacy_filter(value)
            else:
                filtered[key] = value
        
        return filtered
    
    elif isinstance(data, list):
        # Recursively filter list items
        return [_apply_privacy_filter(item) for item in data]
    
    # For other types (numbers, booleans, etc.), return as-is
    return data


# Example usage and testing
async def run_demo():
    """Demonstrate analyst capabilities"""
    
    # Simulate search results from HARVESTING stage (Serper.dev 'organic' list format)
    sample_search_results = [
        {
            "organic": [
                {
                    "title": "John Doe - LinkedIn Profile",
                    "link": "https://linkedin.com/in/johndoe123",
                    "snippet": "Software engineer at TechCorp, based in San Francisco. Email: john.doe@example.com"
                },
                {
                    "title": "test@example.com - Breach Database Entry",
                    "link": "https://breachdb.example.com/entry/12345",
                    "snippet": "Email found in 2023 data breach collection"
                }
            ]
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
        print(f"Confidence Score: {verified['confidence_score']:.2f}{boost_info}")


if __name__ == "__main__":
    import asyncio
    
    # Run demo if executed directly
    asyncio.run(run_demo())
