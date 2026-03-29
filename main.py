#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - Main Entry Point
=========================================
Version: 1.5

Multi-stage OSINT investigation tool: RECON → HARVESTING → ANALYST → SCRIBE

Usage:
    python main.py "Matthew Pumphrey" --wip-limit 5 --format both
    python main.py "example.com" --target-type domain --format pdf --output ./reports
    python main.py --target "John Doe" --format html --verbose
"""

# BUGFIX: replacing sys.stdout with a TextIOWrapper at import time breaks any
# library that writes raw bytes to stdout and confuses log handlers that capture
# the original object. Use the PYTHONIOENCODING=utf-8 env var instead (set in
# .env or shell) — that is the correct way to control console encoding on Windows.
import asyncio
import json
import logging
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from state_storage import load_json, save_json
import pathlib

# ------------------------------------------------------------------
#  Helper: remember when main.py was last executed successfully
LAST_RUN_FILE = str(pathlib.Path.home() / ".osint_last_run.json")

def load_last_run() -> float:
    """Return epoch seconds of the previous successful run (0 if unknown)."""
    state = load_json(LAST_RUN_FILE)
    return state.get("last_run", 0.0)

def save_last_run(epoch: float):
    """Persist current run time."""
    save_json(LAST_RUN_FILE, {"last_run": epoch})

# BUGFIX: Load .env from the script's own directory with an absolute path so
# the pipeline finds keys regardless of the working directory.
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).parent / '.env'
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
        logging.getLogger('OSINT_MAIN').debug(f"Loaded .env from {_env_path}")
    else:
        load_dotenv()  # Fallback: search parent directories
        logging.getLogger('OSINT_MAIN').warning(".env not found at script directory, using CWD fallback")

except ImportError:
    print("WARNING: python-dotenv not installed. Run: pip install python-dotenv")


# Configure logging (level may be overridden by --verbose below)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger('OSINT_MAIN')

# Placeholder values that count as "not configured"
_PLACEHOLDER_KEYS = {
    "YOUR_SERPER_API_KEY",
    "YOUR_SCRAPINGANT_API_KEY",
    "YOUR_LEAK_LOOKUP_API_KEY",
    "your_serper_api_key",
    "your_scrapingant_api_key",
}


class OSINTPipeline:
    """Main pipeline orchestrator with proper data flow"""

    # Tool name → GitHub clone URL used by _update_registered_tools
    _DEFAULT_TOOL_REPOS: Dict[str, str] = {
        "whois": "https://github.com/rfc1036/whois.git",
        "nmap":  "https://github.com/nmap/nmap.git",
    }

    def __init__(self, privacy_mode: str = "hybrid"):
        self.privacy_mode = privacy_mode
        self.api_keys = {
            'serper':     os.getenv("SERPER_API_KEY"),
            'scrapingant': os.getenv("SCRAPINGANT_API_KEY"),
            'leak_lookup': os.getenv("LEAK_LOOKUP_API_KEY"),
        }
        self._validate_api_keys()

    def _validate_api_keys(self):
        """Ensure required API keys are configured.

        Behaviour varies by privacy_mode:
          private  — all cloud keys must be present (strict)
          public   — missing keys are only warnings (permissive)
          hybrid   — original behaviour: raise on missing required keys
        """
        missing = []

        serper_key = self.api_keys['serper']
        if not serper_key or serper_key in _PLACEHOLDER_KEYS:
            missing.append("SERPER_API_KEY")

        scrapeant_key = self.api_keys['scrapingant']
        if not scrapeant_key or scrapeant_key in _PLACEHOLDER_KEYS:
            missing.append("SCRAPINGANT_API_KEY")

        # Warn about common typo variants present in env
        all_env = list(os.environ.keys())
        if 'SERPER_KEY' in all_env and 'SERPER_API_KEY' not in all_env:
            logger.warning("Found SERPER_KEY in environment — the required name is SERPER_API_KEY")

        if missing:
            if self.privacy_mode == "public":
                # Permissive: cloud keys optional in public mode (uses local LLM)
                logger.warning(
                    f"API keys not configured (public mode — cloud calls will be skipped): "
                    f"{', '.join(missing)}"
                )
            else:
                # private and hybrid both require the keys
                raise ValueError(
                    f"Missing required API keys: {', '.join(missing)}\n"
                    f"Add them to your .env file or environment:\n"
                    f"  SERPER_API_KEY=<your Serper.dev key>\n"
                    f"  SCRAPINGANT_API_KEY=<your ScrapingAnt v2 key>\n"
                    f"  LEAK_LOOKUP_API_KEY=<optional>\n"
                )

        logger.info("All required API keys validated")

    def get_llm_client(self):
        """Return an LLM client appropriate for the current privacy_mode.

        private  → local Ollama/LM-Studio endpoint (no data leaves the machine)
        public   → cloud OpenAI-compatible client (USE_CLOUD_LLM env flag or default)
        hybrid   → cloud if keys present, else local fallback
        """
        use_cloud = os.getenv("USE_CLOUD_LLM", "").lower() in ("1", "true", "yes")

        if self.privacy_mode == "private" or (self.privacy_mode == "hybrid" and not use_cloud):
            # Local Ollama endpoint
            try:
                from openai import OpenAI as _OAI  # openai>=1.0 works with Ollama
                base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
                return _OAI(api_key="ollama", base_url=base_url)
            except ImportError:
                logger.warning("openai package not installed; LLM client unavailable")
                return None
        else:
            # Cloud client
            try:
                from openai import OpenAI as _OAI
                return _OAI(api_key=os.getenv("OPENAI_API_KEY"))
            except ImportError:
                logger.warning("openai package not installed; LLM client unavailable")
                return None

    async def _update_registered_tools(self, tool_repos: Dict[str, str]):
        """Provision/update CLI tools if more than 7 days have passed since the last run."""
        now = time.time()
        last = load_last_run()
        seven_days = 7 * 24 * 3600

        if now - last < seven_days:
            logger.debug("Tool auto-update skipped (last run < 7 days ago)")
            return

        logger.info("Running 7-day tool auto-update …")
        try:
            from osint_provisioner import ToolProvisioner
            prov = ToolProvisioner(workspace_root="./OSINT_WORKSPACE")
            for tool_name, repo_url in tool_repos.items():
                try:
                    prov.provision_tool_from_github(
                        repo_url, install_dependencies=True, security_check=False
                    )
                    logger.info(f"  Updated tool: {tool_name}")
                except Exception as tool_err:
                    logger.warning(f"  Failed to update {tool_name}: {tool_err}")
        except ImportError:
            logger.warning("osint_provisioner not available; skipping tool update")

        save_last_run(now)

    async def run_investigation(
        self,
        query: str,
        target_type: str = "person",
        report_format: str = "both",
        output_path: str = "./reports",
        wip_limit: int = 5,
        tool_repos: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a complete OSINT investigation through all 4 stages.

        Args:
            query:         Search query or target to investigate.
            target_type:   Entity type — person | company | domain | product.
            report_format: Output format — pdf | html | both.
            output_path:   Directory where reports are written.
            wip_limit:     Work-in-progress limit per Kanban column.
            tool_repos:    Optional tool-name → GitHub URL overrides.

        Returns:
            Dict with status, report_path, and execution metrics.
        """
        logger.info(f"Starting investigation: '{query}' (type={target_type}, fmt={report_format}, privacy={self.privacy_mode})")

        # Ensure output directory exists
        Path(output_path).mkdir(parents=True, exist_ok=True)

        # 7-day auto-update of registered CLI tools (non-fatal)
        merged_repos = {**self._DEFAULT_TOOL_REPOS, **(tool_repos or {})}
        try:
            await self._update_registered_tools(merged_repos)
        except Exception as upd_err:
            logger.warning(f"Tool auto-update failed (non-fatal): {upd_err}")

        try:
            from osint_kanban_manager import OSINTKanbanManager, PipelineConfig

            # BUGFIX: wip_limit and report_format are now accepted and forwarded
            wip_limits = {stage: wip_limit for stage in ("RECON", "HARVESTING", "ANALYST", "SCRIBE")}
            config = PipelineConfig(
                query=query,
                target_name=target_type,
                wip_limits=wip_limits,
                serper_api_key=self.api_keys['serper'],
                scrapingant_api_key=self.api_keys['scrapingant'],
                leak_lookup_api_key=self.api_keys.get('leak_lookup') or None,
                privacy_mode=self.privacy_mode,
                tool_repos=merged_repos,
            )

            manager = OSINTKanbanManager(config)
            await manager.start_pipeline(query, target_type)

            results = await manager.execute_pipeline(
                query=query,
                report_format=report_format,
                output_path=output_path,
                graceful_failure_handling=True,
            )

            return {
                "status": "completed",
                "query": query,
                "target_type": target_type,
                "report_format": report_format,
                "total_processed": results.total_processed,
                "successful": results.successful,
                "failed": results.failed,
                "execution_time_seconds": round(results.execution_time, 2),
                "report_path": results.report_path,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Investigation failed: {e}")
            traceback.print_exc()
            return {
                "status": "failed",
                "query": query,
                "target_type": target_type,
                "failed": 1,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


def print_investigation_summary(result: Dict[str, Any]):
    """Print a formatted summary of the investigation results."""

    print("\n" + "=" * 70)
    print("OSINT INVESTIGATION SUMMARY")
    print("=" * 70)

    if result.get("status") == "completed":
        print(f"\nTarget:         {result['query']} ({result['target_type']})")
        print(f"Status:         COMPLETED")
        print(f"Format:         {result.get('report_format', 'both')}")
        print(f"Execution time: {result['execution_time_seconds']}s")
        print(f"Processed:      {result['total_processed']}")
        print(f"Successful:     {result['successful']}")
        print(f"Failed:         {result['failed']}")

        rp = result.get("report_path")
        if rp:
            print(f"\nReport: {rp}")
            if os.path.exists(rp):
                size = os.path.getsize(rp)
                print(f"  Size: {size:,} bytes ({size / 1024:.1f} KB)")
        else:
            print("\nNo report path available")

    elif result.get("status") == "failed":
        print(f"\nStatus:  FAILED")
        print(f"Target:  {result['query']} ({result.get('target_type', '?')})")
        print(f"Error:   {result.get('error', 'unknown')}")

    else:
        print(f"\nUnknown status: {result.get('status')}")

    print("=" * 70)


async def main():
    """Main entry point for CLI usage."""

    import argparse

    # BUGFIX: re-added --wip-limit, --format, and --output flags that were
    # missing from the previous implementation, causing argparse to reject
    # valid README command lines.
    parser = argparse.ArgumentParser(
        description='OSINT Kanban Pipeline — Multi-stage investigation tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "Matthew Pumphrey" --wip-limit 5 --format both
  python main.py "example.com" --target-type domain --format pdf --output ./reports
  python main.py --target "John Doe" --format html --verbose

Required environment variables (.env):
  SERPER_API_KEY      — Google search via Serper.dev
  SCRAPINGANT_API_KEY   — Web scraping via ScrapingAnt v2
  LEAK_LOOKUP_API_KEY — (optional) breach database lookup
        """,
    )

    # Positional argument — the target/query string
    # BUGFIX: made nargs='?' so --target can supply it instead when provided
    parser.add_argument(
        'query',
        nargs='?',
        default=None,
        help='Search query or target to investigate (positional)',
    )

    # BUGFIX: added --target as an alternative way to pass the query string,
    # matching the README example `python main.py --target "Matthew Pumphrey"`.
    parser.add_argument(
        '--target', '-q',
        default=None,
        metavar='QUERY',
        help='Target query (alternative to positional argument)',
    )

    # Added -t alias for --target-type
    parser.add_argument(
        '--target-type', '-t',
        default='person',
        choices=['person', 'company', 'domain', 'product'],
        help='Entity type being investigated (default: person)',
    )

    # BUGFIX: added --wip-limit flag (README "WIP Limits" section); added -w alias
    parser.add_argument(
        '--wip-limit', '-w',
        type=int,
        default=5,
        metavar='N',
        help='Work-in-progress limit per Kanban column (default: 5)',
    )

    # BUGFIX: added --format flag to control report output format; added -f alias
    parser.add_argument(
        '--format', '-f',
        default='both',
        choices=['pdf', 'html', 'both'],
        help='Report output format (default: both)',
    )

    # BUGFIX: added --output flag for custom report directory; added -o alias
    parser.add_argument(
        '--output', '-o',
        default='./reports',
        metavar='PATH',
        help='Output directory for reports (default: ./reports)',
    )

    parser.add_argument(
        '--privacy', '-p',
        default='hybrid',
        choices=['public', 'private', 'hybrid'],
        help='Privacy mode: public (cloud LLM, permissive keys), private (local LLM, strict keys), hybrid (default)',
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable DEBUG-level logging',
    )

    args = parser.parse_args()

    # Resolve the query from positional or --target
    query = args.query or args.target
    if not query:
        parser.error("Provide a query either as a positional argument or via --target")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        pipeline = OSINTPipeline(privacy_mode=args.privacy)

        logger.info("Starting OSINT Kanban Pipeline...")
        result = await pipeline.run_investigation(
            query=query,
            target_type=args.target_type,
            report_format=args.format,
            output_path=args.output,
            wip_limit=args.wip_limit,
        )

        print_investigation_summary(result)
        return 0 if result.get("status") == "completed" else 1

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
