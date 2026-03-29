"""
Leak-Lookup.com API Connector for OSINT AI Automation Tool

This module provides integration with Leak-Lookup.com to search for breached databases
associated with email addresses or domains.

Usage:
    from osint_connector.leak_lookup import search_leak_lookup
    
    results = search_leak_lookup(
        target="example@company.com",
        api_key="your_api_key_here"
    )
"""

import requests
from typing import List, Dict, Any
from enum import Enum


class SearchType(Enum):
    """Enumeration for supported search types."""
    EMAIL = "email"
    DOMAIN = "domain"


class LeakLookupError(Exception):
    """Base exception for Leak-Lookup API errors."""
    pass


class AuthenticationError(LeakLookupError):
    """Raised when API authentication fails."""
    pass


class ConnectionTimeoutError(LeakLookupError):
    """Raised when connection to API times out."""
    pass


class RateLimitError(LeakLookupError):
    """Raised when rate limit is exceeded."""
    pass


def search_leak_lookup(target: str, api_key: str) -> List[str]:
    """
    Query Leak-Lookup.com API to find breached databases for an email or domain.

    Args:
        target (str): The email address or domain to search for.
            Examples: "user@example.com" or "example.com"
        api_key (str): Valid API key for Leak-Lookup.com authentication.

    Returns:
        List[str]: Clean list of breached database names found.
            Example: ["LinkedIn", "Adobe_2013", "Dropbox"]

    Raises:
        AuthenticationError: If the API key is invalid or expired.
        ConnectionTimeoutError: If the connection to the API times out.
        RateLimitError: If the rate limit has been exceeded.
        LeakLookupError: For other unexpected errors during the query.
    
    Supported Search Types:
        - 'email': Searches for breaches associated with a specific email address
        - 'domain': Searches for all breaches affecting a domain

    Note:
        The function auto-detects search type based on target format.
        Email addresses trigger EMAIL search, anything else triggers DOMAIN search.
    
    Example:
        >>> results = search_leak_lookup("user@example.com", "abc123")
        >>> print(results)
        ['LinkedIn', 'Adobe_2013', 'Collection#1']
    """
    
    # Validate input parameters
    if not target or not isinstance(target, str):
        raise ValueError("Target must be a non-empty string.")
    
    if not api_key or not isinstance(api_key, str):
        raise ValueError("API key must be a non-empty string.")
    
    # Detect search type from target format
    search_type = _detect_search_type(target)
    
    # Build API request parameters
    params = {
        "type": search_type.value,
        "target": target.strip()
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "OSINT-AI-Tool/1.0 Leak-Lookup-Connector"
    }
    
    # Define API endpoint (adjust URL based on actual Leak-Lookup API)
    base_url = "https://api.leak-lookup.com/v1/search"
    
    try:
        # Make the API request with timeout handling
        response = requests.get(
            url=base_url,
            params=params,
            headers=headers,
            timeout=(5.0, 30.0)  # (connect_timeout, read_timeout) in seconds
        )
        
        # Handle HTTP error responses
        if response.status_code == 401:
            raise AuthenticationError(
                "API key is invalid or expired. Please verify your credentials."
            )
        elif response.status_code == 403:
            raise RateLimitError(
                "Rate limit exceeded. Please wait before retrying."
            )
        elif response.status_code == 429:
            raise RateLimitError(
                f"Too many requests. Retry after {response.headers.get('Retry-After', '60')} seconds."
            )
        elif not response.ok:
            raise LeakLookupError(
                f"API returned error status {response.status_code}: {response.text}"
            )
        
        # Parse JSON response
        try:
            data = response.json()
        except ValueError as json_error:
            raise LeakLookupError(
                f"Failed to parse API response as JSON: {json_error}"
            )
        
        # Extract breached databases from response
        breached_dbs = _extract_breached_databases(data)
        
        return breached_dbs
        
    except requests.exceptions.Timeout:
        raise ConnectionTimeoutError(
            "Connection to Leak-Lookup.com timed out. Please check your network connection."
        )
    except requests.exceptions.ConnectionError as conn_error:
        raise LeakLookupError(
            f"Failed to connect to Leak-Lookup.com API: {conn_error}"
        )
    except requests.exceptions.RequestException as req_error:
        raise LeakLookupError(
            f"Request failed during execution: {req_error}"
        )


def _detect_search_type(target: str) -> SearchType:
    """
    Auto-detect search type based on target format.

    Args:
        target (str): The target string to analyze.

    Returns:
        SearchType: EMAIL if target contains '@', otherwise DOMAIN.
    """
    if "@" in target and "." in target.split("@")[-1]:
        return SearchType.EMAIL
    
    # Treat anything else as domain search for flexibility
    return SearchType.DOMAIN


def _extract_breached_databases(data: Dict[str, Any]) -> List[str]:
    """
    Extract clean list of breached database names from API response.

    Args:
        data (Dict): Parsed JSON response from Leak-Lookup API.

    Returns:
        List[str]: Clean list of breached database names.
    
    Supports various response formats and normalizes results.
    """
    if not data or not isinstance(data, dict):
        return []
    
    # Common keys used in leak lookup responses (adjust based on actual API)
    possible_keys = [
        "breaches",
        "databases",
        "leaks",
        "found_databases",
        "results"
    ]
    
    breached_list = None
    
    for key in possible_keys:
        if key in data and isinstance(data[key], list):
            breached_list = data[key]
            break
    
    # If not found as list, check single object format
    if breached_list is None:
        breach_object = next((data.get(k) for k in possible_keys if k in data), None)
        if isinstance(breach_object, dict):
            breached_list = [breach_object]
    
    # Normalize results to clean list of database names
    cleaned_results = []
    
    if breached_list:
        for item in breached_list:
            if isinstance(item, str):
                # Direct string entry (database name)
                db_name = item.strip()
                if db_name and len(db_name) > 0:
                    cleaned_results.append(db_name)
            
            elif isinstance(item, dict):
                # Object entry - extract database name
                possible_fields = [
                    "name", 
                    "database_name", 
                    "source", 
                    "title", 
                    "leak_name"
                ]
                
                for field in possible_fields:
                    if field in item and isinstance(item[field], str):
                        db_name = item[field].strip()
                        if db_name and len(db_name) > 0:
                            cleaned_results.append(db_name)
                        break
    
    return cleaned_results


async def search_leak_lookup_batch(targets: List[str], api_key: str,
                                   max_concurrent: int = 3) -> Dict[str, List[str]]:
    """
    Perform batch searches on Leak-Lookup.com API.

    Args:
        targets (List[str]): List of email addresses or domains to search.
        api_key (str): Valid API key for authentication.
        max_concurrent (int): Maximum number of concurrent requests. Default is 3.

    Returns:
        Dict[str, List[str]]: Dictionary mapping each target to its list of breached databases.
            Example: {"user@example.com": ["LinkedIn", "Adobe"], "example.com": ["Collection#1"]}
    """
    import asyncio

    # BUGFIX: the previous implementation used ThreadPoolExecutor which submits
    # synchronous work on a thread pool but still blocks the asyncio event loop
    # when awaited, defeating the point of async concurrency.
    # Use asyncio.to_thread so each blocking requests.get() runs in the default
    # thread-pool executor without stalling other coroutines.
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _search_one(target: str) -> tuple:
        async with semaphore:
            try:
                result = await asyncio.to_thread(search_leak_lookup, target, api_key)
                return target, result
            except LeakLookupError as e:
                print(f"Warning: Failed to search {target}: {e}")
                return target, []

    pairs = await asyncio.gather(*[_search_one(t) for t in targets])
    return {target: result for target, result in pairs}


if __name__ == "__main__":
    # Example usage and testing
    import os
    
    TEST_API_KEY = os.environ.get("LEAK_LOOKUP_API_KEY", "YOUR_API_KEY_HERE")
    TARGET_EMAIL = "test@example.com"
    
    print(f"Testing Leak-Lookup API connector...")
    print(f"Target: {TARGET_EMAIL}")
    
    try:
        results = search_leak_lookup(TARGET_EMAIL, TEST_API_KEY)
        
        if results:
            print(f"\nFound {len(results)} breached databases:")
            for i, db in enumerate(sorted(results), 1):
                print(f"  {i}. {db}")
        else:
            print("\nNo breached databases found.")
            
    except AuthenticationError as e:
        print(f"Authentication failed: {e}")
    except ConnectionTimeoutError as e:
        print(f"Connection error: {e}")
    except LeakLookupError as e:
        print(f"API Error: {e}")
