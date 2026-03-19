#!/usr/bin/env python3
"""
OSINT Intelligence Analyst Stage
=================================
Processes raw JSON results from HARVESTING stage to produce verified intelligence.

Features:
- Cross-referencing across multiple sources
- Confidence scoring (Truth Score 0-100%)
- Intelligent deduplication
- Privacy mode with local LLMs (Ollama/LM Studio)
Author: Matt Pumphrey
Date: 3/16/2026
"""

import os
import json
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from enum import Enum

# Local LLM integration for privacy mode
try:
    from ollama import chat as ollama_chat
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


class PrivacyMode(Enum):
    """Privacy levels for analyst operations"""
    PUBLIC = "public"      # Use cloud LLMs (OpenAI, etc.)
    LOCAL = "local"        # Use local Ollama/LM Studio
    HYBRID = "hybrid"      # Mix of both based on sensitivity


class ConfidenceLevel(Enum):
    """Confidence scoring levels"""
    VERIFIED = 100         # All sources agree (3+ sources)
    HIGHLY_LIKELY = 85     # Multiple sources agree (2-3 sources)
    LIKELY = 70            # Single source with strong indicators
    UNVERIFIED = 45        # Weak or contradictory evidence
    SUSPICIOUS = 25        # Low-quality or conflicting data


@dataclass
class Fact:
    """Represents a discovered fact with metadata"""
    fact_type: str              # e.g., "email", "username", "location"
    value: str                  # The actual fact value
    sources: List[str]          # Which tools found this
    confidence_score: float     # 0-100 truth score
    context: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass 
class IntelligenceReport:
    """Consolidated intelligence output"""
    target_name: str
    facts: List[Fact]
    confidence_summary: Dict[str, float]  # Average per fact type
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    
    def to_json(self) -> str:
        return json.dumps({
            "target": self.target_name,
            "facts": [f.__dict__ for f in self.facts],
            "confidence_summary": self.confidence_summary,
            "timestamp": self.analysis_timestamp.isoformat()
        }, indent=2)


class CrossReferenceEngine:
    """Core engine for cross-referencing data across sources"""
    
    # Field type mappings for normalization
    FIELD_MAPPINGS = {
        'email': ['email', 'emails', 'e-mail', 'contact_email'],
        'username': ['username', 'usernames', 'handle', 'social_handle', 'alias'],
        'location': ['location', 'city', 'country', 'address', 'geolocation'],
        'bio_keywords': ['bio', 'about', 'description', 'biography'],
        'phone': ['phone', 'telephone', 'mobile', 'contact_phone'],
        'company': ['company', 'organization', 'employer', 'affiliation'],
        'ip_addresses': ['ip', 'ips', 'network_ips', 'associated_ips'],
    }
    
    def __init__(self):
        self.source_cache: Dict[str, List[Fact]] = defaultdict(list)

    def extract_facts_from_source(self, source_data: Any, tool_name: str) -> List[Fact]:
        """Extract structured facts from raw tool output (Handles Lists and Serper.dev JSON structure)
        
        This method handles various input formats including:
        - Direct list of result dictionaries
        - Dictionary with 'organic' key containing search results (Serper.dev format)
        - Nested data structures
        
        Args:
            source_data: Any type of data structure (dict, list, or single item)
            tool_name: Name of the tool that produced this data
            
        Returns:
            List[Fact]: Extracted facts from the source data
        """
        extracted = []
        
        # Handle Serper.dev JSON structure - extract 'organic' list first if present
        # This is critical for properly parsing Google Search results
        if isinstance(source_data, dict) and 'organic' in source_data:
            items_to_process = source_data['organic']
        elif isinstance(source_data, list):
            items_to_process = source_data
        else:
            # Convert single item to list for processing
            items_to_process = [source_data] if not isinstance(source_data, dict) or not self._is_empty_dict(source_data) else []

        for item in items_to_process:
            if not isinstance(item, dict):
                continue

            # 1. Email extraction
            emails = self._extract_field(item, ['email', 'emails'])
            for email in emails:
                extracted.append(Fact(fact_type='email', value=email, sources=[tool_name], confidence_score=90.0))
            
            # 2. Username extraction
            usernames = self._extract_field(item, ['username', 'handle', 'title'])
            for username in usernames:
                extracted.append(Fact(fact_type='username', value=username, sources=[tool_name], confidence_score=85.0))
            
            # 3. Location extraction
            locations = self._extract_field(item, ['location', 'city', 'country'])
            for loc in locations:
                extracted.append(Fact(fact_type='location', value=loc, sources=[tool_name], confidence_score=80.0))
            
            # 4. Company extraction
            companies = self._extract_field(item, ['company', 'organization'])
            for company in companies:
                extracted.append(Fact(fact_type='company', value=company, sources=[tool_name], confidence_score=90.0))
            
            # 5. IP addresses extraction
            ips = self._extract_field(item, ['ip', 'ips', 'network_ips'])
            for ip in ips:
                extracted.append(Fact(fact_type='ip_addresses', value=ip, sources=[tool_name], confidence_score=98.0))
            
            # 6. EVIDENCE LINKS
            links = self._extract_field(item, ['link', 'url'])
            for link in links:
                extracted.append(Fact(fact_type='source_link', value=link, sources=[tool_name], confidence_score=100.0))

            # 7. Bio/Keywords - handle Serper.dev 'snippet' field
            bio_text = self._extract_field(item, ['bio', 'about', 'description', 'snippet'])
            if bio_text:
                # Joining if bio_text is a list
                value_str = " ".join(bio_text) if isinstance(bio_text, list) else str(bio_text)
                extracted.append(Fact(fact_type='bio_keywords', value=value_str, sources=[tool_name], confidence_score=75.0, context={"raw_bio": value_str}))

        return extracted
        
    def _is_empty_dict(self, data: Any) -> bool:
        """Check if the data is an empty or nearly-empty dictionary"""
        if not isinstance(data, dict):
            return False
        # Consider it "empty" if it has no meaningful keys for processing
        meaningful_keys = {'organic', 'data', 'results', 'items'}
        return all(key.lower() not in str(k).lower() for k in data.keys())

    def normalize_field_name(self, field_name: str) -> str:
        """Normalize various field names to standard types"""
        field_lower = field_name.lower().strip()
        for fact_type, variations in self.FIELD_MAPPINGS.items():
            if any(variation in field_lower for variation in variations):
                return fact_type
        return "other"

    def _extract_field(self, source_data: Any, field_patterns: List[str]) -> List[str]:
        """Extract field values using multiple patterns
        
        This method handles both string and list values robustly.
        
        Args:
            source_data: The data structure to extract from (must be dict-like for get())
            field_patterns: List of possible field names to search for
            
        Returns:
            List[str]: Extracted field values as strings
        """
        results = []
        
        # Ensure we're working with a dict for the first extraction attempt
        if not isinstance(source_data, dict):
            return []
            
        for pattern in field_patterns:
            value = source_data.get(pattern)
            if value is None:
                continue
                
            if isinstance(value, str):
                results.append(value)
            elif isinstance(value, list):
                # Convert each item to string, filtering out non-string items
                for item in value:
                    try:
                        results.append(str(item))
                    except (TypeError, ValueError):
                        continue
        
        # Also search nested keys - handle various nesting levels
        if 'data' in source_data and isinstance(source_data['data'], dict):
            for pattern in field_patterns:
                if pattern in source_data['data']:
                    value = source_data['data'][pattern]
                    if isinstance(value, str):
                        results.append(value)
                    elif isinstance(value, list):
                        for item in value:
                            try:
                                results.append(str(item))
                            except (TypeError, ValueError):
                                continue
        
        # Additional search in 'organic' key (for Serper.dev results that might be nested deeper)
        if 'organic' in source_data and isinstance(source_data['organic'], list):
            for item in source_data['organic'][:5]:  # Limit to first 5 items
                if not isinstance(item, dict):
                    continue
                for pattern in field_patterns:
                    value = item.get(pattern)
                    if value is None:
                        continue
                    if isinstance(value, str):
                        results.append(value)
                    elif isinstance(value, list):
                        for subitem in value:
                            try:
                                results.append(str(subitem))
                            except (TypeError, ValueError):
                                pass
        
        return [r.strip() for r in results if r and len(r.strip()) > 0]
    
    def cross_reference(self, all_facts: List[Tuple[str, Dict]]) -> List[Fact]:
        """Cross-reference facts across multiple sources"""
        all_extracted = []
        
        # Extract facts from each source
        for tool_name, source_data in all_facts:
            extracted = self.extract_facts_from_source(source_data, tool_name)
            all_extracted.extend(extracted)
            
            # Cache for later deduplication
            for fact in extracted:
                self.source_cache[fact.fact_type].append(fact)
        
        # Now cross-reference and assign confidence scores
        final_facts = []
        for fact_type, facts in self.source_cache.items():
            if not facts:
                continue
            
            # Group by value (for deduplication)
            value_groups = defaultdict(list)
            for fact in facts:
                value_groups[fact.value].append(fact)
            
            # Create consolidated facts with confidence scoring
            for value, matching_facts in value_groups.items():
                num_sources = len(matching_facts)
                
                # Calculate confidence based on source agreement
                if num_sources >= 3:    
                    confidence = ConfidenceLevel.VERIFIED.value
                elif num_sources == 2:
                    confidence = ConfidenceLevel.HIGHLY_LIKELY.value
                else:
                    confidence = ConfidenceLevel.LIKELY.value
                
                # Adjust confidence based on data quality indicators
                final_confidence = self._adjust_confidence(confidence, matching_facts)
                
                consolidated = Fact(
                    fact_type=fact_type,
                    value=value,
                    sources=[f.sources[0] for f in matching_facts],  # Unique source names
                    confidence_score=final_confidence,
                    context={
                        "source_count": num_sources,
                        "original_source_names": list(set(f.sources[0] for f in matching_facts))
                    }
                )
                final_facts.append(consolidated)
        
        # Clear cache after processing
        self.source_cache.clear()
        
        return final_facts
    
    def _adjust_confidence(self, base_score: float, facts: List[Fact]) -> float:
        """Adjust confidence based on additional quality indicators"""
        score = float(base_score)
        
        # Boost for high-quality sources (tools with good reputation)
        quality_sources = {'shodan', 'builtwith'}
        if all(f.sources[0].lower() in quality_sources for f in facts):
            score += 5
        
        # Reduce confidence for contradictory data
        values = [f.value.lower() for f in facts]
        unique_values = len(set(values))
        if unique_values > len(values) * 0.5:  # More than half are different
            score -= 20
        
        return max(10, min(100, score))


class LLMAnalyzer:
    """Privacy-mode aware LLM analyzer for intelligence extraction"""
    
    def __init__(self):
        self.privacy_mode = PrivacyMode.LOCAL if OLLAMA_AVAILABLE else PrivacyMode.PUBLIC
        
    def set_privacy_mode(self, mode: str) -> None:
        """Set the privacy mode"""
        if mode.lower() == 'local':
            if not OLLAMA_AVAILABLE:
                print("Warning: Ollama not available. Switching to public mode.")
                self.privacy_mode = PrivacyMode.PUBLIC
            else:
                self.privacy_mode = PrivacyMode.LOCAL
        elif mode.lower() == 'public':
            self.privacy_mode = PrivacyMode.PUBLIC
        elif mode.lower() == 'hybrid':
            self.privacy_mode = PrivacyMode.HYBRID
    
    def analyze_bio_keywords(self, bio_text: str) -> Dict[str, List[str]]:
        """Extract keywords from bio text using local LLM for privacy"""
        if self.privacy_mode in [PrivacyMode.LOCAL, PrivacyMode.HYBRID] and OLLAMA_AVAILABLE:
            return self._local_llm_analysis(bio_text)
        else:
            # Use heuristic-based extraction (public mode fallback)
            return self._heuristic_extraction(bio_text)
    
    def _local_llm_analysis(self, bio_text: str) -> Dict[str, List[str]]:
        """Use Ollama for keyword extraction (privacy-focused)"""
        try:
            response = ollama_chat(
                model='mistral',  
                messages=[{
                    'role': 'system',
                    'content': '''You are an OSINT analysis assistant. Extract the following from the bio text:
1. SKILLS - List any professional skills mentioned
2. INTERESTS - List personal interests or hobbies
3. LOCATIONS - Any locations, cities, countries mentioned
4. ORGANIZATIONS - Companies, schools, organizations mentioned

Format your response as JSON with keys: "skills", "interests", "locations", "organizations"'''
                }, {
                    'role': 'user',
                    'content': bio_text[:500] 
                }]
            )   
            
            # Parse the JSON response
            if isinstance(response, dict) and 'message' in response:
                msg_content = response['message']['content']
                try:
                    return json.loads(msg_content)
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse LLM output. Raw: {msg_content}")
                    
            return {"skills": [], "interests": [], "locations": [], "organizations": []}
            
        except Exception as e:
            print(f"Local LLM analysis failed: {e}. Falling back to heuristics.")
            return self._heuristic_extraction(bio_text)
    
    def _heuristic_extraction(self, bio_text: str) -> Dict[str, List[str]]:
        """Basic keyword extraction without LLM (fallback for public mode)"""
        # Convert to lowercase for processing
        text = bio_text.lower()
        
        return {
            "skills": self._extract_skills(text),
            "interests": self._extract_interests(text),
            "locations": self._extract_locations(text),
            "organizations": self._extract_organizations(text)
        }
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills using keyword patterns"""
        skill_patterns = [
            r'\b(programming|python|javascript|java|c\+\+|rust)\b',
            r'\b(machine learning|ai|data science)\b',
            r'\b(analysis|research|investigation)\b',
            r'\b(management|leadership|team lead)\b',
        ]
        
        skills = []
        for pattern in skill_patterns:
            matches = re.findall(pattern, text)
            skills.extend(matches)
        
        return list(set(skills))
    
    def _extract_interests(self, text: str) -> List[str]:
        """Extract interests from bio"""
        interest_keywords = ['hobby', 'interest', 'passion', 'love', 'enjoy']
        interests = []
        for keyword in interest_keywords:
            if keyword in text:
                # Look at surrounding words (up to 10 before/after)
                start = max(0, text.find(keyword) - 20)
                end = min(len(text), text.find(keyword) + 30)
                phrase = text[start:end].strip()
                if len(phrase) > 5:
                    interests.append(phrase[:100])
        
        return list(set(interests))[:5]
    
    def _extract_locations(self, text: str) -> List[str]:
        """Extract location mentions"""
        # Common city/country patterns (simplified)
        locations = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
        return [loc for loc in locations if len(loc.split()) == 1 and len(loc) > 2][:5]
    
    def _extract_organizations(self, text: str) -> List[str]:
        """Extract organization/company names"""
        org_patterns = [
            r'\b(Inc\.|Corp\.|LLC|Ltd\.|Co\.)',
            r'@[\w.-]+(?:\.\w{2,})+',  # Email domains as proxy for orgs
        ]
        
        orgs = []
        text_lower = text.lower()
        
        # Check for common company indicators
        if any(org in text_lower for org in ['company', 'organization', 'at']):
            # Try to extract following words (simplified)
            start_idx = 0
            while True:
                idx = text.find(' at ', start_idx)
                if idx == -1:
                    break
                end_idx = idx + 50
                potential_org = text[idx+4:end_idx].split()[0] if text[idx+4:end_idx] else ''
                if len(potential_org) > 2:
                    orgs.append(potential_org)
                start_idx = idx + 1
        
        return list(set(orgs))[:5]


class DeduplicationEngine:
    """Intelligent deduplication for merging duplicate records"""
    
    def __init__(self):
        self.fingerprint_cache = {}
        
    def generate_fingerprint(self, fact: Fact) -> str:
        """Generate a unique fingerprint for deduplication comparison"""
        # Normalize the value for comparison
        normalized_value = fact.value.lower().strip()
        
        if fact.fact_type == 'email':
            # Email normalization (remove dots for gmail, lowercase)
            if '@gmail.com' in normalized_value:
                username, domain = normalized_value.split('@')
                username_clean = username.replace('.', '')
                normalized_value = f"{username_clean}@{domain}"
        
        # Generate hash fingerprint
        return hashlib.md5(f"fact_{fact.fact_type}_{normalized_value}".encode()).hexdigest()
    
    def merge_duplicates(self, facts: List[Fact]) -> List[Fact]:
        """Merge duplicate facts using fuzzy matching"""
        merged = {}  # key by fact_type + normalized value
        
        for fact in facts:
            fingerprint = self.generate_fingerprint(fact)
            
            if fingerprint in merged:
                existing = merged[fingerprint]
                
                # Merge sources (avoid duplicates)
                new_sources = [s for s in fact.sources if s not in existing.sources]
                all_sources = list(set(existing.sources + new_sources))
                
                # Average confidence scores
                avg_confidence = (existing.confidence_score * len(existing.sources) + 
                                fact.confidence_score * len(fact.sources)) / \
                               (len(all_sources) if all_sources else 1)
                
                # Merge context information
                existing.context['merged'] = True
                existing.context['source_count'] = len(all_sources)
                existing.context['all_source_names'] = list(set(existing.context.get('all_source_names', []) + new_sources))
                existing.confidence_score = avg_confidence
                
            else:
                merged[fingerprint] = fact
        
        return list(merged.values())


class OSINTAnalystStage:
    """Main analyst stage orchestrator"""
    
    def __init__(self, privacy_mode: str = 'local'):
        self.cross_reference_engine = CrossReferenceEngine()
        self.llm_analyzer = LLMAnalyzer()
        self.deduplication_engine = DeduplicationEngine()
        
        # Set privacy mode
        self.llm_analyzer.set_privacy_mode(privacy_mode)
        
        # Configuration
        self.output_dir = os.path.join(os.getcwd(), 'analyst_output')
        os.makedirs(self.output_dir, exist_ok=True)
    
    def process_harvest_results(self, raw_data: Dict[str, List[Dict]]) -> IntelligenceReport:
        """Process raw harvesting results through analyst pipeline"""
        
        print(f"\n{'='*60}")
        print("🔍 OSINT ANALYST STAGE - Starting Analysis")
        print(f"Privacy Mode: {self.llm_analyzer.privacy_mode.value}")
        print(f"{'='*60}\n")
        
        # Step 1: Cross-reference all sources
        print("[1/4] Cross-referencing data across sources...")
        cross_reference_facts = self.cross_reference_engine.cross_reference(
            list(raw_data.items())
        )
        print(f"      Found {len(cross_reference_facts)} unique facts from {len(raw_data)} sources\n")
        
        # Step 2: Apply deduplication
        print("[2/4] Deduplicating records...")
        deduplicated = self.deduplication_engine.merge_duplicates(cross_reference_facts)
        print(f"      Reduced to {len(deduplicated)} unique facts (merged duplicates)\n")
        
        # Step 3: LLM-enhanced analysis (privacy mode aware)
        print("[3/4] Enhancing with local LLM analysis...")
        enhanced_facts = self._enhance_with_llm(deduplicated)
        print(f"      Keywords extracted from bio data\n")
        
        # Step 4: Generate confidence summary
        print("[4/4] Calculating confidence metrics...")
        target_name = raw_data.get('_target', 'unknown')
        report = IntelligenceReport(
            target_name=target_name,
            facts=enhanced_facts,
            confidence_summary=self._calculate_confidence_summary(enhanced_facts)
        )
        
        print(f"\n✅ Analysis complete for: {target_name}")
        return report
    
    def _enhance_with_llm(self, facts: List[Fact]) -> List[Fact]:
        """Enhance facts with LLM-extracted keywords (privacy mode aware)"""
        enhanced = []
        
        for fact in facts:
            if fact.fact_type == 'bio_keywords' and fact.context.get('raw_bio'):
                # Extract structured keywords using local LLM
                bio_text = fact.context['raw_bio']
                extracted = self.llm_analyzer.analyze_bio_keywords(bio_text)
                
                # Add to facts list
                for keyword_type in ['skills', 'interests', 'locations', 'organizations']:
                    if extracted.get(keyword_type):
                        enhanced.append(Fact(
                            fact_type=keyword_type,
                            value=", ".join(extracted[keyword_type]),
                            sources=fact.sources,
                            confidence_score=70.0,  # LLM-assigned baseline
                            context={"extraction_method": "local_llm"}
                        ))
            
            enhanced.append(fact)
        
        return enhanced
    
    def _calculate_confidence_summary(self, facts: List[Fact]) -> Dict[str, float]:
        """Calculate average confidence by fact type"""
        type_scores = defaultdict(list)
        
        for fact in facts:
            type_scores[fact.fact_type].append(fact.confidence_score)
        
        summary = {
            ft: round(sum(scores) / len(scores), 1) 
            for ft, scores in type_scores.items()
        }
        
        return summary
    
    def save_report(self, report: IntelligenceReport, filename: Optional[str] = None) -> str:
        """Save intelligence report to file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = re.sub(r'[^\w\-]', '_', report.target_name)[:50]
            filename = f"analyst_report_{safe_name}_{timestamp}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report.to_json())
        
        print(f"\n📄 Report saved to: {filepath}")
        return filepath
    
    def display_summary(self, report: IntelligenceReport):
        """Display analysis summary in terminal"""
        print("\n" + "="*60)
        print("INTELLIGENCE ANALYSIS SUMMARY")
        print("="*60)
        
        print(f"\nTarget: {report.target_name}")
        print(f"Analysis Date: {report.analysis_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Privacy Mode: {self.llm_analyzer.privacy_mode.value.upper()}")
        
        print("\n📊 FACTS BY TYPE:")
        type_counts = defaultdict(int)
        for fact in report.facts:
            type_counts[fact.fact_type] += 1
        
        for ftype, count in sorted(type_counts.items()):
            avg_confidence = self._get_avg_confidence_for_type(report.facts, ftype)
            print(f"   • {ftype}: {count} facts (avg confidence: {avg_confidence:.0f}%)")
        
        print("\n🔐 HIGH CONFIDENCE FACTS (>85%):")
        high_conf = [f for f in report.facts if f.confidence_score >= 85]
        for fact in high_conf[:10]:  # Show first 10
            print(f"   • [{fact.fact_type}] {fact.value}")
            print(f"     Sources: {', '.join(fact.sources)}")
        
        if len(high_conf) > 10:
            print(f"   ... and {len(high_conf) - 10} more high-confidence facts")
        
        print("\n⚠️ LOW CONFIDENCE FACTS (<50%):")
        low_conf = [f for f in report.facts if f.confidence_score < 50]
        for fact in low_conf[:5]:
            print(f"   • [{fact.fact_type}] {fact.value} ({fact.confidence_score:.0f}%)")
        
        if len(low_conf) > 5:
            print(f"   ... and {len(low_conf) - 5} more low-confidence facts")
        
        print("\n" + "="*60)
    
    def _get_avg_confidence_for_type(self, facts: List[Fact], fact_type: str) -> float:
        """Get average confidence for a specific fact type."""
        type_facts = [f for f in facts if f.fact_type == fact_type]
        if not type_facts:
            return 0.0
        return sum(f.confidence_score for f in type_facts) / len(type_facts)


def load_harvest_results(filepath: str) -> Dict[str, List[Dict]]:
    """Load harvested results from a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """Main entry point for the analyst stage CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="OSINT Intelligence Analyst Stage - Process harvested data"
    )
    parser.add_argument('--input', '-i', type=str, 
                       help='Path to harvested results JSON file')
    parser.add_argument('--privacy-mode', '-p', type=str, default='local',
                       choices=['public', 'local', 'hybrid'],
                       help='Privacy mode for LLM analysis (default: local)')
    parser.add_argument('--output-dir', '-o', type=str, 
                       default=None, help='Output directory for reports')
    
    args = parser.parse_args()
    
    # Initialize analyst with privacy mode
    analyst = OSINTAnalystStage(privacy_mode=args.privacy_mode)
    
    if args.output_dir:
        analyst.output_dir = args.output_dir
    
    # Load input data (auto-detect latest if no file specified)
    if args.input:
        raw_data = load_harvest_results(args.input)
    else:
        harvest_dir = os.path.join(os.getcwd(), 'harvest_output')
        if not os.path.exists(harvest_dir):
            print("❌ Error: 'harvest_output' directory not found. Please specify input with -i.")
            return
            
        files = sorted([f for f in os.listdir(harvest_dir) 
                       if f.startswith('harvest_result_') and f.endswith('.json')])
        
        if not files:
            print("❌ No harvested results found in 'harvest_output'. Run HARVEST stage first.")
            return
        
        raw_data = load_harvest_results(os.path.join(harvest_dir, files[-1]))
    
    # Process through analyst pipeline
    report = analyst.process_harvest_results(raw_data)
    
    # Save and display results
    filepath = analyst.save_report(report)
    analyst.display_summary(report)


if __name__ == '__main__':
    main()

def analyze_osint_data(harvest_output, privacy_mode: str = 'local'):
    """
    Convenience function to execute the ANALYST stage.
    """
    # Everything inside this function MUST be indented 4 spaces
    analyst = OSINTAnalystStage(privacy_mode=privacy_mode)
    
    raw_data = {
        "_target": getattr(harvest_output, 'target_name', 'unknown'),
        "serper": [r.__dict__ for r in harvest_output.search_results],
        "leak_lookup": [r.__dict__ for r in harvest_output.leak_lookup_results]
    }
    
    return analyst.process_harvest_results(raw_data)

class AnalysisReport:
    """Wrapper class if main.py expects this specific object type"""
    def __init__(self, report):
        self.report = report
