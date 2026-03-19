"""Tests for the SCRIBE stage - Report generation functionality"""

import pytest
from os.path import exists
from osint_scribe_stage import (
    generate_osint_report, 
    ReportGenerationResult,
    ReportFormat
)


class TestScribeStage:
    """Test suite for report generation"""
    
    @pytest.mark.asyncio
    async def test_generate_pdf_only(self):
        """Test PDF-only report generation"""
        
        mock_analysis = MockAnalysisReport()
        
        result = await generate_osint_report(
            analysis_data=mock_analysis,
            target_name="John Doe",
            format=ReportFormat.PDF,
            output_path="./test_output/test_john_doe"
        )
        
        assert isinstance(result, ReportGenerationResult)
        assert result.pdf_generated is True
        assert exists("./test_output/test_john_doe.pdf")
        
    @pytest.mark.asyncio
    async def test_generate_html_only(self):
        """Test HTML-only report generation"""
        
        mock_analysis = MockAnalysisReport()
        
        result = await generate_osint_report(
            analysis_data=mock_analysis,
            target_name="John Doe",
            format=ReportFormat.HTML,
            output_path="./test_output/test_john_doe"
        )
        
        assert isinstance(result, ReportGenerationResult)
        assert result.html_generated is True
        assert exists("./test_output/test_john_doe.html")
        
    @pytest.mark.asyncio
    async def test_generate_both_formats(self):
        """Test generation of both PDF and HTML reports"""
        
        mock_analysis = MockAnalysisReport()
        
        result = await generate_osint_report(
            analysis_data=mock_analysis,
            target_name="John Doe",
            format=ReportFormat.BOTH,
            output_path="./test_output/test_john_doe"
        )
        
        assert isinstance(result, ReportGenerationResult)
        assert result.pdf_generated is True
        assert result.html_generated is True
        assert exists("./test_output/test_john_doe.pdf")
        assert exists("./test_output/test_john_doe.html")
        
    @pytest.mark.asyncio
    async def test_empty_analysis_data(self):
        """Test report generation with minimal/empty analysis data"""
        
        mock_analysis = MockAnalysisReport(verified_entities=[])
        
        result = await generate_osint_report(
            analysis_data=mock_analysis,
            target_name="Empty Target",
            format=ReportFormat.HTML,  # HTML is more forgiving for testing
            output_path="./test_output/test_empty"
        )
        
        assert isinstance(result, ReportGenerationResult)
        assert result.html_generated is True
        
    @pytest.mark.asyncio
    async def test_report_content_structure(self):
        """Verify generated reports contain required sections"""
        
        mock_analysis = MockAnalysisReport()
        
        result = await generate_osint_report(
            analysis_data=mock_analysis,
            target_name="John Doe",
            format=ReportFormat.HTML,
            output_path="./test_output/test_content"
        )
        
        if result.html_generated:
            html_path = "./test_output/test_john_doe.html"
            
            # Read generated HTML and verify structure
            with open(html_path, 'r') as f:
                content = f.read()
                
            # Check for required sections in report
            assert "Executive Summary" in content or "executive-summary" in content.lower()
            assert any(section in content.lower() for section in [
                "people/identity", "social media", "web intelligence", 
                "digital infrastructure", "geolocation", "public records"
            ])


class MockAnalysisReport:
    """Mock object for AnalysisReport testing"""
    
    def __init__(self, verified_entities=None):
        self.verified_entities = verified_entities or [
            {
                "entity_id": "test_001",
                "source_types": ["linkedin_profile"],
                "matched_fields": {
                    "name": {"value": "John Doe", "consensus_score": 0.95},
                    "company": {"value": "Apple Inc", "consensus_score": 0.9}
                },
                "confidence_score": 0.87,
                "verification_status": "VERIFIED"
            }
        ]
        self.potential_matches = []
        self.conflicts = []
        self.manual_review_queue = []
        self.confidence_summary = {
            "average_confidence": 0.85,
            "verification_rate": 0.9,
            "conflict_rate": 0.1
        }


@pytest.fixture(scope="function")
def cleanup_test_output():
    """Cleanup test output files after each test"""
    
    yield
    
    import shutil
    if exists("./test_output"):
        shutil.rmtree("./test_output")
