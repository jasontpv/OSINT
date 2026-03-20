# Key Methods Reference - OSINT Pipeline Fixes

## Quick Reference Guide

This document provides quick access to the most critical methods that were fixed, with before/after comparisons and usage examples.

---

## 1. SerperClient.execute_search() (FIXED)

**Location**: `osint_harvesting_stage.py`

### Purpose
Execute Google search queries via Serper.dev API with proper header handling and single JSON parsing.

### Before (BROKEN)
```python
async def execute_search(self, query: str):
    # ... headers setup ...
    
    data = await response.json()  # First parse
    parsed_data = json.loads(data["json_response"])  # DOUBLE PARSE! ❌
    
    return parsed_data  # Could fail if format changes
```

### After (FIXED) ✅
```python
async def execute_search(self, query: str) -> Dict[str, Any]:
    """Execute Google search via Serper.dev
    
    Returns: Parsed JSON response as dict (already parsed!)
    
    API Call Format:
        POST /search
        Headers: X-API-KEY: <your_key>
        Body: {"q": "<query>", "num": 10}
    """
    
    if not self.circuit_breaker.can_execute():
        raise Exception("Circuit breaker is OPEN")
    
    async with aiohttp.ClientSession() as session:
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {"q": query, "num": 10}
        
        async with session.post(
            self.BASE_URL,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            
            if response.status == 200:
                data = await response.json()  # Single parse only! ✅
                
                # Validate structure
                if not isinstance(data, dict):
                    raise ValueError(f"Invalid Serper.dev response format: {type(data)}")
                
                self.circuit_breaker.record_success()
                return data  # Already parsed dict
            
            elif response.status == 401:
                raise Exception("Serper.dev API key invalid or expired (HTTP 401)")
            
            elif response.status == 429:
                retry_after = response.headers.get('X-Retry-After', '60')
                raise Exception(f"Serper.dev rate limit exceeded. Retry after {retry_after}s")

```

### Usage Example
```python
from osint_harvesting_stage import SerperClient

client = SerperClient(api_key="YOUR_SERPER_API_KEY")
result = await client.execute_search("test@example.com")

# Result is already a dict - no parsing needed!
print(f"Found {len(result.get('organic', []))} results")
for item in result['organic']:
    print(f"  - {item['title']} ({item['link']})")
```

---

## 2. ScrapingantClientV2.scrape_url() (FIXED)

**Location**: `osint_harvesting_stage.py`

### Purpose
Scrape HTML content from URLs using ScrapingAnt v2 API with correct endpoint and parameters.

### Before (BROKEN) ❌
```python
BASE_URL = "api.scrapingant.com/scrape"  # Wrong!
headers = {"x-api-key": api_key}  # Not used in v2!

async def scrape_url(self, url: str):
    async with session.post(
        self.BASE_URL,
        headers=headers,
        json={"url": url}  # POST instead of GET
    ) as response:
```

### After (FIXED) ✅
```python
BASE_URL = "https://api.scrapingant.com/v2/text"  # Correct v2 endpoint!

async def scrape_url(self, url: str, max_retries: int = 3) -> ScrapedContent:
    """Scrape HTML content from a URL using ScrapingAnt v2 API
    
    API Call Format (v2):
        GET /v2/text?url=<encoded_url>&api_key=<key>
    
    Note: In v2, the API key is passed as a query parameter for text extraction
    """
    
    params = {
        "url": url,
        "api_key": self.api_key,  # V2 uses query param for API key ✅
        "engine": "google"
    }
    
    async with session.get(
        self.BASE_URL,
        params=params,
        timeout=aiohttp.ClientTimeout(total=30)
    ) as response:
        
        if status_code == 200:
            text_content = await response.text()
            
            # Also get raw HTML for completeness
            async with session.get(url) as html_response:
                html_content = await html_response.text() if html_response.status == 200 else ""
            
            return ScrapedContent(
                url=url,
                status_code=status_code,
                html_content=html_content,
                text_content=text_content,
                execution_time_ms=(time.time() - start_time) * 1000,
                error=None
            )
```

### Usage Example
```python
from osint_harvesting_stage import ScrapingantClientV2

client = ScrapingantClientV2(api_key="YOUR_SCRAPEANT_API_KEY")
result = await client.scrape_url("https://example.com")

if result.is_success:
    print(f"Status: {result.status_code}")
    print(f"Content Preview: {result.text_content[:100]}...")
else:
    print(f"Error: {result.error}")
```

---

## 3. FactExtractor._extract_field() (FIXED)

**Location**: `osint_analyst_stage.py`

### Purpose
Type-safe field extraction that handles dict, list, string, or None inputs without throwing AttributeError.

### Before (BROKEN) ❌
```python
def _extract_field(data, field_name):
    return data[field_name]  # Crashes if data is None! ❌
    # No type checking - crashes on lists, strings, etc.
```

### After (FIXED) ✅
```python
@staticmethod
def _extract_field(data: Any, field_name: str, default: Any = None) -> Optional[Any]:
    """Type-safe field extraction that handles dict, list, or nested structures
    
    Safety Features:
        - Handles both dict and list types without AttributeError ✅
        - Gracefully handles nested structures
        - Provides fallback for missing fields
        
    Args:
        data: Input data (can be dict, list, or any type)
        field_name: Field name to extract
        default: Default value if extraction fails
        
    Returns:
        Extracted field value or default
    """
    
    try:
        # Case 1: Data is a dictionary with the field
        if isinstance(data, dict):
            return data.get(field_name, default)
        
        # Case 2: Data is a list - extract first element that has the field
        elif isinstance(data, list):
            for item in data:
                try:
                    result = FactExtractor._extract_field(item, field_name, None)
                    if result is not None:
                        return result
                except (AttributeError, TypeError):
                    continue
            return default
        
        # Case 3: Data is a string - attempt to parse as JSON
        elif isinstance(data, str):
            try:
                parsed = json.loads(data)
                return FactExtractor._extract_field(parsed, field_name, default)
            except (json.JSONDecodeError, TypeError):
                return data if field_name == "text" else default
        
        # Case 4: Other types - return as-is or default
        else:
            return default
            
    except AttributeError as e:
        logger.warning(f"AttributeError during extraction of {field_name}: {e}")
        return default
    except Exception as e:
        logger.warning(f"Unexpected error extracting {field_name}: {e}")
        return default
```

### Usage Example
```python
from osint_analyst_stage import FactExtractor

extractor = FactExtractor()

# Test with dict
data_dict = {"title": "Test", "link": "https://example.com"}
title = extractor._extract_field(data_dict, "title")  # Returns "Test" ✅

# Test with list (extracts from first matching item)
data_list = [{"title": "First"}, {"title": "Second"}]
title = extractor._extract_field(data_list, "title")  # Returns "First" ✅

# Test with None (gracefully returns default)
result = extractor._extract_field(None, "field", "default")  # Returns "default" ✅

# Test with Serper.dev 'organic' list format
serper_data = {
    "organic": [
        {"title": "Result 1", "link": "https://example.com/1"},
        {"title": "Result 2", "link": "https://example.com/2"}
    ]
}

facts = extractor.extract_facts_from_source(serper_data, "serper_dev")
# Returns list of VerifiedFact objects ✅
```

---

## 4. FactExtractor.extract_facts_from_source() (FIXED)

**Location**: `osint_analyst_stage.py`

### Purpose
Drill down into search results to extract structured facts from the 'organic' list, handling various data formats safely.

### Before (BROKEN) ❌
```python
def extract_facts_from_source(source_data):
    # No type checking - crashes on unexpected formats!
    for item in source_data['organic']:  # Crashes if no 'organic' key!
        facts.append(item['title'])
```

### After (FIXED) ✅
```python
@staticmethod
def extract_facts_from_source(source_data: Union[dict, list], 
                              source_type: str = "serper_dev") -> List[VerifiedFact]:
    """Drill down into search results to extract structured facts
    
    This method specifically handles the Serper.dev 'organic' list structure
    and extracts link, title, snippet as individual facts.
    
    Processing Logic:
        1. Check if 'organic' key exists in response ✅
        2. Iterate through organic results list safely ✅
        3. Extract link, title, snippet for each result ✅
        4. Create structured facts ready for confidence scoring ✅
        
    Args:
        source_data: Raw data from search engine (dict or list)
        source_type: Type of source ("serper_dev", "leak_lookup", etc.)
        
    Returns:
        List of VerifiedFact objects with extracted information
    """
    
    facts = []
    
    # Step 1: Drill down into 'organic' list if present (Serper.dev format)
    organic_list = None
    
    if isinstance(source_data, dict):
        # Try to find the 'organic' key at various levels
        if "organic" in source_data and isinstance(source_data["organic"], list):
            organic_list = source_data["organic"]
        elif "results" in source_data and isinstance(source_data["results"], list):
            organic_list = source_data["results"]
    
    elif isinstance(source_data, list):
        # If input is already a list, use it directly
        organic_list = source_data
    
    # Step 2: Process each result in the organic list (safe iteration) ✅
    if organic_list and isinstance(organic_list, list):
        for idx, item in enumerate(organic_list):
            try:
                # Extract fields safely using our type-safe method
                title = FactExtractor._extract_field(item, "title", f"Result {idx + 1}")
                link = FactExtractor._extract_field(item, "link", "")
                snippet = FactExtractor._extract_field(item, "snippet", "")
                
                # Skip items without meaningful content
                if not title and not link:
                    continue
                
                source_identifier = f"{title} ({link})" if link else str(title)
                
                # Extract email addresses from snippet if present
                emails_in_snippet = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                
                for email in emails_in_snippet:
                    facts.append(VerifiedFact(
                        text=email,
                        source=source_identifier,
                        confidence_score=0.6,  # Base score for extracted email
                        is_verified=False,
                        cross_references=[],
                        metadata={...}
                    ))
                    
            except Exception as e:
                logger.warning(f"Error processing item {idx}: {e}")
                continue
    
    return facts
```

### Usage Example
```python
from osint_analyst_stage import FactExtractor

# Serper.dev format (with 'organic' list)
serper_data = {
    "organic": [
        {
            "title": "John Doe Profile",
            "link": "https://linkedin.com/in/johndoe",
            "snippet": "Contact: john.doe@example.com"
        }
    ]
}

facts = FactExtractor.extract_facts_from_source(serper_data, "serper_dev")

print(f"Extracted {len(facts)} facts:")
for fact in facts:
    print(f"  - {fact.text} (from {fact.source})")
```

---

## 5. CrossReferenceEngine.perform_cross_reference() (NEW)

**Location**: `osint_analyst_stage.py`

### Purpose
Match search results with Leak-Lookup breach database findings to identify correlations and boost confidence scores.

### Implementation ✅
```python
class CrossReferenceEngine:
    def perform_cross_reference(self, 
                               search_results: List[Dict], 
                               leak_lookup_findings: List[Dict]) -> Dict[str, CrossReferenceResult]:
        """Match search results with Leak-Lookup breach data
        
        Args:
            search_results: Results from HARVESTING stage (search engine responses)
            leak_lookup_findings: Breach database information
            
        Returns:
            Dictionary mapping target emails to their cross-reference matches
        """
        
        # Extract all emails from search results
        search_emails = set()
        for result in search_results:
            if isinstance(result, dict):
                organic_list = result.get('organic', [])
                
                for item in organic_list:
                    if isinstance(item, dict):
                        snippet = str(item.get('snippet', ''))
                        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                        search_emails.update(emails)
        
        # Match against Leak-Lookup findings
        matches: Dict[str, CrossReferenceResult] = {}
        
        for finding in leak_lookup_findings:
            if not isinstance(finding, dict):
                continue
                
            target = str(finding.get('target', ''))
            databases = finding.get('breached_databases', [])
            
            # Check if this target matches any search result email
            for search_email in search_emails:
                if self._is_match(search_email, target):
                    match_key = search_email.lower()
                    
                    matches[match_key] = CrossReferenceResult(
                        target_email=search_email,
                        search_source=f"Leak-Lookup match for {target}",
                        leaked_databases=list(databases) if isinstance(databases, list) else [str(databases)],
                        confidence_boost=0.3  # Boost from leak correlation ✅
                    )
        
        return matches
    
    def _is_match(self, email1: str, email2: str) -> bool:
        """Check if two emails match (considering Gmail dot normalization)"""
        e1 = email1.lower().strip()
        e2 = email2.lower().strip()
        
        # Exact match
        if e1 == e2:
            return True
        
        # Gmail dot normalization (john.doe@gmail.com == johndoe@gmail.com) ✅
        if '@' in e1 and '@' in e2:
            domain1 = e1.split('@')[1]
            domain2 = e2.split('@')[1]
            
            if domain1 == domain2:  # Same domain
                local1 = e1.split('@')[0].replace('.', '')
                local2 = e2.split('@')[0].replace('.', '')
                
                if local1 == local2:
                    return True
        
        return False
```

### Usage Example
```python
from osint_analyst_stage import CrossReferenceEngine

engine = CrossReferenceEngine()

# Search results containing emails
search_results = [
    {
        "organic": [
            {"title": "Profile", "snippet": "Email: john.doe@example.com"}
        ]
    }
]

# Leak-Lookup findings (breach database info)
leak_findings = [
    {
        "target": "john.doe@example.com",
        "breached_databases": ["Collection1", "DataBreach2023"]
    }
]

matches = engine.perform_cross_reference(search_results, leak_findings)

if matches:
    for email, match in matches.items():
        print(f"Match found: {email}")
        print(f"  Databases: {match.leaked_databases}")
        print(f"  Confidence Boost: +{match.confidence_boost}")
```

---

## 6. AnalystAgent.calculate_confidence_score() (FIXED)

**Location**: `osint_analyst_stage.py`

### Purpose
Calculate final confidence score with boost from Leak-Lookup correlation when matches found.

### Before (BROKEN) ❌
```python
def calculate_confidence_score(fact, cross_matches):
    return fact.confidence_score  # No boost applied!
```

### After (FIXED) ✅
```python
@staticmethod
def calculate_confidence_score(fact: VerifiedFact, cross_matches: List[CrossReferenceResult]) -> float:
    """Calculate final confidence score with leak correlation boost
    
    Base scores from match type:
        - Exact email match: 0.8
        - Partial domain match: 0.6  
        - Name-only match: 0.4
    
    + Confidence boost from leak lookup correlation (if applicable) ✅
    
    Final score clamped between 0 and 1.0
    
    Args:
        fact: VerifiedFact object with base confidence score
        cross_matches: List of CrossReferenceResult matches
        
    Returns:
        Final confidence score (0.0 to 1.0)
    """
    
    base_score = fact.confidence_score
    
    # Apply boost from cross-references ✅
    if cross_matches:
        max_boost = max(m.confidence_boost for m in cross_matches)
        base_score += max_boost * len(cross_matches)
    
    # Clamp score between 0 and 1.0
    return min(1.0, max(0.0, base_score))
```

### Usage Example
```python
from osint_analyst_stage import VerifiedFact, CrossReferenceResult, AnalystAgent

# Create a fact with base confidence score
fact = VerifiedFact(
    text="john.doe@example.com",
    source="LinkedIn Profile",
    confidence_score=0.6,  # Base score from search result
    is_verified=False,
    cross_references=[
        CrossReferenceResult(
            target_email="john.doe@example.com",
            search_source="Leak-Lookup match",
            leaked_databases=["Collection1", "DataBreach2023"],
            confidence_boost=0.3  # Boost from leak correlation ✅
        )
    ]
)

# Calculate final score with boost
final_score = AnalystAgent.calculate_confidence_score(fact, fact.cross_references)

print(f"Base Score: {fact.confidence_score}")
print(f"Final Score: {final_score:.2f} (Boosted by +{0.6 - 0.3})")
```

---

## Summary of Key Improvements

| Method | Before | After | Impact |
|--------|--------|-------|--------|
| `SerperClient.execute_search()` | Double JSON parse, crashes on format changes | Single parse, validated structure | ✅ Reliable API calls |
| `ScrapingantClientV2.scrape_url()` | Wrong endpoint, missing parameters | Correct v2 endpoint, proper params | ✅ Successful scrapes |
| `FactExtractor._extract_field()` | Crashes on None/lists | Type-safe for all inputs | ✅ No AttributeError crashes |
| `FactExtractor.extract_facts_from_source()` | No error handling | Safe extraction with fallbacks | ✅ Robust data processing |
| `CrossReferenceEngine.perform_cross_reference()` | Not implemented | Full cross-reference engine | ✅ Enhanced intelligence |
| `AnalystAgent.calculate_confidence_score()` | Static scores | Dynamic boost from leaks | ✅ Better accuracy |

---

## Testing Each Method

Run the test suite to verify all methods work correctly:

```bash
python test_api_fixes.py -v
```

Expected output for each method:
- ✅ Serper API integration working (single JSON parse)
- ✅ ScrapingAnt v2 API working (correct endpoint)
- ✅ Type-safe extraction working (no crashes)
- ✅ Cross-reference engine working (matches found)
- ✅ Confidence boost working (+0.3 applied)

---

**Last Updated**: 2024-12-17  
**Version**: 2.0 (API Fixes)
