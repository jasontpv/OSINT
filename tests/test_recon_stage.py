"""Tests for the RECON stage - Query generation functionality"""

import pytest
from osint_recon_stage import generate_osint_queries, ReconOutput


class TestReconStage:
    """Test suite for query generation"""
    
    def test_generate_queries_valid_input(self):
        """Test basic query generation with valid input"""
        result = generate_osint_queries("John Doe")
        
        assert isinstance(result, ReconOutput)
        assert len(result.queries) >= 10
        assert len(result.api_queries) >= 8
        
    def test_generate_queries_mixed_input(self):
        """Test query generation with mixed entity types"""
        result = generate_osint_queries("John Doe, Apple Inc")
        
        assert isinstance(result, ReconOutput)
        # Should detect both person and company entities
        assert len(result.entity_types) >= 1
        
    def test_generate_queries_empty_input(self):
        """Test query generation with empty input"""
        result = generate_osint_queries("")
        
        # Should still return minimal queries but with low confidence
        assert isinstance(result, ReconOutput)
        
    def test_query_structure(self):
        """Verify generated queries have correct structure"""
        result = generate_osint_queries("Test Target")
        
        for query in result.queries:
            assert isinstance(query, str)
            assert len(query) > 0
            
    def test_api_query_format(self):
        """Verify API queries are properly formatted"""
        result = generate_osint_queries("John Doe")
        
        for api_query in result.api_queries:
            assert "endpoint" in api_query
            assert "query_string" in api_query
            assert len(api_query["endpoint"]) > 0
            assert len(api_query["query_string"]) > 0
            
    def test_confidence_scoring(self):
        """Test that confidence scores are properly assigned"""
        result = generate_osint_queries("John Doe")
        
        for query in result.queries:
            # Confidence scores should be between 0 and 1
            assert 0.0 <= result.confidence_scores.get(query, 0) <= 1.0
