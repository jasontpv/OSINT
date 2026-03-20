#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - Main Entry Point (FIXED)
=================================================

This is the main orchestration script that ties together all pipeline stages.

Key Fixes Implemented:
- Proper API key loading from environment variables
- Correct data flow between all 4 stages (RECON → HARVESTING → ANALYST → SCRIBE)
- Type-safe JSON handling with proper parsing at each stage boundary
- Scribe stage receives flattened list of facts for PDF population
- Comprehensive error handling and logging

Author: OSINT Team (Fixed by Senior AI Solutions Architect)
Date: 2024-12-17
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger('OSINT_MAIN')


class OSINTPipeline:
    """Main pipeline orchestrator with proper data flow"""
    
    def __init__(self):
        self.api_keys = {
            'serper': os.getenv("SERPER_API_KEY"),
            'scrapingant': os.getenv("SCRAPEANT_API_KEY"),
            'leak_lookup': os.getenv("LEAK_LOOKUP_API_KEY")
        }
        
        # Validate API keys are present
        self._validate_api_keys()
    
    def _validate_api_keys(self):
        """Ensure required API keys are configured"""
        missing = []
        
        if not self.api_keys['serper'] or self.api_keys['serper'] == "YOUR_SERPER_API_KEY":
            missing.append("SERPER_API_KEY")
        
        if not self.api_keys['scrapingant'] or self.api_keys['scrapingant'] == "YOUR_SCRAPEANT_API_KEY":
            missing.append("SCRAPEANT_API_KEY")
        
        # Leak-Lookup is optional but recommended for breach checking
        
        if missing:
            raise ValueError(f"Missing required API keys: {', '.join(missing)}\nPlease set them in .env file or environment variables.")
    
    async def run_investigation(self, query: str, target_type: str = "person") -> Dict[str, Any]:
        """
        Run a complete OSINT investigation through all 4 stages
        
        Args:
            query: Search query or target to investigate
            target_type: Type of target (person, company, domain, product)
            
        Returns:
            Dictionary with investigation results and report path
            
        Data Flow:
            RECON → HARVESTING → ANALYST → SCRIBE
            Each stage passes properly typed data to the next
        """
        
        logger.info(f"Starting OSINT investigation for: {query} (Type: {target_type})")
        
        try:
            # Import pipeline manager
            from osint_kanban_manager import OSINTKanbanManager, PipelineConfig
            
            # Create configuration with API keys
            config = PipelineConfig(
                query=query,
                target_name=target_type,
                serper_api_key=self.api_keys['serper'],
                scrapingant_api_key=self.api_keys['scrapingant'],
                leak_lookup_api_key=self.api_keys.get('leak_lookup') or None
            )
            
            # Initialize and run pipeline
            manager = OSINTKanbanManager(config)
            
            logger.info("Starting pipeline execution...")
            await manager.start_pipeline(query, target_type)
            
            results = await manager.execute_pipeline(
                query=query,
                output_path="./reports"
            )
            
            # Compile final results
            investigation_result = {
                "status": "completed",
                "query": query,
                "target_type": target_type,
                "total_processed": results.total_processed,
                "successful": results.successful,
                "failed": results.failed,
                "execution_time_seconds": round(results.execution_time, 2),
                "report_path": results.report_path,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✓ Investigation complete: {investigation_result}")
            
            return investigation_result
            
        except Exception as e:
            logger.error(f"Investigation failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "status": "failed",
                "query": query,
                "target_type": target_type,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


def print_investigation_summary(result: Dict[str, Any]):
    """Print a formatted summary of the investigation results"""
    
    print("\n" + "="*70)
    print("OSINT INVESTIGATION SUMMARY")
    print("="*70)
    
    if result.get("status") == "completed":
        print(f"\n🎯 Target: {result['query']} ({result['target_type']})")
        print(f"✅ Status: COMPLETED SUCCESSFULLY")
        print(f"⏱️  Execution Time: {result['execution_time_seconds']}s")
        print(f"📊 Processed: {result['total_processed']} items")
        print(f"✓ Successful: {result['successful']}")
        print(f"✗ Failed: {result['failed']}")
        
        if result.get("report_path"):
            print(f"\n📄 Report Location: {result['report_path']}")
            
            # Check if report exists
            if os.path.exists(result["report_path"]):
                file_size = os.path.getsize(result["report_path"])
                print(f"   File Size: {file_size:,} bytes ({file_size/1024:.2f} KB)")
        else:
            print("\n⚠️  No report path available")
    
    elif result.get("status") == "failed":
        print(f"\n❌ Status: FAILED")
        print(f"🔍 Target: {result['query']} ({result['target_type']})")
        print(f"💥 Error: {result.get('error', 'Unknown error')}")
    
    else:
        print(f"\n⚠️  Unknown status: {result.get('status')}")
    
    print("="*70)


async def main():
    """Main entry point for CLI usage"""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description='OSINT Kanban Pipeline - Multi-stage OSINT Investigation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "john.doe@example.com" --target-type person
  python main.py "example.com" --target-type company
  python main.py "product name" --target-type product

Environment Variables Required:
  SERPER_API_KEY     - Google search API key (Serper.dev)
  SCRAPEANT_API_KEY  - Web scraping API key (ScrapingAnt v2)
  LEAK_LOOKUP_API_KEY (Optional) - Breach database lookup API key
        """
    )
    
    parser.add_argument('query', help='Search query or target to investigate')
    parser.add_argument('--target-type', default='person',
                       choices=['person', 'company', 'domain', 'product'],
                       help='Type of target being investigated (default: person)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging output')
    
    args = parser.parse_args()
    
    # Set log level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize and run pipeline
        pipeline = OSINTPipeline()
        
        logger.info("Starting OSINT Kanban Pipeline...")
        result = await pipeline.run_investigation(
            query=args.query,
            target_type=args.target_type
        )
        
        # Print summary to console
        print_investigation_summary(result)
        
        # Return exit code based on success
        return 0 if result.get("status") == "completed" else 1
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Pipeline interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
