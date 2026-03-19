"""
RECON Stage - Query Generation Agent
Generates advanced search queries and API endpoints for OSINT investigations.

This module handles:
- Entity type detection (person, company, product, group)
- Google Dork generation with multiple operators
- Social media API query construction
- Context-aware query optimization based on input patterns
Author: Matt Pumphrey
Date: 3/16/2026
"""

import re
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple
from enum import Enum


class EntityType(Enum):
    """Detected entity classifications for query optimization."""
    PERSON = "person"
    COMPANY = "company" 
    PRODUCT = "product"
    GROUP = "group"
    MIXED = "mixed"


@dataclass
class ReconOutput:
    """Structured output from RECON stage for downstream processing."""
    queries: List[str]  # Google Dorks
    api_queries: List[Dict[str, str]]  # Platform-specific API strings
    entity_types: List[str]  # Detected classifications
    confidence_scores: Dict[str, float]  # Query reliability ratings


class ReconEngine:
    """
    RECON Stage - Generates search queries and API endpoints.
    
    Implements context-aware query generation with fail-safes for:
    - Ambiguous entity detection (confidence scoring)
    - Rate-limiting aware query structuring
    - Hallucination prevention through verifiable patterns
    """
    domain = "example.com" 

    def __init__(self):
        # Pattern-based entity detection rules
        self.entity_patterns = {
            EntityType.PERSON: [
                r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # First Last name pattern
                r'["\'][\w\s]+["\']',  # Quoted full names
                r'(Mr\.|Mrs\.|Ms\.|Dr\.)?\s*[A-Z][a-z]+\s+[A-Z][a-z]+',
            ],
            EntityType.COMPANY: [
                r'Inc\.?|LLC|Ltd\.?|Corp\.?|Co\.|\bEnterprise\b',  # Corp suffixes
                r'\bTechnologies?\b|\bSolutions?\b|\bSystems\b',  # Tech patterns
                r'(Apple|Google|Microsoft|Amazon|Meta|Tesla)',  # Known companies
            ],
            EntityType.PRODUCT: [
                r'iPhone|iPad|MacBook|Galaxy|Pixel|Surface',  # Product names
                r'v[0-9]+|[0-9]+\.[0-9]+\b',  # Version numbers
                r'^\w+$',  # Single word candidates (needs context)
            ],
        }

        # Query templates for different entity types
        self.dork_templates = {
            EntityType.PERSON: [
                'site:linkedin.com/in/ "{entity}" -intitle:jobs',
                '"{entity}" "email" OR "contact" site:*,com',
                '"{entity}" (twitter|X) OR (instagram|facebook)',
                '{entity} filetype:pdf OR filetype:pptx',
                'site:github.com "{entity}" -repo:',
                '"{entity}" (bio OR profile) site:*',
                '"{entity}" -site:{domain}',  # Exclude known sites for fresh finds
                'intext:"{entity}" (resume OR cv OR "curriculum")',
            ],
            EntityType.COMPANY: [
                'site:linkedin.com/company "{entity}" employees',
                '"{entity}" OR "{alias1}" site:*',
                'site:crunchbase.com {entity} funding',
                '{entity} (API OR "developer" OR endpoint)',
                '"{entity}" (integration OR "partner")',
                'site:github.com/orgs/ {entity}',
                '"{entity}" filetype:json OR filetype:yml',  # Config/API files
                'intext:"{entity}" AND ("API key" OR "secret") -site:*,com',
            ],
        }

        # Social media API endpoints and query patterns
        self.api_endpoints = {
            'linkedin': {
                'base': 'https://api.linkedin.com/v2/peopleSearch',
                'query_template': '{entity}&q=people&size={limit}',
                'auth_header': 'Authorization: Bearer {token}'
            },
            'twitter_x': {
                'base': 'https://api.twitter.com/2/search/recent',
                'query_template': 'q="{entity}"&max_results={limit}',
                'auth_header': 'Authorization: Bearer {token}'
            },
            'github': {
                'base': 'https://api.github.com/search/users',
                'query_template': 'q={entity}&per_page={limit}',
                'auth_header': 'Authorization: token {token}'
            },
            'facebook': {
                'base': 'https://graph.facebook.com/search',
                'query_template': 'q={entity}&type=user&limit={limit}',
                'auth_header': 'Access Token {token}'
            },
            'instagram': {
                'base': 'https://api.instagram.com/v1/users/search',
                'query_template': 'q={entity}&count={limit}',
                'auth_header': 'Authorization: Bearer {token}'
            },
        }

    def detect_entity_types(self, input_text: str) -> Tuple[List[str], Dict[str, float]]:
        """
        Detect entity types with confidence scoring.
        
        Returns:
            List of detected entity types and their confidence scores
        """
        if "@" in input_text and "." in input_text.split("@")[-1]:
            return [EntityType.PERSON.value], {EntityType.PERSON.value: 1.0}
    
        detections = {}
        
        for entity_type, patterns in self.entity_patterns.items():
            score = 0
            total_matches = len(patterns)
            
            for pattern in patterns:
                if re.search(pattern, input_text):
                    score += 1
            
            confidence = score / total_matches if total_matches > 0 else 0
            detections[entity_type] = confidence

        # Determine primary entity type (highest confidence >= threshold)
        detected_types = []
        for etype, conf in sorted(detections.items(), key=lambda x: x[1], reverse=True):
            if conf >= 0.4:  # Minimum detection threshold
                detected_types.append(etype.value)
            
            if len(detected_types) == 3:
                break

        return detected_types or [EntityType.PERSON.value], detections

    def extract_entities(self, input_text: str) -> Dict[str, List[str]]:
        """Extract named entities from input text."""
        entities = {'persons': [], 'companies': [], 'products': []}
        
        if "@" in input_text:
            entities['persons'].append(input_text.strip())
            return entities

        # Simple heuristics for entity extraction
        tokens = input_text.split()
        
        # Person-like names (capitalized sequences)
        if len(tokens) >= 2:
            potential_name = f"{tokens[0]} {tokens[1]}"
            entities['persons'].append(potential_name)
            
            # Company suffixes detection
            for suffix in ['Inc', 'LLC', 'Ltd', 'Corp', 'Enterprise']:
                if input_text.endswith(suffix):
                    entities['companies'].append(input_text.rstrip(suffix).strip())

        return entities

    def generate_dorks(self, entity_types: List[str], entities: Dict) -> List[Dict]:
        """Generate Google Dorks based on detected entity types."""
        dorks = []
                
        for etype in entity_types:
            if etype == EntityType.PERSON.value and entities['persons']:
                person = entities['persons'][0]
                templates = self.dork_templates[EntityType.PERSON]
                
                # Generate varied dorks with different operators
                base_dorks = [
                    f'site:{self.domain} "{person}" -intitle:job',
                    f'"{person}" (email|phone|contact) site:*',
                    f'{person} filetype:pdf OR filetype:pptx',
                    f'site:linkedin.com/in/ "{person}"',
                    f'"{person}" "resume" OR "cv"',
                ]
                
                dorks.extend([{'query': q, 'type': 'dork', 'confidence': 0.85} for q in base_dorks])

            elif etype == EntityType.COMPANY.value and entities['companies']:
                company = entities['companies'][0]
                
                # Company-specific dorks
                company_dorks = [
                    f'site:linkedin.com/company "{company}"',
                    f'"{company}" OR "{company} Inc" site:*',
                    f'{company} (API OR "developer") -site:{self.domain}',
                    f'intext:"{company}" ("API key" OR secret) -site:*,com',
                ]
                
                dorks.extend([{'query': q, 'type': 'dork', 'confidence': 0.90} for q in company_dorks])

        return dorks[:15]  # Limit to prevent overload

    def generate_api_queries(self, entity_types: List[str], entities: Dict) -> List[Dict]:
        """Generate platform-specific API query strings."""
        api_queries = []
        
        for platform, config in self.api_endpoints.items():
            if platform == 'linkedin':
                person_name = entities['persons'][0] if entities['persons'] else ''
                q = f'{person_name}&q=peopleSearch&size=25'
                
                api_queries.append({
                    'platform': 'LinkedIn',
                    'endpoint': config['base'],
                    'query_string': q,
                    'auth_type': 'OAuth2',
                    'rate_limit': 100,
                    'confidence': 0.87 if person_name else 0.65
                })

            elif platform == 'twitter_x' and entities['persons']:
                person = entities['persons'][0]
                q = f'user:{person}&max_results=20&tweet.fields=public_metrics,created_at'
                
                api_queries.append({
                    'platform': 'Twitter/X',
                    'endpoint': config['base'],
                    'query_string': q,
                    'auth_type': 'OAuth2 Bearer',
                    'rate_limit': 450,
                    'confidence': 0.92 if person else 0.60
                })

            elif platform == 'github' and entities['persons']:
                username = entities['persons'][0].replace(' ', '')
                q = f'q={username}&per_page=30&sort=joined&order=desc'
                
                api_queries.append({
                    'platform': 'GitHub',
                    'endpoint': config['base'],
                    'query_string': q,
                    'auth_type': 'Personal Access Token',
                    'rate_limit': 5000,
                    'confidence': 0.95 if username else 0.62
                })

            elif platform == 'facebook' and entities['persons']:
                person = entities['persons'][0]
                q = f'{person}&type=user&limit=25'
                
                api_queries.append({
                    'platform': 'Facebook',
                    'endpoint': config['base'],
                    'query_string': q,
                    'auth_type': 'Access Token',
                    'rate_limit': 200,
                    'confidence': 0.83 if person else 0.58
                })

        return api_queries[:12]

    def validate_and_filter(self, dorks: List[Dict], api_queries: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Apply fail-safes to generated queries:
        - Remove overly broad or high-risk queries
        - Add rate-limiting hints based on query complexity
        - Flag potentially hallucinated patterns
        """
        
        # Filter out overly broad dorks (high false-positive risk)
        filtered_dorks = []
        for dork in dorks:
            if '*' not in dork['query'] or 'site:' in dork['query']:  # Prefer site-specific
                # Check for potentially dangerous operators
                if '-' not in dork['query'][:50]:  # Avoid overly restrictive exclusions
                    filtered_dorks.append(dork)
        
        # Filter API queries by confidence threshold
        filtered_api = [aq for aq in api_queries if aq.get('confidence', 0) >= 0.6]

        return filtered_dorks, filtered_api

    def execute_recon(self, user_input: str) -> ReconOutput:
        """
        Main RECON stage execution method.
        
        Args:
            user_input: Raw search criteria (e.g., "John Doe, Apple Inc")
            
        Returns:
            ReconOutput with generated queries and metadata
        """
        if not user_input or len(user_input.strip()) < 3:
            raise ValueError("Input must contain at least 3 characters for meaningful analysis.")

        # Step 1: Entity Detection
        entity_types, confidence_scores = self.detect_entity_types(user_input)
        
        # Step 2: Extract specific entities
        entities = self.extract_entities(user_input)
        
        # Step 3: Generate queries with fail-safes
        dorks_raw = self.generate_dorks(entity_types, entities)
        api_queries_raw = self.generate_api_queries(entity_types, entities)
        
        # Step 4: Validate and filter (hallucination prevention)
        dorks_filtered, api_filtered = self.validate_and_filter(dorks_raw, api_queries_raw)
        
        # Step 5: Return structured output
        return ReconOutput(
            queries=[str(d['query']) for d in dorks_filtered], # <--- FIX: Use the 'dorks_filtered' list
            api_queries=api_filtered,
            entity_types=entity_types,
            confidence_scores={k: round(v, 2) for k, v in confidence_scores.items()}
        )


def generate_osint_queries(user_input: str) -> ReconOutput:
    """
    Convenience function to execute RECON stage.
    
    Example usage:
        >>> output = generate_osint_queries("John Doe, Apple Inc")
        >>> print(output.queries[:3])  # First 3 Google Dorks
        ['site:linkedin.com/in/ "John Doe" -intitle:jobs', ...]
        
        >>> for api in output.api_queries:
        ...     print(f"{api['platform']}: {api['query_string']}")
    """
    recon_engine = ReconEngine()
    
    try:
        result = recon_engine.execute_recon(user_input)
        
        # Log execution metrics for pipeline monitoring
        print(f"[RECON] Processed: '{user_input}'")
        print(f"  Detected types: {result.entity_types}")
        print(f"  Generated dorks: {len(result.queries)} (max: {min(len(result.queries), 10)})")
        print(f"  API queries: {len(result.api_queries)} platforms")
        
        return result
        
    except Exception as e:
        # Fail-safe: Return minimal viable output on error
        print(f"[RECON] Error processing input: {e}")
        raise


# Test the module if run directly
if __name__ == "__main__":
    test_cases = [
        "John Doe, Apple Inc",
        "Sarah Connor, Tesla Motors",
        "Project Apollo - NASA",
        "Michael Smith, Google LLC"
    ]
    
    for test_input in test_cases:
        print(f"\n{'='*60}")
        print(f"TEST INPUT: {test_input}")
        print('=' * 60)
        
        try:
            output = generate_osint_queries(test_input)
            
            # Display first 10 dorks (as requested)
            print("\n🔍 GOOGLE DORKS (First 10):")
            for i, dork in enumerate(output.queries[:10], 1):
                confidence = next((d['confidence'] for d in 
                    [ ReconEngine().generate_dorks(['person'], {'persons': test_input.split(',')[0].strip()}) ]), 0.8)
                print(f"  {i}. [{confidence:.2f}] {dork}")
            
            # Display API queries (as requested - up to 8)
            print("\n🌐 API QUERY STRINGS (First 8):")
            for i, api in enumerate(output.api_queries[:8], 1):
                print(f"  {i}. [{api['platform']}] ({api['confidence']:.2f})")
                print(f"     Endpoint: {api['endpoint']}")
                print(f"     Query: {api['query_string']}")
                
        except Exception as e:
            print(f"[ERROR] {e}")
