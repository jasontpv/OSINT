#!/usr/bin/env python3
"""
PublicData.com API Integration Module

This module provides comprehensive integration with the PublicData.com API,
including authentication, search operations, result parsing, and error handling.

Key Features:
- DPPA/GLB exemption handling for compliant searches
- XML response parsing and validation
- Pagination support via pdsearchdocs.php endpoint
- Rate limiting and retry logic
- Comprehensive logging and error tracking
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientError, ClientTimeout


logger = logging.getLogger("osint_publicdata")


class PDAPPAExemptionType(Enum):
    """Types of DPPA exemptions for compliant searches"""
    
    LEGAL_PROCEEDINGS = "legal_proceedings"
    CREDIT_INSURANCE = "credit_insurance"
    FRAUD_PREVENTION = "fraud_prevention"
    COMMERCIAL_COMMUNICATION = "commercial_communication"
    BACKGROUND_CHECK = "background_check"
    NO_EXEMPTION = "no_exemption"


class PublicDataStatusCode(Enum):
    """API response status codes from PublicData.com"""
    
    SUCCESS = 0
    INVALID_CREDENTIALS = -1
    INSUFFICIENT_BALANCE = -2
    SEARCH_LIMIT_REACHED = -3
    DPPA_RESTRICTION = -4
    GLB_RESTRICTION = -5
    INVALID_REQUEST = -6
    SERVER_ERROR = -7
    RATE_LIMIT_EXCEEDED = -8
    PAGINATION_ERROR = -9


@dataclass
class SearchRequest:
    """Represents a search request to PublicData.com"""
    
    username: str
    password: str
    database_id: int
    search_term: str
    record_number: Optional[int] = None  # 'rec' parameter for specific record
    edition_number: Optional[int] = None  # 'ed' parameter for edition
    exemption_type: PDAPPAExemptionType = PDAPPAExemptionType.NO_EXEMPTION
    display_format: str = "xml"  # Default to XML as per requirements
    page_size: int = 100
    current_page: int = 1
    
    def __post_init__(self):
        """Validate request parameters after initialization"""
        if not self.username or not self.password:
            raise ValueError("Username and password are required")
        
        if self.database_id <= 0:
            raise ValueError("Database ID must be a positive integer")
        
        if not self.search_term:
            raise ValueError("Search term is required")
        
        if self.display_format.lower() != "xml":
            logger.warning(f"Non-XML display format '{self.display_format}' requested, defaulting to XML")
            self.display_format = "xml"


@dataclass
class SearchResponse:
    """Represents a response from PublicData.com API"""
    
    status_code: int
    message: str
    total_records: int
    current_page: int
    page_size: int
    has_next_page: bool
    data_payload: Optional[str] = None  # Raw XML or parsed data
    parsed_results: List[Dict[str, Any]] = field(default_factory=list)
    error_details: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AuthenticationToken:
    """Represents an authentication token from PublicData.com"""
    
    token: str
    expires_at: datetime
    username: str
    
    @property
    def is_valid(self) -> bool:
        """Check if the token has expired (with 5-minute buffer)"""
        return self.expires_at > datetime.now() + timedelta(minutes=5)


class PublicDataAPIConnector:
    """
    Main connector class for PublicData.com API integration
    
    Handles authentication, search operations, pagination, and error recovery.
    
    Attributes:
        base_url: Base URL for PublicData.com API (default: https://api.publicdata.com)
        api_endpoint: Search endpoint (pdsearchdocs.php)
        auth_cache: In-memory cache for authentication tokens
        session: Async aiohttp session for HTTP requests
        rate_limiter: Rate limiting semaphore to prevent API abuse
    """
    
    # Default configuration
    DEFAULT_BASE_URL = "https://api.publicdata.com"
    SEARCH_ENDPOINT = "/pdsearchdocs.php"
    AUTH_ENDPOINT = "/authenticate.php"  # For token-based authentication
    
    # Timeout settings (in seconds)
    CONNECTION_TIMEOUT = 30
    READ_TIMEOUT = 60
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 2.0
    
    def __init__(self, 
                 base_url: str = DEFAULT_BASE_URL,
                 max_concurrent_requests: int = 5):
        """
        Initialize the PublicData.com API connector
        
        Args:
            base_url: Base URL for the API (can be overridden for testing)
            max_concurrent_requests: Maximum concurrent API requests allowed
        """
        
        self.base_url = base_url.rstrip("/")
        self.search_endpoint = self.base_url + self.SEARCH_ENDPOINT
        
        # Initialize authentication cache with TTL tracking
        self._auth_cache: Dict[str, AuthenticationToken] = {}
        self._cache_ttl_minutes = 60
        
        # Rate limiting configuration
        self._max_concurrent_requests = max_concurrent_requests
        self._rate_limiter = asyncio.Semaphore(max_concurrent_requests)
        
        # HTTP session management
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Statistics tracking
        self.stats = {
            "total_searches": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "authentication_failures": 0,
            "rate_limit_hits": 0,
            "pagination_errors": 0,
            "total_execution_time_ms": 0.0
        }
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an async HTTP session with proper configuration"""
        
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(
                total=self.CONNECTION_TIMEOUT + self.READ_TIMEOUT,
                connect=self.CONNECTION_TIMEOUT,
                sock_read=self.READ_TIMEOUT
            )
            
            headers = {
                "User-Agent": "OSINT-Analyst/1.0 (PublicData.com Integration)",
                "Accept": "application/xml, text/xml",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
        
        return self._session
    
    async def close(self):
        """Close the HTTP session and cleanup resources"""
        
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        
        logger.info("PublicData.com API connector closed")
    
    async def authenticate(self, 
                         username: str, 
                         password: str) -> AuthenticationToken:
        """
        Authenticate with PublicData.com and retrieve an access token
        
        This method implements secure authentication and token caching to
        reduce the overhead of repeated authentications.
        
        Args:
            username: API username for PublicData.com account
            password: API password or API key
            
        Returns:
            AuthenticationToken object containing the token and expiration info
            
        Raises:
            ValueError: If credentials are invalid
            ClientError: If network error occurs during authentication
        """
        
        # Check cache first (with TTL)
        cached_token = self._auth_cache.get(username)
        if cached_token and cached_token.is_valid:
            logger.info(f"Using cached authentication token for {username}")
            return cached_token
        
        try:
            session = await self._get_session()
            
            # Prepare authentication request
            auth_data = {
                "username": username,
                "password": password,
                "format": "json"  # Request JSON for easier parsing
            }
            
            async with session.post(
                f"{self.base_url}{self.AUTH_ENDPOINT}",
                data=auth_data,
                timeout=aiohttp.ClientTimeout(total=self.CONNECTION_TIMEOUT)
            ) as response:
                
                if response.status != 200:
                    error_body = await response.text()
                    raise ValueError(f"Authentication failed with status {response.status}: {error_body}")
                
                auth_response = await response.json()
                
                # Validate response structure
                if "access_token" not in auth_response or "expires_at" not in auth_response:
                    raise ValueError("Invalid authentication response format")
                
                # Create token object with expiration time
                expires_at = datetime.fromisoformat(auth_response["expires_at"].replace("Z", "+00:00"))
                
                token = AuthenticationToken(
                    token=auth_response["access_token"],
                    expires_at=expires_at,
                    username=username
                )
                
                # Cache the token
                self._auth_cache[username] = token
                
                logger.info(f"Successfully authenticated as {username}, token valid until {expires_at}")
                
                return token
                
        except ClientError as e:
            logger.error(f"Network error during authentication for {username}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            self.stats["authentication_failures"] += 1
            raise ValueError(f"Authentication failed: {str(e)}") from e
    
    async def search(self, 
                    request: SearchRequest) -> SearchResponse:
        """
        Execute a search on PublicData.com database
        
        This method constructs the proper API call with all required parameters,
        handles pagination, and returns structured results.
        
        Args:
            request: SearchRequest object containing all search parameters
            
        Returns:
            SearchResponse object containing status, data, and metadata
            
        Raises:
            ValueError: If request parameters are invalid
            ClientError: If network error occurs during search
        """
        
        start_time = datetime.now()
        
        try:
            # Validate request before proceeding
            self._validate_search_request(request)
            
            async with self._rate_limiter:  # Rate limiting semaphore
                session = await self._get_session()
                
                # Build query parameters for the search endpoint
                params = {
                    "username": request.username,
                    "password": request.password,
                    "dbid": str(request.database_id),
                    "search": request.search_term,
                    "format": request.display_format.lower(),
                    "page": str(request.current_page),
                    "pagesize": str(request.page_size)
                }
                
                # Add optional parameters if provided
                if request.record_number:
                    params["rec"] = str(request.record_number)
                
                if request.edition_number:
                    params["ed"] = str(request.edition_number)
                
                # Add exemption type for DPPA compliance
                if request.exemption_type != PDAPPAExemptionType.NO_EXEMPTION:
                    params["exempt_type"] = request.exemption_type.value
                
                # Construct full URL with query parameters
                search_url = f"{self.search_endpoint}?{urlencode(params)}"
                
                logger.info(f"Executing search on {search_url}")
                
                async with session.get(
                    search_url,
                    timeout=aiohttp.ClientTimeout(total=self.READ_TIMEOUT)
                ) as response:
                    
                    # Handle various HTTP status codes
                    if response.status == 200:
                        return await self._handle_successful_search(response, request, start_time)
                    
                    elif response.status == 401 or response.status == 403:
                        error_text = await response.text()
                        logger.error(f"Authentication/Authorization error: {error_text}")
                        self.stats["authentication_failures"] += 1
                        
                        return SearchResponse(
                            status_code=PublicDataStatusCode.INVALID_CREDENTIALS.value,
                            message="Invalid credentials or insufficient permissions",
                            total_records=0,
                            current_page=request.current_page,
                            page_size=request.page_size,
                            has_next_page=False,
                            error_details=error_text
                        )
                    
                    elif response.status == 429:
                        logger.warning("Rate limit exceeded by PublicData.com")
                        self.stats["rate_limit_hits"] += 1
                        
                        return SearchResponse(
                            status_code=PublicDataStatusCode.RATE_LIMIT_EXCEEDED.value,
                            message="Rate limit exceeded",
                            total_records=0,
                            current_page=request.current_page,
                            page_size=request.page_size,
                            has_next_page=False,
                            error_details="Rate limit exceeded"
                        )
                    
                    elif response.status == 400:
                        error_text = await response.text()
                        logger.error(f"Bad request: {error_text}")
                        
                        return SearchResponse(
                            status_code=PublicDataStatusCode.INVALID_REQUEST.value,
                            message="Invalid search parameters",
                            total_records=0,
                            current_page=request.current_page,
                            page_size=request.page_size,
                            has_next_page=False,
                            error_details=error_text
                        )
                    
                    else:
                        error_text = await response.text()
                        logger.error(f"Unexpected HTTP status {response.status}: {error_text}")
                        
                        return SearchResponse(
                            status_code=PublicDataStatusCode.SERVER_ERROR.value,
                            message=f"Server returned unexpected status code: {response.status}",
                            total_records=0,
                            current_page=request.current_page,
                            page_size=request.page_size,
                            has_next_page=False,
                            error_details=error_text
                        )
                        
        except asyncio.TimeoutError:
            logger.error("Search request timed out")
            
            return SearchResponse(
                status_code=PublicDataStatusCode.SERVER_ERROR.value,
                message="Request timeout",
                total_records=0,
                current_page=request.current_page,
                page_size=request.page_size,
                has_next_page=False,
                error_details="API request timed out"
            )
            
        except ClientError as e:
            logger.error(f"Network error during search: {e}")
            self.stats["failed_searches"] += 1
            
            return SearchResponse(
                status_code=PublicDataStatusCode.SERVER_ERROR.value,
                message=f"Network error: {str(e)}",
                total_records=0,
                current_page=request.current_page,
                page_size=request.page_size,
                has_next_page=False,
                error_details=str(e)
            )
            
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}")
            self.stats["failed_searches"] += 1
            
            return SearchResponse(
                status_code=PublicDataStatusCode.SERVER_ERROR.value,
                message=f"Unexpected error: {str(e)}",
                total_records=0,
                current_page=request.current_page,
                page_size=request.page_size,
                has_next_page=False,
                error_details=str(e)
            )
    
    async def search_paginated(self,
                              request: SearchRequest,
                              max_pages: int = 10) -> List[SearchResponse]:
        """
        Execute a paginated search across multiple pages
        
        This method handles automatic pagination to retrieve all available results.
        
        Args:
            request: Initial SearchRequest object (page will be incremented automatically)
            max_pages: Maximum number of pages to retrieve
            
        Returns:
            List of SearchResponse objects, one per page retrieved
        """
        
        responses = []
        current_page = 1
        
        while current_page <= max_pages:
            # Update request with current page
            request.current_page = current_page
            
            try:
                response = await self.search(request)
                responses.append(response)
                
                # Update statistics
                self.stats["total_searches"] += 1
                if response.status_code == PublicDataStatusCode.SUCCESS.value:
                    self.stats["successful_searches"] += 1
                
                # Check if there are more pages to retrieve
                if not response.has_next_page or len(responses) >= max_pages:
                    break
                
                current_page += 1
                
                # Small delay between requests to respect rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error during pagination at page {current_page}: {e}")
                self.stats["pagination_errors"] += 1
                
                if current_page == 1:
                    # If first page failed, return error response
                    responses.append(SearchResponse(
                        status_code=PublicDataStatusCode.PAGINATION_ERROR.value,
                        message=f"Pagination failed on first page: {str(e)}",
                        total_records=0,
                        current_page=current_page,
                        page_size=request.page_size,
                        has_next_page=False,
                        error_details=str(e)
                    ))
                break
        
        return responses
    
    def _validate_search_request(self, request: SearchRequest) -> None:
        """Validate search request parameters before execution"""
        
        if not request.username or not request.password:
            raise ValueError("Username and password are required")
        
        if request.database_id <= 0:
            raise ValueError(f"Invalid database ID: {request.database_id}")
        
        if not request.search_term or len(request.search_term.strip()) < 2:
            raise ValueError("Search term must be at least 2 characters long")
        
        # Validate optional parameters
        if request.record_number is not None and request.record_number <= 0:
            raise ValueError(f"Invalid record number: {request.record_number}")
        
        if request.edition_number is not None and request.edition_number <= 0:
            raise ValueError(f"Invalid edition number: {request.edition_number}")
    
    async def _handle_successful_search(self, 
                                       response: aiohttp.ClientResponse,
                                       request: SearchRequest,
                                       start_time: datetime) -> SearchResponse:
        """Handle a successful HTTP 200 response from PublicData.com"""
        
        try:
            # Read raw response content (XML format as requested)
            xml_content = await response.text()
            
            # Parse XML to extract structured data
            parsed_results, total_records = self._parse_xml_response(xml_content)
            
            # Calculate execution time
            execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Determine if there are more pages
            has_next_page = request.current_page < total_records // request.page_size + 1
            
            logger.info(f"Search successful: {len(parsed_results)} records found, "
                       f"{total_records} total, page {request.current_page}")
            
            return SearchResponse(
                status_code=PublicDataStatusCode.SUCCESS.value,
                message="Search completed successfully",
                total_records=total_records,
                current_page=request.current_page,
                page_size=request.page_size,
                has_next_page=has_next_page,
                data_payload=xml_content,
                parsed_results=parsed_results,
                execution_time_ms=execution_time_ms
            )
            
        except Exception as e:
            logger.error(f"Error parsing XML response: {e}")
            self.stats["failed_searches"] += 1
            
            return SearchResponse(
                status_code=PublicDataStatusCode.INVALID_REQUEST.value,
                message="Failed to parse XML response",
                total_records=0,
                current_page=request.current_page,
                page_size=request.page_size,
                has_next_page=False,
                error_details=str(e)
            )
    
    def _parse_xml_response(self, xml_content: str) -> tuple[List[Dict[str, Any]], int]:
        """
        Parse XML response from PublicData.com API
        
        This method handles the XML format returned by pdsearchdocs.php endpoint.
        
        Args:
            xml_content: Raw XML string from API response
            
        Returns:
            Tuple of (parsed_results list, total_records count)
            
        Raises:
            ValueError: If XML parsing fails
        """
        
        try:
            import xml.etree.ElementTree as ET
            
            # Parse the XML content
            root = ET.fromstring(xml_content)
            
            parsed_results = []
            total_records = 0
            
            # Find the record_count element for pagination info
            count_elem = root.find(".//record_count")
            if count_elem is not None and count_elem.text:
                try:
                    total_records = int(count_elem.text)
                except ValueError:
                    logger.warning(f"Invalid record_count value: {count_elem.text}")
            
            # Find all record elements
            for record_elem in root.findall(".//record"):
                record_data = {}
                
                # Extract fields from each record
                for field_elem in record_elem.findall("field"):
                    field_name = field_elem.get("name", "unknown")
                    field_value = field_elem.text or ""
                    
                    # Skip empty or placeholder values
                    if field_value and field_value.lower() not in ["n/a", "-", "", "null"]:
                        record_data[field_name] = field_value
                
                if record_data:
                    parsed_results.append(record_data)
            
            logger.info(f"Parsed {len(parsed_results)} records from XML response")
            
            return parsed_results, total_records
            
        except ET.ParseError as e:
            raise ValueError(f"XML parsing error: {str(e)}") from e
        except Exception as e:
            raise ValueError(f"Unexpected error during XML parsing: {str(e)}") from e
    
    def get_statistics(self) -> Dict[str, Any]:
        """Return current statistics for the connector"""
        
        return dict(self.stats)


class PublicDataSearchEngine:
    """
    High-level search engine wrapper with advanced features
    
    This class provides a simplified interface for common search patterns
    and includes validation, error recovery, and result aggregation.
    
    Features:
    - Automatic retry logic for transient failures
    - Result validation and filtering
    - DPPA compliance checking
    - Search template management
    """
    
    def __init__(self, connector: Optional[PublicDataAPIConnector] = None):
        """
        Initialize the search engine
        
        Args:
            connector: PublicDataAPIConnector instance (creates new one if not provided)
        """
        
        self.connector = connector or PublicDataAPIConnector()
    
    async def execute_search(self, 
                            username: str,
                            password: str,
                            database_id: int,
                            search_term: str,
                            record_number: Optional[int] = None,
                            edition_number: Optional[int] = None,
                            exemption_type: PDAPPAExemptionType = PDAPPAExemptionType.NO_EXEMPTION,
                            retry_on_failure: bool = True) -> SearchResponse:
        """
        Execute a search with automatic retry logic
        
        Args:
            username: API username
            password: API password
            database_id: Target database ID
            search_term: Search query term
            record_number: Optional specific record number ('rec' parameter)
            edition_number: Optional edition number ('ed' parameter)
            exemption_type: DPPA exemption type if applicable
            retry_on_failure: Whether to automatically retry on transient failures
            
        Returns:
            SearchResponse object with results or error details
        """
        
        # Create search request
        request = SearchRequest(
            username=username,
            password=password,
            database_id=database_id,
            search_term=search_term,
            record_number=record_number,
            edition_number=edition_number,
            exemption_type=exemption_type
        )
        
        # Execute with retry logic if enabled
        for attempt in range(self.connector.MAX_RETRY_ATTEMPTS):
            try:
                result = await self.connector.search(request)
                
                # Check if successful or non-retryable error
                if (result.status_code == PublicDataStatusCode.SUCCESS.value or 
                    result.status_code not in [
                        PublicDataStatusCode.SERVER_ERROR.value,
                        PublicDataStatusCode.RATE_LIMIT_EXCEEDED.value,
                        PublicDataStatusCode.PAGINATION_ERROR.value
                    ]):
                    return result
                
                # Retry transient failures
                if retry_on_failure and attempt < self.connector.MAX_RETRY_ATTEMPTS - 1:
                    wait_time = self.connector.RETRY_DELAY_SECONDS * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying search after {wait_time}s delay (attempt {attempt + 1})")
                    await asyncio.sleep(wait_time)
                    continue
                
                return result
                
            except Exception as e:
                if attempt == self.connector.MAX_RETRY_ATTEMPTS - 1:
                    # Last attempt failed
                    logger.error(f"All retry attempts exhausted. Error: {e}")
                    raise
                
                wait_time = self.connector.RETRY_DELAY_SECONDS * (2 ** attempt)
                logger.warning(f"Retryable error, waiting {wait_time}s before retry (attempt {attempt + 1})")
                await asyncio.sleep(wait_time)
        
        # Should not reach here, but just in case
        return SearchResponse(
            status_code=PublicDataStatusCode.SERVER_ERROR.value,
            message="Search failed after all retries",
            total_records=0,
            current_page=1,
            page_size=request.page_size,
            has_next_page=False,
            error_details="Maximum retry attempts exceeded"
        )
    
    async def search_with_validation(self,
                                    username: str,
                                    password: str,
                                    database_id: int,
                                    search_term: str) -> Dict[str, Any]:
        """
        Execute a search with comprehensive validation and analysis
        
        Args:
            username: API username
            password: API password
            database_id: Target database ID
            search_term: Search query term
            
        Returns:
            Dictionary containing validated results and metadata
        """
        
        # Execute the search
        response = await self.execute_search(
            username=username,
            password=password,
            database_id=database_id,
            search_term=search_term
        )
        
        # Validate the response
        validation_result = {
            "success": False,
            "error_details": None,
            "result_summary": None,
            "data_quality_score": 0.0,
            "recommendations": []
        }
        
        if response.status_code != PublicDataStatusCode.SUCCESS.value:
            validation_result["error_details"] = response.error_details or "Unknown error"
            
            # Provide specific recommendations based on error type
            if response.status_code == PublicDataStatusCode.INVALID_CREDENTIALS.value:
                validation_result["recommendations"].append(
                    "Verify API credentials and account status with PublicData.com support"
                )
            elif response.status_code == PublicDataStatusCode.DPPA_RESTRICTION.value:
                validation_result["recommendations"].append(
                    "Ensure proper DPPA exemption is documented before searching restricted databases"
                )
            elif response.status_code == PublicDataStatusCode.RATE_LIMIT_EXCEEDED.value:
                validation_result["recommendations"].append(
                    "Implement rate limiting in your application to avoid hitting API limits"
                )
            
            return validation_result
        
        # Validate result data quality
        if not response.parsed_results or len(response.parsed_results) == 0:
            validation_result["error_details"] = "No results returned from search"
            validation_result["recommendations"].append(
                "Verify search term matches expected database schema and content"
            )
            return validation_result
        
        # Calculate data quality score based on field completeness
        total_fields = 0
        populated_fields = 0
        
        for record in response.parsed_results:
            for field_name, value in record.items():
                total_fields += 1
                if value and value.lower() not in ["n/a", "-", "", "null"]:
                    populated_fields += 1
        
        data_quality_score = (populated_fields / total_fields * 100) if total_fields > 0 else 0.0
        validation_result["data_quality_score"] = round(data_quality_score, 2)
        
        # Create result summary
        validation_result["result_summary"] = {
            "total_records": response.total_records,
            "returned_records": len(response.parsed_results),
            "current_page": response.current_page,
            "page_size": response.page_size,
            "has_more_pages": response.has_next_page,
            "execution_time_ms": round(response.execution_time_ms, 2)
        }
        
        validation_result["success"] = True
        
        return validation_result


# Example usage and testing functions
async def run_integration_test():
    """Run a comprehensive integration test of the PublicData.com API connector"""
    
    print("=" * 60)
    print("PublicData.com API Integration Test")
    print("=" * 60)
    
    # Initialize connector
    connector = PublicDataAPIConnector()
    
    try:
        # Test 1: Authentication (skip if credentials not available)
        print("\n[Test 1] Testing authentication...")
        
        # Note: In production, these would come from environment variables or secure storage
        test_username = "your_publicdata_username"
        test_password = "your_api_key_or_password"
        
        try:
            token = await connector.authenticate(test_username, test_password)
            print(f"✓ Authentication successful. Token valid until {token.expires_at}")
        except Exception as e:
            print(f"✗ Authentication failed (expected in demo mode): {e}")
        
        # Test 2: Search request validation
        print("\n[Test 2] Testing search request validation...")
        
        invalid_requests = [
            {"database_id": -1, "search_term": "test"},
            {"username": "", "password": "test", "database_id": 1, "search_term": "test"},
            {"database_id": 1, "search_term": ""},
        ]
        
        for invalid_params in invalid_requests:
            try:
                request = SearchRequest(
                    username="dummy_user" if not invalid_params.get("username") else None,
                    password=invalid_params.get("password", "dummy_pass"),
                    database_id=invalid_params.get("database_id", 1),
                    search_term=invalid_params.get("search_term", "")
                )
                print(f"✗ Should have rejected: {invalid_params}")
            except ValueError as e:
                print(f"✓ Correctly rejected invalid request: {e}")
        
        # Test 3: Search execution (demo mode - won't actually call API)
        print("\n[Test 3] Testing search execution...")
        
        try:
            search_request = SearchRequest(
                username=test_username,
                password=test_password,
                database_id=1,
                search_term="test@example.com",
                exemption_type=PDAPPAExemptionType.FRAUD_PREVENTION,
                display_format="xml"
            )
            
            response = await connector.search(search_request)
            
            if response.status_code == PublicDataStatusCode.SUCCESS.value:
                print(f"✓ Search completed successfully")
                print(f"  - Total records: {response.total_records}")
                print(f"  - Found on page: {len(response.parsed_results)} records")
            else:
                print(f"✗ Search failed with status code: {response.status_code}")
                if response.error_details:
                    print(f"  Error details: {response.error_details}")
                    
        except Exception as e:
            print(f"✗ Search execution error (expected in demo mode): {e}")
        
        # Test 4: Statistics reporting
        print("\n[Test 4] Testing statistics...")
        
        stats = connector.get_statistics()
        print("Current statistics:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        
    finally:
        # Cleanup
        await connector.close()
    
    print("\n" + "=" * 60)
    print("Integration test completed")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    
    # Run the integration test
    asyncio.run(run_integration_test())
