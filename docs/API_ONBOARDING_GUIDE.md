# OSINT API Onboarding System - User Guide

## Overview

The **API Onboarding System** allows you to dynamically add and configure external OSINT tools (like Shodan, SpiderFoot, BuiltWith) without modifying code. It automatically updates your `.env` file with secure API key handling.

---

## Quick Start

### 1. List Available Tools

```bash
python osint_api_onboarding.py list-tools
```

**Output:**
```
======================================================================
AVAILABLE OSINT TOOLS FOR ONBOARDING
======================================================================

[ ] BUILTWITH
   Display Name: BuiltWith Technology Profiler
   Category: Technology_detection, Reconnaissance, Competitive_analysis
   Rate Limit: 60 req/min
   Status: Not configured - run 'onboard builtwith' to set up

[ ] SHODAN
   Display Name: Shodan Internet Scanner
   Category: Reconnaissance, Network_scanning, Vulnerability
   Rate Limit: 60 req/min
   Status: Not configured - run 'onboard shodan' to set up

[ ] SPIDERFOOT
   Display Name: SpiderFoot OSINT Automation
   Category: Osint, Reconnaissance, Threat_intelligence
   Rate Limit: 10 req/min
   Status: Not configured - run 'onboard spiderfoot' to set up
```

The `[ ]` indicator means the tool is not yet configured. Once you add an API key, it changes to `[OK]`.

---

### 2. Onboard a Tool (Interactive)

To configure **Shodan**:

```bash
python osint_api_onboarding.py onboard shodan
```

**Interactive Flow:**
1. Shows tool details and rate limits
2. Creates automatic backup of `.env` file
3. Prompts for API key (hidden input)
4. Validates key length
5. Tests connection to Shodan API
6. Confirms successful configuration

**Example Output:**
```
============================================================
Onboarding Tool: shodan
Display Name: Shodan Internet Scanner
Category: reconnaissance, network_scanning, vulnerability
Rate Limit: 60 requests/min
============================================================

[OK] Created backup: .env.backup.20240115_143022

Enter your SHODAN API Key
```

After entering and confirming the key:
```
[OK] SHODAN API key successfully stored!
   Environment variable: SHODAN_API_KEY

Testing Shodan API connection...
[OK] Shodan connection successful!
   Account Type: Free
   API Calls Today: 0 / 100

[OK] Shodan successfully onboarded!
   Environment variable 'SHODAN_API_KEY' is now set

Tip: Use the following in your scripts:
   import os
   api_key = os.environ.get('SHODAN_API_KEY')
```

---

### 3. Check Configuration Status

View all currently configured tools:

```bash
python osint_api_onboarding.py status
```

**Output:**
```
============================================================
CURRENT API CONFIGURATION STATUS
============================================================

[OK] SHODAN
   Environment Variable: SHODAN_API_KEY
   API Key: 1a2b...3c4d (length: 32)

[OK] BUILTWITH
   Environment Variable: BUILTWITH_API_KEY
   API Key: x9y8...z7w6 (length: 28)

============================================================
```

---

### 4. Remove a Tool's Configuration

To remove Shodan from your configuration:

```bash
python osint_api_onboarding.py remove shodan
```

**Interactive Flow:**
1. Warns about what will be removed
2. Asks for confirmation
3. Removes the API key from `.env` file
4. Confirms successful removal

---

### 5. Add Custom Tools

If you need to onboard a tool not in the built-in list:

```bash
python osint_api_onboarding.py custom \
    --name mytool \
    --display-name "My Custom OSINT Tool" \
    --category reconnaissance \
    --api-base-url https://api.mytool.com/v1/ \
    --auth-type API_KEY \
    --rate-limit 30
```

**Options:**
- `--name`: Unique identifier (lowercase, no spaces)
- `--display-name`: Human-readable name shown in UI
- `--category`: Comma-separated categories (can specify multiple times)
- `--api-base-url`: Base URL for the API
- `--auth-type`: One of: `API_KEY`, `OAUTH2`, `BASIC`, `NONE`
- `--rate-limit`: Max requests per minute

---

## Integration with Your Scripts

Once a tool is onboarded, you can use it in your Python scripts:

### Basic Usage Pattern

```python
import os

# Load environment variables automatically (if using python-dotenv)
from dotenv import load_dotenv
load_dotenv()

# Get API key from environment
shodan_api_key = os.environ.get('SHODAN_API_KEY')

if not shodan_api_key:
    raise EnvironmentError("SHODAN_API_KEY not configured. Run 'onboard shodan' first.")

# Use the key with your preferred library
import shodan

api = shodan.Shodan(shodan_api_key)

try:
    # Search for devices
    results = api.host.search('apache')
    
    print(f"Found {results['total']} results")
    
except Exception as e:
    print(f"Error: {e}")
```

### For BuiltWith

```python
import os
import requests

builtwith_api_key = os.environ.get('BUILTWITH_API_KEY')

if not builtwith_api_key:
    raise EnvironmentError("BUILTWITH_API_KEY not configured")

# Make API request
response = requests.get(
    'https://api.builtwith.com/v13/API.json',
    params={'key': builtwith_api_key, 'DOMAIN': 'example.com'}
)

if response.status_code == 200:
    data = response.json()
    print(f"Technologies found: {len(data)}")
```

---

## Security Features

### 1. Automatic Backups

Every time you onboard or remove a tool, the system creates a timestamped backup of your `.env` file:

```bash
ls -la .env.backup.*
# .env.backup.20240115_143022
# .env.backup.20240115_120015
```

You can restore from a backup if needed:
```bash
cp .env.backup.20240115_143022 .env
python osint_api_onboarding.py status  # Verify configuration restored
```

### 2. Key Validation

- API keys must be at least 8 characters long
- Environment variable names are validated (uppercase, alphanumeric, underscores only)
- Connection tests verify the key works before finalizing configuration

### 3. Secure Storage

API keys are stored as environment variables in your `.env` file:
```bash
SHODAN_API_KEY=your_actual_api_key_here
BUILTWITH_API_KEY=another_actual_key
```

**Never hardcode API keys directly in your scripts!**

---

## Troubleshooting

### "Required API keys are missing" error

This means your pipeline requires `SERPER_API_KEY` or `SCRAPINGANT_API_KEY`. Configure them:

```bash
python osint_api_onboarding.py onboard serper  # or scrapingant
```

Note: These tools must be added to the registry first if they're not already there.

### Connection Tests Fail

If API connection tests fail:
1. Verify your API key is correct and active
2. Check for typos in the key (copy-paste carefully)
3. Ensure you have an internet connection
4. For rate-limited services, wait a few minutes and try again

### "Invalid tool name" error

Tool names must be:
- Lowercase letters only
- No spaces or special characters
- Unique within the registry

Example valid names: `shodan`, `builtwith`, `my_custom_tool`

---

## Advanced Usage

### Programmatic API Key Check

```python
from osint_api_onboarding import EnvFileHandler, ToolRegistry

# Initialize handlers
env_handler = EnvFileHandler()
registry = ToolRegistry()

# Check if a tool is configured
def is_tool_configured(tool_name: str) -> bool:
    env_key = f"{tool_name.upper()}_API_KEY"
    return bool(env_handler.get_env_value(env_key))

# Usage in your pipeline
if not is_tool_configured('shodan'):
    print("ERROR: Shodan API key missing! Run 'python osint_api_onboarding.py onboard shodan'")
    exit(1)
```

### Automated Configuration Validation

Add this to your `main.py` before running the pipeline:

```python
from osint_api_onboarding import EnvFileHandler, ToolRegistry

def validate_required_tools():
    """Validate that all required tools are configured"""
    handler = EnvFileHandler()
    
    required_keys = [
        'SERPER_API_KEY', 
        'SCRAPINGANT_API_KEY'
    ]
    
    missing = []
    for key in required_keys:
        if not handler.get_env_value(key):
            missing.append(key)
    
    if missing:
        print(f"ERROR: Missing API keys: {', '.join(missing)}")
        print("Run 'python osint_api_onboarding.py status' to see configured tools")
        return False
    
    return True

# In main() function:
if not validate_required_tools():
    sys.exit(1)
```

---

## Available Commands Summary

| Command | Description | Example |
|---------|-------------|---------|
| `list-tools` | Show all available tools and their status | `python osint_api_onboarding.py list-tools` |
| `onboard <tool>` | Interactive setup for a specific tool | `python osint_api_onboarding.py onboard shodan` |
| `remove <tool>` | Remove API key configuration | `python osint_api_onboarding.py remove builtwith` |
| `status` | Show all configured tools and keys | `python osint_api_onboarding.py status` |
| `backup` | Create manual backup of .env file | `python osint_api_onboarding.py backup` |
| `custom ...` | Register new custom tool | See section above |

---

## Best Practices

1. **Always check status before running pipeline** - Run `status` to verify all required tools are configured
2. **Use strong API keys** - Generate keys with sufficient entropy from your provider's dashboard
3. **Backup regularly** - The system auto-backups, but you can also run manual backups
4. **Rotate keys periodically** - Update API keys before they expire or if compromised
5. **Never commit .env to git** - Add `.env` and `.env.backup.*` to your `.gitignore`

---

## Next Steps

Now that you have tools configured:

1. Test each tool individually using the connection tests
2. Integrate API key retrieval into your harvesting scripts
3. Implement rate limiting in your actual usage code
4. Set up monitoring for API quota limits
5. Document which tools are required vs optional for different investigation types

---

*Document Version: 1.0 | Last Updated: March 16, 2026*

Written By: Matt Pumphrey

