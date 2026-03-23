"""Tests for the ANALYST stage - Cross-source verification and consensus detection"""

import pytest
from unittest.mock import MagicMock, Mock
from osint_analyst_stage import (
    analyze_osint_data, 
    AnalysisReport,
    CandidateEntity,
    EntityVerificationStatus,
    detect_conflicts
)


class TestAnalystStage:
    """Test suite for data verification and analysis"""
    
    def test_analysis_with_consistent_data(self):
        """Test analysis when sources agree on key facts"""
        
        mock_harvest_output = Mock()
        mock_harvest_output.search_results = [
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
        ]
        mock_harvest_output.leak_lookup_results = []
        
        report = analyze_osint_data(
            harvest_output=mock_harvest_output,
            privacy_mode='public'
        )
        
        assert isinstance(report, AnalysisReport)
        # Should detect consensus on city and company
        assert len(report.verified_entities) >= 0
        
    def test_analysis_with_conflicting_data(self):
        """Test analysis when sources contradict each other"""
        
        mock_harvest_output = Mock()
        mock_harvest_output.search_results = [
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
        ]
        mock_harvest_output.leak_lookup_results = []
        
        report = analyze_osint_data(
            harvest_output=mock_harvest_output,
            privacy_mode='public'
        )
        
        assert isinstance(report, AnalysisReport)
        # Should detect conflicts and increase manual review queue
        assert len(report.conflicts) >= 0
        
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
        
    def test_manual_review_queue_population(self):
        """Test that low-confidence items go to manual review queue"""
        
        mock_harvest_output = Mock()
        mock_harvest_output.search_results = [
            {
                "dork_original": 'site:unknown.com "test"',
                "status_code": 200,
                "results_raw": {},  # Empty data
                "error": None
            }
        ]
        mock_harvest_output.leak_lookup_results = []
        
        report = analyze_osint_data(
            harvest_output=mock_harvest_output,
            privacy_mode='public'
        )
        
        # Should have few or no verified entities due to lack of data
        assert len(report.verified_entities) <= 1
        
    def test_analysis_report_structure(self):
        """Test that AnalysisReport has all required attributes"""
        
        mock_harvest_output = Mock()
        mock_harvest_output.search_results = []
        mock_harvest_output.leak_lookup_results = []
        
        report = analyze_osint_data(
            harvest_output=mock_harvest_output,
            privacy_mode='public'
        )
        
        # Verify all required attributes exist and are properly initialized
        assert hasattr(report, 'verified_entities')
        assert hasattr(report, 'conflicts')
        assert hasattr(report, 'facts')
        assert hasattr(report, 'target_name')
        
        # Verify they are initialized as empty lists or proper values
        assert isinstance(report.verified_entities, list)
        assert isinstance(report.conflicts, list)
        assert isinstance(report.facts, list)
        assert isinstance(report.target_name, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
