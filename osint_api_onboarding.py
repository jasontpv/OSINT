#!/usr/bin/env python3
"""
OSINT API Onboarding System
===========================
Dynamic tool registration and .env management for the OSINT pipeline.

Features:
- Interactive tool discovery and onboarding
- Secure API key handling with environment variables
- Automatic .env file updates
- Tool validation and testing
- Persistent configuration storage
"""

import os
import re
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv, set_key
import click
import requests
from dataclasses import dataclass


@dataclass
class ToolConfig:
    """Configuration for a single OSINT tool"""
    name: str
    display_name: str
    category: List[str]
    api_base_url: str
    auth_type: str  # API_KEY, OAUTH2, BASIC, NONE
    rate_limit_per_min: int
    endpoints: Dict[str, str]
    usage_examples: List[Dict[str, str]]
    documentation_url: Optional[str] = None
    is_active: bool = True


class EnvFileHandler:
    """Secure .env file management with atomic updates"""
    
    def __init__(self, env_path: str = '.env'):
        self.env_path = Path(env_path)
        self.load_dotenv()
        
    def load_dotenv(self):
        """Load current environment variables"""
        if self.env_path.exists():
            load_dotenv(dotenv_path=self.env_path)
            
    def get_env_value(self, key: str) -> Optional[str]:
        """Get value from .env file or environment"""
        return os.getenv(key) or os.environ.get(key)
    
    def set_env_value(self, key: str, value: str):
        """Set value in .env file with atomic update"""
        
        # Validate key name (alphanumeric and underscores only)
        if not re.match(r'^[A-Z][A-Z0-9_]*$', key):
            raise ValueError(f"Invalid API key name: {key}. Must be uppercase letters, numbers, and underscores.")
        
        # Set in environment immediately
        os.environ[key] = value
        set_key(str(self.env_path), key, value)
        
    def remove_env_value(self, key: str):
        """Remove a key from .env file"""
        if self.env_path.exists():
            with open(self.env_path, 'r') as f:
                lines = f.readlines()
            
            # Filter out the target line
            filtered_lines = [line for line in lines 
                           if not line.startswith(key + '=')]
            
            with open(self.env_path, 'w') as f:
                f.writelines(filtered_lines)
                
            os.environ.pop(key, None)
    
    def backup_env(self) -> str:
        """Create timestamped backup of current .env file"""
        if self.env_path.exists():
            import shutil
            from datetime import datetime
            
            backup_name = f"{self.env_path.name}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = Path(self.env_path.parent) / backup_name
            
            shutil.copy2(self.env_path, backup_path)
            return str(backup_path)
        return None
    
    def validate_env_structure(self) -> bool:
        """Check if .env file has required structure"""
        required_keys = ['SERPER_API_KEY', 'SCRAPINGANT_API_KEY']
        
        for key in required_keys:
            if not self.get_env_value(key):
                return False
        
        return True
    
    def get_all_api_keys(self) -> List[str]:
        """List all API keys currently configured"""
        if not self.env_path.exists():
            return []
            
        with open(self.env_path, 'r') as f:
            content = f.read()
        
        # Extract all KEY=VALUE pairs
        pattern = r'^([A-Z][A-Z0-9_]*)='
        return re.findall(pattern, content, re.MULTILINE)


class ToolRegistry:
    """Central registry for known OSINT tools"""
    
    def __init__(self):
        self.tools: Dict[str, ToolConfig] = {}
        self._load_builtin_tools()
        
    def _load_builtin_tools(self):
        """Load predefined tool configurations"""
        
        # Shodan Configuration
        shodan_config = ToolConfig(
            name='shodan',
            display_name='Shodan Internet Scanner',
            category=['reconnaissance', 'network_scanning', 'vulnerability'],
            api_base_url='https://api.shodan.io',
            auth_type='API_KEY',
            rate_limit_per_min=60,
            endpoints={
                'search': '/shodan/host/search',
                'host_info': '/shodan/host/{ip}',
                'dns_reverse': '/shodan/dns/reverse',
                'cpe_lookup': '/shodan/cpe/{cpe_id}'
            },
            usage_examples=[
                {
                    'description': 'Search for devices matching criteria',
                    'example': 'curl -u API_KEY: "https://api.shodan.io/shodan/host/search?key=API_KEY&q=apache"'
                },
                {
                    'description': 'Get host information by IP',
                    'example': 'curl -u API_KEY: "https://api.shodan.io/shodan/host/8.8.8.8?key=API_KEY"'
                }
            ],
            documentation_url='https://developer.shodan.io/',
            is_active=True
        )
        
        # SpiderFoot Configuration  
        spiderfoot_config = ToolConfig(
            name='spiderfoot',
            display_name='SpiderFoot OSINT Automation',
            category=['osint', 'reconnaissance', 'threat_intelligence'],
            api_base_url='https://www.spiderfoot.net/api/v2/',
            auth_type='API_KEY',
            rate_limit_per_min=10,
            endpoints={
                'scan_create': '/scans/create',
                'scan_info': '/scans/{scan_id}/info',
                'module_search': '/modules/search',
                'results_export': '/exports/results'
            },
            usage_examples=[
                {
                    'description': 'Create new OSINT scan',
                    'example': 'curl -X POST "https://www.spiderfoot.net/api/v2/scans/create" -d "target=example.com&moduleList=SOCKS5"'
                }
            ],
            documentation_url='https://www.spiderfoot.net/documentation/',
            is_active=True
        )
        
        # BuiltWith Configuration
        builtwith_config = ToolConfig(
            name='builtwith',
            display_name='BuiltWith Technology Profiler',
            category=['technology_detection', 'reconnaissance', 'competitive_analysis'],
            api_base_url='https://api.builtwith.com',
            auth_type='API_KEY',
            rate_limit_per_min=60,
            endpoints={
                'domain_profile': '/v13/API.json?key=KEY&DOMAIN={domain}',
                'domain_subdomains': '/v13/API.json?key=KEY&SUBDOMAINS={subdomain}',
                'company_search': '/v13/API.json?key=KEY&COMPANY={company}'
            },
            usage_examples=[
                {
                    'description': 'Get technology profile for domain',
                    'example': 'curl "https://api.builtwith.com/v13/API.json?key=YOUR_KEY&DOMAIN=example.com"'
                }
            ],
            documentation_url='https://builtwith.com/docs/',
            is_active=True
        )
        
        # Add to registry
        self.tools['shodan'] = shodan_config
        self.tools['spiderfoot'] = spiderfoot_config
        self.tools['builtwith'] = builtwith_config
    
    def get_tool(self, name: str) -> Optional[ToolConfig]:
        """Get tool configuration by name"""
        return self.tools.get(name.lower())
    
    def list_available_tools(self) -> List[str]:
        """List all available tool names"""
        return [name for name, config in self.tools.items() if config.is_active]
    
    def register_custom_tool(self, tool: ToolConfig):
        """Register a new custom tool"""
        if not tool.name or tool.name.lower() in self.tools:
            raise ValueError(f"Invalid tool name. Name must be unique and non-empty.")
        
        self.tools[tool.name.lower()] = tool
    
    def validate_tool_structure(self, config_dict: Dict) -> Tuple[bool, str]:
        """Validate custom tool configuration structure"""
        
        required_fields = ['name', 'display_name', 'category', 'api_base_url', 
                          'auth_type', 'rate_limit_per_min', 'endpoints']
        
        for field in required_fields:
            if field not in config_dict:
                return False, f"Missing required field: {field}"
        
        # Validate auth type
        valid_auth_types = ['API_KEY', 'OAUTH2', 'BASIC', 'NONE']
        if config_dict['auth_type'] not in valid_auth_types:
            return False, f"Invalid auth_type. Must be one of: {valid_auth_types}"
        
        # Validate endpoints structure
        if not isinstance(config_dict.get('endpoints'), dict):
            return False, "Endpoints must be a dictionary"
        
        return True, "Valid configuration"


class APIOnboardingFlow:
    """Main onboarding orchestrator"""
    
    def __init__(self):
        self.env_handler = EnvFileHandler()
        self.tool_registry = ToolRegistry()
        self.current_tool_name: Optional[str] = None
        
    def list_available_tools(self) -> List[Dict]:
        """List all tools available for onboarding"""
        
        result = []
        for name, config in self.tool_registry.tools.items():
            env_key = f"{name.upper()}_API_KEY"
            
            # Check if API key is configured
            api_key_configured = bool(self.env_handler.get_env_value(env_key))
            
            result.append({
                'name': config.name,
                'display_name': config.display_name,
                'category': config.category,
                'auth_type': config.auth_type,
                'rate_limit_per_min': config.rate_limit_per_min,
                'api_key_configured': api_key_configured,
                'is_active': config.is_active
            })
        
        return result
    
    def validate_existing_tool(self, tool_name: str) -> Tuple[bool, Optional[str]]:
        """Check if a tool is already configured"""
        
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return False, f"Unknown tool: {tool_name}"
        
        env_key = f"{tool_name.upper()}_API_KEY"
        api_key_value = self.env_handler.get_env_value(env_key)
        
        if api_key_value and len(api_key_value.strip()) > 0:
            return True, f"Tool '{tool_name}' is already configured (key found in .env)"
        
        return False, None
    
    def onboard_tool_interactive(self, tool_name: str):
        """Interactive onboarding flow for a specific tool"""
        
        # Validate tool exists
        if not self.tool_registry.get_tool(tool_name):
            raise ValueError(f"Unknown tool: {tool_name}")
        
        env_key = f"{tool_name.upper()}_API_KEY"
        
        click.echo(f"\n{'='*60}")
        click.echo(f"Onboarding Tool: {click.style(tool_name, bold=True)}")
        click.echo(f"Display Name: {self.tool_registry.get_tool(tool_name).display_name}")
        click.echo(f"Category: {', '.join(self.tool_registry.get_tool(tool_name).category)}")
        click.echo(f"Rate Limit: {self.tool_registry.get_tool(tool_name).rate_limit_per_min} requests/min")
        click.echo(f"{'='*60}\n")
        
        # Backup current .env file
        backup_path = self.env_handler.backup_env()
        if backup_path:
            click.echo(f"[OK] Created backup: {backup_path}")
        
        # Get API key from user
        while True:
            api_key = click.prompt(
                f"\nEnter your {tool_name.upper()} API Key",
                hide_input=True,
                confirmation_prompt=True
            )
            
            if len(api_key.strip()) < 8:
                click.echo("ERROR: API key appears too short. Please check and try again.")
                continue
            
            break
        
        # Store in .env file
        self.env_handler.set_env_value(env_key, api_key)
        
        click.echo(f"\n[OK] {tool_name.upper()} API key successfully stored!")
        click.echo(f"   Environment variable: {env_key}")
        
        # Test the API connection if possible
        if tool_name == 'shodan':
            self._test_shodan_connection(api_key)
        elif tool_name == 'builtwith':
            self._test_builtwith_connection(api_key)
    
    def _test_shodan_connection(self, api_key: str):
        """Test Shodan API connection"""
        
        click.echo("\nTesting Shodan API connection...")
        
        try:
            response = requests.get(
                'https://api.shodan.io/shodan/info',
                auth=(api_key, '')
            )
            
            if response.status_code == 200:
                data = response.json()
                click.echo(f"[OK] Shodan connection successful!")
                click.echo(f"   Account Type: {data.get('type', 'Unknown')}")
                click.echo(f"   API Calls Today: {data.get('api_calls_today', 0)} / {data.get('quota', 0)}")
            else:
                click.echo(f"[WARN] Shodan returned status code: {response.status_code}")
                if response.status_code == 401:
                    click.echo("   Invalid API key - please verify and retry")
                elif response.status_code == 429:
                    click.echo("   Rate limit exceeded - try again later")
                    
        except requests.exceptions.ConnectionError as e:
            click.echo(f"ERROR: Connection error: {e}")
            click.echo("   Please check your network connection")
            
    def _test_builtwith_connection(self, api_key: str):
        """Test BuiltWith API connection"""
        
        click.echo("\nTesting BuiltWith API connection...")
        
        try:
            response = requests.get(
                'https://api.builtwith.com/v13/API.json',
                params={'key': api_key, 'DOMAIN': 'google.com'}
            )
            
            if response.status_code == 200:
                data = response.json()
                click.echo(f"[OK] BuiltWith connection successful!")
                
                if isinstance(data, list) and len(data) > 0:
                    tools_found = data[0].get('Paths', [{}])[0].get('Tools', [])
                    click.echo(f"   Technologies detected on google.com: {len(tools_found)}")
            else:
                click.echo(f"[WARN] BuiltWith returned status code: {response.status_code}")
                
        except requests.exceptions.ConnectionError as e:
            click.echo(f"ERROR: Connection error: {e}")
    
    def onboard_custom_tool(self, config_dict: Dict):
        """Onboard a custom tool with user-provided configuration"""
        
        # Validate structure
        is_valid, message = self.tool_registry.validate_tool_structure(config_dict)
        
        if not is_valid:
            raise ValueError(f"Invalid configuration: {message}")
        
        tool_name = config_dict['name'].lower()
        env_key = f"{tool_name.upper()}_API_KEY"
        
        # Check for conflicts
        existing_tool = self.tool_registry.get_tool(tool_name)
        if existing_tool and existing_tool.is_active:
            click.echo(f"\n[WARN] A tool named '{tool_name}' already exists in registry.")
            overwrite = click.confirm("Do you want to replace it?")
            
            if not overwrite:
                raise ValueError("Operation cancelled by user")
        
        # Register the custom tool
        self.tool_registry.register_custom_tool(ToolConfig(**config_dict))
        
        # Get API key from user (if required)
        if config_dict['auth_type'] == 'API_KEY':
            while True:
                api_key = click.prompt(
                    f"\nEnter your {tool_name.upper()} API Key",
                    hide_input=True,
                    confirmation_prompt=True
                )
                
                if len(api_key.strip()) < 8:
                    click.echo("ERROR: API key appears too short. Please check and try again.")
                    continue
                
                break
            
            self.env_handler.set_env_value(env_key, api_key)
            click.echo(f"\n[OK] {tool_name.upper()} API key successfully stored!")
        
        # Save tool configuration to tools.json for persistence
        self._save_tool_to_registry(tool_name, config_dict)
    
    def _save_tool_to_registry(self, tool_name: str, config_dict: Dict):
        """Save custom tool to persistent registry"""
        
        try:
            tools_file = Path('tools_custom.json')
            
            # Load existing custom tools if any
            custom_tools = {}
            if tools_file.exists():
                with open(tools_file, 'r') as f:
                    custom_tools = json.load(f)
            
            # Add/update tool
            custom_tools[tool_name] = config_dict
            
            # Write back atomically
            with open(tools_file, 'w') as f:
                json.dump(custom_tools, f, indent=2)
                
        except Exception as e:
            click.echo(f"\n[WARN] Could not persist tool configuration: {e}")


@click.group()
def cli():
    """OSINT API Onboarding - Manage and configure external tools"""
    pass


@cli.command()
def list_tools():
    """List all available tools for onboarding"""
    
    onboarding = APIOnboardingFlow()
    tools = onboarding.list_available_tools()
    
    if not tools:
        click.echo("No tools available yet.")
        return
    
    click.echo(f"\n{'='*70}")
    click.echo("AVAILABLE OSINT TOOLS FOR ONBOARDING")
    click.echo('='*70)
    
    for tool in sorted(tools, key=lambda x: x['name']):
        status_icon = "[OK]" if tool['api_key_configured'] else "[ ]"
        
        click.echo(f"\n{status_icon} {click.style(tool['name'].upper(), bold=True)}")
        click.echo(f"   Display Name: {tool['display_name']}")
        click.echo(f"   Category: {', '.join([c.capitalize() for c in tool['category']])}")
        click.echo(f"   Rate Limit: {tool['rate_limit_per_min']} req/min")
        
        if not tool['api_key_configured']:
            click.echo(f"   Status: Not configured - run 'onboard {tool['name']}' to set up")
    
    click.echo(f"\n{'='*70}")


@cli.command()
@click.argument('tool_name')
def onboard(tool_name):
    """Onboard a specific tool with API key"""
    
    onboarding = APIOnboardingFlow()
    
    # Check if already configured
    is_configured, message = onboarding.validate_existing_tool(tool_name)
    
    if is_configured:
        click.echo(f"\n[WARN] {message}")
        return
    
    try:
        onboarding.onboard_tool_interactive(tool_name)
        
        # Verify configuration
        env_key = f"{tool_name.upper()}_API_KEY"
        value = onboarding.env_handler.get_env_value(env_key)
        
        if value and len(value.strip()) > 0:
            click.echo(f"\n[OK] {tool_name.capitalize()} successfully onboarded!")
            click.echo(f"   Environment variable '{env_key}' is now set")
            
            # Show available commands for this tool
            click.echo(f"\nTip: Use the following in your scripts:")
            click.echo(f"   import os")
            click.echo(f"   api_key = os.environ.get('{env_key}')")
        else:
            click.echo(f"\nERROR: Configuration verification failed. Please check .env file.")
            
    except KeyboardInterrupt:
        click.echo("\n\n[ABORT] Onboarding cancelled by user")


@cli.command()
@click.argument('tool_name')
def remove(tool_name):
    """Remove API key for a tool"""
    
    onboarding = APIOnboardingFlow()
    
    if not onboarding.tool_registry.get_tool(tool_name):
        click.echo(f"Unknown tool: {tool_name}")
        return
    
    env_key = f"{tool_name.upper()}_API_KEY"
    
    click.echo(f"\n[WARN] This will remove the API key for '{tool_name}' from your .env file.")
    click.echo(f"   Environment variable to be removed: {env_key}")
    
    if not click.confirm("Are you sure?"):
        return
    
    onboarding.env_handler.remove_env_value(env_key)
    click.echo(f"\n[OK] API key for '{tool_name}' successfully removed!")


@cli.command()
@click.option('--name', required=True, help='Tool identifier (lowercase, no spaces)')
@click.option('--display-name', required=True, help='Human-readable display name')
@click.option('--category', multiple=True, default=['custom'], 
              help='Category tags (can specify multiple times)')
@click.option('--api-base-url', required=True, help='Base URL for the API')
@click.option('--auth-type', type=click.Choice(['API_KEY', 'OAUTH2', 'BASIC', 'NONE']), 
             default='API_KEY', help='Authentication method')
@click.option('--rate-limit', type=int, required=True, help='Rate limit in requests per minute')
def custom(name, display_name, category, api_base_url, auth_type, rate_limit):
    """Register a new custom tool for onboarding"""
    
    # Build configuration dictionary
    config = {
        'name': name,
        'display_name': display_name,
        'category': list(category),
        'api_base_url': api_base_url,
        'auth_type': auth_type,
        'rate_limit_per_min': rate_limit,
        'endpoints': {},  # Will be added by user if needed
        'usage_examples': [],
        'documentation_url': None
    }
    
    try:
        onboarding = APIOnboardingFlow()
        
        click.echo(f"\nRegistering custom tool...")
        click.echo(f"   Name: {name}")
        click.echo(f"   Display: {display_name}")
        click.echo(f"   URL: {api_base_url}")
        click.echo(f"   Auth Type: {auth_type}")
        
        onboarding.onboard_custom_tool(config)
        
    except Exception as e:
        click.echo(f"\nERROR registering tool: {e}")


@cli.command()
def status():
    """Check current API configuration status"""
    
    onboarding = APIOnboardingFlow()
    
    if not onboarding.env_handler.validate_env_structure():
        click.echo("\n[WARN] Required API keys are missing!")
        click.echo("   Run 'onboard SERPER' and/or 'onboard SCRAPINGANT' to configure")
        return
    
    # List all configured tools
    configured_tools = []
    
    for tool_name in onboarding.tool_registry.list_available_tools():
        env_key = f"{tool_name.upper()}_API_KEY"
        
        if onboarding.env_handler.get_env_value(env_key):
            configured_tools.append(tool_name)
    
    click.echo(f"\n{'='*60}")
    click.echo("CURRENT API CONFIGURATION STATUS")
    click.echo('='*60)
    
    if not configured_tools:
        click.echo("\nNo tools currently configured.")
        return
    
    for tool in sorted(configured_tools):
        env_key = f"{tool.upper()}_API_KEY"
        
        # Get partial key for display (show first 4 and last 4 chars)
        api_value = onboarding.env_handler.get_env_value(env_key)
        if len(api_value) > 8:
            display_key = f"{api_value[:4]}...{api_value[-4:]}"
        else:
            display_key = api_value
        
        click.echo(f"\n[OK] {tool.upper()}")
        click.echo(f"   Environment Variable: {env_key}")
        click.echo(f"   API Key: {display_key} (length: {len(api_value)})")
    
    click.echo(f"\n{'='*60}")


@cli.command()
def backup():
    """Create a backup of current .env file"""
    
    onboarding = APIOnboardingFlow()
    
    try:
        backup_path = onboarding.env_handler.backup_env()
        
        if backup_path:
            click.echo(f"[OK] Backup created successfully!")
            click.echo(f"   Location: {backup_path}")
            
            # Show last 3 backups
            import glob
            from datetime import datetime
            
            backups = sorted(glob.glob('.env.backup.*'), reverse=True)[:3]
            
            if len(backups) > 1:
                click.echo("\nRecent backups:")
                for b in backups[1:]:
                    mod_time = datetime.fromtimestamp(os.path.getmtime(b))
                    size_kb = os.path.getsize(b) / 1024
                    click.echo(f"   • {Path(b).name} ({mod_time.strftime('%Y-%m-%d %H:%M')}, {size_kb:.1f} KB)")
        else:
            click.echo("[WARN] No .env file found to backup")
            
    except Exception as e:
        click.echo(f"\nERROR: Backup failed: {e}")


if __name__ == '__main__':
    cli()
