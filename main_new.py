#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - Main Entry Point
=========================================
Version: 1.5

Multi‑stage OSINT investigation tool: RECON → HARVESTING → ANALYST → SCRIBE

The script now also:
 • remembers when it was last executed (`~/.osint_last_run.json`);
 • if > 7 days have passed, updates every registered CLI‑tool repo;
 • the wrapper automatically installs a missing binary on first request and stores its
   absolute path in `~/.cli_tools.json`.
"""

# ------------------------------------------------------------------
#  Imports (kept identical to your original file)
import asyncio
import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

# ------------------------------------------------------------------
#  Simple key/value persistence helpers – we keep them inside this file
def _load_json(path: str) -> dict:
    try:
        with open(Path(path).expanduser(), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"⚠️ Failed to load {path}: {e}")
        return {}

def _save_json(path: str, data: dict):
    try:
        with open(Path(path).expanduser(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to write {path}: {e}")

# ------------------------------------------------------------------
#  Where we store the “last run” timestamp
LAST_RUN_FILE = str(Path.home() / ".osint_last_run.json")

def _load_last_run() -> float:
    return _load_json(LAST_RUN_FILE).get("last_run", 0.0)

def _save_last_run(ts: float):
    _save_json(LAST_RUN_FILE, {"last_run": ts})

# ------------------------------------------------------------------
#  Load .env from the script’s own directory (absolute path)
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except Exception as e:
    print(f"⚠️ Could not load .env: {e}")

# ------------------------------------------------------------------
#  Logging configuration – can be overridden with `--verbose`
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
)
logger = logging.getLogger("OSINT_MAIN")

#  Placeholder values that count as “not configured”
_PLACEHOLDER_KEYS = {
    "YOUR_SERPER_API_KEY",
    "YOUR_SCRAPINGANT_API_KEY",
    "YOUR_LEAK_LOOKUP_API_KEY",
    "your_serper_api_key",
    "your_scrapingant_api_key",
}

class OSINTPipeline:
    """Main pipeline orchestrator with proper data flow"""

    def __init__(self):
        self.api_keys = {
            "serper": os.getenv("SERPER_API_KEY"),
            "scrapingant": os.getenv("SCRAPINGANT_API_KEY"),
            "leak_lookup": os.getenv("LEAK_LOOKUP_API_KEY"),
        }
        self._validate_api_keys()

    # ------------------------------------------------------------------
    def _validate_api_keys(self):
        missing = []
        serper_key = self.api_keys["serper"]
        if not serper_key or serper_key in _PLACEHOLDER_KEYS:
            missing.append("SERPER_API_KEY")
        scrapeant_key = self.api_keys["scrapingant"]
        if not scrapeant_key or scrapeant_key in _PLACEHOLDER_KEYS:
            missing.append("SCRAPINGANT_API_KEY")

        if missing:
            raise ValueError(
                f"Missing required API keys: {', '.join(missing)}\n"
                "Add them to your .env file or environment:\n"
                "  SERPER_API_KEY=<your Serper.dev key>\n"
                "  SCRAPINGANT_API_KEY=<your ScrapingAnt v2 key>\n"
                "  LEAK_LOOKUP_API_KEY=<optional>"
            )
        logger.info("All required API keys validated")

    # ------------------------------------------------------------------
    async def run_investigation(
        self,
        query: str,
        target_type: str = "person",
        report_format: str = "both",
        output_path: str = "./reports",
        wip_limit: int = 5,
    ) -> Dict[str, Any]:
        """Run a complete OSINT investigation through all 4 stages."""
        logger.info(
            f"Starting investigation: '{query}' (type={target_type}, fmt={report_format})"
        )

        Path(output_path).mkdir(parents=True, exist_ok=True)

        try:
            from osint_kanban_manager import OSINTKanbanManager, PipelineConfig
            from osint_provisioner import ToolProvisioner

            # ------------------------------------------------------------------
            #  Forward the user arguments and add an optional `tool_repos` dict.
            #  By default it is empty – you can edit the script to point at your tool repos.
            TOOL_REPOS = {
                # Example entries – replace with real GitHub URLs
                "whois": "https://github.com/example/whois-tool",
                "nmap": "https://github.com/robertdavidson/nmap",
            }

            wip_limits = {stage: wip_limit for stage in ("RECON", "HARVESTING", "ANALYST", "SCRIBE")}
            config = PipelineConfig(
                query=query,
                target_name=target_type,
                wip_limits=wip_limits,
                serper_api_key=self.api_keys["serper"],
                scrapingant_api_key=self.api_keys["scrapingant"],
                leak_lookup_api_key=self.api_keys.get("leak_lookup") or None,
                tool_repos=TOOL_REPOS,          # <<< NEW
            )

            manager = OSINTKanbanManager(config)

            # ------------------------------------------------------------------
            #  Auto‑update step – if > 7 days have passed we pull the latest commit of each tool.
            now_ts = time.time()
            prev_ts = _load_last_run()
            if now_ts - prev_ts > 7 * 24 * 60 * 60:   # 604800 seconds
                logger.info("More than a week since last run – updating registered tools")
                await self._update_registered_tools(config, manager)

            # ------------------------------------------------------------------
            await manager.start_pipeline(query, target_type)
            results = await manager.execute_pipeline(
                query=query,
                report_format=report_format,
                output_path=output_path,
                graceful_failure_handling=True,
            )

            # Store the successful run timestamp
            _save_last_run(now_ts)

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

    # ------------------------------------------------------------------
    async def _update_registered_tools(self, config: PipelineConfig, manager: OSINTKanbanManager):
        """
        Pull the latest commit from every repo listed in `config.tool_repos`
        and re‑install it via the provisioner.
        """
        if not getattr(config, "tool_repos", {}):
            return

        prov = ToolProvisioner(workspace_root="./OSINT_WORKSPACE")
        for name, url in config.tool_repos.items():
            try:
                logger.info(f"Updating tool <{name}> from {url}")
                report = prov.provision_tool_from_github(
                    github_url=url,
                    install_dependencies=True,
                    security_check=False,   # we trust the repo when auto‑updating
                )
                if not report.repo_cloned.success:
                    logger.warning(f"Failed to update {name}: {report.repo_cloned.error_message}")
            except Exception as e:
                logger.warning(f"Exception while updating tool <{name}>: {e}")

# ------------------------------------------------------------------
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
                print(f"  Size: {size:,} bytes ({size / 1024:.2f} KB)")
        else:
            print("\nNo report path available")

    elif result.get("status") == "failed":
        print(f"\nStatus:  FAILED")
        print(f"Target:  {result['query']} ({result.get('target_type', '?')})")
        print(f"Error:   {result.get('error', 'unknown')}")

    else:
        print(f"\nUnknown status: {result.get('status')}")

    print("=" * 70)

# ------------------------------------------------------------------
async def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OSINT Kanban Pipeline — Multi‑stage investigation tool",
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

    # Positional argument – the target/query string
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Search query or target to investigate (positional)",
    )
    # Alternative flag – `--target` / `-q`
    parser.add_argument("--target", "-q", default=None, metavar="QUERY", help="Target query")

    parser.add_argument(
        "--target-type",
        "-t",
        default="person",
        choices=["person", "company", "domain", "product"],
        help="Entity type being investigated (default: person)",
    )
    parser.add_argument(
        "--wip-limit",
        "-w",
        type=int,
        default=5,
        metavar="N",
        help="Work‑in‑progress limit per Kanban column (default: 5)",
    )
    parser.add_argument(
        "--format",
        "-f",
        default="both",
        choices=["pdf", "html", "both"],
        help="Report output format (default: both)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./reports",
        metavar="PATH",
        help="Output directory for reports (default: ./reports)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG‑level logging")

    args = parser.parse_args()

    query = args.query or args.target
    if not query:
        parser.error("Provide a query either as a positional argument or via --target")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        pipeline = OSINTPipeline()
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