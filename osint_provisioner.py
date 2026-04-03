#!/usr/bin/env python3
"""
OSINT Tool Provisioner - Clones GitHub repositories and installs dependencies.
Supports requirements.txt, setup.py, PyPI packages with security sandboxing.
Author: Matt Pumphrey
Date: 3/16/2026
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CloneResult:
    """Result of repository cloning operation"""
    success: bool
    repo_name: str
    local_path: str
    git_branch: str
    remote_url: str
    clone_timestamp: datetime
    error_message: Optional[str] = None


@dataclass
class InstallationResult:
    """Result of dependency installation"""
    success: bool
    dependencies_installed: int
    virtual_env_path: str
    errors: List[str]
    installed_at: datetime


@dataclass
class ProvisioningReport:
    """Complete provisioning result summary"""
    repo_cloned: CloneResult
    deps_installed: Optional[InstallationResult]
    security_scan_passed: bool
    total_time_seconds: float


class GitRepositoryCloner:
    """Secure GitHub repository cloning with workspace boundary validation"""

    def __init__(self, tools_dir: str):
        self.tools_dir = os.path.abspath(tools_dir)

    def validate_workspace_boundary(self, target_path: str) -> bool:
        """Ensure clone stays within tools directory"""
        resolved_target = os.path.abspath(target_path)

        if not resolved_target.startswith(self.tools_dir):
            print(f"❌ Clone destination outside workspace boundary!")
            return False

        if '..' in target_path.split(os.path.sep):
            print("❌ Path traversal detected in repository URL")
            return False

        return True

    def clone_repository(self, github_url: str) -> CloneResult:
        """Clone GitHub repository to workspace/tools directory"""
        start_time = datetime.now()

        try:
            url_match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', github_url)

            if not url_match:
                return CloneResult(
                    success=False, repo_name="", local_path="",
                    git_branch="", remote_url=github_url,
                    clone_timestamp=datetime.now(),
                    error_message=f"Invalid GitHub URL format: {github_url}"
                )

            owner = url_match.group(1)
            repo_name = url_match.group(2)
            safe_repo_name = re.sub(r'[^\w\-]', '_', f"{repo_name}_{owner}")
            clone_path = os.path.join(self.tools_dir, safe_repo_name)

            if not self.validate_workspace_boundary(clone_path):
                return CloneResult(
                    success=False, repo_name="", local_path="",
                    git_branch="", remote_url=github_url,
                    clone_timestamp=datetime.now(),
                    error_message="Clone destination outside allowed boundaries"
                )

            if os.path.exists(clone_path):
                # Pull latest changes instead of just returning stale clone
                print(f"📥 Repository exists at {clone_path} — pulling latest …")
                try:
                    pull = subprocess.run(
                        ["git", "pull", "--ff-only"],
                        capture_output=True, text=True,
                        cwd=clone_path, timeout=120,
                    )
                    if pull.returncode == 0:
                        print(f"✅ Updated {repo_name}")
                    else:
                        print(f"⚠️ git pull failed (non-fatal): {pull.stderr.strip()}")
                except Exception as pull_err:
                    print(f"⚠️ Could not pull {repo_name}: {pull_err}")

                return CloneResult(
                    success=True, repo_name=repo_name, local_path=clone_path,
                    git_branch="existing", remote_url=github_url,
                    clone_timestamp=datetime.now()
                )

            print(f"📥 Cloning {github_url}...")
            process = subprocess.run(
                ["git", "clone", "--depth=1", github_url, clone_path],
                capture_output=True, text=True, timeout=300
            )

            if process.returncode != 0:
                return CloneResult(
                    success=False, repo_name="", local_path="",
                    git_branch="", remote_url=github_url,
                    clone_timestamp=datetime.now(),
                    error_message=f"Git clone failed: {process.stderr}"
                )

            return CloneResult(
                success=True, repo_name=repo_name, local_path=clone_path,
                git_branch="main", remote_url=github_url,
                clone_timestamp=datetime.now()
            )

        except Exception as e:
            return CloneResult(
                success=False, repo_name="", local_path="",
                git_branch="", remote_url=github_url,
                clone_timestamp=datetime.now(), error_message=str(e)
            )


class DependencyInstaller:
    """Installs Python dependencies with virtual environment isolation"""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)

    def detect_requirements_file(self, repo_path: str) -> Optional[str]:
        """Find requirements.txt or setup.py in repository"""
        possible_files = ['requirements.txt', 'setup.py', 'pyproject.toml']
        for filename in possible_files:
            filepath = os.path.join(repo_path, filename)
            if os.path.exists(filepath):
                return filepath
        return None

    def create_virtual_environment(self, repo_path: str) -> Optional[str]:
        """Create isolated virtual environment for the tool"""
        venv_path = os.path.join(repo_path, '.venv')
        if os.path.exists(venv_path):
            return venv_path

        try:
            print(f"🔧 Creating virtual environment at {venv_path}...")
            subprocess.run(["python3", "-m", "venv", venv_path], check=True, timeout=120)
            return venv_path
        except Exception as e:
            print(f"❌ Error creating venv: {e}")
            return None

    def install_dependencies(self, repo_path: str, requirements_file: Optional[str], venv_path: str) -> InstallationResult:
        """Install dependencies in isolated virtual environment"""
        start_time = datetime.now()
        if not requirements_file:
            return InstallationResult(False, 0, "", ["No requirements file"], datetime.now())

        pip_executable = os.path.join(venv_path, 'bin', 'pip')
        if sys.platform == 'win32':
            pip_executable = os.path.join(venv_path, 'Scripts', 'pip.exe')

        try:
            print(f"📦 Installing dependencies from {requirements_file}...")
            subprocess.run([pip_executable, 'install', '-r', requirements_file], check=True, timeout=600)
            return InstallationResult(True, 1, venv_path, [], datetime.now())
        except Exception as e:
            return InstallationResult(False, 0, "", [str(e)], datetime.now())
    def install_dependencies(
        self,
        repo_path: str,
        requirements_file: Optional[str],
        venv_path: str
    ) -> InstallationResult:
        """Install dependencies in isolated virtual environment"""

        start_time = datetime.now()

        if not requirements_file or not os.path.exists(requirements_file):
            return InstallationResult(
                success=False,
                dependencies_installed=0,
                virtual_env_path="",
                errors=["No requirements file found"],
                installed_at=datetime.now()
            )

        try:
            # Determine pip executable path in venv
            if sys.platform == 'win32':
                pip_executable = os.path.join(venv_path, 'Scripts', 'pip.exe')
            else:
                pip_executable = os.path.join(venv_path, 'bin', 'pip')

            # Check that pip exists in venv
            if not os.path.exists(pip_executable):
                return InstallationResult(
                    success=False,
                    dependencies_installed=0,
                    virtual_env_path="",
                    errors=["pip executable not found in virtual environment"],
                    installed_at=datetime.now()
                )

            print(f"📦 Installing dependencies from {requirements_file}...")

            # Execute pip install with actual subprocess logic
            process = subprocess.run(
                [pip_executable, 'install', '-r', requirements_file],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=600  # 10 minute timeout for large installs
            )

            if process.returncode != 0:
                errors = [process.stderr]
                return InstallationResult(
                    success=False,
                    dependencies_installed=0,
                    virtual_env_path="",
                    errors=errors,
                    installed_at=datetime.now()
                )

            # Count installed packages (approximate)
            count_process = subprocess.run(
                [pip_executable, 'list'],
                capture_output=True,
                text=True,
                cwd=repo_path
            )

            if count_process.returncode == 0:
                lines = count_process.stdout.strip().split('\n')
                # Skip header line and pip/setuptools entries
                installed_count = len([l for l in lines[2:] if l.strip()])
            else:
                installed_count = -1

            print(f"✅ Dependencies installed successfully")
            print(f" Duration: {(datetime.now() - start_time).total_seconds():.2f}s")

            return InstallationResult(
                success=True,
                dependencies_installed=installed_count,
                virtual_env_path=venv_path,
                errors=[],
                installed_at=datetime.now()
            )

        except subprocess.TimeoutExpired:
            return InstallationResult(
                success=False,
                dependencies_installed=0,
                virtual_env_path="",
                errors=["Dependency installation timed out after 10 minutes"],
                installed_at=datetime.now()
            )

        except Exception as e:
            return InstallationResult(
                success=False,
                dependencies_installed=0,
                virtual_env_path="",
                errors=[str(e)],
                installed_at=datetime.now()
            )


class SecuritySandbox:
    """Scans repositories for malicious patterns before installation"""

    MALICIOUS_PATTERNS = [
        r'rm\s+-rf\s+/',             # System-wide deletion
        r'chmod\s+[7-9]\s+/etc',     # Privilege escalation
        r'sudo\s+(passwd|useradd)',  # Account manipulation
        r'/tmp/.*\.(sh|py|bash)',    # Script files in temp
    ]

    @staticmethod
    def scan_repository(repo_path: str) -> Tuple[bool, List[str]]:
        """Scan repository for malicious patterns"""
        found_patterns = []

        for root, dirs, files in os.walk(repo_path):
            if any(skip in root.lower() for skip in ['.git', '__pycache__', 'venv']):
                continue

            for file in files:
                if not (file.endswith('.py') or file == 'setup.py'):
                    continue

                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        for pattern in SecuritySandbox.MALICIOUS_PATTERNS:
                            if re.search(pattern, content, re.IGNORECASE):
                                found_patterns.append(f"{pattern} in {filepath}")
                except Exception:
                    continue

        return len(found_patterns) == 0, found_patterns


class ToolProvisioner:
    """Main provisioner class that orchestrates cloning and installation"""

    def __init__(self, workspace_root: str = "./OSINT_WORKSPACE"):
        self.workspace_root = os.path.abspath(workspace_root)
        self.tools_dir = os.path.join(self.workspace_root, 'tools')

        if not os.path.exists(self.tools_dir):
            print(f"Creating tools directory at {self.tools_dir}")
            os.makedirs(self.tools_dir)

        self.cloner = GitRepositoryCloner(self.tools_dir)
        self.installer = DependencyInstaller(self.workspace_root)

    def provision_tool_from_github(
        self,
        github_url: str,
        install_dependencies: bool = True,
        security_check: bool = True
    ) -> ProvisioningReport:
        """Provision tool from GitHub repository with full workflow"""

        start_time = datetime.now()

        print("=" * 70)
        print(f"🔧 Provisioning Tool from GitHub")
        print(f" URL: {github_url}")
        print("=" * 70)

        # Step 1: Clone
        print("\n📥 STEP 1: Cloning Repository")
        clone_result = self.cloner.clone_repository(github_url)

        if not clone_result.success:
            return ProvisioningReport(clone_result, None, False, 
                                     (datetime.now() - start_time).total_seconds())

        # Step 2: Security scan
        is_safe = True
        if security_check:
            print("\n🛡️ STEP 2: Running Security Scan")
            is_safe, patterns = SecuritySandbox.scan_repository(clone_result.local_path)
            if not is_safe:
                print("⚠️ Security threats detected!")
                return ProvisioningReport(clone_result, None, False, 
                                         (datetime.now() - start_time).total_seconds())
            print("✅ Security scan passed")

        # Step 3: Install
        install_result = None
        if install_dependencies:
            print("\n📦 STEP 3: Installing Dependencies")
            req_file = self.installer.detect_requirements_file(clone_result.local_path)
            venv_p = self.installer.create_virtual_environment(clone_result.local_path)
            
            if req_file and venv_p:
                install_result = self.installer.install_dependencies(clone_result.local_path, req_file, venv_p)

        # Step 4: Auto-register the tool in ToolRegistry + persist binary path
        if clone_result.success:
            self._auto_register_tool(clone_result, install_result)

        total_time = (datetime.now() - start_time).total_seconds()
        return ProvisioningReport(clone_result, install_result, is_safe, total_time)

    # ------------------------------------------------------------------
    #  Auto-registration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_binary(clone_path: str, repo_name: str) -> Optional[str]:
        """Heuristic: find an executable with the repo name inside the clone."""
        candidates = [
            Path(clone_path) / repo_name,
            Path(clone_path) / "bin" / repo_name,
            Path(clone_path) / f"{repo_name}.py",
        ]
        # Also check for a main.py that might be the entry-point
        candidates.append(Path(clone_path) / "main.py")

        for c in candidates:
            if c.exists():
                return str(c.resolve())

        # Fallback: search shutil.which (tool may already be on PATH)
        found = shutil.which(repo_name)
        return found

    @staticmethod
    def _build_command_template(binary_path: str, repo_name: str,
                                venv_path: Optional[str] = None) -> str:
        """Build a command_template string suitable for ToolRegistry."""
        bp = Path(binary_path)
        if bp.suffix == ".py":
            python = "python"
            if venv_path:
                if sys.platform == "win32":
                    python = str(Path(venv_path) / "Scripts" / "python.exe")
                else:
                    python = str(Path(venv_path) / "bin" / "python")
            return f"{python} {binary_path} {{target}}"
        return f"{binary_path} {{target}}"

    def _auto_register_tool(self, clone: "CloneResult",
                            install: Optional["InstallationResult"]) -> None:
        """Register the provisioned tool in ToolRegistry and persist its binary path."""
        tool_name = clone.repo_name.lower()
        binary = self._detect_binary(clone.local_path, clone.repo_name)
        if not binary:
            print(f"⚠️ Could not detect binary for {clone.repo_name}; skipping auto-register")
            return

        venv_path = install.virtual_env_path if install and install.success else None
        cmd_template = self._build_command_template(binary, clone.repo_name, venv_path)

        # --- write into ToolRegistry (in-memory, immediate) ---
        try:
            from osint_cli_wrapper import ToolRegistry
            if tool_name not in ToolRegistry.TOOLS:
                ToolRegistry.TOOLS[tool_name] = {
                    "command_template": cmd_template,
                    "description": f"{clone.repo_name} — auto-provisioned from {clone.remote_url}",
                    "required_api_key": None,
                }
                print(f"✅ Registered '{tool_name}' in ToolRegistry")
            else:
                # Update the command template in case the path changed
                ToolRegistry.TOOLS[tool_name]["command_template"] = cmd_template
                print(f"✅ Updated '{tool_name}' command in ToolRegistry")
        except ImportError:
            print("⚠️ osint_cli_wrapper not importable; ToolRegistry not updated")

        # --- persist binary path in ~/.cli_tools.json ---
        try:
            from state_storage import load_json, save_json
            cli_map_path = str(Path.home() / ".cli_tools.json")
            tool_map = load_json(cli_map_path)
            tool_map[tool_name] = binary
            save_json(cli_map_path, tool_map)
            print(f"✅ Persisted '{tool_name}' → {binary} in ~/.cli_tools.json")
        except Exception as persist_err:
            print(f"⚠️ Could not persist binary path: {persist_err}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Provision OSINT tools from GitHub')
    parser.add_argument('github_url', help='GitHub repository URL to provision')
    parser.add_argument('--workspace-root', default='./OSINT_WORKSPACE')

    args = parser.parse_args()

    provisioner = ToolProvisioner(workspace_root=args.workspace_root)
    result = provisioner.provision_tool_from_github(github_url=args.github_url)

    if result.repo_cloned.success:
        print("\n✅ Provisioning completed successfully!")
    else:
        print(f"\n❌ Provisioning failed: {result.repo_cloned.error_message}")
        sys.exit(1)
