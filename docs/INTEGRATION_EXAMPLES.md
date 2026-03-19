# API Onboarding Integration Examples

This document shows how to integrate the API onboarding system into your OSINT pipeline.

---

## 1. Pre-Pipeline Validation (Recommended)

Add this check at the start of `main.py` before running any investigations:

```python
#!/usr/bin/env python3
"""Enhanced main.py with API validation"""

import asyncio
import os
import sys
from pathlib import Path
import click
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import pipeline components
from osint_recon_stage import generate_osint_queries, ReconOutput
from osint_harvesting_stage import execute_osint_harvest, HarvestOutput
from osint_analyst_stage import analyze_osint_data, AnalysisReport
from osint_scribe_stage import generate_osint_report, ReportFormat
from osint_kanban_manager import OsintKanbanManager, PipelineConfig

# Import onboarding utilities
from osint_api_onboarding import EnvFileHandler


def validate_required_tools():
    """Validate that all required API keys are configured"""
    
    handler = EnvFileHandler()
    required_keys = [
        'SERPER_API_KEY', 
        'SCRAPINGANT_API_KEY'
    ]
    
    missing = []
    configured = []
    
    for key in required_keys:
        value = handler.get_env_value(key)
        if not value or len(value.strip()) == 0:
            missing.append(key)
        else:
            configured.append(key)
    
    # Display status
    click.echo(f"\n{'='*60}")
    click.echo("API CONFIGURATION CHECK")
    click.echo('='*60)
    
    if configured:
        for key in configured:
            value = handler.get_env_value(key)
            if len(value) > 8:
                display_key = f"{value[:4]}...{value[-4:]}"
            else:
                display_key = value
            
            click.echo(f"✅ {key}: Configured (length: {len(value)})")
    
    if missing:
        click.echo(f"\n❌ Missing API keys: {', '.join(missing)}")
        click.echo("\nTo configure, run:")
        for key in missing:
            tool_name = key.replace('_API_KEY', '').lower()
            click.echo(f"  python osint_api_onboarding.py onboard {tool_name}")
        click.echo('='*60)
        return False
    
    click.echo(f"\n✅ All required tools configured!")
    click.echo('='*60)
    
    return True


@click.command()
@click.option('--target', '-t', required=True, help='Target name/company/product to investigate')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def main(target: str, verbose: bool):
    """Execute OSINT investigation on target using Kanban pipeline."""
    
    # Pre-flight validation
    if not validate_required_tools():
        sys.exit(1)
    
    click.echo(f"\n🚀 Starting OSINT investigation for '{target}'...\n")
    
    # Rest of main logic...
```

---

## 2. Conditional Feature Usage Based on Configured Tools

Create a utility module to dynamically enable/disable features:

### `tools_config.py` (New File)

```python
"""Dynamic tool availability based on API configuration"""

import os
from typing import Dict, Optional, Any


class ToolAvailabilityChecker:
    """Check which tools are available for use in the pipeline"""
    
    def __init__(self):
        self.configured_tools = {}
        self._load_configuration()
    
    def _load_configuration(self):
        """Load configuration from environment variables"""
        
        # Check each tool's API key presence
        tools = {
            'shodan': os.environ.get('SHODAN_API_KEY', ''),
            'builtwith': os.environ.get('BUILTWITH_API_KEY', ''),
            'spiderfoot': os.environ.get('SPIDERFOOT_API_KEY', ''),
            'serper': os.environ.get('SERPER_API_KEY', ''),
            'scrapingant': os.environ.get('SCRAPINGANT_API_KEY', '')
        }
        
        self.configured_tools = {name: bool(key) for name, key in tools.items()}
    
    def is_available(self, tool_name: str) -> bool:
        """Check if a specific tool is configured"""
        return self.configured_tools.get(tool_name.lower(), False)
    
    def get_configured_tools(self) -> list:
        """Get list of all available tools"""
        return [name for name, available in self.configured_tools.items() 
                if available]
    
    def get_tool_key(self, tool_name: str) -> Optional[str]:
        """Get the environment variable key for a tool"""
        
        keys = {
            'shodan': 'SHODAN_API_KEY',
            'builtwith': 'BUILTWITH_API_KEY',
            'spiderfoot': 'SPIDERFOOT_API_KEY',
            'serper': 'SERPER_API_KEY',
            'scrapingant': 'SCRAPINGANT_API_KEY'
        }
        
        env_key = keys.get(tool_name.lower())
        
        if env_key:
            return os.environ.get(env_key)
        
        return None


# Global instance for easy access
tool_checker = ToolAvailabilityChecker()


def get_available_tools_for_recon():
    """Get list of tools available for reconnaissance"""
    
    available = []
    
    # Always use Serper (required)
    if tool_checker.is_available('serper'):
        available.append(('serper', 'Google Search via Serper.dev'))
    
    # Optional tools based on configuration
    if tool_checker.is_available('shodan'):
        available.append(('shodan', 'Shodan Internet Scanner'))
    
    if tool_checker.is_available('builtwith'):
        available.append(('builtwith', 'BuiltWith Technology Profiler'))
    
    return available


def get_available_tools_for_harvesting():
    """Get list of tools available for data harvesting"""
    
    available = []
    
    # Always use Scrapingant (required)
    if tool_checker.is_available('scrapingant'):
        available.append(('scrapingant', 'ScrapingAnt Proxy Service'))
    
    # Optional tools based on configuration
    if tool_checker.is_available('spiderfoot'):
        available.append(('spiderfoot', 'SpiderFoot OSINT Platform'))
    
    return available


# Example usage in your pipeline:

def execute_recon_with_optional_tools(user_query: str):
    """Execute RECON stage with dynamically selected tools"""
    
    from osint_recon_stage import generate_osint_queries
    
    # Get primary search tool (Serper)
    serper_key = tool_checker.get_tool_key('serper')
    
    if not serper_key:
        raise EnvironmentError("SERPER_API_KEY not configured")
    
    result = generate_osint_queries(user_query, serper_api=serper_key)
    
    # Add optional tools based on configuration
    if tool_checker.is_available('shodan'):
        shodan_results = execute_shodan_recon(user_query, 
                                              api_key=tool_checker.get_tool_key('shodan'))
        result.extend(shodan_results)
    
    if tool_checker.is_available('builtwith'):
        builtwith_results = execute_builtwith_recon(user_query,
                                                    api_key=tool_checker.get_tool_key('builtwith'))
        result.extend(builtwith_results)
    
    return result


def execute_shodan_recon(query: str, api_key: str):
    """Execute Shodan-specific reconnaissance"""
    
    import requests
    
    # Build query for Shodan
    shodan_query = f"product:{query}"
    
    try:
        response = requests.get(
            'https://api.shodan.io/shodan/host/search',
            auth=(api_key, ''),
            params={'key': api_key, 'search': shodan_query, 'limit': 10}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            results = []
            for host in data.get('matches', []):
                results.append({
                    'tool': 'shodan',
                    'type': 'host',
                    'ip': host.get('ip_str'),
                    'port': host.get('port'),
                    'service': host.get('product', ''),
                    'confidence': 0.85
                })
            
            return results
    
    except Exception as e:
        print(f"Shodan error: {e}")
    
    return []


def execute_builtwith_recon(domain: str, api_key: str):
    """Execute BuiltWith technology profiling"""
    
    import requests
    
    try:
        response = requests.get(
            'https://api.builtwith.com/v13/API.json',
            params={'key': api_key, 'DOMAIN': domain}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            results = []
            if isinstance(data, list) and len(data) > 0:
                technologies = data[0].get('Paths', [{}])[0].get('Tools', [])
                
                for tech in technologies[:10]:  # Top 10 technologies
                    results.append({
                        'tool': 'builtwith',
                        'type': 'technology',
                        'name': tech.get('Name', ''),
                        'category': tech.get('Category', ''),
                        'confidence': 0.95
                    })
            
            return results
    
    except Exception as e:
        print(f"BuiltWith error: {e}")
    
    return []
```

---

## 3. Dynamic Pipeline Configuration Based on Available Tools

Modify your `PipelineConfig` to be aware of available tools:

### Updated Pipeline Initialization (in `main.py`)

```python
from osint_api_onboarding import EnvFileHandler, ToolRegistry

def build_pipeline_config(target_name: str, target_type: str):
    """Build pipeline configuration based on configured tools"""
    
    handler = EnvFileHandler()
    
    # Build API keys dictionary with all available tools
    api_keys = {
        'SERPER_API_KEY': handler.get_env_value('SERPER_API_KEY'),
        'SCRAPINGANT_API_KEY': handler.get_env_value('SCRAPINGANT_API_KEY'),
        'SHODAN_API_KEY': handler.get_env_value('SHODAN_API_KEY'),
        'BUILTWITH_API_KEY': handler.get_env_value('BUILTWITH_API_KEY'),
        'SPIDERFOOT_API_KEY': handler.get_env_value('SPIDERFOOT_API_KEY')
    }
    
    # Validate required keys exist
    if not api_keys['SERPER_API_KEY']:
        raise ValueError("SERPER_API_KEY is required")
    
    if not api_keys['SCRAPINGANT_API_KEY']:
        raise ValueError("SCRAPINGANT_API_KEY is required")
    
    config = PipelineConfig(
        target_name=target_name,
        target_type=target_type,
        wip_limits={
            "RECON": 3,
            "HARVESTING": 5 if api_keys['SHODAN_API_KEY'] else 3,  # Higher WIP with Shodan
            "ANALYST": 2,
            "SCRIBE": 1
        },
        api_keys=api_keys,
        max_retries_per_ticket=3,
        enable_circuit_breaker=True,
        recovery_time_after_failure=60
    )
    
    return config


# In your main function:

try:
    config = build_pipeline_config(target_name='John Doe', target_type='person')
    manager = OsintKanbanManager(config=config)
    
except ValueError as e:
    click.echo(f"ERROR: {e}")
    click.echo("\nTo add required tools, run:")
    click.echo("  python osint_api_onboarding.py onboard serper")
    sys.exit(1)
```

---

## 4. Real-Time Status Dashboard (Optional Enhancement)

Create a dashboard that shows pipeline status with tool availability:

### `status_dashboard.py`

```python
"""Real-time pipeline status and tool availability dashboard"""

import time
from datetime import datetime
from osint_api_onboarding import EnvFileHandler, ToolRegistry


class PipelineStatusDashboard:
    """Display real-time status of pipeline and configured tools"""
    
    def __init__(self):
        self.env_handler = EnvFileHandler()
        self.tool_registry = ToolRegistry()
        
    def display_header(self):
        """Print dashboard header"""
        
        click.echo("\n" + "="*70)
        click.echo("OSINT PIPELINE STATUS DASHBOARD")
        click.echo(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo("="*70)
    
    def display_tool_status(self):
        """Display status of all tools"""
        
        click.echo("\n🔧 CONFIGURED TOOLS:")
        click.echo("-"*50)
        
        configured_count = 0
        
        for tool_name in self.tool_registry.list_available_tools():
            env_key = f"{tool_name.upper()}_API_KEY"
            
            if self.env_handler.get_env_value(env_key):
                status_icon = "✅"
                configured_count += 1
                
                # Get partial key for display
                api_value = self.env_handler.get_env_value(env_key)
                if len(api_value) > 8:
                    display_key = f"{api_value[:4]}...{api_value[-4:]}"
                else:
                    display_key = api_value
                
                click.echo(f"   {status_icon} {tool_name.upper()}")
                click.echo(f"      Key length: {len(api_value)} chars")
            else:
                status_icon = "⚠️"
                click.echo(f"   {status_icon} {tool_name.upper()} (not configured)")
        
        if configured_count == 0:
            click.echo("   ⚠️ No tools currently configured!")
        
        click.echo("-"*50)
        click.echo(f"Total configured: {configured_count}/{len(self.tool_registry.list_available_tools())}")
    
    def display_required_validation(self):
        """Check and display required tool validation"""
        
        required_keys = ['SERPER_API_KEY', 'SCRAPINGANT_API_KEY']
        
        click.echo("\n🔒 REQUIRED TOOLS:")
        click.echo("-"*50)
        
        all_present = True
        
        for key in required_keys:
            if self.env_handler.get_env_value(key):
                click.echo(f"   ✅ {key.replace('_API_KEY', '').upper()}")
            else:
                click.echo(f"   ❌ {key.replace('_API_KEY', '').upper()} - MISSING!")
                all_present = False
        
        click.echo("-"*50)
        
        if not all_present:
            click.echo("\n⚠️  Pipeline cannot run without required tools!")
            click.echo("Run 'python osint_api_onboarding.py onboard serper' to fix")
    
    def display_recommendations(self):
        """Display recommendations for available tools"""
        
        click.echo("\n💡 AVAILABLE OPTIONAL TOOLS:")
        click.echo("-"*50)
        
        # Check Shodan
        if self.env_handler.get_env_value('SHODAN_API_KEY'):
            click.echo("   ✅ SHODAN - Available for network reconnaissance")
        else:
            click.echo(f"   ⚠️  SHODAN - Not configured (run 'onboard shodan' to enable)")
        
        # Check BuiltWith
        if self.env_handler.get_env_value('BUILTWITH_API_KEY'):
            click.echo("   ✅ BUILTWITH - Available for technology profiling")
        else:
            click.echo(f"   ⚠️  BUILTWITH - Not configured (run 'onboard builtwith' to enable)")
        
        # Check SpiderFoot
        if self.env_handler.get_env_value('SPIDERFOOT_API_KEY'):
            click.echo("   ✅ SPIDERFOOT - Available for OSINT automation")
        else:
            click.echo(f"   ⚠️  SPIDERFOOT - Not configured (run 'onboard spiderfoot' to enable)")
        
        click.echo("-"*50)


def main():
    """Run dashboard display"""
    
    dashboard = PipelineStatusDashboard()
    
    dashboard.display_header()
    dashboard.display_tool_status()
    dashboard.display_required_validation()
    dashboard.display_recommendations()
    
    click.echo("\n" + "="*70)


if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# Display status before running pipeline
python osint_api_onboarding.py status
python status_dashboard.py

# Or integrate into your main command:
python main.py --target "John Doe"  # Will auto-check and display dashboard
```

---

## 5. Automated Health Check Before Pipeline Start

Add this to `main.py` startup:

```python
def run_health_check():
    """Run pre-pipeline health check"""
    
    from osint_api_onboarding import EnvFileHandler
    
    handler = EnvFileHandler()
    
    click.echo("\n🔍 Running pre-pipeline health checks...")
    
    # Check required API keys
    required_keys = ['SERPER_API_KEY', 'SCRAPINGANT_API_KEY']
    all_ok = True
    
    for key in required_keys:
        if not handler.get_env_value(key):
            click.echo(f"   ❌ {key} - MISSING")
            all_ok = False
        else:
            click.echo(f"   ✅ {key}")
    
    # Check network connectivity (basic)
    try:
        import requests
        response = requests.head('https://google.com', timeout=5)
        
        if response.status_code == 200:
            click.echo("   ✅ Network connectivity - OK")
        else:
            click.echo(f"   ⚠️  Network connectivity - Status {response.status_code}")
    
    except Exception as e:
        click.echo(f"   ❌ Network connectivity - FAILED ({e})")
        all_ok = False
    
    if not all_ok:
        click.echo("\n❌ Health check failed. Please fix issues before continuing.")
        
        # Show onboarding instructions
        for key in required_keys:
            if not handler.get_env_value(key):
                tool_name = key.replace('_API_KEY', '').lower()
                click.echo(f"\nTo configure {tool_name}:")
                click.echo(f"  python osint_api_onboarding.py onboard {tool_name}")
        
        return False
    
    click.echo("\n✅ All health checks passed!\n")
    return True


# In main():

if not run_health_check():
    sys.exit(1)

# Continue with pipeline execution...
```

---

## Summary

The API onboarding system provides:

1. ✅ **Dynamic Tool Configuration** - Add/remove tools without code changes
2. ✅ **Secure Key Management** - All keys stored in `.env` file securely
3. ✅ **Automatic Validation** - Connection tests ensure keys work
4. ✅ **Flexible Integration** - Use conditional logic to enable optional features
5. ✅ **Status Monitoring** - Real-time dashboard and health checks

Choose the integration approach that best fits your workflow:

- **Minimal**: Just call `validate_required_tools()` before pipeline start
- **Moderate**: Use `ToolAvailabilityChecker` for feature toggling  
- **Advanced**: Implement full status dashboard with recommendations

---

*Document Version: 1.0 | Last Updated: January 2024*
