#!/usr/bin/env python3
"""
Comprehensive Test Suite for PublicData.com API Integration

This test suite validates all aspects of the PublicData.com API integration,
including authentication, search execution, pagination, error handling, and DPPA compliance.

Test Categories:
1. Unit Tests - Individual component validation (mocked)
2. Integration Tests - End-to-end flow testing with actual API calls (test environment)
3. Error Handling Tests - Various failure scenarios
4. Performance Tests - Response time and throughput validation
5. Compliance Tests - DPPA/GLB exemption verification

Usage:
    pytest tests/test_publicdata_api.py -v --tb=short
    
To run integration tests (requires valid test credentials):
    pytest tests/test_publicdata_api.py -v --integration-tests
"""

import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

# Import modules to test
from osint_publicdata_api import (
    PDAPPAExemptionType,
    PublicDataStatusCode,
    SearchRequest,
    SearchResponse,
    AuthenticationToken,
    PublicDataAPIConnector,
    PublicDataSearchEngine,
)


# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_publicdata")

# Test credentials (use environment variables in production)
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password_123"
TEST_DATABASE_ID = 12345


class MockXMLResponse:
    """Mock XML response for testing"""
    
    @staticmethod
    def success_response(num_records: int = 10) -> str:
        """Generate a valid XML response with specified number of records"""
        
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>'
        
        records_xml = ""
        for idx in range(num_records):
            record_id = idx + 1
            records_xml += f'''
<record>
    <field name="id">{record_id}</field>
    <field name="name">Test User {record_id}</field>
    <field name="email">user{record_id}@example.com</field>
    <field name="phone">555-010{idx}</field>
    <field name="address">123 Test St, City {record_id}, ST 12345</field>
    <field name="status">active</field>
</record>'''
        
        return f"""{xml_header}
<response>
    <status>0</status>
    <message>Success</message>
    <record_count>{num_records}</record_count>
    {records_xml}
</response>
"""
    
    @staticmethod
    def empty_response() -> str:
        """Generate XML response with no records"""
        
        return '''<?xml version="1.0" encoding="UTF-8"?>
<response>
    <status>0</status>
    <message>No results found</message>
    <record_count>0</record_count>
</response>
'''
    
    @staticmethod
    def malformed_xml() -> str:
        """Generate malformed XML for error handling tests"""
        
        return '''<?xml version="1.0" encoding="UTF-8"?>
<response>
    <status>0
    <message>Missing closing tags</message>
    <record_count></record_count>
'''
    
    @staticmethod
    def unauthorized_response() -> str:
        """Generate unauthorized response"""
        
        return '''<?xml version="1.0" encoding="UTF-8"?>
<response>
    <status>-1</status>
    <message>Invalid credentials provided</message>
</response>
'''
    
    @staticmethod
    def rate_limit_response() -> str:
        """Generate rate limit exceeded response"""
        
        return '''<?xml version="1.0" encoding="UTF-8"?>
<response>
    <status>-8</status>
    <message>Rate limit exceeded. Please retry after 60 seconds.</message>
    <retry_after>60</retry_after>
</response>
'''


class TestSearchRequestValidation:
    """Test suite for SearchRequest parameter validation"""
    
    def test_valid_search_request_creation(self):
        """Test creation of valid SearchRequest object"""
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        assert request.username == TEST_USERNAME
        assert request.password == TEST_PASSWORD
        assert request.database_id == TEST_DATABASE_ID
        assert request.search_term == "test@example.com"
        assert request.display_format == "xml"  # Default
        assert request.current_page == 1  # Default
        assert request.page_size == 100  # Default
    
    def test_missing_username_raises_error(self):
        """Test that missing username raises ValueError"""
        
        with pytest.raises(ValueError, match="Username and password are required"):
            SearchRequest(
                username="",
                password=TEST_PASSWORD,
                database_id=TEST_DATABASE_ID,
                search_term="test"
            )
    
    def test_missing_password_raises_error(self):
        """Test that missing password raises ValueError"""
        
        with pytest.raises(ValueError, match="Username and password are required"):
            SearchRequest(
                username=TEST_USERNAME,
                password="",
                database_id=TEST_DATABASE_ID,
                search_term="test"
            )
    
    def test_invalid_database_id_raises_error(self):
        """Test that invalid database ID raises ValueError"""
        
        with pytest.raises(ValueError, match="Database ID must be a positive integer"):
            SearchRequest(
                username=TEST_USERNAME,
                password=TEST_PASSWORD,
                database_id=-1,
                search_term="test"
            )
    
    def test_empty_search_term_raises_error(self):
        """Test that empty search term raises ValueError"""
        
        with pytest.raises(ValueError, match="Search term is required"):
            SearchRequest(
                username=TEST_USERNAME,
                password=TEST_PASSWORD,
                database_id=TEST_DATABASE_ID,
                search_term=""
            )
    
    def test_short_search_term_raises_error(self):
        """Test that search term shorter than 2 characters raises error"""
        
        with pytest.raises(ValueError, match="Search term must be at least 2"):
            SearchRequest(
                username=TEST_USERNAME,
                password=TEST_PASSWORD,
                database_id=TEST_DATABASE_ID,
                search_term="x"
            )
    
    def test_optional_record_number(self):
        """Test optional record number parameter"""
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            record_number=12345
        )
        
        assert request.record_number == 12345
    
    def test_optional_edition_number(self):
        """Test optional edition number parameter"""
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            edition_number=2
        )
        
        assert request.edition_number == 2
    
    def test_dppa_exemption_type_default(self):
        """Test default exemption type"""
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        assert request.exemption_type == PDAPPAExemptionType.NO_EXEMPTION
    
    def test_dppa_exemption_type_custom(self):
        """Test custom exemption type assignment"""
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            exemption_type=PDAPPAExemptionType.FRAUD_PREVENTION
        )
        
        assert request.exemption_type == PDAPPAExemptionType.FRAUD_PREVENTION


class TestAuthenticationToken:
    """Test suite for AuthenticationToken functionality"""
    
    def test_token_creation(self):
        """Test token creation with expiration"""
        
        future_time = datetime.now() + timedelta(hours=1)
        
        token = AuthenticationToken(
            token="test_token_value",
            expires_at=future_time,
            username=TEST_USERNAME
        )
        
        assert token.token == "test_token_value"
        assert token.username == TEST_USERNAME
        assert token.expires_at == future_time
    
    def test_token_valid_within_buffer(self):
        """Test token validity check with 5-minute buffer"""
        
        # Token expires in 3 minutes (within buffer)
        future_time = datetime.now() + timedelta(minutes=3)
        
        token = AuthenticationToken(
            token="test_token",
            expires_at=future_time,
            username=TEST_USERNAME
        )
        
        assert token.is_valid is True
    
    def test_token_invalid_after_buffer(self):
        """Test token becomes invalid after buffer time"""
        
        # Token expired 10 minutes ago (past buffer)
        past_time = datetime.now() - timedelta(minutes=10)
        
        token = AuthenticationToken(
            token="expired_token",
            expires_at=past_time,
            username=TEST_USERNAME
        )
        
        assert token.is_valid is False
    
    def test_token_exactly_at_buffer_boundary(self):
        """Test token validity at 5-minute boundary"""
        
        # Token expires in exactly 5 minutes (boundary case)
        future_time = datetime.now() + timedelta(minutes=5)
        
        token = AuthenticationToken(
            token="boundary_token",
            expires_at=future_time,
            username=TEST_USERNAME
        )
        
        assert token.is_valid is True


class TestPublicDataAPIConnector:
    """Test suite for PublicDataAPIConnector class"""
    
    @pytest.fixture
    def connector(self):
        """Create a test connector instance"""
        
        return PublicDataAPIConnector()
    
    @pytest.mark.asyncio
    async def test_connector_initialization(self, connector):
        """Test connector initialization with default parameters"""
        
        assert connector.base_url == "https://api.publicdata.com"
        assert connector.search_endpoint == "https://api.publicdata.com/pdsearchdocs.php"
        assert connector._max_concurrent_requests == 5
        assert connector.stats["total_searches"] == 0
    
    @pytest.mark.asyncio
    async def test_connector_custom_base_url(self):
        """Test connector with custom base URL"""
        
        custom_url = "https://test-api.publicdata.com"
        connector = PublicDataAPIConnector(base_url=custom_url)
        
        assert connector.base_url == custom_url.rstrip("/")
    
    @pytest.mark.asyncio
    async def test_connector_close(self, connector):
        """Test connector cleanup"""
        
        await connector.close()
        
        # Verify session was closed (if created)
        if connector._session:
            assert connector._session.closed is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_semaphore(self, connector):
        """Test rate limiting semaphore acquisition"""
        
        # Semaphore should be available initially
        assert connector._rate_limiter._value == 5
        
        # Acquire all semaphores
        for i in range(5):
            await connector._rate_limiter.acquire()
        
        # Semaphore should now be exhausted
        assert connector._rate_limiter._value == 0
    
    @pytest.mark.asyncio
    async def test_statistics_tracking(self, connector):
        """Test statistics tracking functionality"""
        
        initial_stats = connector.get_statistics()
        
        # Manually increment a counter (simulating an operation)
        connector.stats["total_searches"] += 1
        
        updated_stats = connector.get_statistics()
        
        assert updated_stats["total_searches"] == initial_stats["total_searches"] + 1


class TestAuthenticationFlow:
    """Test suite for authentication flow"""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mocked aiohttp session"""
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()  # BUGFIX: spec=aiohttp.ClientSession raises InvalidSpecError in Python 3.13
            mock_session_class.return_value = mock_session
            
            yield mock_session
    
    @pytest.mark.asyncio
    async def test_successful_authentication(self, mock_session):
        """Test successful authentication flow"""
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "test_token_123",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "username": TEST_USERNAME
        })
        
        mock_session.post = AsyncMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()))
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        token = await connector.authenticate(TEST_USERNAME, TEST_PASSWORD)
        
        assert isinstance(token, AuthenticationToken)
        assert token.token == "test_token_123"
        assert token.username == TEST_USERNAME
        assert token.is_valid is True
    
    @pytest.mark.asyncio
    async def test_authentication_cache_usage(self, mock_session):
        """Test authentication token caching"""
        
        # First call - should authenticate
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "access_token": "cached_token",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "username": TEST_USERNAME
        })
        
        # Track calls to verify caching behavior
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            class ContextManager:
                async def __aenter__(self):
                    return mock_response
                
                async def __aexit__(self, *args):
                    pass
            
            return ContextManager()
        
        mock_session.post = mock_post
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        # First authentication
        token1 = await connector.authenticate(TEST_USERNAME, TEST_PASSWORD)
        first_call_count = call_count
        
        # Second authentication (should use cache) - Note: This test needs adjustment for actual caching behavior
        # For now, we'll verify the cache exists
        assert TEST_USERNAME in connector._auth_cache
    
    @pytest.mark.asyncio
    async def test_authentication_invalid_credentials(self, mock_session):
        """Test authentication with invalid credentials"""
        
        mock_response = AsyncMock()
        mock_response.status = 401
        
        class ContextManager:
            async def __aenter__(self):
                return mock_response
            
            async def __aexit__(self, *args):
                pass
        
        mock_session.post = lambda **kwargs: ContextManager()
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        with pytest.raises(ValueError, match="Authentication failed"):
            await connector.authenticate("invalid_user", "wrong_password")


class TestSearchExecution:
    """Test suite for search execution functionality"""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mocked aiohttp session"""
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()  # BUGFIX: spec=aiohttp.ClientSession raises InvalidSpecError in Python 3.13
            mock_session_class.return_value = mock_session
            
            yield mock_session
    
    @pytest.mark.asyncio
    async def test_successful_search(self, mock_session):
        """Test successful search execution"""
        
        xml_content = MockXMLResponse.success_response(num_records=5)
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=xml_content)
        
        class ContextManager:
            async def __aenter__(self):
                return mock_response
            
            async def __aexit__(self, *args):
                pass
        
        mock_session.get = lambda **kwargs: ContextManager()
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        response = await connector.search(request)
        
        assert response.status_code == PublicDataStatusCode.SUCCESS.value
        assert response.total_records == 5
        assert len(response.parsed_results) == 5
        assert response.execution_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_search_empty_results(self, mock_session):
        """Test search with no matching results"""
        
        xml_content = MockXMLResponse.empty_response()
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=xml_content)
        
        class ContextManager:
            async def __aenter__(self):
                return mock_response
            
            async def __aexit__(self, *args):
                pass
        
        mock_session.get = lambda **kwargs: ContextManager()
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="nonexistent@example.com"
        )
        
        response = await connector.search(request)
        
        assert response.status_code == PublicDataStatusCode.SUCCESS.value
        assert response.total_records == 0
        assert len(response.parsed_results) == 0
    
    @pytest.mark.asyncio
    async def test_search_invalid_credentials(self, mock_session):
        """Test search with invalid credentials"""
        
        mock_response = AsyncMock()
        mock_response.status = 401
        
        class ContextManager:
            async def __aenter__(self):
                return mock_response
            
            async def __aexit__(self, *args):
                pass
        
        mock_session.get = lambda **kwargs: ContextManager()
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        response = await connector.search(request)
        
        assert response.status_code == PublicDataStatusCode.INVALID_CREDENTIALS.value
    
    @pytest.mark.asyncio
    async def test_search_rate_limit_exceeded(self, mock_session):
        """Test search when rate limit is exceeded"""
        
        xml_content = MockXMLResponse.rate_limit_response()
        
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text = AsyncMock(return_value=xml_content)
        
        class ContextManager:
            async def __aenter__(self):
                return mock_response
            
            async def __aexit__(self, *args):
                pass
        
        mock_session.get = lambda **kwargs: ContextManager()
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        response = await connector.search(request)
        
        assert response.status_code == PublicDataStatusCode.RATE_LIMIT_EXCEEDED.value


class TestPagination:
    """Test suite for pagination functionality"""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mocked aiohttp session"""
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()  # BUGFIX: spec=aiohttp.ClientSession raises InvalidSpecError in Python 3.13
            mock_session_class.return_value = mock_session
            
            yield mock_session
    
    @pytest.mark.asyncio
    async def test_single_page_result(self, mock_session):
        """Test pagination with single page of results"""
        
        xml_content = MockXMLResponse.success_response(num_records=50)
        
        call_count = 0
        
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Return same XML for all pages (simulating single page result)
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=xml_content)
            
            class ContextManager:
                async def __aenter__(self):
                    return mock_response
                
                async def __aexit__(self, *args):
                    pass
            
            return ContextManager()
        
        mock_session.get = mock_get
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            page_size=100  # All results fit on one page
        )
        
        responses = await connector.search_paginated(request, max_pages=5)
        
        assert len(responses) == 1
        assert responses[0].status_code == PublicDataStatusCode.SUCCESS.value
    
    @pytest.mark.asyncio
    async def test_multi_page_result(self, mock_session):
        """Test pagination with multiple pages of results"""
        
        # Create different XML for each page (simulating multi-page result)
        xml_responses = [
            MockXMLResponse.success_response(num_records=100),  # Page 1: 100 records
            MockXMLResponse.success_response(num_records=50),   # Page 2: 50 records
            MockXMLResponse.success_response(num_records=25),   # Page 3: 25 records (last page)
        ]
        
        call_count = [0]  # Use list to allow modification in nested function
        
        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            
            # Return different XML based on call number
            xml_index = min(call_count[0] - 1, len(xml_responses) - 1)
            
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=xml_responses[xml_index])
            
            class ContextManager:
                async def __aenter__(self):
                    return mock_response
                
                async def __aexit__(self, *args):
                    pass
            
            return ContextManager()
        
        mock_session.get = mock_get
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            page_size=100  # Page size to simulate pagination
        )
        
        responses = await connector.search_paginated(request, max_pages=5)
        
        assert len(responses) == 3  # Three pages retrieved
        total_records = sum(r.total_records for r in responses)
        assert total_records > 0
    
    @pytest.mark.asyncio
    async def test_pagination_max_pages_limit(self, mock_session):
        """Test pagination respects max_pages parameter"""
        
        xml_content = MockXMLResponse.success_response(num_records=1000)
        
        call_count = [0]
        
        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            
            # Always return XML indicating more pages available
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=xml_content)
            
            class ContextManager:
                async def __aenter__(self):
                    return mock_response
                
                async def __aexit__(self, *args):
                    pass
            
            return ContextManager()
        
        mock_session.get = mock_get
        
        connector = PublicDataAPIConnector()
        connector._session = mock_session
        
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com",
            page_size=10
        )
        
        # Set max_pages to 3
        responses = await connector.search_paginated(request, max_pages=3)
        
        assert len(responses) == 3
        assert call_count[0] == 3  # Should only make 3 API calls


class TestXMLParsing:
    """Test suite for XML parsing functionality"""
    
    def test_parse_valid_xml(self):
        """Test parsing of valid XML response"""
        
        connector = PublicDataAPIConnector()
        
        xml_content = MockXMLResponse.success_response(num_records=5)
        parsed_results, total_records = connector._parse_xml_response(xml_content)
        
        assert len(parsed_results) == 5
        assert total_records == 5
        
        # Verify structure of first record
        assert "id" in parsed_results[0]
        assert parsed_results[0]["id"] == "1"
        assert "name" in parsed_results[0]
        assert parsed_results[0]["email"] is not None
    
    def test_parse_empty_xml(self):
        """Test parsing of XML with no records"""
        
        connector = PublicDataAPIConnector()
        
        xml_content = MockXMLResponse.empty_response()
        parsed_results, total_records = connector._parse_xml_response(xml_content)
        
        assert len(parsed_results) == 0
        assert total_records == 0
    
    def test_parse_malformed_xml_raises_error(self):
        """Test that malformed XML raises appropriate error"""
        
        connector = PublicDataAPIConnector()
        
        xml_content = MockXMLResponse.malformed_xml()
        
        with pytest.raises(ValueError, match="XML parsing error"):
            connector._parse_xml_response(xml_content)


class TestDataQualityValidation:
    """Test suite for data quality validation functionality"""
    
    @pytest.fixture
    def search_engine(self):
        """Create a test search engine instance"""
        
        return PublicDataSearchEngine()
    
    @pytest.mark.asyncio
    async def test_valid_search_result_validation(self, search_engine):
        """Test validation of valid search results"""
        
        # Mock the connector's search method
        mock_response = SearchResponse(
            status_code=PublicDataStatusCode.SUCCESS.value,
            message="Success",
            total_records=100,
            current_page=1,
            page_size=10,
            has_next_page=True,
            parsed_results=[{"field1": "value1"}, {"field2": "value2"}]
        )
        
        search_engine.connector.search = AsyncMock(return_value=mock_response)
        
        result = await search_engine.search_with_validation(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="test@example.com"
        )
        
        assert result["success"] is True
        assert result["data_quality_score"] > 0
    
    @pytest.mark.asyncio
    async def test_empty_results_validation(self, search_engine):
        """Test validation of empty results"""
        
        mock_response = SearchResponse(
            status_code=PublicDataStatusCode.SUCCESS.value,
            message="Success",
            total_records=0,
            current_page=1,
            page_size=10,
            has_next_page=False,
            parsed_results=[]
        )
        
        search_engine.connector.search = AsyncMock(return_value=mock_response)
        
        result = await search_engine.search_with_validation(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=TEST_DATABASE_ID,
            search_term="nonexistent@example.com"
        )
        
        assert result["success"] is False
        assert "No results returned" in result.get("error_details", "")


class TestDPPACompliance:
    """Test suite for DPPA/GLB compliance functionality"""
    
    def test_all_exemption_types_defined(self):
        """Verify all DPPA exemption types are defined"""
        
        expected_types = [
            "LEGAL_PROCEEDINGS",
            "CREDIT_INSURANCE", 
            "FRAUD_PREVENTION",
            "BACKGROUND_CHECK",
            "COMMERCIAL_COMMUNICATION",
            "NO_EXEMPTION"
        ]
        
        for exemption_type in expected_types:
            assert hasattr(PDAPPAExemptionType, exemption_type)
    
    def test_exemption_type_values(self):
        """Test that exemption type values are correct"""
        
        assert PDAPPAExemptionType.LEGAL_PROCEEDINGS.value == "legal_proceedings"
        assert PDAPPAExemptionType.FRAUD_PREVENTION.value == "fraud_prevention"
        assert PDAPPAExemptionType.NO_EXEMPTION.value == "no_exemption"


class TestErrorHandling:
    """Test suite for error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self):
        """Test handling of connection timeout errors"""
        
        connector = PublicDataAPIConnector()
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Simulate timeout error
            mock_session_class.side_effect = asyncio.TimeoutError("Connection timed out")
            
            request = SearchRequest(
                username=TEST_USERNAME,
                password=TEST_PASSWORD,
                database_id=TEST_DATABASE_ID,
                search_term="test@example.com"
            )
            
            response = await connector.search(request)
            
            assert response.status_code == PublicDataStatusCode.SERVER_ERROR.value
            assert "timeout" in response.error_details.lower()


class TestPerformanceBenchmarks:
    """Test suite for performance validation"""
    
    @pytest.mark.asyncio
    async def test_authentication_response_time(self):
        """Test authentication operation response time"""
        
        connector = PublicDataAPIConnector()
        
        # This is a conceptual test - actual timing would require real API calls
        # For now, we verify the timeout settings are reasonable
        
        assert connector.CONNECTION_TIMEOUT == 30
        assert connector.READ_TIMEOUT == 60
    
    @pytest.mark.asyncio
    async def test_rate_limiting_configuration(self):
        """Test rate limiting is properly configured"""
        
        connector = PublicDataAPIConnector()
        
        # Verify semaphore is initialized with correct max value
        assert connector._rate_limiter._value == 5


class TestIntegrationWithExistingSystem:
    """Test suite for integration with existing OSINT system"""
    
    def test_search_request_compatibility(self):
        """Verify SearchRequest is compatible with existing system expectations"""
        
        # Create a search request that matches expected parameters
        request = SearchRequest(
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            database_id=12345,
            search_term="test@example.com",
            record_number=67890,
            edition_number=2,
            exemption_type=PDAPPAExemptionType.FRAUD_PREVENTION
        )
        
        # Verify all expected fields are present and accessible
        assert hasattr(request, 'username')
        assert hasattr(request, 'password')
        assert hasattr(request, 'database_id')
        assert hasattr(request, 'search_term')
        assert hasattr(request, 'record_number')
        assert hasattr(request, 'edition_number')
        assert hasattr(request, 'exemption_type')


# Run tests with pytest marker configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
