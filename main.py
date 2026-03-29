#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - Main Entry Point
=========================================

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
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

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
    "YOUR_SCRAPEANT_API_KEY",
    "YOUR_LEAK_LOOKUP_API_KEY",
    "your_serper_api_key",
    "your_scrapeant_api_key",
}


class OSINTPipeline:
    """Main pipeline orchestrator with proper data flow"""

    def __init__(self):
        self.api_keys = {
            'serper':     os.getenv("SERPER_API_KEY"),
            'scrapingant': os.getenv("SCRAPEANT_API_KEY"),
            'leak_lookup': os.getenv("LEAK_LOOKUP_API_KEY"),
        }
        self._validate_api_keys()

    def _validate_api_keys(self):
        """Ensure required API keys are configured with exact environment variable names.

        BUGFIX: accept only SERPER_API_KEY and SCRAPEANT_API_KEY (not SERPER_KEY or
        SCRAPINGANT_API_KEY). Raises ValueError with clear instructions if missing.
        """
        missing = []

        serper_key = self.api_keys['serper']
        if not serper_key or serper_key in _PLACEHOLDER_KEYS:
            missing.append("SERPER_API_KEY")

        scrapeant_key = self.api_keys['scrapingant']
        if not scrapeant_key or scrapeant_key in _PLACEHOLDER_KEYS:
            missing.append("SCRAPEANT_API_KEY")

        # Warn about common typo variants present in env
        all_env = list(os.environ.keys())
        if 'SERPER_KEY' in all_env and 'SERPER_API_KEY' not in all_env:
            logger.warning("Found SERPER_KEY in environment — the required name is SERPER_API_KEY")
        if 'SCRAPINGANT_API_KEY' in all_env and 'SCRAPEANT_API_KEY' not in all_env:
            logger.warning("Found SCRAPINGANT_API_KEY — the required name is SCRAPEANT_API_KEY (no 'ING')")

        if missing:
            raise ValueError(
                f"Missing required API keys: {', '.join(missing)}\n"
                f"Add them to your .env file or environment:\n"
                f"  SERPER_API_KEY=<your Serper.dev key>\n"
                f"  SCRAPEANT_API_KEY=<your ScrapingAnt v2 key>\n"
                f"  LEAK_LOOKUP_API_KEY=<optional>\n"
            )

        logger.info("All required API keys validated")

    async def run_investigation(
        self,
        query: str,
        target_type: str = "person",
        report_format: str = "both",
        output_path: str = "./reports",
        wip_limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Run a complete OSINT investigation through all 4 stages.

        Args:
            query:         Search query or target to investigate.
            target_type:   Entity type — person | company | domain | product.
            report_format: Output format — pdf | html | both.
            output_path:   Directory where reports are written.
            wip_limit:     Work-in-progress limit per Kanban column.

        Returns:
            Dict with status, report_path, and execution metrics.
        """
        logger.info(f"Starting investigation: '{query}' (type={target_type}, fmt={report_format})")

        # Ensure output directory exists
        Path(output_path).mkdir(parents=True, exist_ok=True)

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
  SCRAPEANT_API_KEY   — Web scraping via ScrapingAnt v2
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
        '--target',
        default=None,
        metavar='QUERY',
        help='Target query (alternative to positional argument)',
    )

    parser.add_argument(
        '--target-type',
        default='person',
        choices=['person', 'company', 'domain', 'product'],
        help='Entity type being investigated (default: person)',
    )

    # BUGFIX: added --wip-limit flag (README "WIP Limits" section)
    parser.add_argument(
        '--wip-limit',
        type=int,
        default=5,
        metavar='N',
        help='Work-in-progress limit per Kanban column (default: 5)',
    )

    # BUGFIX: added --format flag to control report output format
    parser.add_argument(
        '--format',
        default='both',
        choices=['pdf', 'html', 'both'],
        help='Report output format (default: both)',
    )

    # BUGFIX: added --output flag for custom report directory
    parser.add_argument(
        '--output',
        default='./reports',
        metavar='PATH',
        help='Output directory for reports (default: ./reports)',
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
        pipeline = OSINTPipeline()

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
