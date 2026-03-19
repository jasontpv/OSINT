#!/usr/bin/env python3
"""
OSINT AI Automation Tool - Main Entry Point
Kanban-style agentic workflow with WIP limits across 4 stages.

Usage:
    python main.py --target "test@example.com" --type email
    python main.py --target "example.com" --type domain
"""

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Import pipeline components
from osint_kanban_manager import KanbanPipelineManager
from recon_stage import generate_recon_queries
from harvesting_agent import execute_osint_harvest
from analyst_agent import verify_search_results, filter_high_confidence
from scribe_agent import generate_pdf_report, generate_html_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("osint_pipeline")


class OSINTPipeline:
    """Main orchestration class for the OSINT Kanban Pipeline"""
    
    def __init__(self, serper_api_key: str, scrapingant_api_key: str, leak_lookup_api_key: str):
        self.serper_api_key = serper_api_key
        self.scrapingant_api_key = scrapingant_api_key
        self.leak_lookup_api_key = leak_lookup_api_key
        
    async def run_pipeline(self, target: str, search_type: str) -> dict:
        """Execute the full OSINT pipeline from RECON to SCRIBE"""
        
        # Initialize manager
        manager = KanbanPipelineManager(
            serper_api_key=self.serper_api_key,
            scrapingant_api_key=self.scrapingant_api_key,
            leak_lookup_api_key=self.leak_lookup_api_key
        )
        
        logger.info(f"Starting OSINT pipeline for {target} ({search_type})")
        
        # Create initial ticket
        ticket = manager.create_ticket(
            target=target,
            search_type=search_type,
            priority="HIGH",
            column="RECON"
        )
        
        try:
            # Execute the pipeline loop (handles WIP limits and stage progression)
            await manager.execute_pipeline()
            
            # Generate reports from final analyst results
            high_conf_results = filter_high_confidence(
                manager.get_ticket_data(ticket.id).analyst_results,
                min_score=0.7
            )
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("reports")
            output_dir.mkdir(exist_ok=True)
            
            # Generate both PDF and HTML reports
            pdf_path = await generate_pdf_report(
                results=high_conf_results,
                leak_lookup_data=manager.get_ticket_data(ticket.id).leak_lookup_results or [],
                filename=output_dir / f"report_{timestamp}.pdf"
            )
            
            html_path = await generate_html_report(
                results=high_conf_results,
                leak_lookup_data=manager.get_ticket_data(ticket.id).leak_lookup_results or [],
                filename=output_dir / f"report_{timestamp}.html"
            )
            
            return {
                "status": "SUCCESS",
                "ticket_id": ticket.id,
                "target": target,
                "high_confidence_matches": len(high_conf_results),
                "pdf_report": str(pdf_path),
                "html_report": str(html_path)
            }
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return {"status": "FAILED", "error": str(e)}


async def main():
    parser = argparse.ArgumentParser(description="OSINT AI Automation Tool")
    parser.add_argument("--target", required=True, help="Target to search (email or domain)")
    parser.add_argument("--type", required=True, choices=["email", "domain"], help="Search type")
    parser.add_argument("--serper-key", env_var="SERPER_API_KEY", help="Serper.dev API key")
    parser.add_argument("--scrapingant-key", env_var="SCRAPINGANT_API_KEY", help="ScrapingAnt API key")
    parser.add_argument("--leak-lookup-key", env_var="LEAK_LOOKUP_API_KEY", help="Leak-Lookup API key")
    
    args = parser.parse_args()
    
    # Validate required keys
    missing_keys = []
    if not args.serper_key:
        missing_keys.append("SERPER_API_KEY")
    if not args.scrapingant_key:
        missing_keys.append("SCRAPINGANT_API_KEY")
    
    if missing_keys:
        print(f"Error: Missing required API keys: {', '.join(missing_keys)}")
        return 1
    
    pipeline = OSINTPipeline(
        serper_api_key=args.serper_key,
        scrapingant_api_key=args.scrapingant_key,
        leak_lookup_api_key=args.leak_lookup_key or ""
    )
    
    result = await pipeline.run_pipeline(args.target, args.type)
    
    print("\n" + "="*60)
    if result["status"] == "SUCCESS":
        print(f"✓ Pipeline completed successfully!")
        print(f"  Target: {result['target']}")
        print(f"  High Confidence Matches: {result['high_confidence_matches']}")
        print(f"  PDF Report: {result['pdf_report']}")
        print(f"  HTML Report: {result['html_report']}")
    else:
        print(f"✗ Pipeline failed: {result.get('error', 'Unknown error')}")
    
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
