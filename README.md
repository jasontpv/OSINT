                                                                                                                                             @@@
                                                                   #####                                     #####                           @@@@@
                                                                 #########                                #########                        @@@@@@@
                                                                 ############                           ###########                        @@@@@@@
                                                                 ##############                      ############                          @@@@@@@
                                                                 #################                 ###########                             @@@@@@@
                                                                 ####### ###########            ############                               @@@@@@@
                                                                 #######   ############       ############          @@@@@@@@@              @@@@@@@
                                                                 #######     ############   ###########           @@@@@@@@@@@@@            @@@@@@@
                                                                 #######        ####################           @@@@@@@@@@@@@@@@@@          @@@@@@@
                                                                 #######          ################           @@@@@@@@@@@@@@@@@@@@@@@       @@@@@@@
                                                                 #######             ##########           @@@@@@@@@@@@     @@@@@@@@@@@     @@@@@@@
                                                                 #######                                @@@@@@@@@@@          @@@@@@@@@@@@  @@@@@@@
                                                                 #######                             @@@@@@@@@@@@              @@@@@@@@@@@@@@@@@@@
                                                                 #######                           @@@@@@@@@@@                    @@@@@@@@@@@@@@@@
                                                                 #######                        @@@@@@@@@@@@                         @@@@@@@@@@@@@
                                                                 #######                       @@@@@@@@@@@                             @@@@@@@@@@@
                                                                 #####                          @@@@@@@                                   @@@@@@
                                                                 ###
                                                                 #


             #####                ####                                          ####                     @@@@                   @@@@
            ########            #######                            ###          ####                     @@@@                   @@@@
            #########          ########                           ####          ####                     @@@@                   @@@@
            ####  #####     ###### ####   ####              ####  ###########   #####################    @@@@         @         @@@@    @@@@@@@@@@@@@@@@@@@      @@@@@@@@@@@@@ @@@@@@          @@@@@@
            ####   ######  ######  ####   ####              ####  ###########   ######################   @@@@       @@@@@       @@@@   @@@@@@@@@@@@@@@@@@@@@    @@@@@@@@@@@@@@   @@@@@@     @@@@@@@
            ####     #########     ####   ####              ####  ####          ####               ####  @@@@     @@@@@@@@@     @@@@  @@@@               @@@@  @@@@                 @@@@@@@@@@@@
           ####       ######      ####   ####              ####  ####          ####               ####  @@@@   @@@@@@ @@@@@@   @@@@  @@@@               @@@@  @@@@                   @@@@@@@@
            ####         ##        ####   ####              ####  ####          ####               ####  @@@@  @@@@@     @@@@@  @@@@  @@@@               @@@@  @@@@                  @@@@@@@@@@
            ####                   ####   ####              ####  #####         ####               ####  @@@@@@@@@         @@@@@@@@@  @@@@               @@@@  @@@@                @@@@@@  @@@@@@
            ####                   ####   ######################   ###########  ####               ####  @@@@@@@@           @@@@@@@@   @@@@@@@@@@@@@@@@@@@@@   @@@@              @@@@@@      @@@@@@
            ####                    ###     ####################     #########   ###               ####   @@@@@               @@@@@     @@@@@@@@@@@@@@@@@@@    @@@@            @@@@@@          @@@@@@
                                                            ####
                                          ######################
                                          #####################

																_ _      _ _       _
																b\\/:    //\/\att  ||)umphrey
																''                L|

## OSINT Kanban Pipeline

A production-ready, multi-stage Open Source Intelligence (OSINT) investigation system built on a Kanban-style workflow architecture. This tool automates the process of gathering, verifying, and reporting intelligence from open sources while maintaining strict quality controls and rate limiting.

## 🚀 Features

- **Kanban Workflow**: Pull-based pipeline with Work-In-Progress (WIP) limits to prevent overload
- **Four Specialized Stages**:
  - **RECON**: Query generation, Google Dork creation, API endpoint identification
  - **HARVESTING**: Search execution using Serper.dev and content scraping via ScrapingAnt
  - **ANALYST**: Cross-source verification, consensus detection, confidence scoring
  - **SCRIBE**: Professional report generation in PDF (ReportLab) or HTML (Jinja2) formats
- **Privacy Modes**: Choose between `public`, `private`, and `hybrid` execution — controls API key enforcement and LLM selection
- **Local or Cloud LLM**: Automatically routes to a local Ollama/LM-Studio instance or a cloud endpoint based on privacy mode
- **Auto-Updating CLI Tools**: On-demand binary installation (whois, nmap) with automatic 7-day repo refresh
- **Persistent State**: Binary paths cached in `~/.cli_tools.json`; last-run timestamp in `~/.osint_last_run.json`
- **Robust Error Handling**: Rate limiting, circuit breakers, exponential backoff
- **Quality Assurance**: Hallucination detection, conflict resolution, manual review queues

## 📦 Installation

### Prerequisites
- Python 3.9+
- pip package manager
- Serper.dev API key (free tier available at https://serper.dev)
- ScrapingAnt API key (free tier available at https://scrapingant.com)

### Step-by-Step Setup

```bash
# 1. Clone the repository
git clone https://github.com/MythWorxAI/OSINT-Automation-Tool
cd osint-kanban-pipeline

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or on Windows:
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
nano .env  # Edit and add your actual API keys
```

### Environment Variables (.env)

Create a `.env` file in the project root with:

```bash
# Required APIs
SERPER_API_KEY=your_serper_api_key_here
SCRAPINGANT_API_KEY=your_scrapingant_api_key_here

# Optional APIs (for enhanced coverage)
LEAK_LOOKUP_API_KEY=optional_leak_lookup_key
TWITTER_API_KEY=optional_twitter_key
LINKEDIN_API_KEY=optional_linkedin_key
GITHUB_TOKEN=optional_github_token

# LLM Configuration (Privacy Mode)
USE_CLOUD_LLM=0                           # Set to 1 to force cloud LLM in hybrid mode
OPENAI_API_KEY=optional_openai_key        # Required when USE_CLOUD_LLM=1 or --privacy public
OLLAMA_BASE_URL=http://localhost:11434/v1  # Local Ollama endpoint (default)

# Pipeline Configuration
MAX_RETRIES_PER_TICKET=3
WIP_LIMITS={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1}
LOG_LEVEL=INFO
```

## 🎯 Usage

### Command-Line Mode

```bash
# Basic execution — positional query
python main.py "John Doe"

# Using --target flag
python main.py --target "Apple Inc"

# Specify report format
python main.py --target "Apple Inc" --format html

# Generate both PDF and HTML reports
python main.py "John Doe" --format both

# Custom output directory
python main.py "Test Target" --output ./custom_reports/

# Investigate a domain (triggers whois during harvesting)
python main.py "example.com" --target-type domain --format pdf

# Full example from README
python main.py "Matthew Pumphrey" --wip-limit 5 --format both
```

### Privacy Mode (`--privacy` / `-p`)

The `--privacy` flag controls how strictly API keys are enforced and which LLM the pipeline uses:

```bash
# hybrid (default) — cloud APIs required; local Ollama used unless USE_CLOUD_LLM=1
python main.py "example.com" --privacy hybrid

# public — missing cloud API keys are warnings only; pipeline continues
python main.py "example.com" --privacy public

# private — all cloud API keys strictly required; local Ollama always used
python main.py "example.com" --privacy private
```

| Mode | Missing API keys | LLM used |
|------|-----------------|----------|
| `hybrid` | Error (pipeline stops) | Local Ollama (unless `USE_CLOUD_LLM=1`) |
| `public` | Warning only (pipeline continues) | Cloud OpenAI (falls back to local) |
| `private` | Error (pipeline stops) | Local Ollama always |

### Short Flag Aliases

| Long flag | Short | Default |
|-----------|-------|---------|
| `--target` | `-q` | — |
| `--target-type` | `-t` | `person` |
| `--wip-limit` | `-w` | `5` |
| `--format` | `-f` | `both` |
| `--output` | `-o` | `./reports` |
| `--privacy` | `-p` | `hybrid` |
| `--verbose` | `-v` | off |

### Report Format Options

- `pdf` — Professional document with headers, footers, and pagination
- `html` — Web-ready searchable report with embedded styling
- `both` — Generate both formats simultaneously (recommended for archival)

## 📊 Pipeline Architecture

```
User Input → [RECON] → [HARVESTING] → [ANALYST] → [SCRIBE] → Report Output
             ↓          ↓              ↓            ↓
         (WIP:3)    (WIP:5)        (WIP:2)       (WIP:1)
             ↓          ↓              ↓            ↓
         Pull      Pull           Pull          Pull
         On Capacity     On Capacity   On Capacity  On Completion
```

### Stage Descriptions

#### 1. RECON Stage
- Analyzes target input to identify entities (names, companies, products)
- Generates 10+ advanced Google Dorks with sophisticated operators
- Creates platform-specific API queries for social media platforms
- Includes confidence scoring and hallucination prevention

#### 2. HARVESTING Stage
- Executes dorks using Serper.dev search API
- Scrapes HTML content from discovered URLs via ScrapingAnt
- **Automatically invokes CLI tools** based on target type:
  - Domain targets → `whois`
  - IP address targets → `nmap`
  - Binary resolved from cache (`~/.cli_tools.json`) → `PATH` → auto-install via ToolProvisioner
- Implements rate limiting (token bucket algorithm)
- Handles failures with circuit breakers and exponential backoff
- Enforces WIP limits to prevent API exhaustion

#### 3. ANALYST Stage
- Cross-checks data across multiple sources for consensus
- Identifies conflicts and contradictory information
- Computes confidence scores based on:
  - Source reliability (LinkedIn > GitHub > Twitter < news)
  - Number of confirming sources
  - Data recency and detail richness
- Routes ambiguous cases to manual review queue

#### 4. SCRIBE Stage
- Generates professional reports in user-specified format
- Includes all required OSINT categories:
  - People/Identity, Social Media, Web Intelligence
  - Digital Infrastructure, Geolocation, Public Records
  - Dark Web Monitoring
- Provides executive summary and source citations
- Supports custom branding and watermarks

## 🔧 Configuration

### WIP Limits (Work-In-Progress)

Adjust parallelism per stage based on your API quotas:

```python
# Conservative mode (high reliability)
WIP_LIMITS={"RECON": 2, "HARVESTING": 3, "ANALYST": 1, "SCRIBE": 1}

# Balanced mode (default)
WIP_LIMITS={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1}

# Aggressive mode (high throughput)
WIP_LIMITS={"RECON": 5, "HARVESTING": 10, "ANALYST": 3, "SCRIBE": 1}
```

### Rate Limiting Configuration

The pipeline automatically handles rate limits with:
- Token bucket algorithm for smooth throttling
- Exponential backoff (1s → 60m max delay)
- Circuit breaker pattern to prevent cascading failures

### 7-Day Automatic Tool Updates

On every run the pipeline checks `~/.osint_last_run.json`. If more than 7 days have passed since the last execution, it re-provisions all entries in `tool_repos` (pulling the latest commit) before starting the investigation. This happens silently and is non-fatal.

To force a re-clone immediately, zero out the timestamp file:

```bash
echo '{"last_run": 0}' > ~/.osint_last_run.json
python main.py "example.com"
```

### Extending CLI Tool Repos

To add a new tool to the auto-update and HARVESTING pipeline, pass `tool_repos` at runtime or extend `OSINTPipeline._DEFAULT_TOOL_REPOS`:

```python
from main import OSINTPipeline
import asyncio

pipeline = OSINTPipeline(privacy_mode="hybrid")
result = asyncio.run(pipeline.run_investigation(
    query="example.com",
    target_type="domain",
    tool_repos={
        "amass":     "https://github.com/owasp-amass/amass.git",
        "subfinder": "https://github.com/projectdiscovery/subfinder.git",
    }
))
```

## 📁 Output Structure

After execution, reports are saved in `./reports/`:

```
reports/
├── osint_[target_name].pdf       # Professional document
├── osint_[target_name].html      # Web-ready report (if requested)
└── pipeline_metrics.json         # Execution statistics and logs
```

### Report Contents

Each report includes:
- **Executive Summary**: Verification status, key findings, risk assessment
- **People/Identity**: Name variations, aliases, demographic data
- **Social Media**: Platform presence, follower counts, activity timelines
- **Web Intelligence**: News mentions, forum discussions, press releases
- **Digital Infrastructure**: Domain ownership, hosting providers
- **Geolocation**: Current/past locations, travel patterns
- **Public Records**: Business filings, property records, court documents
- **Dark Web Monitoring**: Breach exposure, credential leaks
- **Sources Discovered**: Complete reference list with URLs and confidence scores

## 🛡️ Error Handling & Reliability

The system is designed to never crash:

| Failure Type | Automatic Response | Recovery Action |
|--------------|-------------------|-----------------|
| Rate Limit Hit | Exponential backoff retry | Queue item, retry after delay |
| API Timeout | Circuit breaker activation | Fallback to alternative provider |
| Parse Error | Text extraction fallback | Mark as partial data, continue |
| Max Retries | Move to manual review queue | Human intervention required |
| Multiple Failures | Pipeline degradation mode | Continue with available stages |
| CLI tool missing | Auto-install via ToolProvisioner | Path cached after first install |
| LLM unavailable | Log warning, skip LLM step | Pipeline continues without enrichment |

## 🔍 Testing

```bash
# Full unit + integration test suite
pytest -v

# Unit tests only (no live API keys required)
pytest tests/ -v --ignore=tests/integration/

# Live API integration tests (requires keys in .env)
pytest tests/integration/ -v
```

The test suite contains **119 tests** across 7 modules:

| Module | Coverage |
|--------|----------|
| `test_recon_stage.py` | Query generation, dork creation |
| `test_harvesting_stage.py` | Search execution, rate limiting |
| `test_analyst_stage.py` | Consensus detection, confidence scoring |
| `test_scribe_stage.py` | Report generation (ReportResult, MultiFormatReportGenerator) |
| `test_kanban_manager.py` | Pipeline orchestration, circuit breakers |
| `test_publicdata_api.py` | Public data API, pagination |
| `test_cli_and_db.py` | CLI flags (all options including `--privacy`), DatabaseManager, audit log |
| `tests/integration/` | Live Serper/ScrapingAnt/Leak-Lookup — skipped when keys absent |

### Manual Verification Scenarios

```bash
# First run — installs whois on first use (or skips if already on PATH)
python main.py "example.com" --target-type domain

# Second run — no install prompt, binary served from cache
python main.py "example.com" --target-type domain

# Force 7-day update cycle
echo '{"last_run": 0}' > ~/.osint_last_run.json
python main.py "example.com"

# Public mode without keys — pipeline continues with warnings
python main.py "example.com" --privacy public

# Private mode with a missing key — error raised immediately
python main.py "example.com" --privacy private
```

## 📈 Monitoring

During execution, monitor pipeline health in real-time:

```python
async def monitor_pipeline(manager):
    while manager.is_running():
        status = manager.get_status()
        print(f"Throughput: {status.throughput:.2f} tickets/min")
        print(f"Bottleneck Stage: {status.bottleneck}")

        for stage, column in manager.columns.items():
            wip = len(column)
            max_wip = manager.config.wip_limits[stage]
            status_bar = "█" * (wip // 10) + "░" * ((max_wip - wip) // 10)
            print(f"{stage:12} [{status_bar}] {wip}/{max_wip}")

        await asyncio.sleep(5)
```

## 🌐 API Integration

### Serper.dev (Search API)
- Primary search engine for Google, Bing, DuckDuckGo queries
- Free tier: 2,000 searches/month
- URL: https://serper.dev
- Environment variable: `SERPER_API_KEY`

### ScrapingAnt (Web Scraper)
- HTML content extraction from discovered URLs
- Free tier: 1,000 scrapes/month
- URL: https://scrapingant.com
- API endpoint: `api.scrapingant.com/v2/text`
- Environment variable: `SCRAPINGANT_API_KEY`

## 🚀 Production Deployment

For production use:

1. **Environment Variables**: Never commit `.env` to version control
2. **Logging**: Configure centralized logging (ELK, Splunk)
3. **Monitoring**: Set up alerts for pipeline bottlenecks and failures
4. **Scaling**: Increase WIP limits based on API quotas
5. **Backup**: Archive reports in cloud storage (S3, Azure Blob)
6. **Privacy**: Use `--privacy private` in air-gapped or sensitive environments; ensure Ollama is running at `OLLAMA_BASE_URL`

## How to add new OSINT tools

### Option A — Manual entry in ToolRegistry

Find the tool on GitHub (e.g. `https://github.com/s0md3v/Photon`) then add an entry to the `ToolRegistry.TOOLS` dict in [osint_cli_wrapper.py](osint_cli_wrapper.py):

```python
'photon': {
    'command_template': "/path/to/Photon/.venv/bin/python /path/to/photon.py -u {target}",
    'description': 'Photon - Fast crawler for OSINT',
    'required_api_key': None
},
```

### Option B — Auto-install via HARVESTING stage

To have the tool installed automatically and run during HARVESTING, add it to `CLICommandRunner.TOOL_MAP_BY_TARGET` in [osint_cli_wrapper.py](osint_cli_wrapper.py):

```python
TOOL_MAP_BY_TARGET = {
    "domain":     ["whois"],
    "ip_address": ["nmap"],
    "person":     ["theHarvester"],   # example addition
}
```

And register its GitHub URL in `OSINTPipeline._DEFAULT_TOOL_REPOS` in [main.py](main.py):

```python
_DEFAULT_TOOL_REPOS = {
    "whois":        "https://github.com/rfc1036/whois.git",
    "nmap":         "https://github.com/nmap/nmap.git",
    "theHarvester": "https://github.com/laramies/theHarvester.git",
}
```

The binary will be provisioned on first use and its path cached in `~/.cli_tools.json` for all subsequent runs.

## 📄 License

MYTHwORX License - See LICENSE file for details

## ⚠️ Disclaimer

This tool is designed for authorized security research, threat intelligence, and legitimate OSINT investigations only. Users must:
- Obtain proper authorization before investigating targets
- Comply with all applicable laws and terms of service
- Respect privacy and data protection regulations
- Use findings responsibly and ethically

The authors are not responsible for misuse of this tool or any legal consequences arising from its use.

## 📞 Support

For questions, issues, or feature requests:
- GitHub Issues: https://github.com/MythWorxAI/OSINT-Automation-Tool/issues
- Email: support@mythworx.ai

---

**Built with ❤️ by Senior AI Solutions Architects (MaDMaX) specializing in Agentic Workflows and OSINT.**
