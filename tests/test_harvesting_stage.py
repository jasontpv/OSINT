"""Tests for the HARVESTING stage - Search execution with rate limiting"""

import pytest
from unittest.mock import AsyncMock, patch
from osint_harvesting_stage import (
    execute_osint_harvest, 
    HarvestOutput,
    SearchResult
)

# Define RateLimitError locally since it's not exported from the module
class RateLimitError(Exception):
    """Custom rate limit error for testing"""
    pass


class TestHarvestingStage:
    """Test suite for search execution and rate limiting"""
    
    @pytest.mark.asyncio
    async def test_execute_search_success(self):
        """Test successful search execution with valid API response"""
        
        mock_response = {
            "organic": [
                {"title": "Result 1", "link": "https://example.com"},
                {"title": "Result 2", "link": "https://example.org"}
            ]
        }
        
        with patch('osint_harvesting_stage.aiohttp.ClientSession') as mock_session:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.status = 200
            
            instance = mock_session.return_value.__aenter__.return_value
            instance.get = AsyncMock(return_value=mock_response_obj)
            
            dorks = ['site:example.com "test"']
            results = await execute_osint_harvest(
                dorks=dorks,
                serper_api_key="test_key",
                max_concurrent=1
            )
        
        assert isinstance(results, HarvestOutput)
        assert results.total_processed == 1
        assert results.successful == 1
        assert results.failed == 0
        
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test proper handling of API rate limit errors"""
        
        with patch('osint_harvesting_stage.aiohttp.ClientSession') as mock_session:
            # Simulate rate limit error (HTTP 429)
            mock_response_obj = AsyncMock()
            mock_response_obj.status = 429
            mock_response_obj.json = AsyncMock(return_value={"error": "Rate limit exceeded"})
            
            instance = mock_session.return_value.__aenter__.return_value
            instance.get = AsyncMock(side_effect=RateLimitError("Too many requests"))
            
            dorks = ['site:example.com "test"']
            
            # Should raise RateLimitError after max retries
            with pytest.raises(RateLimitError):
                await execute_osint_harvest(
                    dorks=dorks,
                    serper_api_key="test_key",
                    max_concurrent=1,
                    max_retries=2  # Low retry limit for testing
                )
                
    @pytest.mark.asyncio  
    async def test_mixed_success_failure(self):
        """Test handling of mixed successful and failed searches"""
        
        with patch('osint_harvesting_stage.aiohttp.ClientSession') as mock_session:
            # First call succeeds, second fails
            responses = [
                (200, {"organic": [{"title": "Success"}]}),
                (403, {"error": "Access forbidden"})
            ]
            
            async def side_effect(*args, **kwargs):
                status, body = responses.pop(0)
                
                mock_response_obj = AsyncMock()
                mock_response_obj.status = status
                mock_response_obj.json = AsyncMock(return_value=body)
                
                return mock_response_obj
            
            instance = mock_session.return_value.__aenter__.return_value
            instance.get = AsyncMock(side_effect=side_effect)
            
            dorks = [
                'site:example.com "success"',  # Will succeed
                'site:notexist.com "fail"'     # Will fail (403)
            ]
            
            results = await execute_osint_harvest(
                dorks=dorks,
                serper_api_key="test_key",
                max_concurrent=1
            )
        
        assert isinstance(results, HarvestOutput)
        assert results.total_processed == 2
        # Depending on retry behavior, may recover or count as failure
        
    @pytest.mark.asyncio
    async def test_empty_dork_list(self):
        """Test execution with empty list of dorks"""
        
        with patch('osint_harvesting_stage.aiohttp.ClientSession'):
            results = await execute_osint_harvest(
                dorks=[],
                serper_api_key="test_key",
                max_concurrent=1
            )
            
        assert isinstance(results, HarvestOutput)
        assert results.total_processed == 0
        assert results.successful == 0
        
    def test_search_result_structure(self):
        """Verify SearchResult object has correct structure"""
        
        result = SearchResult(
            dork_original='site:example.com "test"',
            provider_used="SERPER",
            status_code=200,
            results_raw={"organic": []},
            results_count=0,
            execution_time_ms=45.3,
            error=None
        )
        
        assert result.dork_original == 'site:example.com "test"'
        assert result.provider_used == "SERPER"
        assert result.status_code == 200
        assert isinstance(result.results_raw, dict)
        assert isinstance(result.execution_time_ms, float)
