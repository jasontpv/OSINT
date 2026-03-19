#!/usr/bin/env python3
"""
OSINT Kanban Pipeline - Main Entry Point
=========================================
Interactive CLI for executing OSINT investigations with Kanban workflow.

Usage:
    python main.py                      # Interactive mode
    python main.py --target "John Doe"  # Non-interactive mode
Author: Matt Pumphrey
Date: 3/16/2026
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
import click
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Needed for the pipeline... 
from osint_recon_stage import generate_osint_queries, ReconOutput
from osint_harvesting_stage import execute_osint_harvest, HarvestOutput
from osint_analyst_stage import analyze_osint_data, AnalysisReport
from osint_scribe_stage import generate_osint_report, ReportFormat, ask_user_report_format
from osint_kanban_manager import OSINTKanbanManager, PipelineConfig



@click.command()
@click.option('--target', '-t', required=True, help='Target name/company/product to investigate')
@click.option('--target-type', type=click.Choice(['person', 'group', 'company']), default='person', 
              help='Type of target being investigated (default: person)')
@click.option('--format', '-f', type=click.Choice(['pdf', 'html', 'both']), default='both', 
              help='Report format (default: both)')
@click.option('--output-dir', '-o', default='./reports', help='Output directory for reports')
@click.option('--wip-recon', type=int, default=3, help='RECON stage WIP limit (default: 3)')
@click.option('--wip-harvesting', type=int, default=5, help='HARVESTING stage WIP limit (default: 5)')
@click.option('--wip-analyst', type=int, default=2, help='ANALYST stage WIP limit (default: 2)')
@click.option('--wip-scribe', type=int, default=1, help='SCRIBE stage WIP limit (default: 1)')
@click.option('--max-retries', type=int, default=3, help='Maximum retries per ticket (default: 3)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def main(target: str, target_type: str, format: str, output_dir: str, 
         wip_recon: int, wip_harvesting: int, wip_analyst: int, wip_scribe: int,
         max_retries: int, verbose: bool):
    """
    Execute OSINT investigation on target using Kanban pipeline.
    
    TARGET: The name, company, or product to investigate
    TARGET_TYPE: Type of entity being investigated (person/group/company)
    
    EXAMPLES:
        python main.py --target "John Doe" --target-type person
        python main.py -t "Apple Inc" --target-type company --format pdf
        python main.py --target "Open Source Community" --target-type group
        python main.py -t "Tesla Model 3" --target-type product
    """
    
    # Validate output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Map format string to enum
    format_map = {
        'pdf': ReportFormat.PDF,
        'html': ReportFormat.HTML,
        'both': ReportFormat.BOTH
    }
    selected_format = format_map.get(format, ReportFormat.BOTH)
    
    # Build configuration with target type
    config = PipelineConfig(
        query=target,
        target_type=target_type,  # New parameter for search criteria
        wip_limits={
            "RECON": wip_recon,
            "HARVESTING": wip_harvesting,
            "ANALYST": wip_analyst,
            "SCRIBE": wip_scribe
        },
        api_keys={
            "SERPER_API_KEY": os.getenv("SERPER_API_KEY"),
            "SCRAPINGANT_API_KEY": os.getenv("SCRAPINGANT_API_KEY")
        },
        max_retries_per_ticket=max_retries,
        enable_circuit_breaker=True,
        recovery_time_after_failure=60
    )
    
    # Validate API keys
    if not config.api_keys["SERPER_API_KEY"]:
        click.echo("❌ Error: SERPER_API_KEY not found in environment variables")
        click.echo("   Please set it via export SERPER_API_KEY='your_key' or in .env file")
        sys.exit(1)
    
    if not config.api_keys["SCRAPINGANT_API_KEY"]:
        click.echo("❌ Error: SCRAPINGANT_API_KEY not found in environment variables")
        click.echo("   Please set it via export SCRAPINGANT_API_KEY='your_key' or in .env file")
        sys.exit(1)
    
    # Initialize manager and execute pipeline
    manager = OsintKanbanManager(config=config)
    
    output_path = os.path.join(output_dir, f"osint_{target.replace(' ', '_')}")
    
    click.echo(f"\n🚀 Starting OSINT investigation for '{target}'...")
    click.echo(f"   Target: {config.target_name}")
    click.echo(f"   Type: {config.target_type.capitalize()}")
    click.echo(f"   Report Format: {'PDF' if selected_format == ReportFormat.PDF else 'HTML' if selected_format == ReportFormat.HTML else 'BOTH'}")
    click.echo(f"   WIP Limits: RECON={wip_recon}, HARVESTING={wip_harvesting}, ANALYST={wip_analyst}, SCRIBE={wip_scribe}")
    click.echo(f"   Max Retries: {max_retries}")
    click.echo(f"\n{'='*60}\n")
    
    try:
        # Execute pipeline
        result = asyncio.run(manager.execute_pipeline(
            query=target,
            report_format=selected_format,
            output_path=output_path
        ))
        
        # Print summary
        click.echo(f"\n{'='*60}")
        click.echo("✅ PIPELINE EXECUTION COMPLETE")
        click.echo(f"   Total Tickets Processed: {result.total_processed}")
        click.echo(f"   Successful: {result.successful}")
        click.echo(f"   Failed (retryable): {result.failed_retryable}")
        click.echo(f"   Permanent Failures: {result.failed_permanent}")
        
        if result.bottlenecks_detected:
            click.echo(f"   Bottlenecks Detected: {', '.join(result.bottlenecks_detected)}")
        
        click.echo(f"\n📊 Report Generated:")
        if result.report_path:
            click.echo(f"   Path: {result.report_path}")
            
            # List generated files
            report_files = []
            if os.path.exists(output_path + ".pdf"):
                size_mb = os.path.getsize(output_path + ".pdf") / (1024 * 1024)
                click.echo(f"   ✓ PDF: {output_path}.pdf ({size_mb:.2f} MB)")
                report_files.append(output_path + ".pdf")
            
            if os.path.exists(output_path + ".html"):
                size_kb = os.path.getsize(output_path + ".html") / 1024
                click.echo(f"   ✓ HTML: {output_path}.html ({size_kb:.2f} KB)")
                report_files.append(output_path + ".html")
            
            if not report_files:
                click.echo("   ⚠️ No report files generated (check error log)")
        
        # Check for critical failures
        if manager.has_critical_failures():
            click.echo("\n⚠️  Pipeline experienced critical failures!")
            click.echo("   Review the error report for details")
            
    except KeyboardInterrupt:
        click.echo("\n\n⏹️ Pipeline interrupted by user")
        click.echo("Saving state for potential resumption...")
        
    finally:
        # Cleanup resources
        asyncio.run(manager.cleanup())
    
    click.echo(f"\n{'='*60}")


if __name__ == '__main__':
    main()
