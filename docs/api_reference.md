# OSINT Kanban Pipeline - API Reference

Complete documentation for all classes, functions, and data structures used in the pipeline.

## Table of Contents
- [Core Modules](#core-modules)
- [RECON Stage API](#recon-stage-api)
- [HARVESTING Stage API](#harvesting-stage-api)
- [ANALYST Stage API](#analyst-stage-api)
- [SCRIBE Stage API](#scribe-stage-api)
- [Kanban Manager API](#kanban-manager-api)

---

## Core Modules

### `osint_recon_stage.py`
Query generation and dork creation module.

### `osint_harvesting_stage.py`  
Search execution with rate limiting and content scraping.

### `osint_analyst_stage.py`
Cross-source verification, consensus detection, confidence scoring.

### `osint_scribe_stage.py`
Professional report generation (PDF/HTML).

### `osint_kanban_manager.py`
Pipeline orchestration with WIP limits and error handling.

---

## RECON Stage API

### `generate_osint_queries(user_query: str) -> ReconOutput`

Generates search queries from user input.

**Parameters:**
- `user_query` (str): Target description (e.g., "John Doe, Apple Inc")

**Returns:** `ReconOutput` dataclass with:
- `queries`: List of Google Dorks (10+ items)
- `api_queries`: Platform-specific API queries (~6-8 platforms)
- `entity_types`: Detected entity classifications
- `confidence_scores`: Reliability metrics per query type

**Example:**
```python
from osint_recon_stage import generate_osint_queries

result = generate_osint_queries("John Doe, Apple Inc")
print(f"Generated {len(result.queries)} dorks")
for dork in result.queries:
    print(dork)
```

### `detect_entity_types(text: str) -> List[str]`

Identifies target types from input text.

**Parameters:**
- `text` (str): Input string to analyze

**Returns:** List of entity type strings (e.g., ["person", "organization"])

### `generate_google_dorks(target_name: str, entity_types: List[str]) -> List[str]`

Creates advanced Google search queries.

**Parameters:**
- `target_name` (str): Target identifier
- `entity_types` (List[str]): Detected entity classifications

**Returns:** List of 10+ sophisticated dorks using operators like:
- `site:` - Site-specific searches
- `filetype:` - File type filtering
- `inurl:` / `intitle:` - URL/title matching
- `"exact phrase"` - Phrase matching

### `create_api_queries(entity_types: List[str], platforms: List[str]) -> List[Dict]`

Generates platform-specific API query strings.

**Parameters:**
- `entity_types` (List[str]): Target classifications
- `platforms` (List[str]): Social media platforms to target

**Returns:** List of dictionaries with:
```python
{
    "platform": "linkedin",
    "endpoint": "/v2/people/search",
    "query_string": "name=John+Doe",
    "auth_required": True,
    "rate_limit_hint": 10  # requests per minute
}
```

---

## HARVESTING Stage API

### `execute_osint_harvest(dorks: List[str], serper_api_key: str, scrapingant_api_key: str, max_concurrent: int = 5) -> HarvestOutput`

Main orchestration function for search execution.

**Parameters:**
- `dorks` (List[str]): Google Dorks to execute
- `serper_api_key` (str): Serper.dev API key
- `scrapingant_api_key` (str): Scrapingant.com API key  
- `max_concurrent` (int): Maximum parallel searches (WIP limit)

**Returns:** `HarvestOutput` dataclass with:
```python
{
    "search_results": List[SearchResult],
    "scraped_contents": List[ScrapedContent],
    "total_processed": int,
    "successful": int,
    "failed": int,
    "success_rate": float  # Percentage
}
```

### `SerperClient` Class

Client for Serper.dev search API.

**Constructor:**
```python
def __init__(self, api_key: str):
    """Initialize with API key"""
```

**Methods:**

#### `execute_search(query: str, provider: SearchProvider = SERPER) -> Dict`
Execute Google search via Serper.dev.

**Parameters:**
- `query` (str): Search query (Google Dork)
- `provider` (SearchProvider): Which search engine to use

**Returns:** Raw JSON response dictionary with:
```python
{
    "status": True,
    "json_response": "{...}",  # Parsed JSON string
    "execution_time_ms": float
}
```

### `ScrapingantClient` Class

Client for Scrapingant.com HTML scraping.

**Constructor:**
```python
def __init__(self, api_key: str):
    """Initialize with API key"""
```

**Methods:**

#### `scrape_url(url: str, max_retries: int = 3) -> ScrapedContent`

Scrape HTML content from URL.

**Parameters:**
- `url` (str): Target URL to scrape
- `max_retries` (int): Maximum retry attempts

**Returns:** `ScrapedContent` dataclass with:
```python
{
    "url": str,
    "status_code": int,
    "html_content": str,  # Raw HTML
    "text_content": str,  # Extracted text (optional)
    "execution_time_ms": float,
    "error": Optional[str]
}
```

### `ScrapingantClient` Important Note:
**API domain is `api.scrapingant.com`**, NOT `scraperant.com`. The client automatically uses the correct domain.

**Example Usage:**
```python
from osint_harvesting_stage import ScrapingantClient

client = ScrapingantClient(api_key="your_key")
result = await client.scrape_url("https://example.com")

if result.is_success:
    print(f"Successfully scraped {len(result.html_content)} bytes")
else:
    print(f"Error: {result.error}")
```

### `RateLimiter` Class

Token bucket rate limiter for API calls.

**Constructor:**
```python
def __init__(self, rate: float = 10.0, burst_size: int = 5):
    """
    Args:
        rate: Requests per second allowed
        burst_size: Maximum burst capacity
    """
```

**Methods:**

#### `async acquire()`
Acquire a token, waiting if necessary to stay within limits.

### `CircuitBreaker` Class

Prevents cascading failures across API calls.

**Constructor:**
```python
def __init__(self, failure_threshold=5, recovery_time=60):
    """
    Args:
        failure_threshold: Failures before opening circuit
        recovery_time: Seconds to wait before attempting recovery
    """
```

**State Transitions:**
- `CLOSED` → Normal operation
- `OPEN` → After threshold failures (blocks execution)
- `HALF_OPEN` → After recovery time (allows one test request)

**Methods:**
```python
def record_success():  # Reset failure counter
def record_failure():   # Increment failure counter
def can_execute() -> bool:  # Check if allowed to proceed
```

---

## ANALYST Stage API

### `analyze_osint_data(harvest_output: HarvestOutput, match_criteria: Dict = None) -> AnalysisReport`

Main orchestration function for verification and consensus detection.

**Parameters:**
- `harvest_output` (HarvestOutput): Raw results from HARVESTING stage
- `match_criteria` (Dict): Matching rules configuration

**Returns:** `AnalysisReport` dataclass with:
```python
{
    "verified_entities": List[VerifiedEntity],      # High-confidence matches
    "potential_matches": List[PotentialMatch],     # Moderate confidence
    "conflicts": List[Conflict],                   # Data contradictions
    "manual_review_queue": List[ManualReviewItem], # Items needing human review
    "confidence_summary": ConfidenceSummary,       # Quality metrics
    "data_quality_flags": List[str]                # Hallucination warnings
}
```

### `detect_consensus(harvested_data: Dict, match_criteria: Dict) -> List[VerifiedEntity]`

Find matching data points across multiple sources.

**Parameters:**
- `harvested_data` (Dict): Raw search results from HARVESTING
- `match_criteria` (Dict): Matching rules

**Returns:** List of verified entities with consensus scores ≥ 0.8

### `resolve_conflicts(conflicting_data: List[Dict]) -> ConflictResolutionStrategy`

Categorize and route conflicting information.

**Parameters:**
- `conflicting_data` (List[Dict]): Contradictory data points

**Returns:** `ConflictResolutionCategory` enum with resolution strategy:
```python
class ConflictResolutionCategory(Enum):
    PROFILE_MISMATCH = "Multiple profiles, different details"
    DATA_CONFLICT = "Same person, contradictory information"  
    INSUFFICIENT_DATA = "Not enough cross-references"
    POTENTIAL_HALLUCINATION = "Data appears fabricated"
```

### `compute_confidence_score(entity: VerifiedEntity) -> float`

Calculate confidence score based on multiple factors.

**Algorithm:**
```python
confidence = (
    source_reliability * 0.4 +        # LinkedIn > GitHub > Twitter < news
    cross_source_agreement * 0.35 +   # More sources agreeing = higher score
    recency_factor * 0.15 +           # Recent data prioritized
    detail_richness * 0.1             # Detailed profiles score better
)

# Returns float between 0.0 and 1.0
```

### `VerifiedEntity` Dataclass

Structure for verified cross-source matches.

**Fields:**
- `entity_id` (str): Unique identifier
- `source_types` (List[str]): Types of sources matched (e.g., ["linkedin", "github"])
- `matched_fields` (Dict): Fields with consensus scores
- `confidence_score` (float): Overall confidence (0.0-1.0)
- `verification_status` (str): One of: "VERIFIED", "POTENTIAL_MATCH", "LOW_CONFIDENCE"

**Example:**
```python
VerifiedEntity(
    entity_id="linkedin_github_2847",
    source_types=["linkedin_profile", "github_repository"],
    matched_fields={
        "city": {"value": "San Francisco", "consensus_score": 0.95},
        "project_name": {"value": "AI Tool", "consensus_score": 1.0}
    },
    confidence_score=0.87,
    verification_status="VERIFIED"
)
```

---

## SCRIBE Stage API

### `generate_osint_report(analysis_data: AnalysisReport, target_name: str, format: ReportFormat, output_path: str) -> ReportGenerationResult`

Generate professional reports from verified data.

**Parameters:**
- `analysis_data` (AnalysisReport): Verified entities and metadata
- `target_name` (str): Target identifier for report header
- `format` (ReportFormat): Desired output format
- `output_path` (str): Base filename (without extension)

**Returns:** `ReportGenerationResult` dataclass with:
```python
{
    "pdf_generated": bool,
    "pdf_size_mb": float,  # Report file size in MB
    "html_generated": bool,
    "html_size_kb": float,  # HTML file size in KB
    "errors": List[str]     # Any warnings or issues encountered
}
```

### `ReportFormat` Enum

Output format options:
```python
class ReportFormat(str, Enum):
    PDF = "pdf"           # Professional document with ReportLab
    HTML = "html"         # Web-ready report with Jinja2 templates
    BOTH = "both"         # Generate both formats simultaneously
```

### `ask_user_report_format() -> ReportFormat`

Interactive prompt for user preference.

**Returns:** User-selected format from `ReportFormat` enum

**Prompt Text:**
```bash
📄 How would you like the report generated?
   [1] PDF Only (Professional document)
   [2] HTML Only (Web-ready format)
   [3] Both Formats (Recommended for archival)

Enter choice: 
```

### `generate_pdf_report(report_data: Dict, output_path: str, branding: Dict = None) -> ReportGenerationResult`

Generate PDF report using ReportLab.

**Parameters:**
- `report_data` (Dict): Compiled report content
- `output_path` (str): File path for output
- `branding` (Dict, optional): Custom branding options

**Branding Options:**
```python
{
    "company_logo": "./assets/logo.png",  # Path to logo image
    "watermark_text": "CONFIDENTIAL",     # Page watermark text
    "color_scheme": "corporate_blue"      # Predefined or custom colors
}
```

**Returns:** `ReportGenerationResult` with PDF details

### `generate_html_report(report_data: Dict, output_path: str) -> ReportGenerationResult`

Generate HTML report using Jinja2 templates.

**Parameters:**
- `report_data` (Dict): Compiled report content  
- `output_path` (str): File path for output

**Template Sections Included:**
- Executive Summary
- People/Identity
- Social Media (all platforms)
- Web Intelligence
- Digital Infrastructure
- Geolocation
- Public Records
- Dark Web Monitoring
- Sources Discovered (complete references)

**Returns:** `ReportGenerationResult` with HTML details

---

## Kanban Manager API

### `OsintKanbanManager` Class

Pipeline orchestration layer coordinating all stages.

**Constructor:**
```python
def __init__(self, config: PipelineConfig):
    """Initialize manager with configuration"""
```

**Parameters:**
- `config` (PipelineConfig): Pipeline settings

### `execute_pipeline(query: str, report_format: ReportFormat, output_path: str) -> PipelineExecutionResult`

Execute complete OSINT investigation pipeline.

**Parameters:**
- `query` (str): User target description
- `report_format` (ReportFormat): Desired report format
- `output_path` (str): Base path for output files

**Returns:** `PipelineExecutionResult` dataclass with:
```python
{
    "total_processed": int,           # Total tickets moved through pipeline
    "successful": int,                # Fully completed without errors
    "failed_retryable": int,          # Failed but recovered after retry
    "failed_permanent": int,          # Moved to manual review queue
    "bottlenecks_detected": List[str],  # Which stages caused slowdowns
    "total_execution_time_seconds": float,
    "average_throughput_per_minute": float,
    "error_summary": Dict[str, int],  # Count by failure type
    "report_path": str | None         # Path to generated report(s)
}
```

**Example:**
```python
from osint_kanban_manager import OsintKanbanManager, PipelineConfig
from osint_scribe_stage import ReportFormat

config = PipelineConfig(
    target_name="John Doe",
    wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
    api_keys={
        "SERPER_API_KEY": os.getenv("SERPER_API_KEY"),
        "SCRAPINGANT_API_KEY": os.getenv("SCRAPINGANT_API_KEY")
    }
)

manager = OsintKanbanManager(config=config)
result = await manager.execute_pipeline(
    query="John Doe, Apple Inc",
    report_format=ReportFormat.BOTH,
    output_path="./reports/osint_john_doe"
)

print(f"Processed {result.total_processed} tickets")
print(f"Success Rate: {(result.successful / result.total_processed * 100):.1f}%")
```

### `PipelineConfig` Dataclass

Configuration settings for pipeline execution.

**Fields:**
- `target_name` (str): Target identifier
- `wip_limits` (Dict[str, int]): WIP limits per stage
- `api_keys` (Dict[str, str]): API credentials
- `max_retries_per_ticket` (int): Retry attempts per ticket
- `enable_circuit_breaker` (bool): Circuit breaker activation
- `recovery_time_after_failure` (int): Seconds to wait before recovery

### `PipelineHealthMonitor` Class

Real-time monitoring and bottleneck detection.

**Methods:**

#### `get_bottleneck_stage() -> Optional[str]`
Identify which stage is causing slowdown.

**Returns:** Stage name or None if no bottleneck detected

#### `calculate_throughput() -> float`
Calculate current throughput rate.

**Returns:** Tickets processed per minute

#### `detect_queue_imbalance() -> Dict[str, int]`
Find stages with accumulating backlog.

**Returns:** Dictionary mapping stage names to queue lengths

### `handle_stage_failure()` Decorator

Automatic retry logic for individual stage failures.

**Usage:**
```python
@handle_stage_failure(max_retries=3)
async def execute_recon_stage(ticket: OsintTicket) -> bool:
    # Stage execution code
    pass
```

**Behavior:**
- Automatically retries failed operations up to `max_retries` times
- Implements exponential backoff between attempts
- Updates error counters for monitoring
- Moves permanently failed items to manual review queue

---

## Data Flow Overview

### Complete Pipeline Execution Flow:

```python
# 1. Initialize pipeline
config = PipelineConfig(
    target_name="John Doe",
    wip_limits={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1},
    api_keys={...}
)

manager = OsintKanbanManager(config=config)

# 2. Execute pipeline
result = await manager.execute_pipeline(
    query="John Doe, Apple Inc",
    report_format=ReportFormat.BOTH,
    output_path="./reports/osint_john_doe"
)

# 3. Review results
print(f"✅ Pipeline complete!")
print(f"   Reports generated: {result.report_path}")
print(f"   Success rate: {result.successful / result.total_processed * 100:.1f}%")
```

### Error Handling Flow:

```python
try:
    # Execute pipeline
    result = await manager.execute_pipeline(...)
    
    if manager.has_critical_failures():
        print("⚠️ Pipeline experienced critical failures!")
        await manager.generate_error_report()
        
except KeyboardInterrupt:
    print("\n⏹️ Interrupted by user")
    await manager.cleanup()  # Save state for resumption
    
finally:
    await manager.cleanup()  # Always cleanup resources
```

---

## Integration Examples

### Custom Configuration Example:

```python
from osint_analyst_stage import AnalystAgent, AnalysisConfig

# Create custom analyst with strict verification
strict_config = AnalysisConfig(
    min_confidence_for_verification=0.85,
    strict_cross_reference=True,
    conflict_detection_depth="deep"
)

analyst_agent = AnalystAgent(config=strict_config)
```

### Real-time Monitoring Example:

```python
async def monitor_pipeline(manager):
    while manager.is_running():
        status = manager.get_status()
        
        print(f"\n{'='*60}")
        print(f"Pipeline Status: {status.state}")
        print(f"Throughput: {status.throughput_per_minute:.2f} tickets/min")
        print(f"Bottleneck: {status.bottleneck or 'None'}")
        
        for stage, column in manager.columns.items():
            wip = len(column)
            max_wip = manager.config.wip_limits[stage]
            status_bar = "█" * (wip // 10) + "░" * ((max_wip - wip) // 10)
            print(f"{stage:12} [{status_bar}] {wip}/{max_wip}")
        
        await asyncio.sleep(5)

# Run monitoring alongside pipeline
monitor_task = asyncio.create_task(monitor_pipeline(manager))
await manager.execute_pipeline(...)
monitor_task.cancel()
```

---

## Error Types and Handling

### `ScrapingantError` (Base Class)
- **Subclasses:** `RateLimitExceeded`, `ScrapingantTimeout`
- **Handling:** Automatic retry with backoff

### `CircuitBreakerOpenException`
- **Cause:** Too many consecutive failures
- **Action:** Wait for recovery time before retry

### `MaxRetriesExceeded`
- **Cause:** Failed after all retry attempts
- **Action:** Move to manual review queue

### `PipelineCriticalFailure`
- **Cause:** Multiple stage failures or data corruption
- **Action:** Generate error report, continue with degraded mode

---

## Performance Metrics

All execution results include:

| Metric | Description | Typical Range |
|--------|-------------|---------------|
| `total_execution_time_seconds` | Total pipeline runtime | 30s - 10min |
| `average_throughput_per_minute` | Tickets processed per minute | 5-20 |
| `success_rate` | Percentage of successful operations | 70-95% |
| `bottleneck_detected` | Stage causing slowdown | None/RECON/HARVESTING |

Use these metrics to optimize configuration for your specific use case.

---

**API Reference Version:** 1.0  
**Last Updated:** 2024-12-17
