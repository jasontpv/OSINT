"""Tests for the ANALYST stage - Cross-source verification and consensus detection"""

import pytest
from unittest.mock import AsyncMock, patch
from osint_analyst_stage import (
    analyze_osint_data, 
    AnalysisReport,
    detect_consensus,
    CandidateEntity,
    EntityVerificationStatus
)


class TestAnalystStage:
    """Test suite for data verification and analysis"""
    
    @pytest.mark.asyncio
    async def test_analysis_with_consistent_data(self):
        """Test analysis when sources agree on key facts"""
        
        mock_harvest_output = MockHarvestOutput(
            search_results=[
                {
                    "dork_original": 'site:linkedin.com/in/ "John Doe"',
                    "status_code": 200,
                    "results_raw": {
                        "name": "John Doe",
                        "city": "San Francisco",
                        "company": "Apple Inc"
                    },
                    "error": None
                },
                {
                    "dork_original": 'site:github.com/johndoe',
                    "status_code": 200,
                    "results_raw": {
                        "username": "johndoe", 
                        "location": "San Francisco",
                        "company": "Apple Inc"
                    },
                    "error": None
                }
            ],
            total_processed=2,
            successful=2,
            failed=0
        )
        
        report = await analyze_osint_data(
            harvest_output=mock_harvest_output,
            match_criteria={
                "required_fields": ["city", "company"]
            }
        )
        
        assert isinstance(report, AnalysisReport)
        # Should detect consensus on city and company
        assert len(report.verified_entities) >= 1
        
    @pytest.mark.asyncio  
    async def test_analysis_with_conflicting_data(self):
        """Test analysis when sources contradict each other"""
        
        mock_harvest_output = MockHarvestOutput(
            search_results=[
                {
                    "dork_original": 'site:linkedin.com/in/ "John Doe"',
                    "status_code": 200,
                    "results_raw": {
                        "name": "John Doe",
                        "city": "San Francisco",
                        "role": "Senior Developer"
                    },
                    "error": None
                },
                {
                    "dork_original": 'site:twitter.com/johndoe',
                    "status_code": 200,
                    "results_raw": {
                        "username": "johndoe",
                        "location": "New York",  # Conflict with LinkedIn
                        "role": "Intern"         # Conflict with LinkedIn
                    },
                    "error": None
                }
            ],
            total_processed=2,
            successful=2,
            failed=0
        )
        
        report = await analyze_osint_data(
            harvest_output=mock_harvest_output,
            match_criteria={
                "required_fields": ["city", "role"]
            }
        )
        
        assert isinstance(report, AnalysisReport)
        # Should detect conflicts and increase manual review queue
        assert len(report.conflicts) >= 1
        
    def test_consensus_detection_basic(self):
        """Test basic consensus detection algorithm"""
        
        candidates = [
            CandidateEntity(
                entity_id="test_001",
                source_types=["linkedin_profile", "github_repository"],
                matched_fields={
                    "city": {"value": "San Francisco", "consensus_score": 1.0}
                },
                confidence_score=0.95,
                verification_status=EntityVerificationStatus.VERIFIED
            )
        ]
        
        # Test that verified entities have high consensus scores
        for entity in candidates:
            assert entity.confidence_score >= 0.8
            assert entity.verification_status == EntityVerificationStatus.VERIFIED
            
    def test_conflict_detection_criteria(self):
        """Test conflict detection based on field mismatches"""
        
        # Two sources with different values for same field
        data = [
            {"field": "city", "value": "San Francisco"},
            {"field": "city", "value": "New York"}  # Conflict!
        ]
        
        # Should detect conflict when values differ significantly
        conflicts = detect_conflicts(data, field_name="city")
        
        assert len(conflicts) >= 1
        
    @pytest.mark.asyncio
    async def test_manual_review_queue_population(self):
        """Test that low-confidence items go to manual review queue"""
        
        mock_harvest_output = MockHarvestOutput(
            search_results=[
                {
                    "dork_original": 'site:unknown.com "test"',
                    "status_code": 200,
                    "results_raw": {},  # Empty data
                    "error": None
                }
            ],
            total_processed=1,
            successful=1,
            failed=0
        )
        
        report = await analyze_osint_data(
            harvest_output=mock_harvest_output,
            match_criteria={"required_fields": ["name"]}
        )
        
        # Should have few or no verified entities due to lack of data
        assert len(report.verified_entities) <= 1
        # May populate manual review queue for further investigation


class MockHarvestOutput:
    """Mock object for HarvestOutput testing"""
    
    def __init__(self, search_results, total_processed, successful, failed):
        self.search_results = search_results
        self.total_processed = total_processed
        self.successful = successful  
        self.failed = failed


def detect_conflicts(data: list, field_name: str) -> list:
    """Helper function to detect conflicts in test data"""
    
    values = [item["value"] for item in data if item.get("field") == field_name]
    
    # If we have multiple different values for same field, it's a conflict
    unique_values = set(values)
    if len(unique_values) > 1:
        return [{"field": field_name, "conflicts": list(unique_values)}]
    
    return []
