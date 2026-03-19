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

# MythWorx OSINT Framework v1.0.0
### Lean Compute. Massive Intelligence. Programmed by Matt Pumphrey

---

## 📋 Table of Contents
- [System Overview](#system-overview)
- [System Architecture](#system-architecture)
- [Feature Breakdown](#feature-breakdown)
- [RECON Stage: Query Generation & Entity Detection](#recon-stage-query-generation--entity-detection)
- [HARVESTING Stage: Dual-Mode Data Collection](#harvesting-stage-dual-mode-data-collection)
- [ANALYST Stage: ML-Based Fact Verification](#analyst-stage-ml-based-fact-verification)
- [PROVISIONER Stage: Secure Tool Integration](#provisioner-stage-secure-tool-integration)
- [SCRIBE Stage: Professional Report Generation](#scribe-stage-professional-report-generation)
- [Tool Registry](#tool-registry)
- [Privacy & Security Features](#privacy--security-features)
- [Technical Stack](#technical-stack)
- [System Status Dashboard](#system-status-dashboard)
- [Installation & Usage](#installation--usage)

---

## 🎯 System Overview

The **MythWorx OSINT Automation Tool** is an enterprise-grade intelligence gathering platform that orchestrates multiple reconnaissance methodologies through a unified, privacy-first architecture. Built on the principles of "Lean Compute" and "Massive Intelligence," the system automatically discovers, validates, and correlates information across dozens of data sources while maintaining complete operational security for sensitive investigations.

**Key Capabilities:**
- 🤖 Automated multi-stage investigation pipeline (RECON → HARVESTING → ANALYST → SCRIBE)
- 🔒 Privacy-preserving analysis using local LLM integration
- 🛡️ Security sandboxing for third-party tool execution
- 📊 Real-time monitoring dashboard with Flask/React architecture
- 🐳 Production-ready Docker/Kubernetes deployment support

---

## 🏗️ System Architecture

The OSINT Automation Tool implements a **Pull-Based Kanban Workflow** where each stage actively requests data from the previous one, ensuring controlled resource utilization and preventing information overload.

```
┌─────────────┐ ┌──────────────────┐ ┌─────────────┐ ┌─────────────┐
│ USER │────▶│ RECON │────▶│ HARVESTING │────▶│ ANALYST │
│ INPUT │ │ (Query Generation) │ │ (Data Collection)│◀──│(Verification)│
└─────────────┘ └──────────────────┘ └─────────────┘ └─────────────┘
│ │
▼ ▼
┌─────────────┐ ┌─────────────┐
│ ANALYST │◀─────────────│ SCRIBE │
│ (Scoring) │ │(Reporting) │
└─────────────┘ └─────────────┘
```

### Pull-Based Kanban Methodology:

| Stage | Status Indicator | WIP Limit | Description |
|-------|-----------------|-----------|-------------|
| **RECON** | 🔵 PENDING | 3 queries | Generates entity-specific search queries |
| **HARVESTING** | 🟡 IN_PROGRESS | 5 concurrent tools | Executes API and CLI commands to collect data |
| **ANALYST** | 🟠 PROCESSING | 2 parallel analyses | Cross-references facts, assigns confidence scores |
| **SCRIBE** | 🟢 COMPLETED | 1 report per investigation | Generates professional reports with evidence trails |

---

## 🔧 Feature Breakdown

### RECON Stage: Query Generation & Entity Detection

**Purpose:** Identify target entities and generate intelligent search queries for harvesting.

#### Capabilities:
- ✅ **Entity Classification Engine**: Automatically detects person, company, product, group entity types from input text
- ✅ **Confidence Scoring**: Assigns classification confidence (0.0–1.0) to detected entities
- ✅ **Context-Aware Query Optimization**: Adjusts query structure based on detected entity type and relationships
- ✅ **Google Dork Generation**: Creates advanced search queries with fail-safes against hallucination

#### Technical Implementation:
```python
# Example of RECON processing flow
class OSINTReconStage:
def process_query(self, user_input: str):
entities = self.entity_detector.detect(user_input) # Classifies input
for entity in entities:
queries = self.dork_generator.generate(
entity_type=entity.type,
query_value=entity.value
)
return {
'entities': entities,
'queries_generated': queries,
'confidence_scores': entity.confidence
}
```

#### Example Output:
| Detected Entity | Type | Confidence | Generated Queries |
|-----------------|------|------------|-------------------|
| `john.doe@example.com` | EMAIL | 98% | `site:linkedin.com "John Doe" email:*@example.com` |
| `Apple Inc.` | COMPANY | 95% | `site:apple.com employees AND "engineering"` |

---

### HARVESTING Stage: Dual-Mode Data Collection

**Purpose:** Execute tool commands via API or CLI to collect target data from multiple sources.

#### Capabilities:
- ✅ **API Tool Execution**: Makes authenticated HTTP requests to external OSINT APIs (Shodan, BuiltWith, Intelligence X)
- ✅ **Local Linux CLI Wrapper**: Executes shell commands (`sf.py`, `nmap`, `whois`) via controlled subprocess execution with timeout management
- ✅ **Output Capture System**: Real-time streaming of stdout/stderr with structured logging
- ✅ **Path Validation Engine**: Ensures all operations stay within workspace boundaries for security
- ✅ **Format Detection**: Automatically identifies JSON, CSV, or text output formats

#### Technical Implementation:
```python
# CLI execution logic example
class CLICommandRunner:
def run_command(self, command_template: str, target: str):
actual_command = command_template.replace("{target}", target)

# Subprocess execution with timeout and streaming
process = subprocess.Popen(
actual_command,
shell=True,
stdout=subprocess.PIPE,
stderr=subprocess.PIPE,
text=True
)

for line in iter(process.stdout.readline):
self._stream_output(line) # Real-time capture
```

#### Supported Execution Modes:
| Mode | Description | Timeout Default | Security Features |
|------|-------------|-----------------|-------------------|
| **API Tool** | REST API requests with authentication | 30s per request | Rate limiting, retry logic |
| **CLI Wrapper** | Local command execution via subprocess | 120s per command | Path validation, sandboxing |

---

### ANALYST Stage: ML-Based Fact Verification

**Purpose:** Process raw harvested data, cross-reference facts across sources, and assign confidence scores.

#### Capabilities:
- ✅ **Cross-Reference Engine**: Matches data points (emails, usernames, locations) across all harvested sources with normalization for Gmail variants, case-insensitivity
- ✅ **Confidence Scoring System**: Assigns Truth Scores (0–100%) based on source agreement patterns
- ✅ **Deduplication Engine**: Fingerprint-based merging of duplicate facts using MD5 hashing
- ✅ **ML-Based Verification**: Ensemble model combining RandomForest, GradientBoosting, LogisticRegression, and SVM classifiers for fact validation

#### Technical Implementation:
```python
# ML verification logic example
class MLFactVerifier:
def predict_fact_confidence(self, fact: Dict) -> Tuple[float, List[Dict]]:
features = self.extract_verification_features(fact) # Source count, quality, cross-ref match

model_predictions = {
'random_forest': rf.predict_proba(features),
'gradient_boosting': gb.predict_proba(features),
'logistic_regression': lr.predict_proba(features),
'svm': svm.predict_proba(features)
}

# Weighted ensemble scoring
final_confidence = sum(
model_predictions[name] * self.model_weights.get(name, 0)
for name in model_predictions.keys()
)

return round(final_confidence, 4), model_predictions
```

#### Confidence Scoring Rules:
| Source Agreement | Base Score | Quality Adjustment | Final Classification |
|------------------|------------|--------------------|---------------------|
| **3+ sources** | 70% | +30% (reputation) | ✅ VERIFIED (100%) |
| **2 sources** | 50% | +35% (reputation) | ⭐ HIGHLY_LIKELY (85%) |
| **Single source** | 30% | +40% (strong API) | 🔍 LIKELY (70%) |
| **Contradictory data** | -20% | Penalties apply | ❓ UNVERIFIED (45%) |

---

### PROVISIONER Stage: Secure Tool Integration

**Purpose:** Automatically provision new OSINT tools from GitHub with security validation.

#### Capabilities:
- ✅ **Secure Git Cloning**: Subprocess-based repository cloning with workspace boundary enforcement
- ✅ **Security Sandboxing**: Pattern detection for malicious code (reverse shells, data exfiltration, crypto miners)
- ✅ **Automated Dependency Installation**: Virtual environment creation and pip install automation
- ✅ **Dataset Indexing**: Automatic scanning of CSV/JSON files for Analyst stage queries

#### Technical Implementation:
```python
# Provisioner execution flow example
class ToolProvisioner:
def provision_tool_from_github(self, github_url):
# Step 1: Clone repository
clone_result = self.cloner.clone_repository(github_url)

# Step 2: Security scan (block if threats detected)
is_safe, patterns = SecuritySandbox.scan_repository(clone_result.local_path)

# Step 3: Create virtual environment and install dependencies
venv_path = self.installer.create_virtual_environment(clone_result.local_path)
install_result = self.installer.install_dependencies(venv_path)

return {
'clone_status': clone_result,
'security_passed': is_safe,
'dependencies_installed': install_result.dependencies_installed
}
```

#### Security Pattern Detection:
| Threat Category | Example Patterns Blocked | Severity Level |
|-----------------|--------------------------|----------------|
| **Reverse Shell** | `python -c "import socket,os,sys"`, `/bin/sh -i` | 🔴 CRITICAL |
| **Data Exfiltration** | `curl data.com/upload`, `scp sensitive-data@remote:` | 🟠 HIGH |
| **Crypto Miners** | `xmrig`, `stratum+tcp://pool.mining.com:3333` | 🟡 MEDIUM |
| **System Compromise** | `rm -rf /`, `chmod 777 /etc/passwd` | 🔴 CRITICAL |

---

### SCRIBE Stage: Professional Report Generation

**Purpose:** Generate branded, multi-format reports with executive summaries and evidence trails.

#### Capabilities:
- ✅ **Jinja2 Template Rendering**: HTML report generation with MythWorx branding
- ✅ **ReportLab PDF Generation**: Professional PDF documents with custom styling
- ✅ **Markdown & JSON Export**: Structured data formats for programmatic access
- ✅ **Evidence Trail Linking**: All facts traceable to original source tools

#### Technical Implementation:
```python
# Report generation logic example
class MultiFormatReportGenerator:
def generate_report(self, config: ReportConfig, output_format: str):
if output_format == 'html':
template = self.jinja_env.get_template('report.html')
content = template.render(**config)

elif output_format == 'pdf':
from reportlab.platypus import SimpleDocTemplate, Paragraph
doc = SimpleDocTemplate(buffer, pagesizes=pagesizes.A4)
story = [Paragraph(config.title, self.styles['CustomHeader'])]
# ... build PDF content
```

#### Report Format Comparison:
| Format | Best For | Features | Branding |
|--------|----------|----------|----------|
| **HTML** | Web viewing & sharing | Interactive charts, clickable evidence links | ✅ Full MythWorx branding |
| **PDF** | Print & client delivery | Professional layout, page numbering | ✅ Complete company identity |
| **Markdown** | Developer integration | Syntax highlighting, easy editing | ⚙️ Minimal branding header |
| **JSON** | API consumption | Structured data, machine-readable | 📊 Metadata with attribution |

---

## 🔧 Tool Registry

### Pre-Loaded Tools (Production Ready)

The system comes pre-configured with the following OSINT tools. Each tool includes rate limiting information and API key requirements:

| Tool Name | Type | Rate Limit | API Key Required | Description |
|-----------|------|------------|------------------|-------------|
| **Shodan** | API | 60 req/min, unlimited daily | ✅ Yes (`SHODAN_API_KEY`) | Internet scanner for network reconnaissance and IP address information |
| **SpiderFoot** | CLI/API | 10 req/min (API) / Unlimited (CLI) | ❌ No | Comprehensive OSINT automation platform with 400+ modules |
| **BuiltWith** | API | 60 req/min, 1000 daily | ✅ Yes (`BUILTWITH_API_KEY`) | Technology profiler for identifying website technologies and competitors |
| **Intelligence X** | API | Custom pricing tier | ✅ Yes (`INTELLIGENCE_X_API_KEY`) | Search engine with deep web indexing and historical data access |
| **WHOIS** | CLI | N/A (local command) | ❌ No | Domain registration lookup for ownership information |
| **nmap** | CLI | N/A (local command) | ❌ No | Network scanner for port scanning and service detection |
| **Photon** | CLI | Unlimited (local execution) | ❌ No | Web crawler for subdomain discovery and URL harvesting |

### New or Additional Tool Registration Process:

I have included a way to add additional tools for the agents to utilize. (See README.md) It will also git pull for updates once a month automatically.

```bash
# Register a new tool via API
python osint_api_onboarding.py onboard shodan

# Prompts for:
# 1. API Key validation
# 2. Rate limit configuration
# 3. Endpoint verification test
# 4. Status confirmation in registry
```

To grow the "Library" using the Provisioner, you have to download a github repo you want to add.
The, the osint_provisioner.py will clone https://github.com/repo/tool. Once cloned,  it will then use the Librarian logic to scan the folder for CSV files and index them for the Analyst.
**As part of a "Safety Check" I implemented, it uses the Security Sandbox to scan the repo for malicious code before it allows the clone to finish.


Example:

python osint_provisioner.py https://github.com/s0md3v/Photon

======================================================================
🔧 Provisioning Tool from GitHub
 URL: https://github.com/s0md3v/Photon
======================================================================

📥 STEP 1: Cloning Repository
📥 Cloning https://github.com/s0md3v/Photon...

🛡️ STEP 2: Running Security Scan
✅ Security scan passed

📦 STEP 3: Installing Dependencies
🔧 Creating virtual environment at /mnt/c/AI_Agent/OSINT_WORKSPACE/tools/Photon_s0md3v/.venv...
Next, add the tool to the ToolRegistry class in 'osint_cli_wrapper.py' (See *README.md). **Important to not skip this step so the agent knows how to use the new tool.
---

## 🔒 Privacy & Security Features

### Local LLM Integration (Privacy Mode)

The system supports **local Large Language Model** execution for private analysis, ensuring sensitive investigation data never leaves your infrastructure:

#### Supported Platforms:
| Platform | Installation Command | API Endpoint | Use Case |
|----------|---------------------|--------------|----------|
| **Ollama** | `ollama pull llama3.2` | `http://localhost:11434/api/generate` | Default local LLM (recommended) |
| **LM Studio** | Download & run executable | `http://localhost:1234/v1/chat/completions` | Alternative local inference engine |

#### Privacy Mode Configuration:
```python
# Configure privacy mode in main.py execution
python main.py "target.com" --privacy-mode local

# Options:
# - local: Maximum privacy (Ollama/LM Studio)
# - public: Cloud LLMs (faster, less private)
# - hybrid: Adaptive based on sensitivity level
```

#### Privacy Features Summary:
- ✅ **End-to-end encryption** for investigation data in transit
- ✅ **Local-only model execution** when privacy mode enabled
- ✅ **No cloud API calls** for sensitive analysis operations
- ✅ **Automatic fallback** to heuristic extraction if LLM unavailable

---

### Security Sandboxing (Third-Party Tools)

All externally provisioned tools undergo **mandatory security scanning** before installation:

#### Security Scan Categories:
| Category | Detection Method | Actions on Threats |
|----------|------------------|--------------------|
| **Malicious Patterns** | Regex pattern matching against 20+ threat signatures | 🔴 BLOCK IMMEDIATELY |
| **Network Activity** | Static analysis of outbound connection attempts | 🟡 FLAG FOR REVIEW |
| **File System Ops** | Monitor for dangerous file access patterns | 🟠 WARNING REPORTED |
| **Code Execution Risks** | Detect eval/exec, shell=True usage | 🔴 BLOCK EXECUTION |

#### Sandbox Enforcement:
```python
# Security validation example
class SecuritySandbox:
def scan_repository(self, repo_path):
dangerous_patterns = [
r'rm\s+-rf\s+/', # System-wide deletion
r'sudo\s+(passwd|useradd)', # Account manipulation
r'/tmp/.*\.(sh|py|bash)', # Script files in temp
]

for pattern in dangerous_patterns:
if re.search(pattern, content):
return False, "Security violation detected"

return True, "Repository passed security scan"
```

---

## 🛠️ Technical Stack

### Core Technologies

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Language** | Python | 3.10+ | Primary development language |
| **API Server** | Flask | 2.3.x | REST API for investigation orchestration |
| **Dashboard** | React + Socket.IO | 18.x / 4.x | Real-time monitoring interface |
| **Report Generation** | Jinja2 + ReportLab | 3.1.x / 2.20.x | HTML and PDF report creation |
| **Machine Learning** | scikit-learn | 1.3.x | Ensemble fact verification models |
| **Containerization** | Docker & Compose | 24.0+ | Production deployment orchestration |
| **Orchestration** | Kubernetes | 1.27+ | Scalable container management |

### Infrastructure Components:
```yaml
# docker-compose.yml architecture overview
services:
osint-tool-api: # Flask API server (main orchestration)
monitoring-dashboard: # React/Flask real-time dashboard
redis-cache: # Session and metric caching
postgres-db: # Investigation data persistence
ollama-service: # Local LLM inference engine
```

---

## 📊 System Status Dashboard

### Real-Time Monitoring Features:
- ✅ **Live investigation progress tracking** with WebSocket updates
- ✅ **Tool health monitoring** with automated status indicators
- ✅ **System metrics visualization** (charts, graphs, trend analysis)
- ✅ **Alert system** for failed operations and security events

#### Dashboard Metrics Displayed:
```javascript
// Real-time data points monitored:
{
"system_health_score": 87.5, // Overall platform status (0–100)
"active_investigations": 3, # Currently running investigations
"tools_healthy": 6, # Number of operational tools
"failed_operations_last_hour": 2, # Recent error count
"avg_report_generation_time": 4.2 // Seconds for report creation
}
```

---

## 📥 Installation & Usage

### Quick Start Commands:

```bash
# Install all dependencies
pip install -r requirements.txt

# Run full pipeline investigation (default privacy mode)
python main.py "example.com"

# Use cloud LLMs instead of local for faster analysis
python main.py "example.com" --privacy-mode public

# Generate PDF report instead of HTML
python main.py "example.com" --report-format pdf

# Include tool repository maintenance updates
python main.py "example.com" --run-maintenance

# View system status before execution
python main.py "target.com" --show-status
```

### Production Deployment:

```bash
# Deploy to Kubernetes cluster
kubectl apply -f k8s/production-deployment.yaml
kubectl rollout status deployment/osint-tool-production

# Monitor with Docker Compose
docker-compose up -d
docker-compose logs -f osint-tool-api

# Access monitoring dashboard
open http://localhost:5001
```

---

## 📜 License & Attribution

**Copyright © 2026 MythWorx, LLC. All rights reserved.**

Developed by **Matt Pumphrey**.
For more information visit [mythworx.ai](https://mythworx.ai)

This project is licensed under the MIT License. See LICENSE file for details. 

---

## 📞 Support & Contact

| Channel | Description | URL |
|---------|-------------|-----|
| **GitHub Issues** | Report bugs, request features | [github.com/mypumphrey/osint-automation-tool/issues](https://github.com/mypumphrey/osint-automation-tool/issues) |
| **Documentation** | Complete usage guide and API reference | [docs/README.md](docs/README.md) |
| **Email Support** | Enterprise inquiries | support@mythworx.ai |

---

*Last Updated: March 2026*
*Version: 1.0.0 (Stable Release)*
