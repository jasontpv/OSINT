#!/usr/bin/env python3
"""
OSINT CLI Wrapper - Executes external tools via subprocess and captures output.
Handles Spiderfoot, Shodan CLI, nmap, whois, and custom command execution.
Author: Matt Pumphrey
Date: 3/16/2026
"""

import asyncio
import os
import sys
import json
import time
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from state_storage import load_json, save_json  # persist tool-binary paths


@dataclass
class ProcessResult:
    """Structured result from CLI execution"""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timestamp: datetime


class PathValidator:
    """Validates paths stay within workspace boundaries"""

    def __init__(self, base_workspace: str):
        self.base_workspace = os.path.abspath(base_workspace)

    def validate_safe_path(self, requested_path: str) -> bool:
        """Ensure path doesn't escape workspace directory"""
        try:
            resolved = os.path.abspath(requested_path)

            # Must start with workspace path
            if not resolved.startswith(os.path.join(self.base_workspace)):
                print(f"Path traversal detected! {requested_path}")
                return False

            # No .. in path components
            if '..' in requested_path.replace('\\', '/').split('/'):
                print("Invalid path component: '..'")
                return False

            return True

        except Exception as e:
            print(f"Error validating path: {e}")
            return False


class CLICommandRunner:
    """Executes shell commands with timeout and output capture"""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.validator = PathValidator(self.workspace_dir)
        self.tool_binaries = {}          # name → absolute path
        self._load_tool_map()

    # Maps target-type strings to the ordered list of CLI tools to try
    TOOL_MAP_BY_TARGET: Dict[str, List[str]] = {
        "domain":     ["whois"],
        "ip_address": ["nmap"],
    }

    def _load_tool_map(self):
        """Load persisted mapping from ~/.cli_tools.json"""
        try:
            state = load_json(str(Path.home() / ".cli_tools.json"))
            self.tool_binaries.update(state)
        except Exception as e:
            print(f"⚠️ Could not load tool map: {e}")

    def _save_tool_map(self):
        """Persist the mapping."""
        save_json(str(Path.home() / ".cli_tools.json"), self.tool_binaries)

    async def execute_tool_for_target(
        self,
        target_type: str,
        target_value: str,
        timeout: int = 120,
        tool_repos: Optional[Dict[str, str]] = None,
    ) -> "ProcessResult":
        """Look up the right CLI tool for *target_type*, resolve its binary
        (persisted map → shutil.which → ToolProvisioner), and run it.

        Args:
            target_type:  One of the keys in TOOL_MAP_BY_TARGET (e.g. "domain").
            target_value: The actual target string passed to the tool.
            timeout:      Per-tool subprocess timeout in seconds.
            tool_repos:   Optional override mapping tool_name → GitHub clone URL.

        Returns:
            ProcessResult for the first matching tool, or a no-op ProcessResult
            when no tool is registered for *target_type*.
        """
        tools = self.TOOL_MAP_BY_TARGET.get(target_type, [])
        if not tools:
            return ProcessResult(
                command="",
                exit_code=0,
                stdout="",
                stderr=f"No CLI tool registered for target type '{target_type}'",
                duration_seconds=0.0,
                timestamp=datetime.now(),
            )

        _default_repos: Dict[str, str] = {
            "whois": "https://github.com/rfc1036/whois.git",
            "nmap":  "https://github.com/nmap/nmap.git",
        }
        repos = {**_default_repos, **(tool_repos or {})}

        for tool in tools:
            # 1. Check persisted path first
            binary: Optional[str] = self.tool_binaries.get(tool)

            # 2. Fallback to PATH lookup
            if not binary or not Path(binary).exists():
                binary = shutil.which(tool)

            # 3. If still not found, try ToolProvisioner
            if not binary:
                repo_url = repos.get(tool)
                if repo_url:
                    try:
                        from osint_provisioner import ToolProvisioner
                        prov = ToolProvisioner(workspace_root=self.workspace_dir)
                        report = prov.provision_tool_from_github(
                            repo_url, install_dependencies=True, security_check=False
                        )
                        if report.repo_cloned.success:
                            candidate = Path(report.repo_cloned.local_path) / tool
                            if not candidate.exists():
                                candidate = Path(report.repo_cloned.local_path) / "bin" / tool
                            if candidate.exists():
                                binary = str(candidate.resolve())
                    except Exception as prov_err:
                        print(f"⚠️ ToolProvisioner failed for {tool}: {prov_err}")

            if not binary:
                print(f"⚠️ Binary for '{tool}' not found; skipping.")
                continue

            # 4. Persist resolved path for future runs
            self.tool_binaries[tool] = binary
            self._save_tool_map()

            # 5. Run the command asynchronously (sync subprocess → thread)
            result: ProcessResult = await asyncio.to_thread(
                self.run_command,
                f"{binary} {{target}}",
                target_value,
                timeout,
            )
            return result

        # None of the mapped tools could be run
        return ProcessResult(
            command="",
            exit_code=1,
            stdout="",
            stderr=f"All tools for target type '{target_type}' unavailable.",
            duration_seconds=0.0,
            timestamp=datetime.now(),
        )

    def _find_binary_path(self, tool_name: str) -> Optional[str]:
        """Return absolute path if already known; otherwise None."""
        return self.tool_binaries.get(tool_name)
   
    
    def run_command(
        self,
        command_template: str,
        target_value: str,
        timeout: int = 120,
        cwd: Optional[str] = None
    ) -> ProcessResult:
        """Execute CLI tool with actual subprocess logic

        Args:
            command_template: Command with {target} placeholder
            target_value: Value to substitute for {target}
            timeout: Maximum seconds to wait (default 120)
            cwd: Working directory (defaults to workspace_dir)

        Returns:
            ProcessResult with stdout, stderr, exit_code

        Example:
            result = runner.run_command(
                command_template="sf.py -s {target}",
                target_value="example.com",
                timeout=300
            )
        """
        if not self.validator.validate_safe_path(cwd or self.workspace_dir):
            raise PermissionError("Command execution outside workspace boundaries")

        start_time = time.time()

        # Substitute target value into command
        actual_command = command_template.replace("{target}", target_value)

        print(f"🔧 Executing: {actual_command}")
        print(f" Timeout: {timeout}s")
        print(f" Working Dir: {cwd or self.workspace_dir}")

        try:
            # Create process with actual subprocess logic
            process = subprocess.Popen(
                actual_command,
                shell=True,  # Allow shell commands like wildcards
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd or self.workspace_dir,
                env=os.environ.copy(),  # Inherit environment variables
                text=True,  # Work with text (strings) not bytes
                bufsize=1  # Line buffered for real-time output
            )

            # Stream output in real-time while waiting
            stdout_lines = []
            stderr_lines = []

            def stream_output(stream, target_list):
                """Thread function to capture output lines"""
                if stream:
                    for line in iter(stream.readline, ''):
                        target_list.append(line.rstrip('\n'))
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {line.strip()}")

            import threading

            stdout_thread = threading.Thread(
                target=stream_output,
                args=(process.stdout, stdout_lines),
                daemon=True
            )

            stderr_thread = threading.Thread(
                target=stream_output,
                args=(process.stderr, stderr_lines),
                daemon=True
            )

            stdout_thread.start()
            stderr_thread.start()

            # Wait for completion with timeout
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"⚠️ Command timed out after {timeout}s")
                process.kill()  # Force terminate
                return ProcessResult(
                    command=actual_command,
                    exit_code=124,  # Standard timeout exit code
                    stdout='\n'.join(stdout_lines),
                    stderr='Command timed out',
                    duration_seconds=time.time() - start_time,
                    timestamp=datetime.now()
                )

            # Collect all output after completion
            stdout_content = ''.join(stdout_lines)
            if process.stdout:
                stdout_content += process.stdout.read()
            stderr_content = ''.join(stderr_lines)
            if process.stderr:
                stderr_content += process.stderr.read()

            duration = time.time() - start_time

            return ProcessResult(
                command=actual_command,
                exit_code=process.returncode,
                stdout=stdout_content,
                stderr=stderr_content,
                duration_seconds=round(duration, 2),
                timestamp=datetime.now()
            )

        except FileNotFoundError as e:
            print(f"❌ Command not found: {actual_command}")
            return ProcessResult(
                command=actual_command,
                exit_code=127,
                stdout="",
                stderr=f"Command not found or not in PATH: {str(e)}",
                duration_seconds=time.time() - start_time,
                timestamp=datetime.now()
            )

        except Exception as e:
            print(f"❌ Unexpected error executing command: {e}")
            return ProcessResult(
                command=actual_command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=time.time() - start_time,
                timestamp=datetime.now()
            )


class ToolRegistry:
    """Manages predefined tool commands for common OSINT tools"""

    TOOLS = {
        'shodan': {
            'command_template': "shodan search '{target}'",
            'description': 'Shodan CLI - Internet scan data',
            'required_api_key': 'SHODAN_API_KEY'
        },
        'spiderfoot': {
            'command_template': "sf.py -s {target}",
            'description': 'SpiderFoot OSINT Automation',
            'required_api_key': None  # No API key needed for CLI
        },
        'nmap': {
            'command_template': "/usr/bin/nmap -sV {target}",
            'description': 'Nmap Network Scanner',
            'required_api_key': None
        },
        'whois': {
            'command_template': "/usr/bin/whois {target}",
            'description': 'WHOIS Domain Lookup',
            'required_api_key': None
        },
        'theHarvester': {
            'command_template': "theHarvester -d {target} -b all",
            'description': 'TheHarvester - Email/IP/Username finder',
            'required_api_key': None
        },
        'robin': {
            'command_template': "/mnt/c/AI_Agent/OSINT_WORKSPACE/tools/robin_sycomix/.venv/bin/python /mnt/c/AI_Agent/OSINT_WORKSPACE/tools/robin_sycomix/main.py {target}",
            'description': 'Robin - AI-powered OSINT search and scraper',
            'required_api_key': None
        },
        'photon': {
            'command_template': "/mnt/c/AI_Agent/OSINT_WORKSPACE/tools/Photon_s0md3v/.venv/bin/python /mnt/c/AI_Agent/OSINT_WORKSPACE/tools/Photon_s0md3v/photon.py -u {target}",
            'description': 'Photon - Fast crawler for OSINT',
            'required_api_key': None
        }
    }

    @classmethod
    def get_tool_config(cls, tool_name: str) -> Optional[Dict]:
        """Get configuration for a registered tool"""
        return cls.TOOLS.get(tool_name.lower())

    @classmethod
    def list_available_tools(cls) -> List[str]:
        """List all available tool names"""
        return list(cls.TOOLS.keys())


class OutputParser:
    """Parses CLI output into structured data for Analyst stage"""

    @staticmethod
    def detect_output_format(output: str) -> str:
        """Detect if output is JSON, text, or other format"""

        stripped = output.strip()

        # Try parsing as JSON first
        try:
            json.loads(stripped)
            return 'json'
        except (json.JSONDecodeError, ValueError):
            pass

        # Check for CSV headers
        if ',' in stripped and ('email,' in stripped.lower() or 'ip,' in stripped.lower()):
            return 'csv'

        # Default to text
        return 'text'

    @staticmethod
    def extract_emails(output: str) -> List[str]:
        """Extract email addresses from CLI output using regex"""
        import re
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, output)
        # Normalize: lowercase and remove Gmail dots for comparison
        normalized_emails = []
        for email in emails:
            lower_email = email.lower()
            parts = lower_email.split('@')
            if len(parts) == 2 and ('gmail' in parts[1] or 'googlemail' in parts[1]):
                normalized = parts[0].replace('.', '') + '@' + parts[1]
                if normalized not in normalized_emails:
                    normalized_emails.append(normalized)
            else:
                if lower_email not in normalized_emails:
                    normalized_emails.append(lower_email)
        return list(set(normalized_emails))  # Return unique normalized emails

    @staticmethod
    def extract_ips(output: str) -> List[str]:
        """Extract IP addresses from CLI output using regex"""
        import re
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, output)
        # Filter out invalid IPs (0-255 per octet)
        valid_ips = []
        for ip in ips:
            octets = [int(octet) for octet in ip.split('.')]
            if all(0 <= o <= 255 for o in octets):
                valid_ips.append(ip)
        return list(set(valid_ips))


class CLIWrapper:
    """Main CLI Wrapper class that orchestrates execution"""

    def __init__(self, workspace_dir: str = "./OSINT_WORKSPACE"):
        self.runner = CLICommandRunner(workspace_dir)
        self.output_parser = OutputParser()

    def execute_tool(self, tool_name: str, target: str, timeout: int = 120) -> ProcessResult:
        """Execute a registered OSINT tool

        Args:
            tool_name: Name of tool (shodan, spiderfoot, etc.)
            target: Target value (domain, IP, email)
            timeout: Execution timeout in seconds

        Returns:
            ProcessResult with command output and status

        Usage:
            wrapper = CLIWrapper()
            result = wrapper.execute_tool('spiderfoot', 'example.com')
        """
        # Get tool configuration
        tool_config = ToolRegistry.get_tool_config(tool_name)

        if not tool_config:
            print(f"❌ Unknown tool: {tool_name}")
            return ProcessResult(
                command="",
                exit_code=1,
                stdout="",
                stderr=f"Unknown tool: {tool_name}",
                duration_seconds=0,
                timestamp=datetime.now()
            )

        # 1. Resolve absolute binary path (if we have it)
        binary_path = self._find_binary_path(tool_name)

        if not binary_path:
            # Tool unknown → ask user
            print(f"🔧 Tool <{tool_name}> not found locally.")
            choice = input("Install this tool from its GitHub repo? (y/n) ").strip().lower()
            if choice != 'y':
                return ProcessResult(command="",
                                      exit_code=1,
                                      stdout="",
                                      stderr=f"Tool {tool_name} not installed and user declined.",
                                      duration_seconds=0.0,
                                      timestamp=datetime.now())

            # Look up the repo URL – we keep a simple dict for now
            TOOL_REPOS = {
                "whois": "https://github.com/rfc1036/whois.git",
                "nmap":  "https://github.com/nmap/nmap.git",
            }

            repo_url = TOOL_REPOS.get(tool_name)
            if not repo_url:
                return ProcessResult(command="",
                                      exit_code=1,
                                      stdout="",
                                      stderr=f"No known GitHub URL for tool {tool_name}.",
                                      duration_seconds=0.0,
                                      timestamp=datetime.now())

            # Call the provisioner
            from osint_provisioner import ToolProvisioner
            prov = ToolProvisioner(workspace_root="./OSINT_WORKSPACE")
            report = prov.provision_tool_from_github(repo_url,
                                                      install_dependencies=True,
                                                      security_check=False)

            if not report.repo_cloned.success:
                return ProcessResult(command="",
                                      exit_code=1,
                                      stdout="",
                                      stderr=f"Failed to clone {repo_url}: {report.repo_cloned.error_message}",
                                      duration_seconds=0.0,
                                      timestamp=datetime.now())

            # After a successful provision we need the path of the binary.
            # The provisioner returns `clone_result.local_path` – inside that folder
            # we look for an executable with the same name as the tool (case‑insensitive).
            possible_bin = Path(report.repo_cloned.local_path) / tool_name
            if not possible_bin.exists():
                # maybe it is in a bin/ subfolder
                possible_bin = Path(report.repo_cloned.local_path) / "bin" / tool_name

            binary_path = str(possible_bin.resolve())
            if not os.path.isfile(binary_path):
                return ProcessResult(command="",
                                      exit_code=1,
                                      stdout="",
                                      stderr=f"Could not locate binary {tool_name} after provision.",
                                      duration_seconds=0.0,
                                      timestamp=datetime.now())

            # Persist the mapping for future runs
            self.tool_binaries[tool_name] = binary_path
            self._save_tool_map()

        # 2. Build the actual command – use the absolute path now
        actual_command = tool_config['command_template'].replace("{target}", target)
        actual_command = actual_command.replace(tool_name, binary_path)   # simple placeholder

        # Check for required API key
        if tool_config.get('required_api_key'):
            api_key = os.environ.get(tool_config['required_api_key'])

            if not api_key:
                print(f"❌ Required API key missing: {tool_config['required_api_key']}")
                return ProcessResult(
                    command="",
                    exit_code=1,
                    stdout="",
                    stderr=f"Missing required environment variable: {tool_config['required_api_key']}",
                    duration_seconds=0,
                    timestamp=datetime.now()
                )

        # Execute the command using actual subprocess logic
        result = self.runner.run_command(
            command_template=tool_config['command_template'],
            target_value=target,
            timeout=timeout
        )

        return result

    def save_output_to_file(self, result: ProcessResult, output_dir: str) -> str:
        """Save CLI output to file for Analyst stage

        Args:
            result: ProcessResult from execution
            output_dir: Directory to save results

        Returns:
            Path to saved file
        """
        os.makedirs(output_dir, exist_ok=True)

        # Determine file format based on content
        output_format = self.output_parser.detect_output_format(result.stdout)

        filename = f"{result.command[:50]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{output_format}"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            if output_format == 'json':
                try:
                    json.dump({
                        'command': result.command,
                        'exit_code': result.exit_code,
                        'output': json.loads(result.stdout),
                        'timestamp': result.timestamp.isoformat()
                    }, f, indent=2)
                except json.JSONDecodeError:
                    # Fallback to text format if JSON parsing fails
                    f.write(f"Command: {result.command}\n")
                    f.write(f"Exit Code: {result.exit_code}\n\n")
                    f.write("Output:\n" + result.stdout)
            else:
                f.write(result.stdout)
            if result.stderr:
                f.write("\n--- STDERR ---\n")
                f.write(result.stderr)

        print(f"✅ Output saved to {filepath}")
        return filepath


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Execute OSINT CLI tools')
    parser.add_argument('tool', help='Tool name (shodan, spiderfoot, nmap, whois)')
    parser.add_argument('target', help='Target value to scan')
    parser.add_argument('--timeout', type=int, default=120, help='Timeout in seconds')
    parser.add_argument('--output-dir', default='./data/harvesting/cli_results',
                        help='Output directory for results')

    args = parser.parse_args()

    # Initialize wrapper and execute
    wrapper = CLIWrapper(workspace_dir="./OSINT_WORKSPACE")
    result = wrapper.execute_tool(args.tool, args.target, timeout=args.timeout)

    # Save output to file
    saved_path = wrapper.save_output_to_file(result, args.output_dir)

    # Print summary
    print("\n📊 Execution Summary:")
    print(f" Command: {result.command}")
    print(f" Exit Code: {result.exit_code}")
    print(f" Duration: {result.duration_seconds}s")
    print(f" Output Format: {wrapper.output_parser.detect_output_format(result.stdout)}")

    # Extract structured data
    if result.exit_code == 0:
        emails = wrapper.output_parser.extract_emails(result.stdout)
        ips = wrapper.output_parser.extract_ips(result.stdout)

        if emails:
            print(f"\n📧 Emails Found: {len(emails)}")
            for email in emails[:5]:
                print(f" - {email}")

        if ips:
            print(f"\n🌐 IPs Found: {len(ips)}")
            for ip in ips[:5]:
                print(f" - {ip}")

    sys.exit(result.exit_code)
