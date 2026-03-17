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
  - **HARVESTING**: Search execution using Serper.dev and content scraping via Scrapingant.com
  - **ANALYST**: Cross-source verification, consensus detection, confidence scoring
  - **SCRIBE**: Professional report generation in PDF (ReportLab) or HTML (Jinja2) formats
- **Robust Error Handling**: Rate limiting, circuit breakers, exponential backoff
- **Quality Assurance**: Hallucination detection, conflict resolution, manual review queues

## 📦 Installation

### Prerequisites
- Python 3.9+
- pip package manager
- Serper.dev API key (free tier available at https://serper.dev)
- Scrapingant.com API key (free tier available at https://scrapingant.com)

### Step-by-Step Setup

```bash
# 1. Clone the repository or download files
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
TWITTER_API_KEY=optional_twitter_key
LINKEDIN_API_KEY=optional_linkedin_key
GITHUB_TOKEN=optional_github_token

# Pipeline Configuration
MAX_RETRIES_PER_TICKET=3
WIP_LIMITS={"RECON": 3, "HARVESTING": 5, "ANALYST": 2, "SCRIBE": 1}
LOG_LEVEL=INFO
```

## 🎯 Usage

### Interactive Mode (Recommended for First Use)

```bash
python main.py
```

This will:
1. Prompt you for investigation target (person, company, product)
2. Ask your preferred report format (PDF, HTML, or Both)
3. Execute the full pipeline with real-time monitoring
4. Generate professional reports in your specified format

### Command-Line Mode

```bash
# Basic execution
python main.py --target "John Doe"

# Specify report format
python main.py --target "Apple Inc" --format html

# Generate both PDF and HTML reports
python main.py --target "John Doe, Apple Inc" --format both

# Custom output directory
python main.py --target "Test Target" --output ./custom_reports/

# Set parallelism levels (advanced)
python main.py --target "Target Name" --wip-limit 5
```

### Report Format Options

- `pdf` - Professional document with headers, footers, and pagination
- `html` - Web-ready searchable report with embedded styling  
- `both` - Generate both formats simultaneously (recommended for archival)

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
- Scrapes HTML content from discovered URLs via Scrapingant.com
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

## 🔍 Testing

Run the test suite to verify installation:

```bash
pytest -v
```

Tests cover:
- Query generation accuracy
- Search execution and rate limiting
- Consensus detection logic
- Report generation quality
- Pipeline orchestration

## 📈 Monitoring

During execution, monitor pipeline health in real-time:

```python
# In main.py or custom script
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

### Scrapingant.com (Web Scraper)  
- HTML content extraction from discovered URLs
- Free tier: 1,000 scrapes/month
- URL: https://scrapingant.com
- Correct domain for API calls: `api.scrapingant.com`

## 🚀 Production Deployment

For production use:

1. **Environment Variables**: Never commit `.env` to version control
2. **Logging**: Configure centralized logging (ELK, Splunk)
3. **Monitoring**: Set up alerts for pipeline bottlenecks and failures
4. **Scaling**: Increase WIP limits based on API quotas
5. **Backup**: Archive reports in cloud storage (S3, Azure Blob)

## How to manually update osint_cli_wrapper.py with new OSINT Tools:

Find Tools you want to use on github.com (ie. 'https://github.com/Photon_s0md3v/photon')
Find the ToolRegistry class in 'osint_cli_wrapper.py' and add this entry so the AI knows how to use its new "hands":

'photon': {
    'command_template': "/mnt/c/OSINT-Automation-Tool/OSINT_WORKSPACE/tools/Photon_s0md3v/.venv/bin/python /mnt/c/OSINT-Automation-Tool/OSINT_WORKSPACE/tools/Photon_s0md3v/photon.py -u {target}",
    'description': 'Photon - Fast crawler for OSINT',
    'required_api_key': None
},


## 📄 License

MIT License - See LICENSE file for details

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
