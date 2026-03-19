# OSINT Kanban Pipeline - Detailed Usage Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Configuration Deep Dive](#configuration-deep-dive)
3. [Stage-by-Stage Workflow](#stage-by-stage-workflow)
4. [Advanced Configuration](#advanced-configuration)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)

---

## Quick Start

### 1. Installation (2 minutes)

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
nano .env  # Add your Serper.dev and Scrapingant.com keys
```

### 2. First Investigation (1 minute)

```bash
python main.py
```

Follow the interactive prompts:
- Enter target name/company/product
- Choose report format (PDF, HTML, or Both)
- Watch real-time pipeline execution
- Receive professional OSINT report in `./reports/`

### 3. Verify Results

Check your reports directory:
```bash
ls -lh ./reports/
# You should see:
# osint_[target_name].pdf
# osint_[target_name].html (if you chose "both")
```

---

## Configuration Deep Dive

### Environment Variables Explained

Create/edit `.env` file with these variables:

#### Required APIs

**Serper.dev Search API** (`SERPER_API_KEY`)
- Purpose: Google, Bing, DuckDuckGo search queries
- Get your key at: https://serper.dev/signup
- Free tier includes 2,000 searches/month
- Example value: `your_serper_api_key_here`

**Scrapingant.com Web Scraper** (`SCRAPINGANT_API_KEY`)  
- Purpose: HTML content extraction from discovered URLs
- Get your key at: https://scrapingant.com/signup
- Free tier includes 1,000 scrapes/month
- **IMPORTANT**: API calls use domain `api.scrapingant.com` (not scraperant.com)
- Example value: `your_scrapingant_api_key_here`

#### Optional Enhanced APIs

**Twitter/X API** (`TWITTER_API_KEY`)
- Purpose: Twitter profile and tweet analysis
- Get key at: https://developer.twitter.com/
- Required for social media intelligence on X platform

**LinkedIn API** (`LINKEDIN_API_KEY`)
- Purpose: Professional network analysis  
- Note: LinkedIn has strict rate limits; use with caution
- Requires premium account access

**GitHub Token** (`GITHUB_TOKEN`)
- Purpose: Code repository and developer activity analysis
- Create at: https://github.com/settings/tokens
- Set scopes: `public_repo`, `user`

#### Pipeline Configuration

```bash
# Maximum retry attempts per ticket before giving up
MAX_RETRIES_PER_TICKET=3

# Work-in-progress limits per stage (prevent overload)
WIP_LIMITS={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1}

# Logging verbosity: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
```

### WIP Limits Explained

Work-in-Progress (WIP) limits control parallelism per stage:

| Stage | Default | Conservative | Aggressive | Use Case |
|-------|---------|--------------|------------|----------|
| **RECON** | 3 | 2 | 5 | Query generation speed |
| **HARVESTING** | 5 | 3 | 10 | Search execution rate |
| **ANALYST** | 2 | 1 | 3 | Verification depth |
| **SCRIBE** | 1 | 1 | 2 | Report generation throughput |

**Conservative Mode**: Higher reliability, slower execution (recommended for critical investigations)
**Aggressive Mode**: Faster execution, higher rate limit risk (use with large API quotas)

---

## Stage-by-Stage Workflow

### RECON Stage: Query Generation

**Input**: User target description  
**Output**: 10+ Google Dorks + Platform-specific queries

**Example Process**:
```python
User Input: "John Doe, Apple Inc"

RECON Output:
{
    "queries": [
        'site:linkedin.com/in/ "John Doe" -intitle:jobs',
        '"Apple Inc" OR "AAPL" filetype:pdf',
        'inurl:"login" OR inurl:"signin"',
        # ... 7 more sophisticated dorks
    ],
    "api_queries": [
        {"platform": "linkedin", "endpoint": "/v2/people/search", "query": "name=John+Doe"},
        {"platform": "github", "endpoint": "/users/johndoe/repos", "query": ""},
        # ... 6 more platform queries
    ],
    "entity_types": ["person", "organization"],
    "confidence_scores": 0.87
}
```

**Key Features**:
- Pattern-based entity detection (names, companies, products)
- Confidence scoring to prevent false positives
- Hallucination prevention via site-specific filtering
- Automatic query diversification across search engines

### HARVESTING Stage: Search Execution

**Input**: List of Google Dorks from RECON  
**Output**: Structured JSON results + scraped HTML content

**Execution Flow**:
1. **Rate Limiting**: Token bucket algorithm ensures smooth throttling
2. **Circuit Breaker**: Prevents cascading failures
3. **Parallel Execution**: Up to 5 concurrent searches (configurable)
4. **Error Recovery**: Exponential backoff on failures

**Example Output**:
```json
{
    "search_results": [
        {
            "dork_original": "site:linkedin.com/in/ \"John Doe\"",
            "provider_used": "SERPER",
            "status_code": 200,
            "results_raw": {
                "organic": [
                    {"title": "John Doe - Senior Developer", "link": "..."},
                    {"title": "John Doe Profile", "link": "..."}
                ]
            },
            "execution_time_ms": 45.3,
            "error": null
        }
    ],
    "total_processed": 10,
    "successful": 8,
    "failed": 2,
    "success_rate": 80.0
}
```

**Error Handling**:
- **Rate Limit Hit**: Automatically queues item and retries after delay
- **API Timeout**: Exponential backoff with jitter (1s → 60m)
- **Circuit Breaker Open**: Temporarily halts execution to prevent overload

### ANALYST Stage: Verification & Consensus

**Input**: Raw search results from HARVESTING  
**Output**: Verified entities, conflicts, confidence scores

**Consensus Detection Logic**:
```python
# Match data points across sources
if (linkedin_profile.city == github_profile.location) and \
   (linkedin_profile.company == github_bio_company):
    confidence_score += 0.35  # Cross-source agreement bonus

# Source reliability weighting
source_weights = {
    "linkedin": 1.0,      # Highest weight for professional data
    "github": 0.8,        # Strong technical evidence
    "twitter": 0.6,       # Moderate confidence
    "news_site": 0.7      # Variable based on source reputation
}

# Final scoring formula
confidence = (source_reliability * 0.4) + \
             (cross_source_agreement * 0.35) + \
             (recency_factor * 0.15) + \
             (detail_richness * 0.1)
```

**Verification Categories**:
- **VERIFIED** (score ≥ 0.8): Multiple confirming sources, high confidence
- **POTENTIAL_MATCH** (0.5 ≤ score < 0.8): Some evidence, requires review
- **LOW_CONFIDENCE** (score < 0.5): Insufficient or conflicting data

**Conflict Resolution**:
```python
if conflicting_data:
    if conflict_type == "PROFILE_MISMATCH":
        move_to_manual_review("Multiple profiles with same name")
    elif conflict_type == "DATA_CONFLICT":
        flag_as_inconsistent("Same person, contradictory details")
    elif conflict_type == "INSUFFICIENT_DATA":
        request_more_sources("Not enough cross-references")
```

### SCRIBE Stage: Report Generation

**Input**: Verified entities from ANALYST  
**Output**: Professional PDF/HTML report with citations

**User Prompt**:
```bash
How would you like the report generated?
   [1] PDF Only (Professional document)
   [2] HTML Only (Web-ready format)
   [3] Both Formats (Recommended for archival)

Enter choice: 
```

**Report Structure**:
- **Executive Summary**: Key findings, verification status, risk assessment
- **People/Identity**: Names, aliases, demographics, photos
- **Social Media**: Platform presence, engagement metrics
- **Web Intelligence**: News mentions, forum discussions
- **Digital Infrastructure**: Domains, hosting, IP tracking
- **Geolocation**: Current/past locations, travel patterns
- **Public Records**: Business filings, property, court docs
- **Dark Web Monitoring**: Breach exposure, credential leaks
- **Sources Discovered**: Complete reference list with URLs

**Customization Options**:
```python
# Add company branding
report = await generate_report(
    ...
    branding={
        "logo": "./assets/company-logo.png",
        "watermark_text": "CONFIDENTIAL",
        "color_scheme": "corporate_blue"
    }
)

# Set classification level
report = await generate_report(
    ...,
    classification="TOP_SECRET"  # Affects watermark and formatting
)
```

---

## Advanced Configuration

### Custom Confidence Weights

Adjust scoring factors for your investigation type:

```python
from osint_analyst_stage import AnalystAgent, AnalysisConfig

# For high-accuracy investigations (legal/compliance)
strict_config = AnalysisConfig(
    min_confidence_for_verification=0.85,
    strict_cross_reference=True,  # Require matching fields from 2+ sources
    conflict_detection_depth="deep"  # Semantic analysis beyond exact matches
)

# For rapid intelligence gathering (threat hunting)
aggressive_config = AnalysisConfig(
    min_confidence_for_verification=0.65,
    strict_cross_reference=False,  # Accept single-source strong evidence
    conflict_detection_depth="shallow"  # Only explicit contradictions
)

analyst = AnalystAgent(config=strict_config)
```

### Rate Limit Tuning

Adjust rate limiter behavior for your API quotas:

```python
from osint_harvesting_stage import RateLimiter, SerperClient, ScrapingantClient

# Conservative (high reliability)
serper = SerperClient(
    api_key="...", 
    rate_limiter=RateLimiter(rate=5.0, burst_size=2)  # Slower, safer
)

# Aggressive (high throughput)  
scraper = ScrapingantClient(
    api_key="...",
    rate_limiter=RateLimiter(rate=10.0, burst_size=8)  # Faster, riskier
)
```

### Circuit Breaker Configuration

Modify failure thresholds for your environment:

```python
from osint_harvesting_stage import CircuitBreaker

# For critical investigations (few failures tolerated)
critical_breaker = CircuitBreaker(
    failure_threshold=3,  # Open after 3 failures
    recovery_time=120     # Wait 2 minutes before retry
)

# For non-critical operations (more resilient)
standard_breaker = CircuitBreaker(
    failure_threshold=5,  # More tolerance
    recovery_time=60      # Faster recovery
)
```

---

## Troubleshooting

### Common Issues & Solutions

#### Issue: "Circuit breaker OPENED" errors
**Cause**: Too many consecutive API failures  
**Solution**: 
1. Check API key validity
2. Reduce WIP limits (e.g., HARVESTING from 5 to 3)
3. Verify network connectivity
4. Wait for recovery time before retrying

#### Issue: "Rate limit exceeded" warnings
**Cause**: Exceeding API quota  
**Solution**:
1. Check current usage on Serper.dev/Scrapingant.com dashboards
2. Reduce `max_concurrent` parameter in HARVESTING stage
3. Increase `recovery_time` for circuit breaker
4. Upgrade to higher tier plan if needed

#### Issue: Low success rate (<50%)
**Cause**: Poor query quality or target not found  
**Solution**:
1. Review RECON output dorks for relevance
2. Try alternative search terms in user input
3. Check if target exists on monitored platforms
4. Increase `max_retries_per_ticket` parameter

#### Issue: Reports generated but missing sections
**Cause**: Insufficient verified data in ANALYST stage  
**Solution**:
1. Review conflict resolution logs for blocked findings
2. Adjust confidence thresholds to be more lenient
3. Add manual review items before finalizing report
4. Consider expanding search scope with additional dorks

### Debug Mode

Enable detailed logging:
```bash
export LOG_LEVEL=DEBUG
python main.py --target "Test Target"
```

This shows:
- Each query execution timing
- Rate limiter token status
- Circuit breaker state transitions
- Detailed error messages

---

## Best Practices

### For Production Use

1. **Monitor API Usage**: Set up alerts at 80% of monthly quota
2. **Cache Results**: Store previous investigations to avoid redundant searches
3. **Batch Investigations**: Group related targets for efficiency
4. **Regular Backups**: Archive reports in cloud storage (S3, Azure Blob)

### For High-Stakes Investigations

1. Use conservative WIP limits and strict cross-reference requirements
2. Enable deep conflict detection in ANALYST stage
3. Generate both PDF and HTML formats for archival
4. Review manual review queue items before finalizing report

### For Rapid Intelligence Gathering

1. Use aggressive mode with higher parallelism
2. Accept single-source strong evidence (lower confidence threshold)
3. Focus on most critical OSINT categories only
4. Use HTML format for faster delivery

### Security & Compliance

1. **Never commit API keys**: Always use environment variables
2. **Sanitize inputs**: Validate all user-provided targets
3. **Respect privacy**: Only investigate authorized targets
4. **Comply with laws**: Follow GDPR, CCPA, and local regulations
5. **Document findings**: Maintain chain of custody for legal proceedings

---

## Performance Optimization Tips

### Speed vs Accuracy Trade-off

| Mode | WIP Limits | Confidence Threshold | Use Case |
|------|------------|---------------------|----------|
| **Fast** | HARVESTING=10, ANALYST=3 | 0.65 | Rapid threat intel |
| **Balanced** (default) | HARVESTING=5, ANALYST=2 | 0.80 | Standard investigations |
| **Thorough** | HARVESTING=3, ANALYST=1 | 0.85 | Legal/compliance |

### Resource Management

- **Memory**: Large reports can use 50-100MB RAM; use streaming for very large targets
- **CPU**: Parallel execution uses multiple cores; adjust `max_concurrent` accordingly
- **Network**: Rate limits apply per API provider; monitor usage closely

---

## Next Steps

After completing your first investigation:

1. **Review Results**: Check report sections for completeness and accuracy
2. **Adjust Configuration**: Tune WIP limits based on observed performance
3. **Expand Scope**: Add additional target types or platforms as needed
4. **Automate**: Integrate with CI/CD pipelines for scheduled investigations
5. **Share Findings**: Export reports in team-friendly formats

---

**Need more help?** Check the [API Reference](./api_reference.md) or open an issue on GitHub.
